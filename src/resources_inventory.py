#!/usr/bin/env python3
"""
Phase 1.5 (issue #1): build the Resources inventory, one record per image.

    python src/resources_inventory.py    # after `python src/ingestion.py` and `src/tools_inventory.py`

Two sources of images:
  - Every image referenced in a markdown cell (`![..](..)` or `<img>`). This covers all
    image-referencing markdown cells.
  - Every image output of a code cell, i.e. plots.

Image content is never read, extracted or described. The pipeline has no OCR or vision model,
and most markdown images live on Google Drive or a CDN that is not downloaded. So a resource
type is only assigned when the structure gives evidence for it:

  plot                code-cell image output
  decorative          embedded image no larger than 48x48 px
  external_reference  image hot-linked from a third-party site, not course storage
  diagram / formula_image / worked_example / screenshot
                      only when the author's alt text names it (e.g. "architecture diagram")
  unclassified        no evidence; left for the OCR/VLM pass, prioritised by `vision_priority`

A "Screenshot_2023-…png" filename says how the image was captured, not what it shows (screen
grabs of slides, formulas and diagrams). It is kept as a `capture_hint`, not used as the type.

Embedded images (data URIs, attachments, plot outputs) are written to data/processed/images/.
"""
from __future__ import annotations

import base64
import binascii
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
from assets import (DATA_URI_RE, EXT_FORMAT, FILENAME_LIKE_RE, HTML_ALT_RE, HTML_IMG_TAG_RE, HTML_SRC_RE,  # noqa: E402
                    MD_IMG_RE, TopicMapper, concepts_for, first_sentences, image_size, plain_text, save_image)
from notebook_parser import CellRecord, read_notebook, to_text  # noqa: E402
from tools_inventory import Source, Tool, load_cells, load_mapper, pct, source_for, write_jsonl  # noqa: E402

RESOURCES_JSONL = "resources.jsonl"
RESOURCES_REPORT_MD = "resources_report.md"
IMAGES_DIR = "images"
DECORATIVE_MAX_PX = 48
CONCEPT_LOOKBACK_CELLS = 2
TOOL_WINDOW_CELLS = 5

ResourceType = Literal["plot", "diagram", "formula_image", "worked_example", "screenshot", "decorative",
                       "external_reference", "unclassified"]
Availability = Literal["embedded", "google_drive", "external_url", "missing"]
RetrievalStatus = Literal["attachable", "pending_vision", "excluded_decorative", "unavailable"]
VisionPriority = Literal["high", "normal", "low", "none"]

# Hosts where the course keeps its own images. Anything else is a third-party image.
COURSE_HOSTS = re.compile(
    r"^https?://(drive\.google\.com|docs\.google\.com|lh\d\.googleusercontent\.com|d2beiqkhq929f0\.cloudfront\.net"
    r"|hackmd\.io|[\w.-]*clickup-attachments\.com|colab\.research\.google\.com)/", re.I)
GOOGLE_HOSTS = re.compile(r"^https?://(drive|docs)\.google\.com/|^https?://lh\d\.googleusercontent\.com/", re.I)
GENERIC_ALT = re.compile(r"^(picture|image|img|photo|figure|fig|file|download|\d+)[\s\d().,_-]*$", re.I)
SCREENSHOT_NAME_RE = re.compile(r"screen\s*shot|screenshot|screen[_ ]capture", re.I)
ALT_TYPE_RULES = [            # (type, pattern on the author's alt text)
    ("formula_image", re.compile(r"\b(formula|equation|derivation)s?\b", re.I)),
    ("worked_example", re.compile(r"\b(worked|solved)\s+example\b", re.I)),
    ("diagram", re.compile(r"\b(diagram|architecture|flow\s*chart|flowchart|schematic)\b", re.I)),
    ("screenshot", re.compile(r"\b(ui|interface|dashboard|console)\s+screenshot\b", re.I)),
]
DIAGRAM_HINT_RE = re.compile(r"\b(diagram|architecture|figure|flow\s*chart|illustrat)", re.I)
MATH_HINT_RE = re.compile(r"\$|\\frac|\bformula|\bequation|\bderivation", re.I)
SUPPORT_SPAN_ROLES = {"quiz", "instructor_note", "agenda", "business_context", "preamble", "rhetorical_question"}


class ImageReference(BaseModel):
    kind: Literal["markdown_image", "code_output"]
    url: Optional[str]                # None for embedded images
    local_path: Optional[str]         # saved copy of an embedded image
    format: Optional[str]
    width: Optional[int] = None
    height: Optional[int] = None
    bytes: Optional[int] = None


