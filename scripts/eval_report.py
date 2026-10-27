#!/usr/bin/env python3
"""
Summarise the evaluation set, or export it as CSV.

Usage (from the project root):
    python scripts/eval_report.py                      # counts by difficulty, type, topic, status
    python scripts/eval_report.py --topics             # per-topic coverage table
    python scripts/eval_report.py --csv out.csv        # flat CSV export (nested fields as JSON)
    python scripts/eval_report.py --check              # validate difficulty scores and bands

Everything here is derived from evaluation/questions.jsonl, so no summary files are committed.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "evaluation" / "questions.jsonl"

WEIGHTS = {
    "cognitive_operation": 0.35,
    "retrieval_breadth": 0.25,
    "math_demand": 0.20,
    "ambiguity_inference": 0.20,
}
LEVELS = ("easy", "medium", "hard")


def load(path: Path = QUESTIONS) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def band(score: float) -> str:
    if score < 0.40:
        return "easy"
    if score < 0.70:
        return "medium"
    return "hard"


def table(title: str, rows: dict[str, Counter]) -> None:
    print(f"\n{title}")
    print(f"  {'':28} {'easy':>5} {'med':>5} {'hard':>5} {'total':>6}")
    for key in sorted(rows):
        c = rows[key]
        print(f"  {key:28} {c['easy']:5} {c['medium']:5} {c['hard']:5} {sum(c.values()):6}")


def summary(qs: list[dict]) -> None:
    diff = Counter(q["difficulty"] for q in qs)
    total = len(qs)
    print(f"{total} questions")
    for lvl in LEVELS:
        print(f"  {lvl:7} {diff[lvl]:4}  ({diff[lvl] / total:.1%})")

    by_type: dict[str, Counter] = defaultdict(Counter)
    for q in qs:
        by_type[q["question_type"]][q["difficulty"]] += 1
    table("By question type", by_type)

    for field in ("expected_behavior", "evidence_status", "answer_key_review_status"):
        print(f"\nBy {field}")
        for k, v in Counter(q[field] for q in qs).most_common():
            print(f"  {k:46} {v:4}")
    print(f"\nscore_eligible: {sum(q['score_eligible'] for q in qs)} / {total}")


def topics(qs: list[dict]) -> None:
    rows: dict[str, Counter] = defaultdict(Counter)
    names: dict[str, str] = {}
    for q in qs:
        key = q["topic_id"]
        names[key] = q["topic_name"]
        rows[key][q["difficulty"]] += 1
        rows[key]["boundary" if q["question_id"].startswith("B") else "core"] += 1
    print(f"{'topic':5} {'name':42} {'core':>4} {'bnd':>4} {'easy':>5} {'med':>5} {'hard':>5}")
    for key in sorted(rows):
        c = rows[key]
        print(f"{key:5} {names[key][:42]:42} {c['core']:4} {c['boundary']:4} "
              f"{c['easy']:5} {c['medium']:5} {c['hard']:5}")


def export_csv(qs: list[dict], out: Path) -> None:
    fields = list(dict.fromkeys(k for q in qs for k in q))
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for q in qs:
            w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                        for k, v in q.items()})
    print(f"wrote {len(qs)} rows to {out}")


def check(qs: list[dict]) -> int:
    problems = []
    ids = Counter(q["question_id"] for q in qs)
    problems += [f"duplicate id {i}" for i, n in ids.items() if n > 1]
    for q in qs:
        score = round(sum(WEIGHTS[k] * q[k] for k in WEIGHTS), 4)
        if abs(score - q["difficulty_score"]) > 1e-4:
            problems.append(f"{q['question_id']}: score {q['difficulty_score']} != recomputed {score}")
        if band(q["difficulty_score"]) != q["difficulty"]:
            problems.append(f"{q['question_id']}: label {q['difficulty']} != band {band(q['difficulty_score'])}")
    print("\n".join(problems) if problems else f"OK: {len(qs)} questions, scores and bands consistent")
    return 1 if problems else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--topics", action="store_true", help="per-topic coverage table")
    ap.add_argument("--csv", type=Path, help="export a flat CSV to this path")
    ap.add_argument("--check", action="store_true", help="validate scores, bands and ids")
    args = ap.parse_args()

    qs = load()
    if args.check:
        return check(qs)
    if args.csv:
        export_csv(qs, args.csv)
    elif args.topics:
        topics(qs)
    else:
        summary(qs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
