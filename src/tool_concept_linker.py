#!/usr/bin/env python3
"""
Phase 1.5 (issue #1): link each Tool to the Concept spans it implements, demonstrates or visualizes.

    python src/tool_concept_linker.py    # after src/tools_inventory.py

Candidates are teaching, retrieval-eligible spans in the tool's notebook. Each candidate is scored
from evidence, and the evidence is stored with the link:

  same_section       the span is in the tool's section                          +0.40
  ancestor_section   the span is in a parent section of the tool's section      +0.15
                     (+0.30 when it is the closest ancestor with any prose: the tool's own
                     section is only a heading, so its explanation lives in the parent)
  precedes_tool      the span comes 1-5 cells before the tool (closer = more)    up to +0.30
  explanation        the span is the tool's nearby explanation                  +0.20
  shared_identifier  the span names a function/class/method the tool uses       +0.35
  shared_topic       the span's section maps to one of the tool's topics        +0.05

A link with confidence >= 0.55 gets a relationship from the tool's role (implements, demonstrates,
visualizes) when the span is structurally the tool's explanation (same section, nearest explanation,
or closest parent section with prose); otherwise `supports`. A tool with no
such link keeps at most one `uncertain` link (>= 0.35). Below that, no link is made.
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
from assets import TopicMapper  # noqa: E402
from notebook_parser import CellRecord  # noqa: E402
from tools_inventory import Tool, load_cells, load_mapper, pct, write_jsonl  # noqa: E402

LINKS_JSONL = "tool_concept_links.jsonl"
LINK_THRESHOLD = 0.55
UNCERTAIN_THRESHOLD = 0.35
MAX_LINKS_PER_TOOL = 3
PRECEDE_WINDOW = 5

Relationship = Literal["implements", "demonstrates", "visualizes", "supports", "uncertain"]
ROLE_RELATIONSHIP = {
    "tool_implementation": "implements", "tool_function": "implements", "tool_demonstration": "demonstrates",
    "tool_workflow": "demonstrates", "visualization": "visualizes",
}
# Identifiers too common to count as evidence that a span talks about this tool
COMMON_IDENTIFIERS = {
    "print", "len", "range", "list", "dict", "set", "str", "int", "float", "type", "zip", "map", "sum", "max", "min",
    "head", "tail", "shape", "fit", "predict", "transform", "plot", "show", "values", "index", "columns", "data",
    "df", "x", "y", "np", "pd", "plt", "sns", "tf", "keras", "model", "self", "append", "copy", "mean", "array",
    "figure", "title", "xlabel", "ylabel", "legend", "format", "items", "keys", "train", "test", "score", "loc",
    "iloc", "reshape", "apply", "sort_values", "astype", "compile", "summary", "layers", "random", "abs", "round",
}
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


class Evidence(BaseModel):
    kind: str
    detail: str
    weight: float


class ToolConceptLink(BaseModel):
    link_id: str
    tool_id: str
    tool_cell_id: str
    span_id: str
    span_cell_id: str
    relationship: Relationship
    confidence: float
    evidence: list[Evidence]
    notebook_id: str
    tool_section_path: str
    span_section_path: str


def tool_identifiers(tool: Tool) -> set[str]:
    """Functions, classes and methods the tool calls or defines (not variables or common names)."""
    names = set(re.findall(r"\b([A-Za-z_]\w{2,})\s*\(", tool.code))      # calls and definitions
    names |= set(re.findall(r"\b(?:def|class)\s+([A-Za-z_]\w*)", tool.code))
    return {n for n in names if n.lower() not in COMMON_IDENTIFIERS and not n.startswith("__")}


def span_identifiers(text: str) -> set[str]:
    code_bits = " ".join(re.findall(r"`([^`]+)`", text))                 # inline code is the strongest signal
    words = set(IDENT_RE.findall(code_bits))
    words |= {w for w in IDENT_RE.findall(text) if "_" in w or re.search(r"[a-z][A-Z]", w)}   # snake/camel case
    return words


def score(tool: Tool, tool_pos: int, tool_section: tuple, span, span_pos: int, tool_idents: set[str],
          mapper: TopicMapper, prose_section: Optional[tuple] = None) -> list[Evidence]:
    ev: list[Evidence] = []
    span_section = tuple(span.section_path)
    if span_section == tool_section:
        ev.append(Evidence(kind="same_section", detail=" > ".join(span_section), weight=0.40))
    elif span_section and tool_section[:len(span_section)] == span_section:
        if span_section == prose_section:
            ev.append(Evidence(kind="ancestor_section", weight=0.30,
                               detail=" > ".join(span_section) + " (closest section with prose)"))
        else:
            ev.append(Evidence(kind="ancestor_section", detail=" > ".join(span_section), weight=0.15))
    gap = tool_pos - span_pos
    if 1 <= gap <= PRECEDE_WINDOW:
        ev.append(Evidence(kind="precedes_tool", detail=f"{gap} cell(s) before the tool",
                           weight=round(0.30 * (PRECEDE_WINDOW + 1 - gap) / PRECEDE_WINDOW, 2)))
    if span.span_id in tool.explanation_span_ids:
        ev.append(Evidence(kind="explanation", detail="nearest explanation of the tool", weight=0.20))
    shared = sorted(tool_idents & span_identifiers(span.content))
    if shared:
        ev.append(Evidence(kind="shared_identifier", detail=", ".join(shared[:5]), weight=0.35))
    # Topics only discriminate in notebooks that cover several; and an ambiguous span (mapped to every
    # topic of the notebook) says nothing.
    nb_topics = {tid for tid, _ in mapper.by_nb.get(tool.source.notebook_id, [])}
    span_topics = set(mapper.topics(tool.source.notebook_id, " ".join(span.section_path)))
    common = sorted(span_topics & set(tool.topic_ids))
    if len(nb_topics) > 1 and common and span_topics != nb_topics:
        ev.append(Evidence(kind="shared_topic", detail=", ".join(common), weight=0.05))
    return ev


def relationship_for(tool: Tool, ev: list[Evidence], confidence: float) -> Relationship:
    if confidence < LINK_THRESHOLD:
        return "uncertain"
    kinds = {e.kind for e in ev}
    closest_parent = any(e.kind == "ancestor_section" and e.weight >= 0.30 for e in ev)
    if "same_section" in kinds or "explanation" in kinds or closest_parent:
        return ROLE_RELATIONSHIP[tool.tool_type]
    return "supports"          # related by proximity/identifiers only, not by structure


def build_links(cells: list[CellRecord], tools: list[Tool], mapper: TopicMapper) -> list[ToolConceptLink]:
    by_nb: dict[str, list[CellRecord]] = defaultdict(list)
    for c in cells:
        by_nb[c.notebook_id].append(c)
    position = {c.cell_id: i for nb in by_nb.values() for i, c in enumerate(nb)}
    candidates: dict[str, list[tuple]] = {}
    for nb_id, nb_cells in by_nb.items():
        candidates[nb_id] = [(sp, position[c.cell_id], c.cell_id) for c in nb_cells if c.cell_type == "markdown"
                             for sp in c.spans if sp.content_role == "teaching" and sp.retrieval_eligible]
    links: list[ToolConceptLink] = []
    for tool in tools:
        nb_id = tool.source.notebook_id
        tool_cell = by_nb[nb_id][position[tool.cell_id]]
        tool_section = tuple(tool_cell.section_path)
        idents = tool_identifiers(tool)
        sections_with_prose = {tuple(sp.section_path) for sp, _, _ in candidates[nb_id]}
        prose_section = next((tool_section[:k] for k in range(len(tool_section), 0, -1)
                              if tool_section[:k] in sections_with_prose), None)
        scored = []
        for sp, pos, cell_id in candidates[nb_id]:
            ev = score(tool, position[tool.cell_id], tool_section, sp, pos, idents, mapper, prose_section)
            conf = round(min(1.0, sum(e.weight for e in ev)), 2)
            if conf >= UNCERTAIN_THRESHOLD and {e.kind for e in ev} - {"shared_topic"}:
                scored.append((conf, -abs(position[tool.cell_id] - pos), sp, cell_id, ev))
        scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
        strong = [s for s in scored if s[0] >= LINK_THRESHOLD][:MAX_LINKS_PER_TOOL]
        chosen = strong or scored[:1]
        for conf, _, sp, cell_id, ev in chosen:
            links.append(ToolConceptLink(
                link_id="", tool_id=tool.tool_id, tool_cell_id=tool.cell_id, span_id=sp.span_id,
                span_cell_id=cell_id, relationship=relationship_for(tool, ev, conf), confidence=conf, evidence=ev,
                notebook_id=nb_id, tool_section_path=" > ".join(tool_section),
                span_section_path=" > ".join(sp.section_path)))
    for n, link in enumerate(links, 1):
        link.link_id = f"LINK_{n:05d}"
    return links


def link_status(tools: list[Tool], links: list[ToolConceptLink]) -> dict[str, str]:
    by_tool: dict[str, list[ToolConceptLink]] = defaultdict(list)
    for link in links:
        by_tool[link.tool_id].append(link)
    status = {}
    for t in tools:
        ls = by_tool.get(t.tool_id, [])
        status[t.tool_id] = "unlinked" if not ls else "uncertain_only" if all(
            l.relationship == "uncertain" for l in ls) else "linked"
    return status


def links_report_section(tools: list[Tool], links: list[ToolConceptLink]) -> list[str]:
    status = link_status(tools, links)
    total = len(tools)
    sc = Counter(status.values())
    L = ["## Tool–Concept links", "",
         f"Links: {len(links):,} (threshold {LINK_THRESHOLD}; one `uncertain` link kept below it if ≥ "
         f"{UNCERTAIN_THRESHOLD}; at most {MAX_LINKS_PER_TOOL} per tool). Each link stores its evidence.", "",
         "| Link status | Tools | Share |", "|---|---:|---:|"]
    for k in ("linked", "uncertain_only", "unlinked"):
        L.append(f"| {k} | {sc[k]:,} | {pct(sc[k], total)} |")
    L += ["", "| Relationship | Links |", "|---|---:|"]
    rc = Counter(l.relationship for l in links)
    for k in ("implements", "demonstrates", "visualizes", "supports", "uncertain"):
        L.append(f"| {k} | {rc[k]:,} |")
    ec = Counter(e.kind for l in links for e in l.evidence)
    L += ["", "Evidence on links: " + ", ".join(f"{k} {v:,}" for k, v in ec.most_common()), "",
          "Link status by tool type:", "", "| Tool type | linked | uncertain_only | unlinked |", "|---|---:|---:|---:|"]
    by_type: dict[str, Counter] = defaultdict(Counter)
    for t in tools:
        by_type[t.tool_type][status[t.tool_id]] += 1
    for k, c in sorted(by_type.items()):
        L.append(f"| {k} | {c['linked']:,} | {c['uncertain_only']:,} | {c['unlinked']:,} |")
    return L + [""]


def run(processed_dir: Path = config.PROCESSED_DIR, quiet: bool = False, cells: Optional[list[CellRecord]] = None,
        tools: Optional[list[Tool]] = None) -> list[ToolConceptLink]:
    cells = cells if cells is not None else load_cells(processed_dir / config.CELLS_JSONL)
    if tools is None:
        tools = [Tool.model_validate_json(l) for l in
                 (processed_dir / "tools.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    links = build_links(cells, tools, load_mapper())
    write_jsonl(processed_dir / LINKS_JSONL, links)
    if not quiet:
        print(f"{len(links)} links: " + ", ".join(f"{k} {v}" for k, v in Counter(
            link_status(tools, links).values()).most_common()))
    return links


if __name__ == "__main__":
    run()