class Caption(BaseModel):
    source: Literal["alt_text", "same_span", "nearby_markdown", "none"]
    text: str


class Resource(BaseModel):
    resource_id: str
    cell_id: str
    span_id: Optional[str]            # markdown span holding the image; None for plot outputs
    span_role: Optional[str]          # content_role of that span
    image_index: int                  # position of the image within its cell
    title: str
    description: str
    resource_type: ResourceType
    type_confidence: float
    type_evidence: str
    capture_hint: Optional[str]       # e.g. "screenshot_filename"; not a type
    context_hints: list[str]          # words near the image (diagram, math); not used as the type
    availability: Availability
    source: Source
    image_reference: ImageReference
    caption: Caption
    content_extracted: bool = False   # no OCR/VLM has run; nothing below describes the image itself
    ocr_text: Optional[str] = None
    vlm_caption: Optional[str] = None
    concepts: list[str]
    topic_ids: list[str]
    linked_concept_span_ids: list[str]
    linked_tool_ids: list[str]
    retrieval_status: RetrievalStatus
    vision_priority: VisionPriority
    vision_priority_reason: str
    created_at: str


# ----------------------------------------------------------------------------
# Finding images
# ----------------------------------------------------------------------------
def images_with_positions(text: str) -> list[tuple[int, str, str]]:
    """(offset, alt text, src) for every markdown or HTML image, in order of appearance."""
    found = [(m.start(), m.group(1), m.group(2)) for m in MD_IMG_RE.finditer(text)]
    for m in HTML_IMG_TAG_RE.finditer(text):
        src = HTML_SRC_RE.search(m.group(0))
        if src:
            alt = HTML_ALT_RE.search(m.group(0))
            found.append((m.start(), alt.group(1) if alt else "", src.group(1)))
    return sorted(found)


def span_at(cell: CellRecord, offset: int):
    for sp in cell.spans:
        if sp.char_start <= offset < sp.char_end:
            return sp
    return cell.spans[-1] if cell.spans else None


def availability_of(src: str, has_data: bool) -> Availability:
    if src.startswith("data:") or src.startswith("attachment:"):
        return "embedded" if has_data else "missing"
    if GOOGLE_HOSTS.match(src):
        return "google_drive"
    if re.match(r"^https?://", src, re.I):
        return "external_url"
    return "missing"                                      # relative path to a file that is not in the corpus


def decode_embedded(src: str, attachments: dict) -> tuple[Optional[str], Optional[bytes]]:
    m = DATA_URI_RE.match(src)
    try:
        if m:
            return m.group(1), base64.b64decode(m.group(2))
        if src.startswith("attachment:") and src[11:] in attachments:
            mime, b64 = next(iter(attachments[src[11:]].items()))
            return mime, base64.b64decode(b64)
    except (binascii.Error, ValueError, StopIteration):
        pass
    return None, None


def meaningful_alt(alt: str) -> bool:
    alt = alt.strip()
    return bool(alt) and not FILENAME_LIKE_RE.match(alt) and not GENERIC_ALT.match(alt) \
        and not re.search(r"\.(png|jpe?g|gif|svg|webp|bmp)$", alt, re.I)


def resource_type_for(kind: str, src: str, alt: str, width: Optional[int], height: Optional[int]
                      ) -> tuple[ResourceType, float, str]:
    if kind == "code_output":
        return "plot", 0.95, "Image output of a code cell."
    if width and height and max(width, height) <= DECORATIVE_MAX_PX:
        return "decorative", 0.9, f"Embedded image of {width}x{height} px (icon size)."
    if meaningful_alt(alt):
        for rtype, pattern in ALT_TYPE_RULES:
            if pattern.search(alt):
                return rtype, 0.7, f"Author alt text names it: '{alt.strip()[:60]}'."
    if re.match(r"^https?://", src, re.I) and not COURSE_HOSTS.match(src):
        host = re.match(r"^https?://([^/]+)", src).group(1)
        return "external_reference", 0.8, f"Hot-linked from a third-party site ({host})."
    return "unclassified", 0.0, "No structural evidence of the image type; needs OCR/VLM."


# ----------------------------------------------------------------------------
# Context: captions, concept spans, tools
# ----------------------------------------------------------------------------
def span_text_without_images(text: str) -> str:
    return plain_text(text)


