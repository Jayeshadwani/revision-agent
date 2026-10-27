#!/usr/bin/env python3
"""
Validate and summarise the evaluation sets, or export one as CSV.

    evaluation/golden_set.jsonl     20 fully keyed samples (answer + sources); must all be complete
    evaluation/retrieval_set.jsonl  320 questions for retrieval evaluation; answer keys come later

Usage (from the project root):
    python scripts/eval_report.py                          # summary of both sets
    python scripts/eval_report.py --set golden             # summary of one set
    python scripts/eval_report.py --check                  # validate both; exits 1 on errors
    python scripts/eval_report.py --set retrieval --csv x.csv   # flat CSV ('|' separates list items)

Everything is derived from the JSONL files, so no summary files are committed.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETS = {
    "golden": ROOT / "evaluation" / "golden_set.jsonl",
    "retrieval": ROOT / "evaluation" / "retrieval_set.jsonl",
}

QUESTION_TYPES = {
    "definition", "formula_recall", "math_derivation", "concept_explanation", "comparison",
    "code_implementation", "code_explanation", "debugging", "multi_notebook_synthesis",
    "topic_recommendation", "revision_plan", "refusal", "partial_answer",
}
TEMPLATES = {
    "concept_explanation", "formula", "mathematical_explanation", "comparison",
    "code_implementation", "code_explanation", "misconception", "synthesis",
    "topic_recommendation", "revision_plan", "refusal", "partial_answer",
}
DIFFICULTIES = ("easy", "medium", "hard")
SOURCE_TYPES = {"markdown", "code", "output", "mixed"}
TOP_LEVEL = [
    "question_id", "version", "question", "question_type", "difficulty", "difficulty_score",
    "expected_answer", "expected_sources", "expected_chunk_ids", "expected_topics",
    "requirements", "answer_template", "evaluation", "notes",
]
REQUIREMENTS = [
    "requires_math", "requires_code", "requires_comparison", "requires_multi_notebook",
    "requires_recommendation", "requires_step_by_step", "partial_evidence_only", "should_refuse",
]


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def band(score: float) -> str:
    return "easy" if score < 0.40 else "medium" if score < 0.70 else "hard"


def has_key_answer(q: dict) -> bool:
    ea = q["expected_answer"]
    return bool(ea.get("summary") or ea.get("key_points"))


def has_sources(q: dict) -> bool:
    return bool(q["expected_sources"])


def is_complete(q: dict) -> bool:
    """Ready to score: an answer key, plus sources unless it is a refusal."""
    return has_key_answer(q) and (q["requirements"]["should_refuse"] or has_sources(q))


# ----------------------------------------------------------------------------
# Validation: errors break the schema; "incomplete" just means the answer key is pending.
# ----------------------------------------------------------------------------
def validate(q: dict) -> list[str]:
    e = []
    qid = q.get("question_id", "?")
    missing = [k for k in TOP_LEVEL if k not in q]
    if missing:
        return [f"{qid}: missing fields {missing}"]
    if not q["question"].strip():
        e.append(f"{qid}: empty question")
    if q["question_type"] not in QUESTION_TYPES:
        e.append(f"{qid}: bad question_type {q['question_type']!r}")
    if q["answer_template"] not in TEMPLATES:
        e.append(f"{qid}: bad answer_template {q['answer_template']!r}")
    if q["difficulty"] not in DIFFICULTIES:
        e.append(f"{qid}: bad difficulty {q['difficulty']!r}")
    elif band(q["difficulty_score"]) != q["difficulty"]:
        e.append(f"{qid}: difficulty {q['difficulty']} != band of score {q['difficulty_score']}")

    req = q["requirements"]
    if sorted(req) != sorted(REQUIREMENTS):
        e.append(f"{qid}: requirements keys {sorted(req)}")
        return e
    if req["should_refuse"] and q["expected_sources"]:
        e.append(f"{qid}: should_refuse but has expected_sources")
    if req["should_refuse"] != (q["question_type"] == "refusal"):
        e.append(f"{qid}: should_refuse inconsistent with question_type")
    if req["partial_evidence_only"] != (q["question_type"] == "partial_answer"):
        e.append(f"{qid}: partial_evidence_only inconsistent with question_type")
    if req["requires_math"] and q["answer_template"] not in ("formula", "mathematical_explanation") \
            and not {"mathematical_form", "formula"} & set(q["expected_answer"]["required_sections"]) \
            and q["question_type"] not in ("refusal", "partial_answer"):
        e.append(f"{qid}: requires_math but no math template or required math section")

    nbs = {s.get("notebook_id") for s in q["expected_sources"]}
    if req["requires_multi_notebook"] and q["expected_sources"] and len(nbs) < 2:
        e.append(f"{qid}: requires_multi_notebook but sources from {len(nbs)} notebook")
    for s in q["expected_sources"]:
        if s.get("source_type") not in SOURCE_TYPES:
            e.append(f"{qid}: bad source_type {s.get('source_type')!r}")
        if not s.get("notebook_id") or not s.get("cell_ids"):
            e.append(f"{qid}: source without notebook_id or cell_ids")

    ea = q["expected_answer"]
    if "sources" not in ea["required_sections"] and q["answer_template"] != "refusal":
        e.append(f"{qid}: required_sections lacks 'sources'")
    if set(ea["required_sections"]) & set(ea["optional_sections"]):
        e.append(f"{qid}: section both required and optional")
    return e


def check(sets: dict[str, list[dict]]) -> int:
    all_qs = [q for qs in sets.values() for q in qs]
    errors = [f"duplicate id {i} (across sets)" for i, n in
              Counter(q["question_id"] for q in all_qs).items() if n > 1]
    for name, qs in sets.items():
        for q in qs:
            errors += [f"[{name}] {e}" for e in validate(q)]
            if name == "golden" and not is_complete(q):
                errors.append(f"[golden] {q['question_id']}: golden samples need an answer key and sources")
    if errors:
        print("\n".join(errors))
        print(f"\n{len(errors)} errors")
        return 1
    for name, qs in sets.items():
        done = sum(is_complete(q) for q in qs)
        print(f"OK [{name}]: {len(qs)} records valid, {done} with answer key + sources, "
              f"{len(qs) - done} pending.")
    return 0


# ----------------------------------------------------------------------------
# Reports
# ----------------------------------------------------------------------------
def summary(qs: list[dict]) -> None:
    total = len(qs)
    diff = Counter(q["difficulty"] for q in qs)
    print(f"{total} questions")
    for lvl in DIFFICULTIES:
        print(f"  {lvl:7} {diff[lvl]:4}  ({diff[lvl] / total:.1%})")

    rows: dict[str, Counter] = defaultdict(Counter)
    for q in qs:
        c = rows[q["question_type"]]
        c[q["difficulty"]] += 1
        c["answer"] += has_key_answer(q)
        c["sources"] += has_sources(q)
        c["complete"] += is_complete(q)
    print(f"\n  {'question_type':26} {'easy':>4} {'med':>4} {'hard':>4} {'total':>5}"
          f" {'key':>4} {'src':>4} {'done':>4}")
    for t in sorted(rows):
        c = rows[t]
        n = c["easy"] + c["medium"] + c["hard"]
        print(f"  {t:26} {c['easy']:4} {c['medium']:4} {c['hard']:4} {n:5}"
              f" {c['answer']:4} {c['sources']:4} {c['complete']:4}")
    print("\n  key = has expected answer, src = has expected sources, done = both (or a refusal with a key)")

    print("\nBy answer_template")
    for k, v in Counter(q["answer_template"] for q in qs).most_common():
        print(f"  {k:26} {v:4}")
    print("\nBy topic")
    for k, v in sorted(Counter(t for q in qs for t in q["expected_topics"]).items()):
        print(f"  {k:42} {v:3}")


def export_csv(qs: list[dict], out: Path) -> None:
    def j(items):
        return "|".join(str(x) for x in items)

    cols = ["question_id", "version", "question", "question_type", "difficulty", "difficulty_score",
            "expected_summary", "expected_key_points", "required_sections", "expected_notebook_ids",
            "expected_cell_ids", "expected_chunk_ids", "expected_topics", *REQUIREMENTS,
            "answer_template", "min_faithfulness", "min_correctness", "min_context_recall", "notes"]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for q in qs:
            ea, ev, src = q["expected_answer"], q["evaluation"], q["expected_sources"]
            w.writerow([
                q["question_id"], q["version"], q["question"], q["question_type"], q["difficulty"],
                q["difficulty_score"], ea["summary"], j(ea["key_points"]), j(ea["required_sections"]),
                j(dict.fromkeys(s["notebook_id"] for s in src)),
                j(f"{s['notebook_id']}:{c}" for s in src for c in s["cell_ids"]),
                j(q["expected_chunk_ids"]), j(q["expected_topics"]),
                *[q["requirements"][k] for k in REQUIREMENTS],
                q["answer_template"], ev["min_faithfulness"], ev["min_correctness"],
                ev["min_context_recall"], q["notes"],
            ])
    print(f"wrote {len(qs)} rows to {out}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", choices=sorted(SETS), help="limit to one set (default: both)")
    ap.add_argument("--check", action="store_true", help="validate the schema")
    ap.add_argument("--csv", type=Path, help="export a flat CSV of --set to this path")
    args = ap.parse_args()

    names = [args.set] if args.set else list(SETS)
    sets = {n: load(SETS[n]) for n in names}
    if args.check:
        return check(sets)
    if args.csv:
        if not args.set:
            ap.error("--csv needs --set golden or --set retrieval")
        export_csv(sets[args.set], args.csv)
        return 0
    for i, (name, qs) in enumerate(sets.items()):
        print(("\n" if i else "") + f"=== {name} set ({SETS[name].name}) ===")
        summary(qs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
