#!/usr/bin/env python3
"""
PH4-RETRIEVE-001 (issue #9): hybrid retrieval with filters and attached Tools/Resources.

    prompt -> dense Qdrant search (50) -+
           -> BM25 keyword search (50) -+-> RRF (k=60) -> filters -> top 5 concepts + 3 tools (max 8)
                                                         -> attach linked Tools (<= 2 per concept)
                                                         -> attach attachable Resources (vision pending)

Modes: "dense", "bm25", "hybrid_rrf". The default mode comes from the measured decision written by
src/retrieval_eval.py (data/processed/retrieval_decision.json). Until one is measured it is "dense",
because hybrid is only adopted if it improves retrieval quality.

Manual QA from the command line (needs OPENAI_API_KEY and the Qdrant index for dense/hybrid):
    python src/retrieval.py "curse of dimensionality" --mode bm25
    python src/retrieval.py "train a CNN" --mode hybrid_rrf --type tool
    python src/retrieval.py "loss derivative" --math
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
from bm25_index import BM25Index, matches  # noqa: E402
from embeddings import DEFAULT_CONFIG, EmbeddingConfig, embed_query, embedding_text  # noqa: E402
from hybrid_fusion import RRF_K, rrf  # noqa: E402

MODES = ("dense", "bm25", "hybrid_rrf")
PRIMARY_RELATIONSHIPS = ("implements", "demonstrates", "visualizes")
EXCLUDED_ROLES = frozenset({"instructor_note", "quiz", "agenda", "business_context", "rhetorical_question",
                            "preamble", "data_loading", "environment_setup", "debugging", "non_teaching", "unknown"})
FILTER_FIELDS = ("chunk_type", "notebook_id", "content_role", "contains_math", "retrieval_eligible")
DECISION_FILE = config.PROCESSED_DIR / "retrieval_decision.json"
QUERY_CACHE = config.PROCESSED_DIR / "query_embeddings.jsonl"


@dataclass(frozen=True)
class RetrievalConfig:
    dense_candidate_k: int = 50
    bm25_candidate_k: int = 50
    rrf_k: int = RRF_K
    concept_k: int = 5
    tool_k: int = 3
    max_context_chunks: int = 8
    tools_per_concept: int = 2
    resources_per_concept: int = 3
    ranking_depth: int = 20                    # length of the fused ranking kept for evaluation


DEFAULT_RETRIEVAL = RetrievalConfig()


def chunk_meta(ch: dict) -> dict:
    """The filterable fields, computed exactly as the Qdrant payload computes them."""
    return {
        "chunk_id": ch["chunk_id"], "chunk_type": ch["chunk_type"], "notebook_id": ch["notebook_id"],
        "content_role": "teaching" if ch["chunk_type"] == "concept" else ch["tool_type"],
        "contains_math": bool(ch.get("contains_math", False)) if ch["chunk_type"] == "concept" else False,
        "retrieval_eligible": bool(ch.get("retrieval_eligible")),
    }


def check_filters(filters: Optional[dict]) -> dict:
    out = {"retrieval_eligible": True}
    for k, v in (filters or {}).items():
        if k not in FILTER_FIELDS:
            raise ValueError(f"unsupported filter {k!r}; use one of {FILTER_FIELDS}")
        out[k] = v
    return out


def default_mode() -> str:
    try:
        return json.loads(DECISION_FILE.read_text())["default_mode"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return "dense"


class QueryCache:
    """Query vectors keyed by model, dimensions and text, so re-running the evaluation is free."""

    def __init__(self, path: Optional[Path]):
        self.path, self.data = path, {}
        if path and path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self.data[rec["key"]] = rec["vector"]

    @staticmethod
    def key(model: str, dims: int, text: str) -> str:
        return hashlib.sha256(f"{model}|{dims}|{text}".encode()).hexdigest()[:24]

    def get_or_embed(self, text: str, embedder, cfg: EmbeddingConfig) -> list[float]:
        k = self.key(embedder.model, embedder.dimensions, text)
        if k not in self.data:
            self.data[k] = embed_query(text, embedder, cfg)
            if self.path:
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"key": k, "model": embedder.model, "vector": self.data[k]}) + "\n")
        return self.data[k]


@dataclass
class Corpus:
    chunks: dict[str, dict]                                  # chunk_id -> concept/tool chunk
    tool_chunk_by_tool: dict[str, str]                       # tool_id -> TOOLCHUNK id
    links: dict[tuple[str, str], dict]                       # (tool_id, span_id) -> link
    resources: dict[str, dict]                               # RESCHUNK id -> attachable resource chunk
    order: dict[str, int] = field(default_factory=dict)      # corpus position, for stable ties

    @classmethod
    def load(cls, processed_dir: Path = config.PROCESSED_DIR) -> "Corpus":
        from index_builder import load_chunks
        chunks, _ = load_chunks(processed_dir)
        links = {}
        path = processed_dir / "tool_concept_links.jsonl"
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    link = json.loads(line)
                    links[(link["tool_id"], link["span_id"])] = link
        resources = {}
        path = processed_dir / "resource_chunks.jsonl"
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rc = json.loads(line)
                    if rc.get("attachable"):
                        resources[rc["chunk_id"]] = rc
        return cls.from_parts(chunks, links, resources)

    @classmethod
    def from_parts(cls, chunks: list[dict], links: dict, resources: dict) -> "Corpus":
        by_id = {c["chunk_id"]: c for c in chunks}
        return cls(chunks=by_id, links=links, resources=resources,
                   tool_chunk_by_tool={c["tool_id"]: c["chunk_id"] for c in chunks if c["chunk_type"] == "tool"},
                   order={c["chunk_id"]: i for i, c in enumerate(chunks)})


class Retriever:
    def __init__(self, corpus: Corpus, dense_index=None, embedder=None, cfg: RetrievalConfig = DEFAULT_RETRIEVAL,
                 embed_cfg: EmbeddingConfig = DEFAULT_CONFIG, query_cache: Optional[QueryCache] = None):
        self.corpus, self.dense_index, self.embedder = corpus, dense_index, embedder
        self.cfg, self.embed_cfg = cfg, embed_cfg
        self.cache = query_cache or QueryCache(None)
        self.bm25 = BM25Index()
        for cid, ch in corpus.chunks.items():
            self.bm25.add(cid, embedding_text(ch), chunk_meta(ch))
        self.guard_dropped = 0                               # results removed by the safety guard

    @property
    def dense_available(self) -> bool:
        return self.dense_index is not None and self.embedder is not None

    # candidates -----------------------------------------------------------------
    def _allowed(self, cid: str, filters: dict) -> bool:
        ch = self.corpus.chunks.get(cid)
        if ch is None:                                        # vector for a chunk no longer in the corpus
            self.guard_dropped += 1
            return False
        meta = chunk_meta(ch)
        if meta["content_role"] in EXCLUDED_ROLES or ch["chunk_type"] not in ("concept", "tool"):
            self.guard_dropped += 1
            return False
        return matches(meta, filters)

    def dense_candidates(self, query: str, filters: dict) -> list[tuple[str, float]]:
        if not self.dense_available:
            raise RuntimeError("dense search needs the Qdrant index and an embedder (OPENAI_API_KEY)")
        vec = self.cache.get_or_embed(query, self.embedder, self.embed_cfg)
        hits = self.dense_index.search(vec, filters=filters, limit=self.cfg.dense_candidate_k)
        return [(p["chunk_id"], s) for s, p in hits if self._allowed(p["chunk_id"], filters)]

    def bm25_candidates(self, query: str, filters: dict) -> list[tuple[str, float]]:
        hits = self.bm25.search(query, filters=filters, limit=self.cfg.bm25_candidate_k)
        return [(cid, s) for s, cid in hits if self._allowed(cid, filters)]

    def rank(self, query: str, mode: str, filters: dict) -> list[dict]:
        """Full ranking (best first) as dicts with chunk_id, score, source and per-retriever ranks."""
        if mode == "dense":
            return [{"chunk_id": c, "score": round(s, 6), "source": "dense", "ranks": {"dense": i}}
                    for i, (c, s) in enumerate(self.dense_candidates(query, filters), 1)]
        if mode == "bm25":
            return [{"chunk_id": c, "score": round(s, 6), "source": "bm25", "ranks": {"bm25": i}}
                    for i, (c, s) in enumerate(self.bm25_candidates(query, filters), 1)]
        if mode == "hybrid_rrf":
            lists = {"bm25": [c for c, _ in self.bm25_candidates(query, filters)],
                     "dense": [c for c, _ in self.dense_candidates(query, filters)]}
            return [{"chunk_id": f.chunk_id, "score": round(f.score, 6), "source": f.source, "ranks": f.ranks}
                    for f in rrf(lists, self.cfg.rrf_k)]
        raise ValueError(f"unknown mode {mode!r}; use one of {MODES}")

    # context package --------------------------------------------------------------
    def search(self, query: str, mode: Optional[str] = None, filters: Optional[dict] = None) -> dict:
        mode = mode or default_mode()
        flt = check_filters(filters)
        ranking = self.rank(query, mode, flt)
        selected, n_concept, n_tool = [], 0, 0
        only_type = flt.get("chunk_type")
        for item in ranking:
            if len(selected) >= self.cfg.max_context_chunks:
                break
            ch = self.corpus.chunks[item["chunk_id"]]
            if ch["chunk_type"] == "concept" and (n_concept < self.cfg.concept_k or only_type == "concept"):
                n_concept += 1
            elif ch["chunk_type"] == "tool" and (n_tool < self.cfg.tool_k or only_type == "tool"):
                n_tool += 1
            else:
                continue
            selected.append(item)
        rank_of = {r["chunk_id"]: i for i, r in enumerate(ranking, 1)}
        retrieved = []
        for i, item in enumerate(selected, 1):
            ch = self.corpus.chunks[item["chunk_id"]]
            retrieved.append({
                "rank": i, "chunk_id": ch["chunk_id"], "chunk_type": ch["chunk_type"], "score": item["score"],
                "source": item["source"], "ranks": item["ranks"], "notebook_id": ch["notebook_id"],
                "notebook_title": ch["notebook_title"], "section_path": " > ".join(ch["section_path"]),
                "content_role": chunk_meta(ch)["content_role"], "tool_id": ch.get("tool_id"),
                "text": embedding_text(ch)})
        tools, resources = self.attach(selected, rank_of)
        return {"prompt": query, "retrieval_mode": mode, "filters_applied": flt, "retrieved_chunks": retrieved,
                "attached_tools": tools, "attached_resources": resources,
                "ranking": [{"rank": i, "chunk_id": r["chunk_id"], "score": r["score"], "source": r["source"]}
                            for i, r in enumerate(ranking[: self.cfg.ranking_depth], 1)]}

    def attach(self, selected: list[dict], rank_of: dict[str, int]) -> tuple[list[dict], list[dict]]:
        """Up to 2 primary-linked Tools per retrieved Concept (tools that ranked anyway first), and the
        Concept's attachable Resources, which carry no text evidence."""
        tools, resources, seen_t, seen_r = [], [], set(), set()
        in_context = {s["chunk_id"] for s in selected}
        for item in selected:
            ch = self.corpus.chunks[item["chunk_id"]]
            if ch["chunk_type"] != "concept":
                continue
            options = []
            for tool_id in ch.get("linked_tool_ids", []):
                tchunk = self.corpus.tool_chunk_by_tool.get(tool_id)
                link = max((self.corpus.links.get((tool_id, sid)) for sid in ch["source_span_ids"]
                            if (tool_id, sid) in self.corpus.links), key=lambda l: l["confidence"], default=None)
                if tchunk is None or link is None or link["relationship"] not in PRIMARY_RELATIONSHIPS:
                    continue
                options.append((rank_of.get(tchunk, 10**6), -link["confidence"], tool_id, tchunk, link))
            for r, _, tool_id, tchunk, link in sorted(options)[: self.cfg.tools_per_concept]:
                if tool_id in seen_t:
                    continue
                seen_t.add(tool_id)
                tools.append({"tool_id": tool_id, "tool_chunk_id": tchunk, "concept_chunk_id": ch["chunk_id"],
                              "relationship": link["relationship"], "link_confidence": link["confidence"],
                              "attachment_reason": "also_retrieved" if tchunk in in_context else
                              ("ranked_candidate" if r < 10**6 else "linked_to_retrieved_concept")})
            for rid in ch.get("linked_resource_chunk_ids", [])[: self.cfg.resources_per_concept]:
                rc = self.corpus.resources.get(rid)
                if rc is None or rid in seen_r:               # pending-vision resources have no chunk
                    continue
                seen_r.add(rid)
                resources.append({
                    "resource_id": rc["resource_id"], "resource_chunk_id": rid, "concept_chunk_id": ch["chunk_id"],
                    "resource_type": rc["resource_type"], "availability": rc["availability"],
                    "caption": rc["caption"], "image_url": rc.get("image_url"), "local_path": rc.get("local_path"),
                    "vision_status": rc["vision_status"],
                    "not_usable_as_text_evidence": rc["vision_status"] != "done"})
        return tools, resources