def caption_for(alt: str, span, nb_cells: list[CellRecord], i: int) -> Caption:
    if meaningful_alt(alt):
        return Caption(source="alt_text", text=alt.strip())
    if span is not None:
        own = span_text_without_images(span.content)
        if len(own) >= 15:
            return Caption(source="same_span", text=first_sentences(own))
    for j in (i - 1, i + 1):
        if 0 <= j < len(nb_cells) and nb_cells[j].cell_type == "markdown" and nb_cells[j].spans:
            sp = nb_cells[j].spans[-1] if j < i else nb_cells[j].spans[0]
            if sp.section_path == nb_cells[i].section_path:
                text = span_text_without_images(sp.content)
                if len(text) >= 15:
                    return Caption(source="nearby_markdown", text=first_sentences(text))
    return Caption(source="none", text="")


def concept_spans_near(nb_cells: list[CellRecord], i: int, span) -> list[str]:
    """Teaching, retrieval-eligible spans in the image's section: its own span, else the closest
    one before it (up to CONCEPT_LOOKBACK_CELLS cells back), plus the next one after it."""
    section = span.section_path if span is not None else nb_cells[i].section_path

    def ok(sp) -> bool:
        return sp.content_role == "teaching" and sp.retrieval_eligible and sp.section_path == section

    if span is not None and ok(span):
        return [span.span_id]
    out: list[str] = []
    before = [sp for c in nb_cells[max(0, i - CONCEPT_LOOKBACK_CELLS):i] if c.cell_type == "markdown"
              for sp in c.spans]
    if span is not None:
        before += [sp for sp in nb_cells[i].spans if sp.char_end <= span.char_start]
    before = [sp for sp in before if ok(sp)]
    if before:
        out.append(before[-1].span_id)
    after = []
    if span is not None:
        after += [sp for sp in nb_cells[i].spans if sp.char_start >= span.char_end]
    if i + 1 < len(nb_cells) and nb_cells[i + 1].cell_type == "markdown":
        after += nb_cells[i + 1].spans
    after = [sp for sp in after if ok(sp)]
    if after:
        out.append(after[0].span_id)
    return out


def vision_priority_for(rtype: str, availability: str, span_role: Optional[str]) -> tuple[VisionPriority, str]:
    if rtype == "decorative" or availability == "missing":
        return "none", "Decorative or missing image."
    if rtype in ("diagram", "formula_image", "worked_example"):
        return "high", f"High-value type ({rtype}) for OCR/VLM."
    if rtype == "plot":
        return "low", "Plot output; it can be regenerated from its tool's code."
    if span_role in SUPPORT_SPAN_ROLES:
        return "normal", f"Image in a {span_role} span, not teaching text."
    if rtype == "unclassified":
        return "high", "Unclassified image in teaching content; may be a diagram, formula or worked example."
    return "normal", f"{rtype.replace('_', ' ').capitalize()}; useful but not a core teaching image."


def retrieval_status_for(rtype: str, availability: str, concept_ids: list, tool_ids: list) -> RetrievalStatus:
    if availability == "missing":
        return "unavailable"
    if rtype == "decorative":
        return "excluded_decorative"
    return "attachable" if concept_ids or tool_ids else "pending_vision"


