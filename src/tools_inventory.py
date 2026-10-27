#!/usr/bin/env python3
"""
Phase 1.5 (issue #1): build the Tools inventory from the classified corpus.

    python src/tools_inventory.py        # after `python src/ingestion.py`

A Tool is a retrieval-eligible code cell whose content_role (PH1-ROLE-001) is one of
tool_implementation, tool_demonstration, tool_function, tool_workflow or visualization.
Every other code cell is left out, and the report says why (role or ineligibility).

Writes data/processed/tools.jsonl. Titles and descriptions come from function names, leading
comments and the nearest teaching span; nothing is generated. The notebook code is never run.
"""
from __future__ import annotations

import ast
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
from assets import (TopicMapper, code_lines, concepts_for, first_comment, first_sentences,  # noqa: E402
                    humanize, names_io, notebook_symbols, parseable, plain_text)
from content_role_classifier import CODE_ROLES, TOOL_ROLES  # noqa: E402
from notebook_parser import CellRecord  # noqa: E402

TOOLS_JSONL = "tools.jsonl"
TOOL_EXCLUSIONS_JSONL = "tool_exclusions.jsonl"
EXPLANATION_LOOKBACK = 3          # cells before a tool searched for its explanation
MIN_EXPLANATION_CHARS = 40

ToolType = Literal["tool_implementation", "tool_demonstration", "tool_function", "tool_workflow", "visualization"]

VERB = {
    "tool_implementation": "Implements", "tool_demonstration": "Demonstrates",
    "tool_function": "Defines a function for", "tool_workflow": "Runs a workflow for",
    "visualization": "Visualizes",
}


class Source(BaseModel):
    notebook_id: str
    notebook_title: str
    section_path: str
    cell_ids: list[str]
    cell_indexes: list[int]


class ToolQuality(BaseModel):
    is_self_contained: bool          # defines or imports everything it reads
    has_output: bool                 # has a non-error output
    has_error_output: bool
    has_nearby_explanation: bool     # a teaching span shortly before it, in the same section
    parses: bool                     # valid Python (shell/magic lines ignored)
    complexity: Literal["low", "medium", "high"]
    execution_status: str = "not_executed"
    suitable_for_answer: bool        # good enough to show as-is in an answer
    unsuitable_reasons: list[str]


class Tool(BaseModel):
    tool_id: str
    cell_id: str
    title: str
    description: str
    description_source: Literal["nearby_explanation", "leading_comment", "section"]
    tool_type: ToolType
    role_confidence: float
    role_method: str
    language: str = "python"
    libraries: list[str]
    code: str
    purpose: str
    inputs: list[str]
    outputs: list[str]
    output_roles: list[str]          # roles of the cell's outputs (result, log, dataframe_dump, ...)
    concepts: list[str]
    topic_ids: list[str]
    explanation_span_ids: list[str]
    source: Source
    quality: ToolQuality
    retrieval_eligible: bool = True
    created_at: str


class ToolExclusion(BaseModel):
    cell_id: str
    content_role: str
    reason: str


def source_for(cell: CellRecord) -> Source:
    return Source(notebook_id=cell.notebook_id, notebook_title=cell.notebook_title,
                  section_path=" > ".join(cell.section_path) or config.DEFAULT_SECTION,
                  cell_ids=[cell.cell_id], cell_indexes=[cell.cell_index])


def explanation_spans(nb_cells: list[CellRecord], i: int) -> list:
    """Teaching, retrieval-eligible spans just before code cell i, in the same section.

    Walks back up to EXPLANATION_LOOKBACK cells and stops at the first cell that holds one, so the
    explanation is the closest prose, not a paragraph from further up the section."""
    cell = nb_cells[i]
    for prev in reversed(nb_cells[max(0, i - EXPLANATION_LOOKBACK):i]):
        if prev.cell_type != "markdown":
            continue
        spans = [sp for sp in prev.spans
                 if sp.section_path == cell.section_path and sp.content_role == "teaching"
                 and sp.retrieval_eligible and len(plain_text(sp.content)) >= MIN_EXPLANATION_CHARS]
        if spans:
            return spans
    return []


