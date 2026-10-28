#!/usr/bin/env python3
"""
PH5-RETRIEVE-002 (issue #11), Gate A: offline, no-cost comparison of child sizes for parent retrieval.

    python src/parent_experiment.py

BM25 only: no embedding calls, no model download, no index change. It answers "do small children
mapped back to their parents retrieve the labelled sources better than the current chunks?" for
keyword search, and produces the resource estimates the PO needs to approve dense experiments.

Variants (same labelled prompts, same 50-candidate budget, same scoring as retrieval_eval.py):
  baseline     BM25 over the current 2,174 Concept/Tool chunks
  child_128    BM25 over <=128-token children -> deduplicated parents (Concept chunks / Tools)
  child_256    BM25 over <=256-token children -> deduplicated parents
Children carry their parent's breadcrumb (notebook + section path) so a window keeps its context.

Prompts are split deterministically (sha256 of prompt_id): 60% dev, 40% held-out test. Gate A tunes
nothing; the split is fixed now so Gate B can tune on dev only and report test once.

Writes data/processed/parent_experiment_report.md and parent_experiment_results.jsonl.
"""
from __future__ import annotations

import hashlib
import json
import statistics
import sys
import time
import tracemalloc
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
from bm25_index import BM25Index  # noqa: E402
from chunking import content_tokens  # noqa: E402
from embeddings import DEFAULT_CONFIG, embedding_text  # noqa: E402
from parent_retrieval import CHILD_SIZES, ParentStore, build_corpus_store  # noqa: E402
from retrieval import Corpus, Retriever  # noqa: E402
from retrieval_eval import CATEGORIES, categories, chunk_cells, expected_cells, load_prompts, score_prompt  # noqa: E402

CANDIDATE_K = 50
CHILD_CANDIDATE_K = 150            # children per query before parent dedup (several children share a parent)
TOP_CONTEXT = 5
REPORT_MD = "parent_experiment_report.md"
RESULTS_JSONL = "parent_experiment_results.jsonl"
TEST_SHARE = 0.4
VECTOR_BYTES = DEFAULT_CONFIG.dimensions * 4


def split_of(prompt_id: str) -> str:
    h = int(hashlib.sha256(prompt_id.encode()).hexdigest()[:8], 16)
    return "test" if (h % 100) < TEST_SHARE * 100 else "dev"


class ChildSearch:
    def __init__(self, store: ParentStore):
        self.store = store
        self.bm25 = BM25Index()
        for cid, child in store.children.items():
            parent = store.parents.get(child.parent_id)
            crumb = f"Notebook: {child.notebook_id}\nSection path: {parent.section if parent else ''}\n\n"
            self.bm25.add(cid, crumb + child.text, {"notebook_id": child.notebook_id})

    def parent_ranking(self, query: str) -> tuple[list[str], dict]:
        hits = [cid for _, cid in self.bm25.search(query, limit=CHILD_CANDIDATE_K)]
        exp = self.store.expand(hits, context_budget=10**9)       # rank all; budgets are measured separately
        return [p.parent_id for p in exp.parents][:CANDIDATE_K], {"errors": len(exp.errors),
                                                                   "children_hit": len(hits)}


