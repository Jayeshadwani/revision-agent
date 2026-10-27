#!/usr/bin/env python3
"""
PH4-RETRIEVE-001 (issue #9): measure retrieval quality for dense-only, BM25-only and hybrid RRF on the
same labelled prompts.

    python src/retrieval_eval.py              # all modes that can run (dense needs the index + API key)
    python src/retrieval_eval.py --bm25-only  # no API calls

Labelled prompts:
  evaluation/golden_prompts.jsonl      20 prompts (17 with expected sources; 3 refusals are reported
                                       separately because they have no relevant source)
  evaluation/retrieval_qa_set.jsonl    30 prompts: 10 concept, 5 math, 5 tool, 5 broad short,
                                       5 multi-notebook (labelled from the notebook sections)
evaluation/retrieval_prompts.jsonl (320) has no expected sources yet, so it cannot be scored.

Relevance: a retrieved chunk is relevant when one of its source cells is an expected source cell.
Expected cells that no retrieval-eligible chunk contains (image-only cells, for example) cannot be
retrieved; recall is computed over the reachable ones, and the unreachable ones are listed.

Metrics per prompt, on the fused/ranked list (not the type-capped context package):
  Recall@k  share of reachable expected cells covered by the top k chunks
  Hit@1     the first chunk is relevant
  MRR       1 / rank of the first relevant chunk (0 if none in the top 20)
Tool coverage: prompts with expected code cells (or expected tool IDs) where a matching tool is in the
top 10 or attached to a retrieved concept.

Writes data/processed/retrieval_results.jsonl, retrieval_report.md and, when dense and hybrid were
both measured, retrieval_decision.json (the default mode used by src/retrieval.py).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
from retrieval import DECISION_FILE, EXCLUDED_ROLES, MODES, Retriever, build_retriever, chunk_meta  # noqa: E402

EVAL_DIR = config.ROOT / "evaluation"
PROMPT_FILES = ("golden_prompts.jsonl", "retrieval_qa_set.jsonl")
RESULTS_JSONL = "retrieval_results.jsonl"
REPORT_MD = "retrieval_report.md"
CATEGORIES = ("all", "concept", "math", "tool", "multi_notebook", "formula_keyword", "broad_short")
FILTER_PROBES = [
    ("precision and recall", {"chunk_type": "tool"}),
    ("precision and recall", {"chunk_type": "concept"}),
    ("gradient descent update", {"contains_math": True}),
    ("decision tree split", {"notebook_id": "nb_16"}),
    ("define a function", {"content_role": "tool_function"}),
]
ACRONYM_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,}\b")                       # PCA, GMM, F1, LSTM (case-sensitive)
IDENT_RE = re.compile(r"\w+_\w+|\w+\(\)|\.\w+\(|[=^$]")                # fillna(), train_test_split, formulas
TERM_RE = re.compile(r"\b(formula|equation|derivative|theorem|entropy|gini|harmonic|cosine|sigmoid|softmax|"
                     r"silhouette|f1|fillna|groupby|gridsearchcv|standardscaler|spacy|keras|sklearn)\b", re.I)


def keyword_heavy(prompt: str) -> bool:
    """Prompts whose answer hinges on an exact term: acronyms, identifiers, formula words."""
    return bool(ACRONYM_RE.search(prompt) or IDENT_RE.search(prompt) or TERM_RE.search(prompt))


# ----------------------------------------------------------------------------
# Prompts and labels
# ----------------------------------------------------------------------------
def load_prompts(eval_dir: Path = EVAL_DIR) -> list[dict]:
    prompts = []
    for name in PROMPT_FILES:
        path = eval_dir / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                p = json.loads(line)
                p["_file"] = name
                prompts.append(p)
    return prompts


def expected_cells(p: dict) -> set[tuple[str, int]]:
    return {(s["notebook_id"], int(i)) for s in p.get("expected_sources", []) for i in s["cell_ids"]}


def categories(p: dict) -> list[str]:
    """Category tags. The QA set names its category; golden prompts are tagged from their labels."""
    req = p.get("requirements", {})
    srcs = p.get("expected_sources", [])
    tags = {"all"}
    if p.get("category"):
        tags.add(p["category"])
    if any(s.get("source_type") == "markdown" for s in srcs) and p.get("category") in (None, "concept"):
        tags.add("concept")
    if req.get("requires_math") or p.get("prompt_type") in ("math_derivation", "formula_recall") or \
            p.get("category") == "math":
        tags.add("math")
    if req.get("requires_tool") or any(s.get("source_type") == "code" for s in srcs) or p.get("category") == "tool":
        tags.add("tool")
    if len({s["notebook_id"] for s in srcs}) > 1:
        tags.add("multi_notebook")
    if keyword_heavy(p["prompt"]):
        tags.add("formula_keyword")
    if len(p["prompt"].split()) <= 4:
        tags.add("broad_short")
    return [c for c in CATEGORIES if c in tags]


def chunk_cells(ch: dict) -> set[tuple[str, int]]:
    return {(ch["notebook_id"], int(i)) for i in ch["source_cell_ids"]}


# ----------------------------------------------------------------------------
# Scoring
# ----------------------------------------------------------------------------
def score_prompt(ranking_ids: list[str], package: dict, chunks: dict, expected: set, reachable: set,
                 expected_tools: set) -> dict:
    cells_at = [chunk_cells(chunks[c]) & reachable for c in ranking_ids]
    relevant = [bool(c) for c in cells_at]

    def recall(k: int) -> float:
        covered = set().union(*cells_at[:k]) if cells_at[:k] else set()
        return len(covered) / len(reachable) if reachable else 0.0
    first = next((i for i, r in enumerate(relevant, 1) if r), None)
    code_cells = {c for c in expected if c in reachable}
    tool_hit = None
    if expected_tools or package.get("_expects_code"):
        top_tools = {chunks[c].get("tool_id") for c in ranking_ids[:10] if chunks[c]["chunk_type"] == "tool"}
        top_tool_cells = set().union(*(chunk_cells(chunks[c]) for c in ranking_ids[:10]
                                       if chunks[c]["chunk_type"] == "tool")) if ranking_ids else set()
        attached = {t["tool_id"] for t in package["attached_tools"]}
        attached_cells = set().union(*(chunk_cells(chunks[t["tool_chunk_id"]]) for t in package["attached_tools"])) \
            if package["attached_tools"] else set()
        tool_hit = bool((expected_tools & (top_tools | attached)) or (code_cells & (top_tool_cells | attached_cells)))
    return {"recall_at_5": round(recall(5), 4), "recall_at_10": round(recall(10), 4),
            "hit_at_1": 1.0 if relevant[:1] == [True] else 0.0, "mrr": round(1.0 / first, 4) if first else 0.0,
            "first_relevant_rank": first, "expected_source_hit": any(relevant[:10]), "tool_hit": tool_hit}


def violations(package: dict, chunks: dict) -> list[str]:
    bad = []
    for r in package["retrieved_chunks"] + package["ranking"]:
        ch = chunks.get(r["chunk_id"])
        if ch is None or ch["chunk_type"] not in ("concept", "tool") or chunk_meta(ch)["content_role"] in EXCLUDED_ROLES:
            bad.append(f"{r['chunk_id']}: excluded content")
        elif not ch.get("retrieval_eligible"):
            bad.append(f"{r['chunk_id']}: not retrieval-eligible")
        else:
            meta = chunk_meta(ch)
            for k, v in package["filters_applied"].items():
                if meta.get(k) != v:
                    bad.append(f"{r['chunk_id']}: filter {k}={v} violated")
    for res in package["attached_resources"]:
        if not res["not_usable_as_text_evidence"] and res["vision_status"] != "done":
            bad.append(f"{res['resource_id']}: pending-vision resource usable as evidence")
    return bad


def mean(xs: list[float]) -> Optional[float]:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 4) if xs else None


def evaluate(retriever: Retriever, prompts: list[dict], modes: list[str]) -> dict:
    chunks = retriever.corpus.chunks
    reachable_all = set().union(*(chunk_cells(c) for c in chunks.values()))
    rows, per_mode, refusals, unreachable = [], defaultdict(list), defaultdict(list), []
    for p in prompts:
        exp = expected_cells(p)
        cats = categories(p)
        reach = exp & reachable_all
        if exp - reachable_all:
            unreachable.append((p["prompt_id"], sorted(exp - reachable_all), len(reach)))
        for mode in modes:
            pkg = retriever.search(p["prompt"], mode)
            pkg["_expects_code"] = any(s.get("source_type") == "code" for s in p.get("expected_sources", []))
            ids = [r["chunk_id"] for r in pkg["ranking"]]
            bad = violations(pkg, chunks)
            row = {"prompt_id": p["prompt_id"], "prompt": p["prompt"], "prompt_set": p["_file"], "categories": cats,
                   "retrieval_mode": mode, "filters_applied": pkg["filters_applied"],
                   "retrieved_chunks": [{k: r[k] for k in ("rank", "chunk_id", "chunk_type", "score", "source",
                                                         "notebook_id", "section_path")} for r in pkg["retrieved_chunks"]],
                   "ranking_top10": ids[:10],
                   "attached_tools": [{k: t[k] for k in ("tool_id", "relationship", "attachment_reason",
                                                       "concept_chunk_id")} for t in pkg["attached_tools"]],
                   "attached_resources": [{k: r[k] for k in ("resource_id", "vision_status",
                                                           "not_usable_as_text_evidence")}
                                          for r in pkg["attached_resources"]],
                   "violations": bad}
            if not exp:
                row["note"] = "no expected sources (refusal): not scored"
                top = pkg["ranking"][0]["score"] if pkg["ranking"] else None
                refusals[mode].append((p["prompt_id"], top))
            elif not reach:
                row["note"] = "expected sources not in any retrieval-eligible chunk: not scored"
            else:
                row.update(score_prompt(ids, pkg, chunks, exp, reach, set(p.get("expected_tool_ids", []))))
                per_mode[mode].append(row)
            rows.append(row)
    summary = {}
    for mode in modes:
        summary[mode] = {}
        for cat in CATEGORIES:
            rr = [r for r in per_mode[mode] if cat in r["categories"]]
            summary[mode][cat] = {"n": len(rr), "recall_at_5": mean([r["recall_at_5"] for r in rr]),
                                  "recall_at_10": mean([r["recall_at_10"] for r in rr]),
                                  "mrr": mean([r["mrr"] for r in rr]), "hit_at_1": mean([r["hit_at_1"] for r in rr]),
                                  "tool_coverage": mean([1.0 if r["tool_hit"] else 0.0 for r in rr
                                                         if r["tool_hit"] is not None])}
    probes = filter_probes(retriever, modes)
    return {"rows": rows, "summary": summary, "refusals": dict(refusals), "unreachable": unreachable,
            "probes": probes, "violations": sum(len(r["violations"]) for r in rows) + sum(p["violations"] for p in probes),
            "guard_dropped": retriever.guard_dropped}


def filter_probes(retriever: Retriever, modes: list[str]) -> list[dict]:
    out = []
    for query, flt in FILTER_PROBES:
        for mode in modes:
            pkg = retriever.search(query, mode, flt)
            out.append({"query": query, "filters": flt, "mode": mode, "results": len(pkg["ranking"]),
                        "violations": len(violations(pkg, retriever.corpus.chunks))})
    return out


def decide(summary: dict) -> Optional[dict]:
    """Hybrid becomes the default only if it beats dense on Recall@5 or MRR without losing on either."""
    if "dense" not in summary or "hybrid_rrf" not in summary:
        return None
    d, h = summary["dense"]["all"], summary["hybrid_rrf"]["all"]
    better = (h["recall_at_5"] > d["recall_at_5"] or h["mrr"] > d["mrr"])
    not_worse = h["recall_at_5"] >= d["recall_at_5"] and h["mrr"] >= d["mrr"]
    mode = "hybrid_rrf" if better and not_worse else "dense"
    return {"default_mode": mode, "rule": "hybrid if Recall@5 or MRR improves and neither drops (all prompts)",
            "dense": {k: d[k] for k in ("recall_at_5", "mrr")}, "hybrid_rrf": {k: h[k] for k in ("recall_at_5", "mrr")}}


# ----------------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------------
def fmt(x) -> str:
    return "—" if x is None else f"{x:.3f}"


def build_report(res: dict, modes: list[str], skipped: dict, decision: Optional[dict], n_prompts: int) -> str:
    L = ["# Retrieval Report", "", f"PH4-RETRIEVE-001 · `src/retrieval_eval.py` · modes run: {', '.join(modes)}", ""]
    for m, why in skipped.items():
        L.append(f"- **{m} not run:** {why}")
    if skipped:
        L.append("")
    scored = {m: res["summary"][m]["all"]["n"] for m in modes}
    L += ["## Setup", "",
          f"- Prompts: {n_prompts} labelled ({', '.join(PROMPT_FILES)}); scored per mode: "
          + ", ".join(f"{m} {n}" for m, n in scored.items()),
          "- Dense: Qdrant `revision_agent_v1`, top 50. BM25: Okapi (k1 1.5, b 0.75) over the same 2,174 texts, top 50. "
          "Fusion: RRF, k = 60, no weights.",
          "- Metrics are computed on the ranked list (top 20 kept); the context package (5 concepts + 3 tools, max 8) "
          "is what generation will receive.", ""]
    L += ["## Results (all scored prompts)", "", "| Mode | Recall@5 | Recall@10 | MRR | Hit@1 | Tool coverage |",
          "|---|---:|---:|---:|---:|---:|"]
    for m in modes:
        s = res["summary"][m]["all"]
        L.append(f"| {m} | {fmt(s['recall_at_5'])} | {fmt(s['recall_at_10'])} | {fmt(s['mrr'])} | "
                 f"{fmt(s['hit_at_1'])} | {fmt(s['tool_coverage'])} |")
    L += ["", "## By category", "", "| Category | n | " + " | ".join(f"{m} R@5 / MRR" for m in modes) + " |",
          "|---|---:|" + "---:|" * len(modes)]
    for cat in CATEGORIES[1:]:
        n = res["summary"][modes[0]][cat]["n"]
        cells = [f"{fmt(res['summary'][m][cat]['recall_at_5'])} / {fmt(res['summary'][m][cat]['mrr'])}" for m in modes]
        L.append(f"| {cat} | {n} | " + " | ".join(cells) + " |")
    L += ["", "Categories overlap (a prompt can be math and multi-notebook). Small n: read category numbers as "
          "directional.", ""]
    L += ["## Decision", ""]
    if decision:
        L += [f"- Default mode: **{decision['default_mode']}** ({decision['rule']}).",
              f"- Dense Recall@5 {fmt(decision['dense']['recall_at_5'])}, MRR {fmt(decision['dense']['mrr'])}; "
              f"hybrid Recall@5 {fmt(decision['hybrid_rrf']['recall_at_5'])}, MRR {fmt(decision['hybrid_rrf']['mrr'])}.",
              f"- Written to `{DECISION_FILE.relative_to(config.ROOT)}`; `src/retrieval.py` uses it as the default.", ""]
    else:
        L += ["- Not decided: dense and hybrid were not both measured. `src/retrieval.py` keeps `dense` as the default.", ""]
    ok = res["violations"] == 0
    L += ["## Safety and filters", "",
          f"- Filter correctness: **{'PASS' if ok else 'FAIL'}** — {len(res['probes'])} filtered probes "
          f"({len(FILTER_PROBES)} filters × {len(modes)} modes) and every scored query checked; violations: "
          f"{res['violations']}.",
          f"- Excluded support content, resources or ineligible chunks in results: "
          f"{'none' if ok else 'see retrieval_results.jsonl'}. Guard drops (stale index entries): {res['guard_dropped']}.",
          "- Attached resources all carry `not_usable_as_text_evidence: true` (vision pending); none are text evidence.", ""]
    L += ["## Not scored", ""]
    for m, items in res["refusals"].items():
        L.append(f"- Refusal prompts ({m}): " + ", ".join(f"{pid} top score {fmt(s)}" for pid, s in items))
    for pid, cells, n_reach in res["unreachable"]:
        L.append(f"- {pid}: expected cells not in any eligible chunk: "
                 + ", ".join(f"{nb} cell {c}" for nb, c in cells) + f" (reachable expected cells left: {n_reach})")
    L.append("")
    return "\n".join(L) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bm25-only", action="store_true", help="skip dense and hybrid (no API calls)")
    args = ap.parse_args(argv)
    skipped = {}
    if args.bm25_only:
        retriever, modes = build_retriever(dense=False), ["bm25"]
        skipped = {"dense": "--bm25-only", "hybrid_rrf": "--bm25-only"}
    else:
        try:
            retriever, modes = build_retriever(dense=True), list(MODES)
        except RuntimeError as e:
            print(f"dense unavailable ({e}); running BM25 only", file=sys.stderr)
            retriever, modes = build_retriever(dense=False), ["bm25"]
            skipped = {"dense": str(e), "hybrid_rrf": str(e)}
    prompts = load_prompts()
    res = evaluate(retriever, prompts, modes)
    decision = decide(res["summary"])
    out = config.PROCESSED_DIR
    (out / RESULTS_JSONL).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in res["rows"]),
                                     encoding="utf-8", newline="\n")
    if decision:
        DECISION_FILE.write_text(json.dumps(decision, indent=2) + "\n", encoding="utf-8")
    (out / REPORT_MD).write_text(build_report(res, modes, skipped, decision, len(prompts)), encoding="utf-8",
                                 newline="\n")
    for m in modes:
        s = res["summary"][m]["all"]
        print(f"{m:<11} R@5 {fmt(s['recall_at_5'])}  R@10 {fmt(s['recall_at_10'])}  MRR {fmt(s['mrr'])}  "
              f"Hit@1 {fmt(s['hit_at_1'])}  tools {fmt(s['tool_coverage'])}  (n={s['n']})")
    print(f"violations {res['violations']}" + (f"  default -> {decision['default_mode']}" if decision else ""))
    return 0 if res["violations"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