def build_retriever(dense: bool = True, processed_dir: Path = config.PROCESSED_DIR) -> Retriever:
    """The retriever over the local corpus; dense search is wired in when its dependencies exist."""
    corpus = Corpus.load(processed_dir)
    index = embedder = None
    if dense:
        from embeddings import OpenAIEmbedder
        from index_builder import QDRANT_PATH
        from vector_index import QdrantIndex
        index = QdrantIndex(DEFAULT_CONFIG.collection, str(QDRANT_PATH))
        if not index.exists() or index.count() == 0:
            raise RuntimeError(f"Qdrant collection {DEFAULT_CONFIG.collection} is missing or empty; "
                               "run python src/index_builder.py")
        embedder = OpenAIEmbedder(DEFAULT_CONFIG)
    return Retriever(corpus, index, embedder, query_cache=QueryCache(QUERY_CACHE))


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query")
    ap.add_argument("--mode", choices=MODES, default=None)
    ap.add_argument("--type", choices=("concept", "tool"), dest="chunk_type")
    ap.add_argument("--notebook", dest="notebook_id")
    ap.add_argument("--role", dest="content_role")
    ap.add_argument("--math", action="store_true", dest="contains_math")
    ap.add_argument("--json", action="store_true", help="print the full context package")
    args = ap.parse_args(argv)
    mode = args.mode or default_mode()
    filters = {k: v for k, v in (("chunk_type", args.chunk_type), ("notebook_id", args.notebook_id),
                                 ("content_role", args.content_role)) if v}
    if args.contains_math:
        filters["contains_math"] = True
    pkg = build_retriever(dense=mode != "bm25").search(args.query, mode, filters)
    if args.json:
        print(json.dumps(pkg, indent=2, ensure_ascii=False))
        return 0
    print(f"mode={pkg['retrieval_mode']} filters={pkg['filters_applied']}")
    for r in pkg["retrieved_chunks"]:
        print(f"{r['rank']:>2} {r['score']:.4f} {r['source']:<10} {r['chunk_id']:<17} {r['notebook_title']} | "
              f"{r['section_path'][-60:]}")
    for t in pkg["attached_tools"]:
        print(f"   + tool {t['tool_id']} ({t['relationship']}, {t['attachment_reason']}) for {t['concept_chunk_id']}")
    for r in pkg["attached_resources"]:
        print(f"   + image {r['resource_id']} ({r['resource_type']}, vision {r['vision_status']}, not text evidence)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