# ----------------------------------------------------------------------------
# Build
# ----------------------------------------------------------------------------
def build_resources(cells: list[CellRecord], tools: list[Tool], mapper: TopicMapper, raw_dir: Path,
                    out_dir: Path) -> list[Resource]:
    images_dir = out_dir / IMAGES_DIR
    tool_by_cell = {t.cell_id: t for t in tools}
    by_nb: dict[str, list[CellRecord]] = defaultdict(list)
    for c in cells:
        by_nb[c.notebook_id].append(c)

    resources: list[Resource] = []
    for nb_id, nb_cells in by_nb.items():
        raw_cells = read_notebook(raw_dir / nb_cells[0].file_name)[0]["cells"]
        for i, cell in enumerate(nb_cells):
            raw = raw_cells[cell.cell_index]
            items: list[dict] = []
            if cell.cell_type == "markdown" and cell.contains_image:
                in_content = images_with_positions(cell.content)
                in_raw = images_with_positions(to_text(raw.get("source", "")))
                if len(in_content) != len(in_raw):
                    raise ValueError(f"{cell.cell_id}: {len(in_content)} images in content, {len(in_raw)} in source")
                attachments = raw.get("attachments") or {}
                for n, ((offset, alt, _), (_, _, src)) in enumerate(zip(in_content, in_raw)):
                    mime, data = decode_embedded(src, attachments)
                    items.append({"n": n, "kind": "markdown_image", "alt": alt, "src": src, "mime": mime,
                                  "data": data, "span": span_at(cell, offset)})
            elif cell.cell_type == "code":
                n = 0
                for o in raw.get("outputs") or []:
                    for mime, payload in sorted((o.get("data") or {}).items()):
                        if mime.startswith("image/"):
                            data = to_text(payload).encode() if mime == "image/svg+xml" \
                                else base64.b64decode(to_text(payload))
                            items.append({"n": n, "kind": "code_output", "alt": "", "src": "data:", "mime": mime,
                                          "data": data, "span": None})
                            n += 1
                            break                                   # one image per output
            if not items:
                continue

            for item in items:
                span, alt, src, data = item["span"], item["alt"], item["src"], item["data"]
                availability = availability_of(src, data is not None)
                fmt = local_path = width = height = size = None
                if data is not None:
                    fmt = item["mime"].split("/")[1].replace("svg+xml", "svg").replace("jpg", "jpeg")
                    width, height = image_size(data)
                    size = len(data)
                    local_path = save_image(images_dir, f"{cell.cell_id}_{item['n']}", fmt, data, config.ROOT)
                elif availability != "missing":
                    ext = re.search(r"\.(png|jpe?g|gif|svg|webp|bmp)(\?|$)", src, re.I)
                    fmt = EXT_FORMAT.get(ext.group(1).lower()) if ext else None
                rtype, conf, evidence = resource_type_for(item["kind"], src, alt, width, height)
                capture = "screenshot_filename" if SCREENSHOT_NAME_RE.search(alt + " " + src) \
                    and rtype not in ("plot", "decorative") else None

                if item["kind"] == "code_output":
                    tool = tool_by_cell.get(cell.cell_id)
                    tool_ids = [tool.tool_id] if tool else []
                    concept_ids = list(tool.explanation_span_ids) if tool else []
                    caption = Caption(source="nearby_markdown", text=tool.description) \
                        if tool and tool.description_source == "nearby_explanation" else Caption(source="none", text="")
                    title = f"Plot: {tool.title}" if tool else f"Plot: {cell.section}"
                    span_role = None
                else:
                    concept_ids = concept_spans_near(nb_cells, i, span)
                    section = span.section_path if span is not None else cell.section_path
                    tool_ids = [tool_by_cell[c.cell_id].tool_id for c in nb_cells[i + 1:i + 1 + TOOL_WINDOW_CELLS]
                                if c.cell_id in tool_by_cell and c.section_path == section][:3]
                    caption = caption_for(alt, span, nb_cells, i)
                    title = alt.strip() if meaningful_alt(alt) else \
                        f"Image in {span.section_title if span is not None else cell.section}"
                    span_role = span.content_role if span is not None else None

                near_text = " ".join([caption.text] + ([span.content] if span is not None else []))
                hints = []
                if DIAGRAM_HINT_RE.search(near_text):
                    hints.append("diagram_mentioned_nearby")
                if MATH_HINT_RE.search(near_text) or (span is not None and span.contains_math):
                    hints.append("math_nearby")
                priority, why = vision_priority_for(rtype, availability, span_role)
                resources.append(Resource(
                    resource_id="",                                 # numbered below, in corpus order
                    cell_id=cell.cell_id,
                    span_id=span.span_id if span is not None else None,
                    span_role=span_role,
                    image_index=item["n"],
                    title=title,
                    description=(caption.text or "No caption.") + " (Image content not extracted.)",
                    resource_type=rtype,
                    type_confidence=conf,
                    type_evidence=evidence,
                    capture_hint=capture,
                    context_hints=hints,
                    availability=availability,
                    source=source_for(cell),
                    image_reference=ImageReference(
                        kind=item["kind"], url=None if data is not None else src, local_path=local_path,
                        format=fmt, width=width, height=height, bytes=size),
                    caption=caption,
                    concepts=concepts_for(cell),
                    topic_ids=mapper.topics(nb_id, " ".join(cell.section_path + [title])),
                    linked_concept_span_ids=concept_ids,
                    linked_tool_ids=tool_ids,
                    retrieval_status=retrieval_status_for(rtype, availability, concept_ids, tool_ids),
                    vision_priority=priority,
                    vision_priority_reason=why,
                    created_at=cell.ingested_at,
                ))
    for n, r in enumerate(resources, 1):
        r.resource_id = f"RES_{n:04d}"
    return resources


