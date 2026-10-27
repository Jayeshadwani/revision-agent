#!/usr/bin/env python3
"""
PH2-CHUNK-001 (issue #3): build Concept, Tool and Resource chunks.

    python src/chunk_builder.py      # after `python src/ingestion.py` and `python src/assets.py`

Reads data/processed/: cells.jsonl (spans with content roles), tools.jsonl, resources.jsonl,
tool_concept_links.jsonl. Writes:
    concept_chunks.jsonl    teaching spans, merged per section (CON_000001 ...)
    tool_chunks.jsonl       one per answer-suitable Tool (TOOLCHUNK_000001 ...)
    resource_chunks.jsonl   one per attachable Resource (RESCHUNK_000001 ...)
    chunk_exclusions.jsonl  every eligible-looking record that did not become a chunk, with a reason
    chunking_report.md

Source records are never modified or deleted. IDs are numbered in corpus order, so a rerun on the
same inputs gives identical files.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
from assets import HTML_IMG_TAG_RE, MD_IMG_RE, code_lines  # noqa: E402
from chunking import (OVERSIZED_TOKENS, TEXT_MAX_TOKENS, TINY_TOKENS, Unit, clean_for_content,  # noqa: E402
                      common_prefix, content_tokens, estimate_tokens, group_units, kept_ranges, split_range,
                      support_ranges)
from notebook_parser import CellRecord  # noqa: E402
from resources_inventory import Resource  # noqa: E402
from tool_concept_linker import ToolConceptLink  # noqa: E402
from tools_inventory import Tool, load_cells  # noqa: E402

CONCEPT_CHUNKS = "concept_chunks.jsonl"
TOOL_CHUNKS = "tool_chunks.jsonl"
RESOURCE_CHUNKS = "resource_chunks.jsonl"
CHUNK_EXCLUSIONS = "chunk_exclusions.jsonl"
CHUNKING_REPORT = "chunking_report.md"

PRIMARY_RELATIONSHIPS = ("implements", "demonstrates", "visualizes")   # attached automatically
SECONDARY_RELATIONSHIPS = ("supports",)                               # stored, not attached
EXCLUDED_SPAN_ROLES = ("instructor_note", "quiz", "rhetorical_question", "agenda", "business_context",
                       "preamble", "unknown")
EXCLUDED_CODE_ROLES = ("data_loading", "environment_setup", "debugging", "non_teaching", "unknown")


# ----------------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------------
class SourceSegment(BaseModel):
    span_id: str
    char_start: int              # offsets into the span's content
    char_end: int
    overlap_chars: int = 0       # leading characters repeated from the previous chunk


class ConceptQuality(BaseModel):
    is_merged: bool
    is_split: bool
    has_overlap: bool
    is_duplicate: bool
    is_oversized: bool
    is_tiny: bool
    stripped_support_content: bool   # embedded instructor note / quiz text was removed


class ConceptChunk(BaseModel):
    chunk_id: str
    chunk_type: Literal["concept"] = "concept"
    notebook_id: str
    notebook_title: str
    section_path: list[str]          # deepest section shared by all source spans
    section_paths: list[list[str]]   # every section the source spans come from
    breadcrumb: str
    source_span_ids: list[str]
    source_cell_ids: list[int]
    source_segments: list[SourceSegment]
    raw_text: str                    # exact text of the source segments, joined by blank lines
    content: str                     # breadcrumb + raw_text with images as [Image RES_x] and HTML styling removed
    token_count: int
    content_roles: list[str]
    contains_math: bool
    contains_latex: bool
    contains_table: bool
    contains_list: bool
    contains_code: bool
    image_resource_ids: list[str]    # images referenced inside the text
    linked_tool_ids: list[str]       # implements / demonstrates / visualizes, answer-suitable tools
    linked_tool_chunk_ids: list[str]
    secondary_tool_ids: list[str]    # supports
    uncertain_tool_ids: list[str]    # stored, never attached automatically
    linked_resource_ids: list[str]
    linked_resource_chunk_ids: list[str]
    duplicate_of: Optional[str] = None
    retrieval_eligible: bool
    quality_flags: ConceptQuality


class ToolQualityFlags(BaseModel):
    is_self_contained: bool
    has_output: bool
    has_nearby_explanation: bool
    is_answer_suitable: bool
    is_duplicate: bool


class ToolChunk(BaseModel):
    chunk_id: str
    chunk_type: Literal["tool"] = "tool"
    tool_id: str
    notebook_id: str
    notebook_title: str
    section_path: list[str]
    breadcrumb: str
    source_cell_id: str
    source_cell_ids: list[int]
    tool_type: str
    title: str
    purpose: str
    description: str
    language: str
    libraries: list[str]
    code: str
    inputs: list[str]
    outputs: list[str]
    content: str
    token_count: int
    linked_concept_chunk_ids: list[str]      # implements / demonstrates / visualizes
    secondary_concept_chunk_ids: list[str]   # supports
    uncertain_concept_chunk_ids: list[str]
    linked_resource_ids: list[str]           # e.g. the plot this tool produced
    duplicate_of: Optional[str] = None       # same code copied (other notebook or same section): not eligible
    repeats_code_of: Optional[str] = None    # same code in a new context (re-run, or a short snippet): eligible
    retrieval_eligible: bool
    quality_flags: ToolQualityFlags


class ResourceQualityFlags(BaseModel):
    is_meaningful: bool
    is_decorative: bool
    requires_vision_model: bool


class ResourceChunk(BaseModel):
    chunk_id: str
    chunk_type: Literal["resource"] = "resource"
    resource_id: str
    notebook_id: str
    notebook_title: str
    section_path: list[str]
    breadcrumb: str
    source_cell_ids: list[int]
    source_span_id: Optional[str]
    resource_type: str
    availability: str
    title: str
    description: str
    caption: str
    caption_source: str
    image_url: Optional[str]
    local_path: Optional[str]
    vision_status: Literal["pending", "done"]
    content: str
    token_count: int
    linked_concept_chunk_ids: list[str]
    linked_tool_ids: list[str]
    linked_tool_chunk_ids: list[str]
    attachable: bool                 # may be shown next to its linked concept/tool chunks
    retrieval_eligible: bool         # retrievable on its own: only once vision_status is done
    quality_flags: ResourceQualityFlags


class Exclusion(BaseModel):
    record_type: Literal["span", "tool", "resource"]
    record_id: str
    reason: str


# ----------------------------------------------------------------------------
# Text helpers
# ----------------------------------------------------------------------------
def image_markup(text: str) -> list[tuple[int, int]]:
    """(start, end) of every markdown/HTML image in text, in order."""
    found = [(m.start(), m.end()) for m in MD_IMG_RE.finditer(text)]
    found += [(m.start(), m.end()) for m in HTML_IMG_TAG_RE.finditer(text) if re.search(r"\bsrc\s*=", m.group(0))]
    return sorted(found)


def norm_hash(text: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", text).strip().lower().encode()).hexdigest()[:16]


SUPPORT_HEADING_RE = re.compile(r"^\W*(quiz|mcq|msq)\b|^\W*(agenda|content|contents|table of contents|"
                                r"topics covered|lecture agenda|agenda of the lecture)\W*$", re.I)


def breadcrumb(title: str, path: list[str]) -> str:
    """Breadcrumb for the chunk text. Headings of quiz questions and agenda containers that authors
    placed above lesson sections ("Quiz 1: ... > 3. Training Neural Network") are left out of the
    breadcrumb; `section_path` keeps the full structural path."""
    shown = [p for p in path if not SUPPORT_HEADING_RE.search(p)] or path
    return f"Notebook: {title}\nSection path: {' > '.join(shown) if shown else title}"


# ----------------------------------------------------------------------------
# Concept chunks
# ----------------------------------------------------------------------------
def concept_units(cell: CellRecord, sp, image_ids: dict) -> tuple[list[Unit], list[tuple]]:
    """Units for one eligible teaching span: its kept ranges (support content stripped), each split
    to the token budget. Returns (units, stripped ranges)."""
    flags = list(sp.role_flags or [])
    stripped = support_ranges(sp.content, flags)
    units: list[Unit] = []
    for k_start, k_end in kept_ranges(sp.content, flags):
        pieces = split_range(sp.content, k_start, k_end, TEXT_MAX_TOKENS, allow_overlap=sp.contains_math)
        for n, pc in enumerate(pieces):
            text = sp.content[pc.start:pc.end]
            units.append(Unit(span_id=sp.span_id, cell_index=cell.cell_index, section_path=tuple(sp.section_path),
                              text=text, char_start=pc.start, char_end=pc.end, tokens=content_tokens(text),
                              overlap_chars=pc.overlap_chars, split_index=n if len(pieces) > 1 else None,
                              stripped=stripped))
    return units, stripped


def with_image_placeholders(cell: CellRecord, sp, unit: Unit, image_ids: dict) -> tuple[str, list[str]]:
    """The unit's text with each image replaced by [Image RES_xxxx]."""
    cell_images = image_markup(cell.content)
    index_of = {start: n for n, (start, _) in enumerate(cell_images)}
    base = sp.char_start + unit.char_start
    text, out, pos, ids = unit.text, [], 0, []
    for s, e in image_markup(text):
        n = index_of.get(base + s)
        rid = image_ids.get((cell.cell_id, n)) if n is not None else None
        out.append(text[pos:s])
        out.append(f"[Image {rid}]" if rid else "[Image]")
        if rid:
            ids.append(rid)
        pos = e
    out.append(text[pos:])
    return "".join(out), ids


