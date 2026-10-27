#!/usr/bin/env python3
"""
PH3-EMBED-001 (issue #5): embed Concept and Tool chunks and keep the Qdrant index in sync.

    pip install openai tiktoken qdrant-client
    export OPENAI_API_KEY=...
    python src/index_builder.py                 # embed new/changed chunks, delete removed ones
    python src/index_builder.py --dry-run       # token counts, diff and cost only; no API calls
    python src/index_builder.py --rebuild       # drop the collection and re-embed everything
    python src/index_builder.py --spot-check    # run the 10 QA searches -> index_spot_check.md

Inputs: data/processed/concept_chunks.jsonl, tool_chunks.jsonl (PH2-CHUNK-001). Resource chunks are
never embedded (vision pending). Only chunks with retrieval_eligible = true are embedded, so
duplicates are left out.

Outputs: data/index/qdrant/ (the collection), data/index/manifest.json,
data/processed/embedding_tokens.jsonl and data/processed/embedding_report.md.

Each run compares content hashes with the payloads already in the collection:
new -> embed + upsert, changed text -> re-embed + upsert, unchanged -> skip (payload refreshed if
its metadata changed), gone -> delete. A collection holding vectors of another model or version is
never mixed: bump `embedding_version` (new collection) or pass --rebuild.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
from embeddings import (DEFAULT_CONFIG, PIPELINE_VERSION, ChunkTooLong, EmbeddingConfig, Embedder,  # noqa: E402
                        Tokenizer, batches, check_length, content_hash, embed_query,
                        embedding_text)
from vector_index import PAYLOAD_INDEXES, IndexConfigMismatch, VectorIndex  # noqa: E402

INDEX_DIR = config.ROOT / "data" / "index"
QDRANT_PATH = INDEX_DIR / "qdrant"
MANIFEST = INDEX_DIR / "manifest.json"
TOKENS_JSONL = "embedding_tokens.jsonl"
REPORT_MD = "embedding_report.md"
SPOT_CHECK_MD = "index_spot_check.md"
CHUNK_FILES = {"concept": "concept_chunks.jsonl", "tool": "tool_chunks.jsonl"}

COMMON_FIELDS = ["chunk_id", "chunk_type", "notebook_id", "notebook_title", "section_path", "content_role",
                 "contains_math", "token_count", "tokenizer", "embedding_model", "embedding_version",
                 "corpus_fingerprint", "content_hash", "source_cell_ids", "retrieval_eligible", "text"]
REQUIRED_FIELDS = {
    "concept": COMMON_FIELDS + ["contains_latex", "contains_table", "source_span_ids", "linked_tool_ids"],
    "tool": COMMON_FIELDS + ["tool_id", "tool_type", "language", "libraries", "linked_concept_chunk_ids"],
}
EXCLUDED_ROLES = {"instructor_note", "quiz", "agenda", "business_context", "rhetorical_question", "preamble",
                  "data_loading", "environment_setup", "debugging", "non_teaching", "unknown"}


# ----------------------------------------------------------------------------
# Loading and payloads
# ----------------------------------------------------------------------------
def load_chunks(processed_dir: Path = config.PROCESSED_DIR) -> tuple[list[dict], dict]:
    """Retrieval-eligible concept and tool chunks, in file order, plus counts of what was left out."""
    chunks, left_out = [], Counter()
    for kind, name in CHUNK_FILES.items():
        path = processed_dir / name
        if not path.exists():
            raise SystemExit(f"{path} not found; run src/chunk_builder.py first")
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            ch = json.loads(line)
            if ch["chunk_type"] != kind:
                raise ValueError(f"{ch['chunk_id']} in {name} has chunk_type {ch['chunk_type']}")
            if ch.get("retrieval_eligible"):
                chunks.append(ch)
            else:
                left_out[f"{kind}: not retrieval-eligible ({'duplicate' if ch.get('duplicate_of') else 'other'})"] += 1
    res = processed_dir / "resource_chunks.jsonl"
    if res.exists():
        left_out["resource: vision pending, never embedded"] = sum(1 for l in res.read_text().splitlines() if l.strip())
    return chunks, dict(left_out)


def payload_for(ch: dict, text: str, tokens: int, chash: str, tokenizer: str, model: str, cfg: EmbeddingConfig,
                fingerprint: str) -> dict:
    p = {
        "chunk_id": ch["chunk_id"], "chunk_type": ch["chunk_type"], "notebook_id": ch["notebook_id"],
        "notebook_title": ch["notebook_title"], "section_path": " > ".join(ch["section_path"]),
        "section_path_list": ch["section_path"], "token_count": tokens, "tokenizer": tokenizer,
        "embedding_model": model, "embedding_version": cfg.embedding_version, "embedding_dimensions": cfg.dimensions,
        "corpus_fingerprint": fingerprint, "content_hash": chash, "source_cell_ids": ch["source_cell_ids"],
        "retrieval_eligible": True, "text": text, "pipeline_version": PIPELINE_VERSION,
    }
    if ch["chunk_type"] == "concept":
        p.update(content_role="teaching", contains_math=ch["contains_math"], contains_latex=ch["contains_latex"],
                 contains_table=ch["contains_table"], contains_code=ch.get("contains_code", False),
                 source_span_ids=ch["source_span_ids"], linked_tool_ids=ch["linked_tool_ids"],
                 linked_tool_chunk_ids=ch["linked_tool_chunk_ids"], linked_resource_ids=ch["linked_resource_ids"],
                 is_tiny=ch["quality_flags"]["is_tiny"], is_oversized=ch["quality_flags"]["is_oversized"])
    else:
        p.update(content_role=ch["tool_type"], tool_type=ch["tool_type"], tool_id=ch["tool_id"],
                 title=ch["title"], language=ch["language"], libraries=ch["libraries"], contains_math=False,
                 source_cell_id=ch["source_cell_id"], linked_concept_chunk_ids=ch["linked_concept_chunk_ids"],
                 linked_resource_ids=ch["linked_resource_ids"], repeats_code_of=ch.get("repeats_code_of"))
    return p


def fingerprint_of(hashes: dict[str, str]) -> str:
    joined = "\n".join(f"{k}:{v}" for k, v in sorted(hashes.items()))
    return hashlib.sha256(joined.encode()).hexdigest()[:16]


# ----------------------------------------------------------------------------
# Sync
# ----------------------------------------------------------------------------
def plan(chunks: list[dict], tokenizer: Tokenizer, model: str, cfg: EmbeddingConfig = DEFAULT_CONFIG) -> dict:
    """Texts, token counts and hashes for every chunk; chunks over the hard limit are failures."""
    items, failed, flags = [], [], {}
    for ch in chunks:
        text = embedding_text(ch)
        tokens = tokenizer.count(text)
        try:
            flag = check_length(ch["chunk_id"], tokens, cfg)
        except ChunkTooLong as e:
            failed.append({"chunk_id": ch["chunk_id"], "reason": str(e)})
            continue
        if flag:
            flags[ch["chunk_id"]] = flag
        items.append({"chunk": ch, "text": text, "tokens": tokens, "hash": content_hash(text, model, cfg)})
    fp = fingerprint_of({i["chunk"]["chunk_id"]: i["hash"] for i in items})
    for i in items:
        i["payload"] = payload_for(i["chunk"], i["text"], i["tokens"], i["hash"], tokenizer.name, model, cfg, fp)
    return {"items": items, "failed": failed, "flags": flags, "fingerprint": fp}


def sync(index: VectorIndex, chunks: list[dict], embedder: Embedder, tokenizer: Tokenizer,
         cfg: EmbeddingConfig = DEFAULT_CONFIG, rebuild: bool = False, dry_run: bool = False) -> dict:
    if embedder.dimensions != cfg.dimensions:
        raise IndexConfigMismatch(f"embedder dimensions {embedder.dimensions} != config {cfg.dimensions}")
    if rebuild and not dry_run:
        index.drop()
    if not dry_run:
        index.ensure_collection(cfg.dimensions, cfg.distance)
        index.create_payload_indexes()
    p = plan(chunks, tokenizer, embedder.model, cfg)
    existing = {} if (dry_run and rebuild) else _existing(index)
    others = {(q.get("embedding_model"), q.get("embedding_version")) for q in existing.values()}
    others.discard((embedder.model, cfg.embedding_version))
    if others:
        raise IndexConfigMismatch(f"collection {index.collection} holds vectors of {sorted(others)}; "
                                  "use a new embedding_version or --rebuild")

    desired = {i["chunk"]["chunk_id"]: i for i in p["items"]}
    to_embed = [i for cid, i in desired.items() if existing.get(cid, {}).get("content_hash") != i["hash"]]
    unchanged = [i for cid, i in desired.items() if existing.get(cid, {}).get("content_hash") == i["hash"]]
    refresh = [i for i in unchanged if existing[i["chunk"]["chunk_id"]] != i["payload"]]
    stale = sorted(set(existing) - set(desired))
    result = {
        "fingerprint": p["fingerprint"], "planned": p["items"], "to_embed": [i["chunk"]["chunk_id"] for i in to_embed],
        "new": sum(i["chunk"]["chunk_id"] not in existing for i in to_embed),
        "changed": sum(i["chunk"]["chunk_id"] in existing for i in to_embed),
        "skipped_unchanged": len(unchanged), "payload_refreshed": len(refresh), "deleted": stale,
        "failed": list(p["failed"]), "flags": p["flags"], "embedded": [], "embedded_tokens": 0, "dry_run": dry_run,
    }
    if dry_run:
        result["embedded_tokens"] = sum(i["tokens"] for i in to_embed)
        return result

    token_counts = [i["tokens"] for i in to_embed]
    for group in batches(to_embed, token_counts, cfg):
        batch = [to_embed[k] for k in group]
        try:
            vectors = embedder.embed([i["text"] for i in batch])
        except Exception as e:                                   # after the embedder's own retries
            result["failed"] += [{"chunk_id": i["chunk"]["chunk_id"], "reason": f"{type(e).__name__}: {e}"}
                                 for i in batch]
            continue
        index.upsert([{"chunk_id": i["chunk"]["chunk_id"], "vector": v, "payload": i["payload"]}
                      for i, v in zip(batch, vectors)])
        result["embedded"] += [i["chunk"]["chunk_id"] for i in batch]
        result["embedded_tokens"] += sum(i["tokens"] for i in batch)
    if refresh:
        index.set_payloads([{"chunk_id": i["chunk"]["chunk_id"], "payload": i["payload"]} for i in refresh])
    index.delete(stale)
    return result


def _existing(index: VectorIndex) -> dict[str, dict]:
    try:
        return index.payloads()
    except Exception:
        return {}


# ----------------------------------------------------------------------------
# Health and report
# ----------------------------------------------------------------------------
def health(index: VectorIndex, result: dict) -> dict:
    payloads = index.payloads()
    desired = {i["chunk"]["chunk_id"] for i in result["planned"]}
    point_ids = index.point_ids()
    missing = [cid for cid, p in payloads.items()
               if any(f not in p for f in REQUIRED_FIELDS.get(p.get("chunk_type"), COMMON_FIELDS))]
    return {
        "collection": index.collection, "vector_count": index.count(),
        "payload_indexes": index.payload_indexes(),
        # two points for one chunk_id, or a point ID reused
        "duplicate_ids": (len(point_ids) - len(set(point_ids))) + (len(point_ids) - len(payloads)),
        "orphans": sorted(set(payloads) - desired),
        "missing_metadata": missing,
        "excluded_roles_present": sorted({p["content_role"] for p in payloads.values()} & EXCLUDED_ROLES),
        "resource_vectors": sum(p.get("chunk_type") == "resource" for p in payloads.values()),
        "by_type": Counter(p["chunk_type"] for p in payloads.values()),
        "tokens_by_type": Counter({t: sum(p["token_count"] for p in payloads.values() if p["chunk_type"] == t)
                                   for t in ("concept", "tool")}),
        "largest": max(((p["token_count"], cid) for cid, p in payloads.items()), default=(0, "")),
    }


def build_report(result: dict, h: dict, expected: Counter, left_out: dict, cfg: EmbeddingConfig, tokenizer: str,
                 model: str) -> str:
    total_tokens = sum(i["tokens"] for i in result["planned"])
    usd = result["embedded_tokens"] / 1e6 * cfg.usd_per_million_tokens
    full_usd = total_tokens / 1e6 * cfg.usd_per_million_tokens
    embedded_types = Counter(cid.split("_")[0] for cid in result["embedded"])
    L = ["# Embedding and Indexing Report", "",
         "## Summary", "",
         f"- Pipeline version: {PIPELINE_VERSION}",
         f"- Corpus fingerprint: {result['fingerprint']}",
         f"- Embedding model: {model}",
         f"- Embedding version: {cfg.embedding_version}",
         f"- Dimensions: {cfg.dimensions}",
         f"- Distance: {cfg.distance}",
         f"- Tokenizer: {tokenizer}",
         f"- Vector store: Qdrant local mode (`{QDRANT_PATH.relative_to(config.ROOT)}`)" if h else "- Vector store: —",
         f"- Run: {'dry run (no embeddings requested)' if result['dry_run'] else 'sync'}", "",
         "## Coverage", "",
         f"- Concept chunks expected: {expected['concept']:,}",
         f"- Concept chunks embedded: {h['by_type']['concept']:,}" if h else "- Concept chunks embedded: — (dry run)",
         f"- Tool chunks expected: {expected['tool']:,}",
         f"- Tool chunks embedded: {h['by_type']['tool']:,}" if h else "- Tool chunks embedded: — (dry run)",
         f"- Total vectors: {h['vector_count']:,}" if h else "- Total vectors: — (dry run)",
         f"- Failed embeddings: {len(result['failed'])}",
         f"- Embedded this run: {len(result['embedded']):,} (concept {embedded_types['CON']:,}, tool "
         f"{embedded_types['TOOLCHUNK']:,}; new {result['new']:,}, changed {result['changed']:,})"
         if not result["dry_run"] else f"- Would embed: {len(result['to_embed']):,} (new {result['new']:,}, "
                                       f"changed {result['changed']:,})",
         f"- Skipped unchanged chunks: {result['skipped_unchanged']:,} (payload refreshed: {result['payload_refreshed']:,})",
         f"- Deleted stale vectors: {len(result['deleted']):,}",
         "- Not embedded: " + (", ".join(f"{k} {v:,}" for k, v in sorted(left_out.items())) or "none"), ""]
    if result["failed"]:
        L += ["| chunk_id | Reason |", "|---|---|"] + [f"| {f['chunk_id']} | {f['reason']} |" for f in result["failed"]] + [""]
    concept_tokens = sum(i["tokens"] for i in result["planned"] if i["chunk"]["chunk_type"] == "concept")
    largest = max(((i["tokens"], i["chunk"]["chunk_id"]) for i in result["planned"]), default=(0, ""))
    L += ["## Token usage", "",
          f"- Total tokens (all {len(result['planned']):,} chunks): {total_tokens:,}",
          f"- Concept tokens: {concept_tokens:,}",
          f"- Tool tokens: {total_tokens - concept_tokens:,}",
          f"- Tokens embedded this run: {result['embedded_tokens']:,}",
          f"- Largest chunk: {largest[0]:,} tokens ({largest[1]})",
          f"- Chunks above safe limit ({cfg.safe_input_tokens:,} tokens): {len(result['flags'])}"
          + (f" — {', '.join(sorted(result['flags']))}" if result["flags"] else ""),
          f"- Chunks above model limit ({cfg.max_input_tokens:,} tokens, not embedded, not truncated): "
          f"{sum('model limit' in f['reason'] for f in result['failed'])}", "",
          "## Cost", "",
          f"- Estimated embedding cost this run: {usd:.4f}",
          f"- Estimated cost of a full re-embed: {full_usd:.4f}",
          "- Currency: USD",
          f"- Price used: {cfg.usd_per_million_tokens} USD per 1M tokens (list price for {model}; check the "
          "provider's pricing page)", ""]
    if h:
        L += ["## Index health", "",
              f"- Collection: {h['collection']}",
              f"- Vector count: {h['vector_count']:,}",
              f"- Payload-indexed fields: {len(h['payload_indexes'])} ({', '.join(h['payload_indexes'])})",
              f"- Duplicate vector IDs: {h['duplicate_ids']}",
              f"- Orphan vectors: {len(h['orphans'])}",
              f"- Missing-metadata vectors: {len(h['missing_metadata'])}",
              f"- Resource vectors: {h['resource_vectors']}",
              f"- Vectors with excluded content roles: {len(h['excluded_roles_present'])}", ""]
    return "\n".join(L) + "\n"


# ----------------------------------------------------------------------------
# Spot check (manual QA aid, not a retrieval API)
# ----------------------------------------------------------------------------
SPOT_QUERIES = [
    ("concept", "What is the difference between precision and recall?", None),
    ("concept", "How does gradient boosting fit residuals at each stage?", None),
    ("concept", "Why do we need positional encoding in transformers?", None),
    ("concept", "What is the curse of dimensionality?", None),
    ("concept", "How does exponential smoothing weight past observations?", None),
    ("tool", "Show code to fill missing values in a pandas column", None),
    ("tool", "How do I tune hyperparameters with GridSearchCV?", None),
    ("tool", "Plot a confusion matrix heatmap with seaborn", None),
    ("filtered: chunk_type=tool", "train a CNN on image data", {"chunk_type": "tool"}),
    ("filtered: contains_math=true", "derivative of the loss with respect to the weights", {"contains_math": True}),
]


def spot_check(index: VectorIndex, embedder: Embedder, cfg: EmbeddingConfig = DEFAULT_CONFIG, k: int = 5) -> str:
    L = ["# Index Spot Check", "", f"Top {k} results per query from `{index.collection}`. Automatic checks are "
         "marked; relevance is judged by a person (fill the last column).", ""]
    for kind, query, filters in SPOT_QUERIES:
        hits = index.search(embed_query(query, embedder, cfg), filters=filters, limit=k)
        ids = [p["chunk_id"] for _, p in hits]
        checks = {
            "no resources": all(p["chunk_type"] != "resource" for _, p in hits),
            "no excluded roles": all(p["content_role"] not in EXCLUDED_ROLES for _, p in hits),
            "no duplicate ids": len(ids) == len(set(ids)),
            "filter respected": all(all(p.get(f) == v for f, v in (filters or {}).items()) for _, p in hits),
            "metadata present": all(p.get("notebook_id") and p.get("section_path") for _, p in hits),
        }
        L += [f"## [{kind}] {query}", "", "Checks: " + ", ".join(f"{n} {'✓' if ok else '✗'}" for n, ok in checks.items()),
              "", "| # | Score | chunk_id | Notebook | Section path | Text | Relevant? |", "|---:|---:|---|---|---|---|---|"]
        for n, (score, p) in enumerate(hits, 1):
            first = " ".join(p["text"].split("\n", 2)[-1].split())[:120].replace("|", "\\|")
            L.append(f"| {n} | {score:.3f} | {p['chunk_id']} | {p['notebook_title']} | "
                     f"{p['section_path'][-60:].replace('|', '/')} | {first} | |")
        L.append("")
    return "\n".join(L) + "\n"


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def write_outputs(processed_dir: Path, result: dict, h: Optional[dict], left_out: dict, cfg: EmbeddingConfig,
                  tokenizer: str, model: str, index: Optional[VectorIndex], expected: Counter) -> None:
    (processed_dir / TOKENS_JSONL).write_text("".join(json.dumps({
        "chunk_id": i["chunk"]["chunk_id"], "chunk_type": i["chunk"]["chunk_type"], "token_count": i["tokens"],
        "tokenizer": tokenizer, "embedding_model": model, "embedding_version": cfg.embedding_version,
        "content_hash": i["hash"], "flag": result["flags"].get(i["chunk"]["chunk_id"])}) + "\n"
        for i in result["planned"]), encoding="utf-8", newline="\n")
    (processed_dir / REPORT_MD).write_text(build_report(result, h, expected, left_out, cfg, tokenizer, model),
                                           encoding="utf-8", newline="\n")
    if index is not None and h is not None:
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(json.dumps({
            "collection": index.collection, "embedding_model": model, "embedding_version": cfg.embedding_version,
            "dimensions": cfg.dimensions, "distance": cfg.distance, "tokenizer": tokenizer,
            "corpus_fingerprint": result["fingerprint"], "vector_count": h["vector_count"],
            "payload_indexes": h["payload_indexes"], "pipeline_version": PIPELINE_VERSION}, indent=2) + "\n")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="count tokens, diff and cost; no embedding calls")
    ap.add_argument("--rebuild", action="store_true", help="drop the collection and re-embed every chunk")
    ap.add_argument("--spot-check", action="store_true", help="run the QA searches against the index")
    ap.add_argument("--index-path", default=str(QDRANT_PATH))
    args = ap.parse_args(argv)
    cfg = DEFAULT_CONFIG

    from embeddings import OpenAIEmbedder, get_tokenizer
    from vector_index import QdrantIndex
    tokenizer = get_tokenizer(cfg)
    index = None if (args.dry_run and not Path(args.index_path).exists()) else QdrantIndex(cfg.collection, args.index_path)

    if args.spot_check:
        if index is None or not index.exists() or index.count() == 0:
            raise RuntimeError(f"collection {cfg.collection} not found or empty at {args.index_path}; "
                               "build it first: python src/index_builder.py")
        out = config.PROCESSED_DIR / SPOT_CHECK_MD
        out.write_text(spot_check(index, OpenAIEmbedder(cfg), cfg), encoding="utf-8", newline="\n")
        print(f"wrote {out}")
        return 0

    chunks, left_out = load_chunks()
    expected = Counter(ch["chunk_type"] for ch in chunks)

    class _NoEmbed:                                    # dry run: never calls the API
        model, dimensions = cfg.model, cfg.dimensions

        def embed(self, texts):
            raise AssertionError("dry run must not embed")

    embedder = _NoEmbed() if args.dry_run else OpenAIEmbedder(cfg)
    from vector_index import MemoryIndex
    target = index if index is not None else MemoryIndex(cfg.collection)
    result = sync(target, chunks, embedder, tokenizer, cfg, rebuild=args.rebuild, dry_run=args.dry_run)
    h = None if args.dry_run else health(target, result)
    write_outputs(config.PROCESSED_DIR, result, h, left_out, cfg, tokenizer.name, embedder.model,
                  None if args.dry_run else target, expected)
    print(f"{'would embed' if args.dry_run else 'embedded'} {len(result['to_embed'] if args.dry_run else result['embedded'])}"
          f"  skipped {result['skipped_unchanged']}  deleted {len(result['deleted'])}  failed {len(result['failed'])}"
          + (f"  vectors {h['vector_count']}" if h else ""))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, IndexConfigMismatch) as e:      # missing package/key, or a model/version clash
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