def build_tools(cells: list[CellRecord], mapper: TopicMapper) -> tuple[list[Tool], list[ToolExclusion]]:
    by_nb: dict[str, list[CellRecord]] = defaultdict(list)
    for c in cells:
        by_nb[c.notebook_id].append(c)
    tools: list[Tool] = []
    excluded: list[ToolExclusion] = []
    for nb_cells in by_nb.values():
        trees = {c.cell_id: parseable(c.content) for c in nb_cells if c.cell_type == "code" and not c.is_empty}
        dependencies = notebook_symbols(list(trees.values()))
        for i, cell in enumerate(nb_cells):
            if cell.cell_type != "code":
                continue
            role = cell.content_role
            if role not in TOOL_ROLES:
                excluded.append(ToolExclusion(cell_id=cell.cell_id, content_role=role or "none",
                                              reason=f"content_role {role} is not a tool role"))
                continue
            if not cell.retrieval_eligible:
                why = ", ".join(cell.role_flags) or "not retrieval-eligible"
                excluded.append(ToolExclusion(cell_id=cell.cell_id, content_role=role,
                                              reason=f"tool role but not retrieval-eligible ({why})"))
                continue

            tree = trees.get(cell.cell_id)
            inputs, outputs, self_contained = names_io(tree, dependencies)
            spans = explanation_spans(nb_cells, i)
            explanation = first_sentences(spans[-1].content) if spans else ""
            comment = first_comment(cell.content)
            funcs = [n.name for n in (tree.body if tree else []) if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
            title = (humanize(funcs[0]).capitalize() if funcs else "") or comment or cell.section
            if explanation:
                description, desc_source = explanation, "nearby_explanation"
            elif comment:
                description, desc_source = comment, "leading_comment"
            else:
                description, desc_source = f"{VERB[role]} {cell.section}.", "section"

            n_lines = len(code_lines(cell.content))
            has_error = any(o.content_type == "error" for o in cell.outputs)
            has_output = any(o.content_type != "error" for o in cell.outputs)
            reasons = []
            if has_error:
                reasons.append("error output")
            if tree is None:
                reasons.append("does not parse")
            if n_lines <= 1 and not has_output:
                reasons.append("one line with no output")
            context = " ".join(cell.section_path + [title] + funcs + cell.libraries)
            tools.append(Tool(
                tool_id="",                                         # numbered below, in corpus order
                cell_id=cell.cell_id,
                title=title,
                description=description,
                description_source=desc_source,
                tool_type=role,
                role_confidence=cell.role_confidence,
                role_method=cell.role_method,
                libraries=cell.libraries,
                code=cell.content,
                purpose=f"{VERB[role]} {cell.section}",
                inputs=inputs,
                outputs=outputs,
                output_roles=sorted({o.output_role for o in cell.outputs if o.output_role}),
                concepts=concepts_for(cell),
                topic_ids=mapper.topics(cell.notebook_id, context),
                explanation_span_ids=[sp.span_id for sp in spans],
                source=source_for(cell),
                quality=ToolQuality(
                    is_self_contained=self_contained,
                    has_output=has_output,
                    has_error_output=has_error,
                    has_nearby_explanation=bool(spans),
                    parses=tree is not None,
                    complexity="low" if n_lines <= 5 else "medium" if n_lines <= 20 else "high",
                    suitable_for_answer=not reasons,
                    unsuitable_reasons=reasons,
                ),
                created_at=cell.ingested_at,
            ))
    for n, t in enumerate(tools, 1):
        t.tool_id = f"TOOL_{n:04d}"
    return tools, excluded


# ----------------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------------
def pct(n: int, total: int) -> str:
    return f"{n / total:.1%}" if total else "—"


def tools_report_section(tools: list[Tool], excluded: list[ToolExclusion], eligible_cells: int) -> list[str]:
    total = len(tools)
    q = [t.quality for t in tools]
    L = ["## Tools", "",
         f"- Retrieval-eligible tool cells in `cells.jsonl`: {eligible_cells:,}",
         f"- Tools written to `tools.jsonl`: {total:,}",
         f"- Code cells excluded: {len(excluded):,}", "",
         "### By tool type", "", "| Tool type | Tools | Share | Suitable for answer |", "|---|---:|---:|---:|"]
    by_type = Counter(t.tool_type for t in tools)
    for role in VERB:
        suit = sum(t.quality.suitable_for_answer for t in tools if t.tool_type == role)
        L.append(f"| {role} | {by_type[role]:,} | {pct(by_type[role], total)} | {suit:,} |")
    L += ["", "### Quality flags", "", "| Flag | Tools | Share |", "|---|---:|---:|"]
    for name in ("is_self_contained", "has_output", "has_error_output", "has_nearby_explanation", "parses",
                 "suitable_for_answer"):
        n = sum(getattr(x, name) for x in q)
        L.append(f"| {name} | {n:,} | {pct(n, total)} |")
    reasons = Counter(r for x in q for r in x.unsuitable_reasons)
    L += ["", "Not suitable for answer, by reason: "
          + (", ".join(f"{k} {v:,}" for k, v in reasons.most_common()) or "none"), "",
          "Complexity: " + ", ".join(f"{k} {v:,}" for k, v in Counter(x.complexity for x in q).most_common()),
          "", "Description source: " + ", ".join(
              f"{k} {v:,}" for k, v in Counter(t.description_source for t in tools).most_common()), ""]
    topics = Counter(len(t.topic_ids) for t in tools)
    L += [f"Topic IDs per tool: " + ", ".join(f"{k} topic(s): {v:,}" for k, v in sorted(topics.items())), ""]
    L += ["### Excluded code cells", "",
          "Every code cell that is not a Tool, by role. Ineligible tool-role cells are listed individually.", "",
          "| Content role | Cells |", "|---|---:|"]
    by_role = Counter(e.content_role for e in excluded)
    for role in CODE_ROLES:
        if by_role[role]:
            L.append(f"| {role} | {by_role[role]:,} |")
    odd = [e for e in excluded if e.content_role in TOOL_ROLES]
    if odd:
        L += ["", "| cell_id | Role | Reason |", "|---|---|---|"]
        L += [f"| {e.cell_id} | {e.content_role} | {e.reason} |" for e in odd]
    return L + [""]


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def load_cells(path: Path) -> list[CellRecord]:
    if not path.exists():
        raise SystemExit(f"{path} not found; run src/ingestion.py first")
    with path.open(encoding="utf-8") as f:
        return [CellRecord.model_validate_json(line) for line in f if line.strip()]


def load_mapper() -> TopicMapper:
    catalog = json.loads(config.TOPIC_CATALOG.read_text(encoding="utf-8")) if config.TOPIC_CATALOG.exists() else {}
    return TopicMapper(catalog)


def write_jsonl(path: Path, records: list[BaseModel]) -> None:
    path.write_text("".join(json.dumps(r.model_dump(), ensure_ascii=False) + "\n" for r in records),
                    encoding="utf-8", newline="\n")


def run(processed_dir: Path = config.PROCESSED_DIR, quiet: bool = False,
        cells: Optional[list[CellRecord]] = None) -> tuple[list[Tool], list[ToolExclusion]]:
    cells = cells if cells is not None else load_cells(processed_dir / config.CELLS_JSONL)
    tools, excluded = build_tools(cells, load_mapper())
    write_jsonl(processed_dir / TOOLS_JSONL, tools)
    write_jsonl(processed_dir / TOOL_EXCLUSIONS_JSONL, excluded)
    if not quiet:
        print(f"{len(tools)} tools: " + ", ".join(f"{k} {v}" for k, v in Counter(t.tool_type for t in tools).most_common()))
        print(f"  suitable for answer: {sum(t.quality.suitable_for_answer for t in tools)}; excluded cells: {len(excluded)}")
    return tools, excluded


if __name__ == "__main__":
    run()