def build_concept_chunks(cells: list[CellRecord], image_ids: dict) -> tuple[list[ConceptChunk], list[Exclusion]]:
    chunks: list[ConceptChunk] = []
    exclusions: list[Exclusion] = []
    by_nb: dict[str, list[CellRecord]] = defaultdict(list)
    for c in cells:
        by_nb[c.notebook_id].append(c)
    for nb_id, nb_cells in by_nb.items():
        units: list[Unit] = []
        span_lookup = {}
        for cell in nb_cells:
            if cell.cell_type != "markdown":
                continue
            for sp in cell.spans:
                if sp.content_role != "teaching" or not sp.retrieval_eligible:
                    continue
                span_lookup[sp.span_id] = (cell, sp)
                u, _ = concept_units(cell, sp, image_ids)
                if not u:
                    exclusions.append(Exclusion(record_type="span", record_id=sp.span_id,
                                                reason="only embedded instructor-note/quiz text after stripping"))
                units += u
        for g in group_units(units):
            title = nb_cells[0].notebook_title
            paths = g.sections
            path = list(common_prefix(paths)) or list(paths[0])
            raw_parts, content_parts, image_rids, segments = [], [], [], []
            for u in g.units:
                cell, sp = span_lookup[u.span_id]
                raw_parts.append(u.text.strip("\n"))
                text, rids = with_image_placeholders(cell, sp, u, image_ids)
                content_parts.append(clean_for_content(text))
                image_rids += rids
                segments.append(SourceSegment(span_id=u.span_id, char_start=u.char_start, char_end=u.char_end,
                                              overlap_chars=u.overlap_chars))
            crumb = breadcrumb(title, path)
            content = crumb + "\n\n" + "\n\n".join(p for p in content_parts if p)
            spans = [span_lookup[sid][1] for sid in dict.fromkeys(u.span_id for u in g.units)]
            raw = "\n\n".join(raw_parts)
            tokens = estimate_tokens(content)
            chunks.append(ConceptChunk(
                chunk_id="", notebook_id=nb_id, notebook_title=title, section_path=path,
                section_paths=[list(p) for p in paths], breadcrumb=crumb,
                source_span_ids=[sp.span_id for sp in spans],
                source_cell_ids=list(dict.fromkeys(u.cell_index for u in g.units)),
                source_segments=segments, raw_text=raw, content=content, token_count=tokens,
                content_roles=["teaching"],
                contains_math=any(sp.contains_math for sp in spans),
                contains_latex="$" in raw or "\\begin" in raw,
                contains_table=any(sp.contains_table for sp in spans),
                contains_list=any(sp.contains_list for sp in spans),
                contains_code="```" in raw or "`" in raw,
                image_resource_ids=list(dict.fromkeys(image_rids)),
                linked_tool_ids=[], linked_tool_chunk_ids=[], secondary_tool_ids=[], uncertain_tool_ids=[],
                linked_resource_ids=[], linked_resource_chunk_ids=[],
                retrieval_eligible=True,
                quality_flags=ConceptQuality(
                    is_merged=len(g.units) > 1, is_split=any(u.split_index is not None for u in g.units),
                    has_overlap=any(u.overlap_chars for u in g.units), is_duplicate=False,
                    is_oversized=tokens > OVERSIZED_TOKENS, is_tiny=tokens < TINY_TOKENS,
                    stripped_support_content=any(u.stripped for u in g.units)),
            ))
    for n, ch in enumerate(chunks, 1):
        ch.chunk_id = f"CON_{n:06d}"
    seen: dict[str, str] = {}
    for ch in chunks:                                # exact repeats of the same explanation
        h = norm_hash(ch.raw_text)
        if h in seen:
            ch.duplicate_of, ch.quality_flags.is_duplicate, ch.retrieval_eligible = seen[h], True, False
        else:
            seen[h] = ch.chunk_id
    return chunks, exclusions