# ----------------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------------
def table(title: str, counter: Counter, total: int, order: Optional[list] = None) -> list[str]:
    keys = order or [k for k, _ in counter.most_common()]
    L = [f"| {title} | Resources | Share |", "|---|---:|---:|"]
    L += [f"| {k} | {counter[k]:,} | {pct(counter[k], total)} |" for k in keys if counter[k] or order]
    return L + [""]


def resources_report(resources: list[Resource], cells: list[CellRecord]) -> str:
    md_cells = {c.cell_id for c in cells if c.cell_type == "markdown" and c.contains_image}
    plot_cells = {r.cell_id for r in resources if r.image_reference.kind == "code_output"}
    covered = {r.cell_id for r in resources}
    total = len(resources)
    md_res = [r for r in resources if r.image_reference.kind == "markdown_image"]
    L = ["# Resources Report", "",
         f"Pipeline `{config.PIPELINE_VERSION}` · `src/resources_inventory.py` · issue #1", "",
         "## Summary", "",
         f"- Image-referencing markdown cells: {len(md_cells):,} — in `resources.jsonl`: "
         f"{len(md_cells & covered):,}",
         f"- Markdown images: {len(md_res):,}",
         f"- Code cells with image outputs: {len(plot_cells):,} — plot images: {total - len(md_res):,}",
         f"- Resources: {total:,}",
         f"- Image content extracted: {sum(r.content_extracted for r in resources)} "
         "(no OCR/VLM in this phase; descriptions come from alt text and nearby markdown only)", "",
         "## Resource type", "",
         "Types are assigned only from structural evidence (see `type_evidence`). `unclassified` means "
         "no evidence yet, not a guess.", ""]
    L += table("Resource type", Counter(r.resource_type for r in resources), total,
               ["plot", "diagram", "formula_image", "worked_example", "screenshot", "decorative",
                "external_reference", "unclassified"])
    L += ["## Availability", ""]
    L += table("Availability", Counter(r.availability for r in resources), total,
               ["embedded", "google_drive", "external_url", "missing"])
    L += ["## Retrieval status", "",
          "`attachable`: linked to a concept span or tool, so it can be shown next to them. "
          "`pending_vision`: no link, needs a caption first.", ""]
    L += table("Retrieval status", Counter(r.retrieval_status for r in resources), total,
               ["attachable", "pending_vision", "excluded_decorative", "unavailable"])
    L += ["## OCR/VLM queue", ""]
    L += table("Vision priority", Counter(r.vision_priority for r in resources), total, ["high", "normal", "low", "none"])
    high = [r for r in resources if r.vision_priority == "high"]
    L += [f"High priority by availability: " + ", ".join(
        f"{k} {v:,}" for k, v in Counter(r.availability for r in high).most_common()),
        f"Screenshot-named images (capture hint only): {sum(r.capture_hint == 'screenshot_filename' for r in resources):,}",
        "Context hints on high-priority images: " + ", ".join(
            f"{k} {v:,}" for k, v in Counter(h for r in high for h in r.context_hints).most_common()), ""]
    L += ["## Links and captions", ""]
    L += table("Caption source", Counter(r.caption.source for r in resources), total)
    L += [f"- With a linked concept span: {sum(bool(r.linked_concept_span_ids) for r in resources):,}",
          f"- With a linked tool: {sum(bool(r.linked_tool_ids) for r in resources):,}",
          f"- Markdown images by span role: " + ", ".join(
              f"{k} {v:,}" for k, v in Counter(r.span_role for r in md_res).most_common()), ""]
    return "\n".join(L) + "\n"


def run(processed_dir: Path = config.PROCESSED_DIR, raw_dir: Path = config.RAW_NOTEBOOKS_DIR,
        quiet: bool = False, cells: Optional[list[CellRecord]] = None, tools: Optional[list[Tool]] = None
        ) -> list[Resource]:
    cells = cells if cells is not None else load_cells(processed_dir / config.CELLS_JSONL)
    if tools is None:
        path = processed_dir / "tools.jsonl"
        if not path.exists():
            raise SystemExit(f"{path} not found; run src/tools_inventory.py first")
        tools = [Tool.model_validate_json(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    resources = build_resources(cells, tools, load_mapper(), raw_dir, processed_dir)
    write_jsonl(processed_dir / RESOURCES_JSONL, resources)
    (processed_dir / RESOURCES_REPORT_MD).write_text(resources_report(resources, cells), encoding="utf-8",
                                                       newline="\n")
    if not quiet:
        print(f"{len(resources)} resources: " + ", ".join(
            f"{k} {v}" for k, v in Counter(r.resource_type for r in resources).most_common()))
    return resources


if __name__ == "__main__":
    run()