def run() -> dict:
    d = config.PROCESSED_DIR
    concepts = [json.loads(l) for l in (d / "concept_chunks.jsonl").read_text().splitlines() if l.strip()]
    tools = [json.loads(l) for l in (d / "tool_chunks.jsonl").read_text().splitlines() if l.strip()]
    concepts = [c for c in concepts if c["retrieval_eligible"]]
    tools = [t for t in tools if t["retrieval_eligible"]]
    spans = {s["span_id"]: s for s in map(json.loads, (d / "spans.jsonl").read_text().splitlines()) if s}
    corpus = Corpus.load(d)
    chunks = corpus.chunks
    reachable_all = set().union(*(chunk_cells(c) for c in chunks.values()))
    prompts = [p for p in load_prompts() if expected_cells(p) & reachable_all]

    variants: dict[str, object] = {"baseline": Retriever(corpus)}
    footprint = {"baseline": {"units": len(chunks), "tokens": sum(content_tokens(embedding_text(c))
                                                                  for c in chunks.values())}}
    stores = {}
    for size in CHILD_SIZES:
        tracemalloc.start()
        t0 = time.perf_counter()
        store = build_corpus_store(concepts, tools, spans, size)
        search = ChildSearch(store)
        build_s = time.perf_counter() - t0
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        name = f"child_{size}"
        variants[name], stores[name] = search, store
        footprint[name] = {"units": len(store.children), "build_seconds": round(build_s, 2),
                           "peak_mb": round(peak / 2**20, 1),
                           "tokens": sum(content_tokens(c.text) for c in store.children.values())}

    rows = []
    for name, v in variants.items():
        for p in prompts:
            exp = expected_cells(p)
            reach = exp & reachable_all
            t0 = time.perf_counter()
            if name == "baseline":
                ranking = [r["chunk_id"] for r in v.rank(p["prompt"], "bm25", {"retrieval_eligible": True})][:CANDIDATE_K]
                info = {}
            else:
                ranking, info = v.parent_ranking(p["prompt"])
            ms = (time.perf_counter() - t0) * 1000
            pkg = {"attached_tools": [],
                   "_expects_code": any(s.get("source_type") == "code" for s in p.get("expected_sources", []))}
            s = score_prompt(ranking, pkg, chunks, exp, reach, set(p.get("expected_tool_ids", [])))
            covered50 = set().union(*(chunk_cells(chunks[c]) for c in ranking)) & reach if ranking else set()
            top = ranking[:TOP_CONTEXT]
            rows.append({"variant": name, "prompt_id": p["prompt_id"], "split": split_of(p["prompt_id"]),
                         "categories": categories(p), **s,
                         "candidate_recall_at_50": round(len(covered50) / len(reach), 4),
                         "context_tokens_top5": sum(content_tokens(embedding_text(chunks[c])) for c in top),
                         "distinct_notebooks_top5": len({chunks[c]["notebook_id"] for c in top}),
                         "useful_parents_top5": sum(bool(chunk_cells(chunks[c]) & reach) for c in top),
                         "latency_ms": round(ms, 2), **info})
    return {"rows": rows, "footprint": footprint, "n_prompts": len(prompts)}