# ----------------------------------------------------------------------------
# Tool and Resource chunks
# ----------------------------------------------------------------------------
def build_tool_chunks(tools: list[Tool], cells_by_id: dict[str, CellRecord], resources: list[Resource]
                      ) -> tuple[list[ToolChunk], list[Exclusion]]:
    chunks, exclusions = [], []
    plots = defaultdict(list)
    for r in resources:
        if r.image_reference.kind == "code_output":
            plots[r.cell_id].append(r.resource_id)
    for t in tools:
        if not t.quality.suitable_for_answer:
            exclusions.append(Exclusion(record_type="tool", record_id=t.tool_id,
                                        reason="not answer-suitable: " + ", ".join(t.quality.unsuitable_reasons)))
            continue
        cell = cells_by_id[t.cell_id]
        crumb = breadcrumb(t.source.notebook_title, list(cell.section_path))
        header = [crumb, f"Tool: {t.title}", f"Type: {t.tool_type}", f"Purpose: {t.purpose}"]
        if t.description_source != "section":
            header.append(f"Description: {t.description}")
        if t.libraries:
            header.append("Libraries: " + ", ".join(t.libraries))
        content = "\n".join(header) + f"\n\n```{t.language}\n{t.code}\n```"
        chunks.append(ToolChunk(
            chunk_id="", tool_id=t.tool_id, notebook_id=t.source.notebook_id,
            notebook_title=t.source.notebook_title, section_path=list(cell.section_path), breadcrumb=crumb,
            source_cell_id=t.cell_id, source_cell_ids=t.source.cell_indexes, tool_type=t.tool_type, title=t.title,
            purpose=t.purpose, description=t.description, language=t.language, libraries=t.libraries, code=t.code,
            inputs=t.inputs, outputs=t.outputs, content=content, token_count=estimate_tokens(content),
            linked_concept_chunk_ids=[], secondary_concept_chunk_ids=[], uncertain_concept_chunk_ids=[],
            linked_resource_ids=plots.get(t.cell_id, []),
            retrieval_eligible=True,
            quality_flags=ToolQualityFlags(
                is_self_contained=t.quality.is_self_contained, has_output=t.quality.has_output,
                has_nearby_explanation=t.quality.has_nearby_explanation, is_answer_suitable=True,
                is_duplicate=False),
        ))
    for n, ch in enumerate(chunks, 1):
        ch.chunk_id = f"TOOLCHUNK_{n:06d}"
    first: dict[str, ToolChunk] = {}
    for ch in chunks:
        h = norm_hash(ch.code)
        orig = first.get(h)
        if orig is None:
            first[h] = ch
        elif (orig.notebook_id != ch.notebook_id and len(code_lines(ch.code)) >= 3) or \
                orig.section_path == ch.section_path:
            # copied lecture content (a multi-line cell in another notebook), or the same cell repeated in
            # the same section; a short line like `df.plot()` matching elsewhere is a coincidence
            ch.duplicate_of, ch.quality_flags.is_duplicate, ch.retrieval_eligible = orig.chunk_id, True, False
        else:
            ch.repeats_code_of = orig.chunk_id   # re-run after the data or model changed: keeps its own context
    return chunks, exclusions


