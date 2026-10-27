#!/usr/bin/env python3
"""
Phase 1 ingestion: parse every notebook into structured records and validate the result.

Usage (from the project root):
    python src/ingestion.py                     # data/raw/notebooks -> data/processed
    python src/ingestion.py --raw DIR --out DIR

Writes (in --out):
    cells.jsonl             one record per cell, in notebook and cell order (input for chunking)
    notebooks.jsonl         one record per notebook: counts, outline, libraries, warnings
    corpus_inventory.csv    one row per notebook
    topic_candidates.csv    deterministic topic candidates from headings and titles
    ingestion_report.md     summary, acceptance checks, warnings, manual-review sample

The output is deterministic: running it twice on the same notebooks gives identical files.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
from notebook_parser import CellRecord, NotebookRecord, parse_notebook  # noqa: E402

# ----------------------------------------------------------------------------
# Topic candidates
# ----------------------------------------------------------------------------
GENERIC = {
    "content", "contents", "agenda", "introduction", "intro", "conclusion", "conclusions", "summary",
    "recap", "example", "examples", "observation", "observations", "solution", "solutions", "problem",
    "problems", "note", "notes", "quiz", "code", "question", "questions", "answer", "choices", "output",
    "result", "results", "insights", "insight", "approach", "steps", "step", "implementation", "case",
    "task", "tasks", "exercise", "homework", "references", "reference", "import libraries",
    "importing libraries", "imports", "dataset", "data", "business context", "problem statement",
    "lets begin", "let's begin", "first try", "second try", "third try", "visualization", "plot",
    "explanation", "intuition", "overview", "definition", "idea", "key takeaways", "takeaways",
}
LEADING_NOISE_RE = re.compile(
    r"^((\d+(\.\d+)*|[ivx]+)[.)]\s*|q\d*[.:)]\s*|step\s*\d+\s*[:.)-]?\s*|case\s*\d+\s*[:.)-]?\s*|part\s*\d+\s*[:.)-]?\s*)",
    re.I,
)
WHAT_IS_RE = re.compile(r"^(what|who)\s+(is|are)\s+(an?\s+|the\s+)?(.+)$", re.I)
QUESTION_START_RE = re.compile(
    r"^(how|why|when|where|which|can|could|do|does|did|is|are|should|will|would|what|let'?s|lets)\b", re.I
)
TITLE_SUFFIX_RE = re.compile(r"\s+\d+$")
IMPLEMENTATION_OF_RE = re.compile(r"^(?:(?:scikit[- ]?learn|sklearn|python|code)\s+)?impl[ei]m\w*\s+of\s+(.+)$", re.I)
PROCEDURAL_RE = re.compile(
    r"walk ?th?r?ough|impl[ei]m\w*|section ends|\b(load|read|download|fetch|import)\w*\s+(the\s+)?"
    r"(data|dataset|libraries|packages|model)\b|interview questions?|key insights?|case study|use ?case|"
    r"\bapplications?\b|data description|(build|train)\w*\s+the\s+model|get the prediction|"
    r"prediction summary|^task\b|^new section|^end of|^recap\b|^summary\b",
    re.I,
)
STOPWORDS = {"and", "or", "of", "the", "a", "an", "in", "for", "to", "with", "based", "using", "vs"}


def candidate_key(text: str) -> tuple[str, str] | None:
    """(normalized key, display name) for a heading, or None if it is not topic-like."""
    t = LEADING_NOISE_RE.sub("", text.strip())
    impl = IMPLEMENTATION_OF_RE.match(t)
    if impl:
        t = impl.group(1)
    if PROCEDURAL_RE.search(t):
        return None
    m = WHAT_IS_RE.match(t.rstrip(" ?"))
    if m:
        t = m.group(4)
    elif t.endswith("?") or QUESTION_START_RE.match(t):
        return None
    t = t.strip(" ?!.:;,-'\"")
    key = re.sub(r"[^a-z0-9+#/ ]+", " ", t.lower())
    key = re.sub(r"\s+", " ", key).strip()
    if not key or key in GENERIC or len(key) < 3 or len(key) > 60:
        return None
    if len(key.split()) > 6 or key.isdigit():
        return None
    return key, t


def content_words(text: str) -> set[str]:
    words = re.sub(r"[^a-z0-9 ]+", " ", text.lower()).split()
    return {w.rstrip("s") for w in words if w not in STOPWORDS and len(w) > 1}


def build_topic_candidates(notebooks: list[NotebookRecord], cells: list[CellRecord], catalog: dict):
    nb_topics: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for t in catalog.get("topics", []):
        for nb in t["notebook_ids"]:
            nb_topics[nb].append((t["topic_id"], t["topic_name"]))

    variants: dict[str, Counter] = defaultdict(Counter)
    heading_cells: dict[str, set[str]] = defaultdict(set)
    notebooks_for: dict[str, set[str]] = defaultdict(set)
    for nb in notebooks:
        title_key = candidate_key(TITLE_SUFFIX_RE.sub("", nb.notebook_title))
        if title_key:
            variants[title_key[0]][title_key[1]] += 1
            notebooks_for[title_key[0]].add(nb.notebook_id)
        for h in nb.outline:
            ck = candidate_key(h["text"])
            if ck:
                variants[ck[0]][ck[1]] += 1
                notebooks_for[ck[0]].add(nb.notebook_id)
                heading_cells[ck[0]].add(f"{nb.notebook_id}_cell_{h['cell_index']:03d}")

    # Evidence: non-empty cells whose section path contains the candidate.
    evidence: dict[str, set[str]] = defaultdict(set)
    per_notebook: dict[str, Counter] = defaultdict(Counter)
    for c in cells:
        if c.is_empty:
            continue
        keys = {ck[0] for ck in map(candidate_key, c.section_path) if ck}
        for k in keys & variants.keys():
            evidence[k].add(c.cell_id)
            per_notebook[c.notebook_id][k] += 1

    rows = []
    for key, names in variants.items():
        n_cells = len(evidence[key])
        nbs = sorted(notebooks_for[key])
        if n_cells < 3 and len(nbs) < 2:
            continue                                   # one-off headings with almost no content
        ranked = sorted(names.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))
        name = ranked[0][0]
        aliases = [v for v, _ in ranked[1:6] if v.lower() != name.lower()]
        parents = Counter(tn for nb in nbs for tn in nb_topics.get(nb, []))
        words = content_words(key)
        parent = min(
            parents.items(),
            key=lambda kv: (-len(words & content_words(kv[0][1])), -kv[1], kv[0][0]),
        )[0][1] if parents else ""
        rows.append({
            "key": key, "topic_name": name, "aliases": "|".join(aliases), "parent_topic": parent,
            "source_notebook_ids": "|".join(nbs),
            "source_cell_ids": "|".join(sorted(heading_cells[key])[:15]),
            "evidence_count": n_cells,
        })
    rows.sort(key=lambda r: (-r["evidence_count"], r["key"]))
    for i, r in enumerate(rows, 1):
        r["topic_candidate_id"] = f"TC{i:03d}"
        r["proposed_importance"] = ""                 # importance scoring is a later phase
        r["proposed_difficulty"] = ""
        r["review_status"] = "pending_review"
    by_key = {r["key"]: r for r in rows}
    top_per_notebook = {
        nb: [by_key[k]["topic_name"] for k, _ in sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))
             if k in by_key][:6]
        for nb, cnt in per_notebook.items()
    }
    return rows, top_per_notebook


# ----------------------------------------------------------------------------
# Writers
# ----------------------------------------------------------------------------
def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def to_jsonl(records) -> str:
    return "".join(json.dumps(r.model_dump(), ensure_ascii=False) + "\n" for r in records)


def to_csv(header: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


INVENTORY_HEADER = [
    "notebook_id", "file_name", "notebook_title", "total_cells", "markdown_cells", "code_cells",
    "empty_cells", "math_cells", "code_with_output_cells", "plot_cells", "table_cells", "image_ref_cells",
    "heading_count", "section_coverage", "libraries", "catalog_topics", "detected_topic_candidates",
    "parse_status", "notes",
]
CANDIDATE_HEADER = [
    "topic_candidate_id", "topic_name", "aliases", "parent_topic", "source_notebook_ids",
    "source_cell_ids", "evidence_count", "proposed_importance", "proposed_difficulty", "review_status",
]


def inventory_rows(notebooks, catalog, top_candidates):
    names = defaultdict(list)
    for t in catalog.get("topics", []):
        for nb in t["notebook_ids"]:
            names[nb].append(t["topic_id"])
    rows = []
    for nb in notebooks:
        rows.append([
            nb.notebook_id, nb.file_name, nb.notebook_title, nb.total_cells, nb.markdown_cells,
            nb.code_cells, nb.empty_cells, nb.math_cells, nb.code_with_output_cells, nb.plot_cells,
            nb.table_cells, nb.image_ref_cells, nb.heading_count, nb.section_coverage,
            "|".join(nb.libraries), "|".join(names.get(nb.notebook_id, [])),
            "|".join(top_candidates.get(nb.notebook_id, [])), nb.parse_status,
            "; ".join(nb.warnings) if nb.warnings else "No parsing issues",
        ])
    return rows


# ----------------------------------------------------------------------------
# Quality checks and report
# ----------------------------------------------------------------------------
def source_cell_counts(raw_dir: Path) -> dict[str, int]:
    counts = {}
    for path in sorted(raw_dir.glob("*.ipynb")):
        try:
            counts[path.name] = len(json.loads(path.read_text(encoding="utf-8")).get("cells", []))
        except Exception:
            counts[path.name] = -1
    return counts


def acceptance_checks(notebooks, cells, raw_dir: Path, catalog) -> list[tuple[str, bool, str]]:
    ok_nbs = [n for n in notebooks if n.parse_status == "success"]
    by_file = Counter(c.file_name for c in cells)
    src_counts = source_cell_counts(raw_dir)
    mismatched = [f for f, n in src_counts.items() if n >= 0 and by_file.get(f, 0) != n]
    empty_nbs = [n.notebook_id for n in ok_nbs if "no_content" in n.warnings]
    missing_meta = [c.cell_id for c in cells
                    if not (c.notebook_id and c.cell_id and c.cell_type and c.section and c.source_hash)]
    non_empty = [c for c in cells if not c.is_empty]
    covered = sum(c.section != config.DEFAULT_SECTION for c in non_empty)
    coverage = covered / len(non_empty) if non_empty else 0.0
    code_ok = all(c.contains_code == (c.cell_type == "code") for c in cells)
    outputs_ok = all(not c.outputs for c in cells if c.cell_type != "code")
    math_cells = sum(c.contains_math for c in cells)
    catalog_nbs = {nb for t in catalog.get("topics", []) for nb in t["notebook_ids"]}
    parsed_ids = {n.notebook_id for n in notebooks}
    dup_files = [h for h, n in Counter(n.file_sha256 for n in notebooks).items() if n > 1]
    return [
        ("Notebook coverage", len(notebooks) == config.EXPECTED_NOTEBOOKS,
         f"{len(notebooks)} of {config.EXPECTED_NOTEBOOKS} expected notebooks found"),
        ("Parse success rate", len(ok_nbs) == len(notebooks),
         f"{len(ok_nbs)}/{len(notebooks)} parsed" +
         "".join(f"; {n.notebook_id} failed: {n.parse_error}" for n in notebooks if n.parse_status != "success")),
        ("Cell preservation", not mismatched,
         "every notebook's cell count matches its source" if not mismatched else f"mismatch: {mismatched}"),
        ("Content integrity", not empty_nbs, "no notebook without content" if not empty_nbs else f"empty: {empty_nbs}"),
        ("Metadata completeness", not missing_meta,
         "every cell has notebook ID, cell ID, index, type, section and source hash"
         if not missing_meta else f"{len(missing_meta)} cells missing metadata"),
        ("Section coverage", coverage >= config.MIN_SECTION_COVERAGE,
         f"{coverage:.1%} of non-empty cells have a real section (target ≥ {config.MIN_SECTION_COVERAGE:.0%})"),
        ("Math detection", math_cells > 0, f"{math_cells} cells flagged as containing math"),
        ("Code detection", code_ok, "every code cell is classified as code, and only code cells"),
        ("Output preservation", outputs_ok, "outputs stored in `outputs`, never merged into `content`"),
        ("Inventory", parsed_ids >= catalog_nbs and len(parsed_ids) == len(notebooks),
         f"inventory covers {len(parsed_ids)} notebooks; all {len(catalog_nbs)} catalog notebooks present"),
        ("No duplicate notebooks", not dup_files, "all notebook files are distinct" if not dup_files
         else f"{len(dup_files)} duplicate file hashes"),
    ]


def review_sample(notebooks: list[NotebookRecord]) -> list[tuple[str, str]]:
    ok = [n for n in notebooks if n.parse_status == "success"]
    if not ok:
        return []
    picks: list[tuple[str, str]] = []

    def pick(reason, key, reverse=True):
        for n in sorted(ok, key=lambda n: (key(n), n.notebook_id), reverse=reverse):
            if n.notebook_id not in {p for p, _ in picks}:
                picks.append((n.notebook_id, reason))
                return

    pick("largest (most cells)", lambda n: n.total_cells)
    pick("smallest (fewest cells)", lambda n: n.total_cells, reverse=False)
    pick("most math cells", lambda n: n.math_cells)
    pick("most code cells", lambda n: n.code_cells)
    pick("most plot cells", lambda n: n.plot_cells)
    pick("most table cells", lambda n: n.table_cells)
    pick("most image references (content in images)", lambda n: n.image_ref_cells)
    pick("most outputs", lambda n: n.code_with_output_cells)
    pick("fewest headings per cell", lambda n: n.heading_count / max(n.total_cells, 1), reverse=False)
    pick("most warnings (unusual formatting)", lambda n: len(n.warnings))
    return picks


def build_report(notebooks, cells, checks, candidates, fingerprint) -> str:
    ok = [n for n in notebooks if n.parse_status == "success"]
    failed = [n for n in notebooks if n.parse_status != "success"]
    t = Counter()
    for c in cells:
        t["cells"] += 1
        t[c.cell_type] += 1
        t["empty"] += c.is_empty
        t["short"] += c.is_short
        t["math"] += c.contains_math
        t["latex"] += c.contains_latex
        t["formula_heavy"] += c.formula_heavy
        t["code_out"] += c.cell_type == "code" and c.has_output
        t["plot"] += c.contains_plot
        t["table"] += c.contains_table or any(o.content_type == "table" for o in c.outputs)
        t["image"] += c.contains_image
        t["instructor"] += c.contains_instructor_note
        t["mcq"] += c.contains_mcq
        t["error"] += "error_output" in c.warnings
        t["unbalanced"] += "unbalanced_math_delimiters" in c.warnings
        t["truncated"] += "output_truncated" in c.warnings
    content_dupes = Counter(c.source_hash for c in cells if c.content_length_chars >= 200)
    dupe_cells = sum(n for n in content_dupes.values() if n > 1)
    readers = Counter(n.reader for n in ok)

    L = ["# Ingestion Report", ""]
    L += [f"Pipeline `{config.PIPELINE_VERSION}` · reader: "
          + ", ".join(f"{k} ({v})" for k, v in sorted(readers.items()))
          + f" · corpus fingerprint `{fingerprint[:16]}`", ""]
    L += ["## Summary", "",
          f"- Total notebooks: {len(notebooks)}",
          f"- Successfully parsed: {len(ok)}",
          f"- Failed: {len(failed)}",
          f"- Total cells: {t['cells']:,}",
          f"- Markdown cells: {t['markdown']:,}",
          f"- Code cells: {t['code']:,}",
          f"- Raw cells: {t['raw']:,}",
          f"- Empty cells (kept, flagged): {t['empty']:,}",
          f"- Short cells (< {config.SHORT_CELL_CHARS} chars, flagged): {t['short']:,}",
          f"- Math-containing cells: {t['math']:,} (LaTeX: {t['latex']:,}; formula-heavy: {t['formula_heavy']:,})",
          f"- Code cells with outputs: {t['code_out']:,}",
          f"- Plot cells: {t['plot']:,}",
          f"- Table cells (markdown or table output): {t['table']:,}",
          f"- Cells referencing images: {t['image']:,}",
          f"- Cells with instructor notes (kept, flagged): {t['instructor']:,}",
          f"- MCQ cells (kept, flagged): {t['mcq']:,}",
          f"- Topic candidates: {len(candidates)}",
          ""]
    L += ["## Acceptance checks", "", "| Check | Result | Detail |", "|---|---|---|"]
    for name, passed, detail in checks:
        L.append(f"| {name} | {'PASS' if passed else 'FAIL'} | {detail} |")
    L += ["| Reproducibility | see tests | `tests/test_ingestion.py` runs the pipeline twice and compares output |",
          "| Manual QA | pending | inspect the sample below |", ""]

    L += ["## Warnings", ""]
    L.append(f"- Cells with unbalanced `$` delimiters (possible broken LaTeX or currency): {t['unbalanced']}")
    L.append(f"- Cells with error outputs: {t['error']}")
    L.append(f"- Cells with truncated outputs (> {config.MAX_OUTPUT_CHARS} chars): {t['truncated']}")
    L.append(f"- Long cells (≥ 200 chars) whose source also appears elsewhere: {dupe_cells}")
    L.append(f"- Cells referencing images: {t['image']}. Text inside images (diagrams, formulas) is not "
             "extracted; check images before marking content as absent.")
    L.append("")
    flagged = [n for n in notebooks if n.warnings]
    if flagged:
        L += ["| Notebook | Title | Warnings |", "|---|---|---|"]
        for n in flagged:
            L.append(f"| {n.notebook_id} | {n.notebook_title} | {', '.join(n.warnings)} |")
        L.append("")
    L += ["## Failures", ""]
    L += [f"- {n.notebook_id} ({n.file_name}): {n.parse_error}" for n in failed] or ["- None"]
    L.append("")
    L += ["## Manual review sample", "",
          "Inspect each: readable markdown, intact code indentation, preserved formulas, sensible sections, "
          "outputs separate from content, nothing important missing, cell order preserved, metadata "
          "pointing to the right notebook and cell.", "",
          "| Notebook | Why selected | Status |", "|---|---|---|"]
    by_id = {n.notebook_id: n for n in notebooks}
    for nb_id, reason in review_sample(notebooks):
        L.append(f"| {nb_id} — {by_id[nb_id].notebook_title} | {reason} | REVIEW |")
    L.append("")
    return "\n".join(L)


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def run(raw_dir: Path, out_dir: Path, quiet: bool = False) -> dict:
    paths = sorted(p for p in raw_dir.glob("*.ipynb") if not p.name.startswith("."))
    if not paths:
        raise SystemExit(f"no .ipynb files found in {raw_dir}")
    catalog = json.loads(config.TOPIC_CATALOG.read_text(encoding="utf-8")) if config.TOPIC_CATALOG.exists() else {}

    notebooks: list[NotebookRecord] = []
    cells: list[CellRecord] = []
    for path in paths:
        nb, nb_cells = parse_notebook(path)
        notebooks.append(nb)
        cells.extend(nb_cells)
        if not quiet:
            status = "ok" if nb.parse_status == "success" else f"FAILED ({nb.parse_error})"
            print(f"{nb.notebook_id:7} {nb.total_cells:4} cells  {status}")
    notebooks.sort(key=lambda n: n.notebook_id)
    order = {n.notebook_id: i for i, n in enumerate(notebooks)}
    cells.sort(key=lambda c: (order[c.notebook_id], c.cell_index))

    fingerprint = hashlib.sha256("".join(n.file_sha256 for n in notebooks).encode()).hexdigest()
    candidates, top_candidates = build_topic_candidates(notebooks, cells, catalog)
    checks = acceptance_checks(notebooks, cells, raw_dir, catalog)

    out_dir.mkdir(parents=True, exist_ok=True)
    write_text(out_dir / config.CELLS_JSONL, to_jsonl(cells))
    write_text(out_dir / config.NOTEBOOKS_JSONL, to_jsonl(notebooks))
    write_text(out_dir / config.INVENTORY_CSV, to_csv(INVENTORY_HEADER, inventory_rows(notebooks, catalog, top_candidates)))
    write_text(out_dir / config.TOPIC_CANDIDATES_CSV,
               to_csv(CANDIDATE_HEADER, [[r[h] for h in CANDIDATE_HEADER] for r in candidates]))
    write_text(out_dir / config.REPORT_MD, build_report(notebooks, cells, checks, candidates, fingerprint))

    failed_checks = [name for name, passed, _ in checks if not passed]
    if not quiet:
        print(f"\n{len(notebooks)} notebooks, {len(cells)} cells, {len(candidates)} topic candidates -> {out_dir}")
        print("acceptance checks: " + ("all passed" if not failed_checks else "FAILED " + ", ".join(failed_checks)))
    return {"notebooks": notebooks, "cells": cells, "checks": checks, "failed_checks": failed_checks}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=config.RAW_NOTEBOOKS_DIR, help="folder with .ipynb files")
    ap.add_argument("--out", type=Path, default=config.PROCESSED_DIR, help="output folder")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    result = run(args.raw, args.out, quiet=args.quiet)
    return 1 if result["failed_checks"] else 0


if __name__ == "__main__":
    sys.exit(main())