def summarise(rows: list[dict], variant: str, split: str = "all", cat: str = "all") -> dict:
    rr = [r for r in rows if r["variant"] == variant and (split == "all" or r["split"] == split)
          and cat in r["categories"]]
    if not rr:
        return {"n": 0}
    m = lambda k: round(statistics.mean(r[k] for r in rr), 3)          # noqa: E731
    lat = sorted(r["latency_ms"] for r in rr)
    tools = [r["tool_hit"] for r in rr if r["tool_hit"] is not None]
    return {"n": len(rr), "recall_at_5": m("recall_at_5"), "recall_at_10": m("recall_at_10"), "mrr": m("mrr"),
            "hit_at_1": m("hit_at_1"), "candidate_recall_at_50": m("candidate_recall_at_50"),
            "context_tokens_top5": round(statistics.mean(r["context_tokens_top5"] for r in rr)),
            "useful_ratio_top5": round(sum(r["useful_parents_top5"] for r in rr) / (TOP_CONTEXT * len(rr)), 3),
            "tool_coverage": round(sum(tools) / len(tools), 3) if tools else None,
            "p50_ms": round(lat[len(lat) // 2], 1), "p95_ms": round(lat[min(len(lat) - 1, int(len(lat) * 0.95))], 1)}


def report(res: dict) -> str:
    rows, fp = res["rows"], res["footprint"]
    variants = list(fp)
    L = ["# Parent Retrieval Experiment (Gate A, BM25 only)", "",
         "Issue #11 · `src/parent_experiment.py` · no embedding calls, no model download, no index change.", "",
         f"- Prompts: {res['n_prompts']} labelled prompts with a reachable source "
         f"(dev {sum(1 for r in rows if r['variant'] == 'baseline' and r['split'] == 'dev')}, "
         f"held-out test {sum(1 for r in rows if r['variant'] == 'baseline' and r['split'] == 'test')}; "
         "split by sha256(prompt_id), fixed before any tuning).",
         f"- Candidate budget: {CANDIDATE_K} parents per query (children: {CHILD_CANDIDATE_K} hits before dedup). "
         "Parents are the existing Concept/Tool chunks, so labels and IDs are unchanged.",
         "- Token counts are the pipeline's estimate (tiktoken is not installed in this workspace).",
         "- Tool coverage here counts tools in the ranking only (no attachment step), for every variant alike.", "",
         "## All prompts", "",
         "| Variant | Recall@5 | Recall@10 | MRR | Hit@1 | Candidate Recall@50 | Tool cov. | Context tokens (top 5) "
         "| Useful parents in top 5 | p50 / p95 ms |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for v in variants:
        s = summarise(rows, v)
        L.append(f"| {v} | {s['recall_at_5']} | {s['recall_at_10']} | {s['mrr']} | {s['hit_at_1']} | "
                 f"{s['candidate_recall_at_50']} | {s['tool_coverage']} | {s['context_tokens_top5']:,} | "
                 f"{s['useful_ratio_top5']} | {s['p50_ms']} / {s['p95_ms']} |")
    L += ["", "## Dev vs held-out test (Recall@5 / MRR)", "", "| Variant | dev | test |", "|---|---|---|"]
    for v in variants:
        dv, ts = summarise(rows, v, "dev"), summarise(rows, v, "test")
        L.append(f"| {v} | {dv['recall_at_5']} / {dv['mrr']} (n={dv['n']}) | {ts['recall_at_5']} / {ts['mrr']} "
                 f"(n={ts['n']}) |")
    L += ["", "## By category (Recall@5 / MRR)", "", "| Category | n | " + " | ".join(variants) + " |",
          "|---|---:|" + "---|" * len(variants)]
    for cat in CATEGORIES[1:]:
        ss = [summarise(rows, v, cat=cat) for v in variants]
        if ss[0]["n"]:
            L.append(f"| {cat} | {ss[0]['n']} | " + " | ".join(f"{s['recall_at_5']} / {s['mrr']}" for s in ss) + " |")
    L += ["", "## Footprint", "", "| Variant | Units indexed | Tokens (est.) | Build s | Peak MB (build) | "
          "Dense vectors storage (1536-d float32) | Embedding cost at $0.02/1M |", "|---|---:|---:|---:|---:|---:|---:|"]
    for v in variants:
        f = fp[v]
        L.append(f"| {v} | {f['units']:,} | {f['tokens']:,} | {f.get('build_seconds', '—')} | {f.get('peak_mb', '—')} | "
                 f"{f['units'] * VECTOR_BYTES / 2**20:.1f} MB | ${f['tokens'] / 1e6 * 0.02:.4f} |")
    L += ["", "Per-query keyword search is local and takes milliseconds; dense child search adds one query "
          "embedding (already cached per query) and a Qdrant search over more vectors.", ""]
    return "\n".join(L) + "\n"


def main() -> int:
    res = run()
    d = config.PROCESSED_DIR
    (d / RESULTS_JSONL).write_text("".join(json.dumps(r) + "\n" for r in res["rows"]), encoding="utf-8")
    (d / REPORT_MD).write_text(report(res), encoding="utf-8")
    for v in res["footprint"]:
        s = summarise(res["rows"], v)
        print(f"{v:<9} R@5 {s['recall_at_5']}  R@10 {s['recall_at_10']}  MRR {s['mrr']}  Hit@1 {s['hit_at_1']}  "
              f"cand@50 {s['candidate_recall_at_50']}  ctx {s['context_tokens_top5']}  units {res['footprint'][v]['units']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