def build_resource_chunks(resources: list[Resource], cells_by_id: dict[str, CellRecord]
                          ) -> tuple[list[ResourceChunk], list[Exclusion]]:
    chunks, exclusions = [], []
    for r in resources:
        if r.retrieval_status != "attachable":
            exclusions.append(Exclusion(record_type="resource", record_id=r.resource_id,
                                        reason=f"retrieval_status {r.retrieval_status}"))
            continue
        cell = cells_by_id[r.cell_id]
        path = list(cell.section_path)
        if r.span_id:
            sp = next((s for s in cell.spans if s.span_id == r.span_id), None)
            path = list(sp.section_path) if sp is not None else path
        crumb = breadcrumb(r.source.notebook_title, path)
        vision = "done" if (r.vlm_caption or r.ocr_text) else "pending"
        content = "\n".join([
            crumb, f"Resource: {r.title}", f"Type: {r.resource_type} ({r.type_evidence})",
            f"Availability: {r.availability}",
            f"Caption ({r.caption.source}): {r.caption.text}" if r.caption.text else "Caption: none",
            "Image content: not extracted (vision pending). Do not use as text evidence." if vision == "pending"
            else f"Image content (vision model): {r.vlm_caption or r.ocr_text}"])
        chunks.append(ResourceChunk(
            chunk_id="", resource_id=r.resource_id, notebook_id=r.source.notebook_id,
            notebook_title=r.source.notebook_title, section_path=path, breadcrumb=crumb,
            source_cell_ids=r.source.cell_indexes, source_span_id=r.span_id, resource_type=r.resource_type,
            availability=r.availability, title=r.title, description=r.description, caption=r.caption.text,
            caption_source=r.caption.source, image_url=r.image_reference.url,
            local_path=r.image_reference.local_path, vision_status=vision, content=content,
            token_count=estimate_tokens(content),
            linked_concept_chunk_ids=[], linked_tool_ids=r.linked_tool_ids, linked_tool_chunk_ids=[],
            attachable=True, retrieval_eligible=vision == "done",
            quality_flags=ResourceQualityFlags(
                is_meaningful=r.resource_type != "decorative", is_decorative=r.resource_type == "decorative",
                requires_vision_model=vision == "pending"),
        ))
    for n, ch in enumerate(chunks, 1):
        ch.chunk_id = f"RESCHUNK_{n:06d}"
    return chunks, exclusions


# ----------------------------------------------------------------------------
# Linking
# ----------------------------------------------------------------------------
def attach(concepts: list[ConceptChunk], tool_chunks: list[ToolChunk], resource_chunks: list[ResourceChunk],
           resources: list[Resource], links: list[ToolConceptLink]) -> None:
    """Fill the link fields. Only implements/demonstrates/visualizes links are attached; supports links
    are stored as secondary and uncertain ones only as uncertain (never attached)."""
    chunks_of_span: dict[str, list[ConceptChunk]] = defaultdict(list)
    for ch in concepts:
        for sid in ch.source_span_ids:
            chunks_of_span[sid].append(ch)
    tool_chunk = {tc.tool_id: tc for tc in tool_chunks}

    def add(lst: list, value: str) -> None:
        if value not in lst:
            lst.append(value)

    visualized_by: dict[str, set[str]] = defaultdict(set)   # tool_id -> concept chunk ids it visualizes
    for link in links:
        tc = tool_chunk.get(link.tool_id)
        for ch in chunks_of_span.get(link.span_id, []):
            if link.relationship in PRIMARY_RELATIONSHIPS and tc is not None:
                add(ch.linked_tool_ids, link.tool_id)
                add(ch.linked_tool_chunk_ids, tc.chunk_id)
                add(tc.linked_concept_chunk_ids, ch.chunk_id)
                if link.relationship == "visualizes":
                    visualized_by[link.tool_id].add(ch.chunk_id)
            elif link.relationship in SECONDARY_RELATIONSHIPS:
                add(ch.secondary_tool_ids, link.tool_id)
                if tc is not None:
                    add(tc.secondary_concept_chunk_ids, ch.chunk_id)
            else:
                add(ch.uncertain_tool_ids, link.tool_id)
                if tc is not None:
                    add(tc.uncertain_concept_chunk_ids, ch.chunk_id)

    res = {r.resource_id: r for r in resources}
    concept_by_id = {ch.chunk_id: ch for ch in concepts}
    for rc in resource_chunks:
        r = res[rc.resource_id]
        targets = [ch.chunk_id for sid in r.linked_concept_span_ids for ch in chunks_of_span.get(sid, [])]
        for tid in r.linked_tool_ids:
            targets += sorted(visualized_by.get(tid, ()))            # plot of a tool that visualizes a concept
            if tid in tool_chunk:
                add(rc.linked_tool_chunk_ids, tool_chunk[tid].chunk_id)
        for cid in dict.fromkeys(targets):
            add(rc.linked_concept_chunk_ids, cid)
            add(concept_by_id[cid].linked_resource_ids, rc.resource_id)
            add(concept_by_id[cid].linked_resource_chunk_ids, rc.chunk_id)


# ----------------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------------
def size_buckets(chunks: list) -> Counter:
    c = Counter()
    for ch in chunks:
        t = ch.token_count
        c["< 100" if t < 100 else "100–299" if t < 300 else "300–800" if t <= 800 else "801–1,200" if t <= 1200
          else "> 1,200"] += 1
    return c


def build_report(cells: list[CellRecord], tools: list[Tool], resources: list[Resource], concepts: list[ConceptChunk],
                 tool_chunks: list[ToolChunk], resource_chunks: list[ResourceChunk], exclusions: list[Exclusion]) -> str:
    spans = [sp for c in cells for sp in c.spans]
    eligible = [sp for sp in spans if sp.content_role == "teaching" and sp.retrieval_eligible]
    in_chunks = {sid for ch in concepts for sid in ch.source_span_ids}
    retrievable = sum(ch.retrieval_eligible for ch in concepts) + sum(ch.retrieval_eligible for ch in tool_chunks) \
        + sum(ch.retrieval_eligible for ch in resource_chunks)
    with_tools = sum(bool(ch.linked_tool_ids) for ch in concepts)
    tools_linked = sum(bool(tc.linked_concept_chunk_ids) for tc in tool_chunks)
    pending = sum(r.retrieval_status == "pending_vision" for r in resources)
    L = ["# Chunking Report", "",
         f"Pipeline `{config.PIPELINE_VERSION}` · `src/chunk_builder.py` · PH2-CHUNK-001 (issue #3)", "",
         "Token counts are estimates (word pieces + punctuation; no tokenizer installed).", "",
         "## Summary", "",
         f"- Concept chunks: {len(concepts):,}",
         f"- Tool chunks: {len(tool_chunks):,}",
         f"- Resource chunks: {len(resource_chunks):,}",
         f"- Total retrieval-eligible chunks: {retrievable:,} (concept {sum(c.retrieval_eligible for c in concepts):,}, "
         f"tool {sum(c.retrieval_eligible for c in tool_chunks):,}, resource "
         f"{sum(c.retrieval_eligible for c in resource_chunks):,}; duplicates and vision-pending resources are not "
         "retrieval-eligible)", "",
         "## Concept coverage", "",
         f"- Retrieval-eligible teaching spans: {len(eligible):,}",
         f"- Spans included in Concept chunks: {len(in_chunks & {sp.span_id for sp in eligible}):,}",
         f"- Spans excluded: {sum(e.record_type == 'span' for e in exclusions):,} (empty after stripping embedded "
         "support text)",
         f"- Concept chunks with at least one linked Tool: {with_tools:,}",
         f"- Concept chunks without linked Tools: {len(concepts) - with_tools:,}",
         f"- Merged chunks: {sum(c.quality_flags.is_merged for c in concepts):,} · split spans: "
         f"{len({s.span_id for c in concepts if c.quality_flags.is_split for s in c.source_segments}):,} · chunks with "
         f"overlap: {sum(c.quality_flags.has_overlap for c in concepts):,} · chunks with stripped instructor/quiz text: "
         f"{sum(c.quality_flags.stripped_support_content for c in concepts):,}", "",
         "Spans not chunked, by role (kept in the source records): " + ", ".join(
             f"{k} {v:,}" for k, v in Counter(sp.content_role for sp in spans
                                              if sp.content_role in EXCLUDED_SPAN_ROLES).most_common())
         + f"; teaching spans that are not retrieval-eligible (heading-only, image-only, formatting) "
           f"{sum(sp.content_role == 'teaching' and not sp.retrieval_eligible for sp in spans):,}.", "",
         "## Tool coverage", "",
         f"- Eligible Tools: {len(tools):,}",
         f"- Answer-suitable Tools: {sum(t.quality.suitable_for_answer for t in tools):,}",
         f"- Tools converted to chunks: {len(tool_chunks):,}",
         f"- Tools linked to Concepts (implements/demonstrates/visualizes): {tools_linked:,}",
         f"- Unlinked Tools: {len(tool_chunks) - tools_linked:,} (of which with a supports link only: "
         f"{sum(not t.linked_concept_chunk_ids and bool(t.secondary_concept_chunk_ids) for t in tool_chunks):,}, "
         f"uncertain only: {sum(not t.linked_concept_chunk_ids and not t.secondary_concept_chunk_ids and bool(t.uncertain_concept_chunk_ids) for t in tool_chunks):,})",
         f"- Tools excluded: {sum(e.record_type == 'tool' for e in exclusions):,} (one line, no output)",
         "- Code not chunked, by role: " + ", ".join(
             f"{k} {v:,}" for k, v in Counter(c.content_role for c in cells if c.cell_type == "code"
                                              and c.content_role in EXCLUDED_CODE_ROLES).most_common()), "",
         "## Resource coverage", "",
         f"- Total Resources: {len(resources):,}",
         f"- Attachable Resources: {sum(r.retrieval_status == 'attachable' for r in resources):,}",
         f"- Pending-vision Resources: {pending:,} (excluded: no linked concept or tool)",
         f"- Resource chunks with vision_status pending: {sum(c.vision_status == 'pending' for c in resource_chunks):,}",
         f"- Resources linked to Concepts: {sum(bool(c.linked_concept_chunk_ids) for c in resource_chunks):,}",
         f"- Resources linked to Tools: {sum(bool(c.linked_tool_chunk_ids) for c in resource_chunks):,}",
         "- Availability: " + ", ".join(f"{k} {v:,}" for k, v in
                                        Counter(c.availability for c in resource_chunks).most_common()), ""]
    L += ["## Chunk-size distribution", "", "| Tokens | Concept | Tool | Resource |", "|---|---:|---:|---:|"]
    sc, st, sr = size_buckets(concepts), size_buckets(tool_chunks), size_buckets(resource_chunks)
    for b in ("< 100", "100–299", "300–800", "801–1,200", "> 1,200"):
        L.append(f"| {b} | {sc[b]:,} | {st[b]:,} | {sr[b]:,} |")
    tok = sorted(c.token_count for c in concepts)
    L += ["", f"Concept chunk tokens: median {tok[len(tok) // 2] if tok else 0}, max {tok[-1] if tok else 0}.", ""]
    tiny = sum(c.quality_flags.is_tiny for c in concepts)
    L += ["## Issues", "",
          f"- Tiny chunks (< {TINY_TOKENS} tokens): {tiny:,} concept. A section whose only prose is short and whose "
          "neighbours are unrelated sections stays on its own rather than being merged across a section boundary.",
          f"- Oversized chunks (> {OVERSIZED_TOKENS} tokens): {sum(c.quality_flags.is_oversized for c in concepts):,} "
          f"concept, {sum(c.token_count > OVERSIZED_TOKENS for c in tool_chunks):,} tool (code is never split).",
          f"- Duplicate chunks: {sum(c.quality_flags.is_duplicate for c in concepts):,} concept, "
          f"{sum(c.quality_flags.is_duplicate for c in tool_chunks):,} tool (flagged, `duplicate_of` set, not "
          "retrieval-eligible). Tool code repeated under another section of the same notebook (re-run after the "
          "data or model changed), or a 1–2 line snippet that also appears in another notebook, keeps its own "
          "context and stays eligible with `repeats_code_of`: "
          f"{sum(bool(c.repeats_code_of) for c in tool_chunks):,}.",
          f"- Chunks with missing source provenance: {missing_provenance(concepts, tool_chunks, resource_chunks)}", ""]
    return "\n".join(L) + "\n"


def missing_provenance(concepts, tool_chunks, resource_chunks) -> int:
    n = sum(not (c.notebook_id and c.source_span_ids and c.source_cell_ids and c.source_segments) for c in concepts)
    n += sum(not (c.notebook_id and c.tool_id and c.source_cell_ids) for c in tool_chunks)
    n += sum(not (c.notebook_id and c.resource_id and c.source_cell_ids) for c in resource_chunks)
    return n


REVIEW_CSV = Path("qa") / "chunk_review_sample.csv"


def review_section(path: Path) -> str:
    """Summary of the manual QA sample, when data/processed/qa/chunk_review_sample.csv exists."""
    import csv
    if not path.exists():
        return ""
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    L = ["## Manual review", "", f"`data/processed/{REVIEW_CSV.as_posix()}` (stratified, seed 3027).", "",
         "| Sample | Reviewed | Passed |", "|---|---:|---:|"]
    for name in dict.fromkeys(r["sample"] for r in rows):
        rr = [r for r in rows if r["sample"] == name]
        L.append(f"| {name} | {len(rr)} | {sum(r['passed'] == 'Y' for r in rr)} |")
    L += [""] + [f"- {r['item']} {r['chunk_id']}: {r['notes']}" for r in rows if r["passed"] != "Y"]
    return "\n".join(L) + "\n"


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def read_jsonl(path: Path, model):
    if not path.exists():
        raise SystemExit(f"{path} not found; run src/assets.py first")
    return [model.model_validate_json(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def build(cells: list[CellRecord], tools: list[Tool], resources: list[Resource], links: list[ToolConceptLink]):
    cells_by_id = {c.cell_id: c for c in cells}
    image_ids = {(r.cell_id, r.image_index): r.resource_id for r in resources if r.image_reference.kind == "markdown_image"}
    concepts, ex1 = build_concept_chunks(cells, image_ids)
    tool_chunks, ex2 = build_tool_chunks(tools, cells_by_id, resources)
    resource_chunks, ex3 = build_resource_chunks(resources, cells_by_id)
    attach(concepts, tool_chunks, resource_chunks, resources, links)
    return concepts, tool_chunks, resource_chunks, ex1 + ex2 + ex3


def run(processed_dir: Path = config.PROCESSED_DIR, quiet: bool = False):
    cells = load_cells(processed_dir / config.CELLS_JSONL)
    tools = read_jsonl(processed_dir / "tools.jsonl", Tool)
    resources = read_jsonl(processed_dir / "resources.jsonl", Resource)
    links = read_jsonl(processed_dir / "tool_concept_links.jsonl", ToolConceptLink)
    concepts, tool_chunks, resource_chunks, exclusions = build(cells, tools, resources, links)
    for name, records in ((CONCEPT_CHUNKS, concepts), (TOOL_CHUNKS, tool_chunks), (RESOURCE_CHUNKS, resource_chunks),
                          (CHUNK_EXCLUSIONS, exclusions)):
        (processed_dir / name).write_text("".join(json.dumps(r.model_dump(), ensure_ascii=False) + "\n" for r in records),
                                          encoding="utf-8", newline="\n")
    (processed_dir / CHUNKING_REPORT).write_text(
        build_report(cells, tools, resources, concepts, tool_chunks, resource_chunks, exclusions)
        + review_section(processed_dir / REVIEW_CSV), encoding="utf-8", newline="\n")
    if not quiet:
        print(f"concept {len(concepts)}  tool {len(tool_chunks)}  resource {len(resource_chunks)}  "
              f"excluded {len(exclusions)}")
    return concepts, tool_chunks, resource_chunks, exclusions


if __name__ == "__main__":
    run()
