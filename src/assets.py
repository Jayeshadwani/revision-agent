#!/usr/bin/env python3
"""
Phase 1.5: build the Tools and Resources inventories from the Phase 1 cell records.

    Concepts explain.  Tools demonstrate.  Resources illustrate.  Prompts ask.

Usage (from the project root, after `python src/ingestion.py`):
    python src/assets.py

Reads data/processed/cells.jsonl, the raw notebooks (for embedded images) and the topic
catalog. Writes, in data/processed/:
    tools.jsonl       one record per non-empty code cell, classified by tool_type
    resources.jsonl   one record per image: markdown images and plot outputs
    images/           embedded images extracted as files (external images are not downloaded)

Everything is rule-based and deterministic. Titles and descriptions come from headings,
comments and nearby markdown; an LLM can normalize them later. Image content is not read:
every meaningful resource is marked `requires_vision_model` until it is captioned.
"""
from __future__ import annotations

import ast
import base64
import builtins
import json
import re
import struct
import sys
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
from ingestion import candidate_key, content_words  # noqa: E402
from notebook_parser import CellRecord, read_notebook, to_text  # noqa: E402

TOOLS_JSONL = "tools.jsonl"
RESOURCES_JSONL = "resources.jsonl"
IMAGES_DIR = "images"

ToolType = Literal[
    "implementation", "demonstration", "function", "workflow", "visualization",
    "data_loading", "environment_setup", "debugging", "non_teaching",
]
# Tool types that may be shown for "show me code" answers in v1
ANSWER_ELIGIBLE = {"implementation", "demonstration", "function", "workflow", "visualization"}

ResourceType = Literal[
    "plot", "diagram", "formula_image", "worked_example", "screenshot", "decorative",
    "external_reference", "unclassified",
]


# ----------------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------------
class Source(BaseModel):
    notebook_id: str
    notebook_title: str
    section_path: str
    cell_ids: list[int]


class ToolQuality(BaseModel):
    is_teaching_code: bool
    is_self_contained: bool
    has_output: bool
    has_error_output: bool
    has_explanation_nearby: bool
    complexity: Literal["low", "medium", "high"]
    execution_status: str = "not_executed"      # the pipeline never runs notebook code
    suitable_for_answer: bool


class Tool(BaseModel):
    tool_id: str
    cell_id: str
    title: str
    description: str
    tool_type: ToolType
    language: str = "python"
    libraries: list[str]
    code: str
    purpose: str
    inputs: list[str]
    outputs: list[str]
    concepts: list[str]
    topic_ids: list[str]
    source: Source
    quality: ToolQuality
    tags: list[str]
    created_at: str


class ImageReference(BaseModel):
    location: Literal["embedded", "google_drive", "url"]
    url: Optional[str]
    local_path: Optional[str]
    format: Optional[str]
    width: Optional[int] = None
    height: Optional[int] = None
    bytes: Optional[int] = None


class Caption(BaseModel):
    source: Literal["alt_text", "nearby_markdown", "none"]
    text: str


class ResourceQuality(BaseModel):
    is_meaningful: bool
    is_decorative: bool
    contains_formula: Optional[bool]          # None = unknown until a vision model has looked at it
    contains_diagram: Optional[bool]
    contains_worked_example: Optional[bool]
    requires_vision_model: bool


class Resource(BaseModel):
    resource_id: str
    cell_id: str
    title: str
    description: str
    resource_type: ResourceType
    modality: str = "image"
    availability: Literal["embedded", "external_unavailable"]
    source: Source
    image_reference: ImageReference
    caption: Caption
    extracted_text: Optional[str] = None
    vlm_caption: Optional[str] = None
    ocr_text: Optional[str] = None
    concepts: list[str]
    topic_ids: list[str]
    linked_tool_ids: list[str]
    retrieval_status: Literal["excluded_from_v1", "unavailable", "excluded_decorative"]
    quality: ResourceQuality
    created_at: str


# ----------------------------------------------------------------------------
# Shared helpers
# ----------------------------------------------------------------------------
TAG_RE = re.compile(r"<[^>]+>")
MD_IMG_RE = re.compile(r"!\[([^\]]*)\]\(\s*<?([^)\s>]+)[^)]*\)")
HTML_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.I)
HTML_SRC_RE = re.compile(r"\bsrc\s*=\s*[\"']?([^\"'\s>]+)", re.I)
HTML_ALT_RE = re.compile(r"\balt\s*=\s*[\"']([^\"']*)[\"']", re.I)
DATA_URI_RE = re.compile(r"data:(image/[\w.+-]+);base64,([A-Za-z0-9+/=\s]+)")
FILENAME_LIKE_RE = re.compile(r"^[\w\s().,-]*\.(png|jpe?g|gif|svg|webp|bmp)$|^image\d*$|^img\d*$|^\s*$", re.I)


def plain_text(markdown: str) -> str:
    text = MD_IMG_RE.sub("", markdown)
    text = HTML_IMG_TAG_RE.sub("", text)
    text = TAG_RE.sub(" ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)          # links -> text
    text = re.sub(r"[#*_`>|]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def first_sentences(text: str, limit: int = 200) -> str:
    text = plain_text(text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return (cut[: end + 1] if end > 60 else cut.rsplit(" ", 1)[0] + "…").strip()


def concepts_for(cell: CellRecord) -> list[str]:
    seen, out = set(), []
    for name in reversed(cell.section_path):                      # innermost first
        ck = candidate_key(name)
        if ck and ck[0] not in seen:
            seen.add(ck[0])
            out.append(ck[1])
    return out[:4]


GENERIC_TOPIC_WORDS = {"data", "analysi", "model", "learning", "machine", "implementation", "basic", "intro"}


class TopicMapper:
    """Assign catalog topics: the notebook's topics, narrowed by word overlap with the context."""

    def __init__(self, catalog: dict):
        self.by_nb: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for t in catalog.get("topics", []):
            for nb in t["notebook_ids"]:
                self.by_nb[nb].append((t["topic_id"], t["topic_name"]))

    def topics(self, notebook_id: str, context: str) -> list[str]:
        options = self.by_nb.get(notebook_id, [])
        if len(options) <= 1:
            return [tid for tid, _ in options]
        words = content_words(context) - GENERIC_TOPIC_WORDS
        scored = [(len(words & (content_words(name) - GENERIC_TOPIC_WORDS)), tid) for tid, name in options]
        best = max(s for s, _ in scored)
        if best == 0:
            return sorted(tid for _, tid in scored)               # ambiguous: keep all
        return sorted(tid for s, tid in scored if s == best)


def section_key(cell: CellRecord) -> tuple[str, tuple[str, ...]]:
    return cell.notebook_id, tuple(cell.section_path)


# ----------------------------------------------------------------------------
# Tools
# ----------------------------------------------------------------------------
SHELL_LINE_RE = re.compile(r"^\s*[!%]")
SETUP_CALL_RE = re.compile(
    r"\b(pip\s+install|nltk\.download|spacy\.cli\.download|drive\.mount|warnings\.filterwarnings|"
    r"tf\.config\.|os\.environ|set_option|sns\.set\b|sns\.set_theme|plt\.style\.use|%matplotlib)"
)
SHELL_DOWNLOAD_RE = re.compile(r"^\s*!\s*(gdown|wget|curl|unzip|tar|kaggle|git\s+clone|mv|cp|ls|mkdir|rm)\b")
LOAD_CALL_RE = re.compile(
    r"\b(read_csv|read_excel|read_json|read_parquet|read_table|read_sql|load_dataset|load_data|"
    r"fetch_\w+|load_iris|load_digits|load_breast_cancer|load_wine|load_diabetes|"
    r"image_dataset_from_directory|flow_from_directory|gdown|wget|unzip|urlretrieve)\b"
)
PLOT_RE = re.compile(
    r"\b(plt|sns|px|go|ax|axes|axs|fig)\.\w+\(|\.plot\(|\.hist\(|\bimshow\(|\.heatmap\(|\bplot_\w+\("
)
MODEL_STEP_RE = re.compile(
    r"\.(fit|fit_transform|transform|predict|predict_proba|score|compile|evaluate|fit_resample)\(|"
    r"\btrain_test_split\(|\bcross_val_score\(|\bGridSearchCV\(|\bPipeline\("
)
INSPECT_RE = re.compile(
    r"^(print\()?\s*[\w.\[\]'\"]+(\.(head|tail|shape|sample|columns|dtypes|info|keys|summary)\b(\(\s*\d*\s*\))?)?\s*\)?\s*;?$"
)
ARITH_RE = re.compile(r"=[^=].*([+\-*/@]|\*\*|np\.\w+\()")
SEPARATOR_RE = re.compile(r"^[#\s=\-*_~]+$")
BUILTINS = set(dir(builtins)) | {"display", "get_ipython", "__file__"}


def code_lines(code: str) -> list[str]:
    return [l for l in code.split("\n") if l.strip() and not l.strip().startswith("#")]


def parseable(code: str) -> Optional[ast.Module]:
    body = "\n".join("" if SHELL_LINE_RE.match(l) else l for l in code.split("\n"))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")                         # notebook code has odd escapes
            return ast.parse(body)
    except SyntaxError:
        return None


def notebook_symbols(trees: list[Optional[ast.Module]]) -> set[str]:
    """Names imported or defined (def/class) anywhere in a notebook: dependencies, not inputs."""
    names = set()
    for tree in trees:
        for node in ast.walk(tree) if tree else []:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names |= {(a.asname or a.name).split(".")[0] for a in node.names}
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
    return names


def names_io(tree: Optional[ast.Module], dependencies: set[str] = frozenset()) -> tuple[list[str], list[str], bool]:
    """(inputs, outputs, self_contained) from a cell's AST.

    inputs: function parameters for a definition cell, else the data names the cell reads
    without defining them (library aliases and notebook-level imports/defs excluded).
    self_contained: the cell defines or imports everything it reads.
    """
    if tree is None:
        return [], [], False
    stored, loaded, imported, defined, params = set(), [], set(), [], []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                imported.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.append(node.name)
            if not isinstance(node, ast.ClassDef):
                params += [a.arg for a in node.args.args + node.args.kwonlyargs if a.arg not in ("self", "cls")]
        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Store):
                stored.add(node.id)
            elif node.id not in loaded:
                loaded.append(node.id)
        elif isinstance(node, ast.arg):
            stored.add(node.arg)
    local = stored | imported | set(defined) | BUILTINS
    free = [n for n in loaded if n not in local]
    if defined and not isinstance(tree.body[0], (ast.Import, ast.ImportFrom)) and params:
        inputs = list(dict.fromkeys(params))
    else:
        inputs = [n for n in free if n not in dependencies]
    top_assigned = []
    for stmt in tree.body:
        targets = []
        if isinstance(stmt, ast.Assign):
            targets = stmt.targets
        elif isinstance(stmt, (ast.AugAssign, ast.AnnAssign)):
            targets = [stmt.target]
        for t in targets:
            for n in ast.walk(t):
                if isinstance(n, ast.Name) and n.id not in top_assigned:
                    top_assigned.append(n.id)
    outputs = list(dict.fromkeys(defined + top_assigned))
    return inputs[:8], outputs[:8], not free


def classify_tool(cell: CellRecord, tree: Optional[ast.Module]) -> ToolType:
    code = cell.content
    lines = code_lines(code)
    if not lines:
        return "non_teaching"
    if all(SHELL_LINE_RE.match(l) or SETUP_CALL_RE.search(l) or re.match(r"\s*(import|from)\s", l) for l in lines) \
            and any(SHELL_LINE_RE.match(l) or SETUP_CALL_RE.search(l) for l in lines):
        downloads = any(SHELL_DOWNLOAD_RE.match(l) or LOAD_CALL_RE.search(l) for l in lines)
        installs = any(re.search(r"pip\s+install|apt|conda|nltk\.download|spacy", l) for l in lines)
        return "data_loading" if downloads and not installs else "environment_setup"
    if any(o.content_type == "error" for o in cell.outputs):
        return "debugging"
    if all(re.match(r"\s*(import|from)\s", l) for l in lines):
        return "non_teaching"                                       # import block
    if tree is not None and any(isinstance(n, (ast.FunctionDef, ast.ClassDef)) for n in tree.body):
        return "function"
    loading = sum(bool(LOAD_CALL_RE.search(l)) for l in lines)
    if loading and loading + sum(bool(re.match(r"\s*(import|from)\s|.*\.(head|tail|shape)\b", l)) for l in lines) >= len(lines):
        return "data_loading"
    if len(lines) <= 2 and all(INSPECT_RE.match(l.strip()) for l in lines):
        return "non_teaching"                                       # bare inspection: df.head(), x.shape
    if PLOT_RE.search(code):
        return "visualization"
    if len(MODEL_STEP_RE.findall(code)) >= 2 and len(lines) >= 4:
        return "workflow"
    if (len(lines) >= 4 or re.search(r"^\s*(for|while)\b", code, re.M)) and ARITH_RE.search(code):
        return "implementation"
    return "demonstration"


def humanize(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[_]+", " ", re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name))).strip()


def first_comment(code: str) -> str:
    for line in code.split("\n"):
        s = line.strip()
        if s.startswith("#") and not SEPARATOR_RE.match(s):
            text = re.sub(r"^#+\s*", "", s)
            text = "".join(ch for ch in text if ch.isprintable() and ord(ch) < 0x2190 or ch.isalnum() or ch == " ").strip()
            if len(text.split()) >= 3:
                return text[:120]
        elif s:
            break                                                   # only leading comments
    return ""


VERB = {
    "implementation": "Implements", "demonstration": "Demonstrates", "function": "Defines a function for",
    "workflow": "Runs a workflow for", "visualization": "Visualizes", "data_loading": "Loads data for",
    "environment_setup": "Sets up the environment for", "debugging": "Shows an error case in",
    "non_teaching": "Supports",
}


def build_tools(cells: list[CellRecord], mapper: TopicMapper) -> list[Tool]:
    by_nb: dict[str, list[CellRecord]] = defaultdict(list)
    for c in cells:
        by_nb[c.notebook_id].append(c)
    tools: list[Tool] = []
    for nb_cells in by_nb.values():
        trees = {c.cell_id: parseable(c.content) for c in nb_cells if c.cell_type == "code" and not c.is_empty}
        dependencies = notebook_symbols(list(trees.values()))
        for i, cell in enumerate(nb_cells):
            if cell.cell_type != "code" or cell.is_empty:
                continue
            tree = trees[cell.cell_id]
            tool_type = classify_tool(cell, tree)
            inputs, outputs, self_contained = names_io(tree, dependencies)

            # Nearest explanation: up to 3 cells back, same section, non-trivial markdown
            explanation = ""
            for prev in reversed(nb_cells[max(0, i - 3):i]):
                if prev.cell_type == "markdown" and prev.section_path == cell.section_path \
                        and len(plain_text(prev.content)) >= 40:
                    explanation = first_sentences(prev.content)
                    break

            funcs = [n.name for n in (tree.body if tree else []) if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
            title = (humanize(funcs[0]).capitalize() if funcs else "") or first_comment(cell.content) or cell.section
            n_lines = len(code_lines(cell.content))
            complexity = "low" if n_lines <= 5 else "medium" if n_lines <= 20 else "high"
            has_error = any(o.content_type == "error" for o in cell.outputs)
            teaching = tool_type in ANSWER_ELIGIBLE
            context = " ".join(cell.section_path + [title] + funcs + cell.libraries)
            tools.append(Tool(
                tool_id="",                                         # numbered below
                cell_id=cell.cell_id,
                title=title,
                description=explanation,
                tool_type=tool_type,
                libraries=cell.libraries,
                code=cell.content,
                purpose=f"{VERB[tool_type]} {cell.section}",
                inputs=inputs,
                outputs=outputs,
                concepts=concepts_for(cell),
                topic_ids=mapper.topics(cell.notebook_id, context),
                source=Source(notebook_id=cell.notebook_id, notebook_title=cell.notebook_title,
                              section_path=" > ".join(cell.section_path) or config.DEFAULT_SECTION,
                              cell_ids=[cell.cell_index]),
                quality=ToolQuality(
                    is_teaching_code=teaching,
                    is_self_contained=self_contained,
                    has_output=any(o.content_type != "error" for o in cell.outputs),
                    has_error_output=has_error,
                    has_explanation_nearby=bool(explanation),
                    complexity=complexity,
                    suitable_for_answer=teaching and not has_error and tree is not None
                    and not (tool_type == "demonstration" and n_lines <= 1 and not cell.outputs),
                ),
                tags=sorted(set(cell.libraries) | {tool_type}),
                created_at=cell.ingested_at,
            ))
    for n, t in enumerate(tools, 1):
        t.tool_id = f"TOOL_{n:04d}"
    return tools


# ----------------------------------------------------------------------------
# Resources
# ----------------------------------------------------------------------------
# Image types are not guessed from nearby text: a spot check found keyword guesses wrong half the
# time (a table labelled formula_image because the caption said "formulating", a handwritten
# derivation labelled screenshot). Markdown images stay `unclassified` until a vision model
# classifies them; plots, decoratives and unreachable external images are known from structure.
EXT_FORMAT = {"png": "png", "jpg": "jpeg", "jpeg": "jpeg", "gif": "gif", "svg": "svg", "webp": "webp", "bmp": "bmp"}
DECORATIVE_MAX_PX = 48


def image_size(data: bytes) -> tuple[Optional[int], Optional[int]]:
    """Width/height from PNG, GIF or JPEG headers (stdlib only)."""
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", data[16:24])
        if data[:6] in (b"GIF87a", b"GIF89a"):
            return struct.unpack("<HH", data[6:10])
        if data[:2] == b"\xff\xd8":
            i = 2
            while i < len(data) - 9:
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    h, w = struct.unpack(">HH", data[i + 5:i + 9])
                    return w, h
                i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    except struct.error:
        pass
    return None, None


def markdown_images(raw_source: str) -> list[tuple[str, str]]:
    """(alt text, src) for every markdown or HTML image, in order of appearance."""
    found = [(m.start(), m.group(1), m.group(2)) for m in MD_IMG_RE.finditer(raw_source)]
    for m in HTML_IMG_TAG_RE.finditer(raw_source):
        src = HTML_SRC_RE.search(m.group(0))
        if src:
            alt = HTML_ALT_RE.search(m.group(0))
            found.append((m.start(), alt.group(1) if alt else "", src.group(1)))
    return [(alt, src) for _, alt, src in sorted(found)]


def save_image(images_dir: Path, name: str, fmt: str, data: bytes, root: Path) -> str:
    images_dir.mkdir(parents=True, exist_ok=True)
    path = images_dir / f"{name}.{fmt}"
    if not path.exists() or path.read_bytes() != data:
        path.write_bytes(data)
    return str(path.relative_to(root)) if path.is_relative_to(root) else str(path)


def build_resources(cells: list[CellRecord], tools: list[Tool], mapper: TopicMapper,
                    raw_dir: Path, out_dir: Path) -> list[Resource]:
    images_dir = out_dir / IMAGES_DIR
    root = config.ROOT
    tool_by_cell = {t.cell_id: t.tool_id for t in tools}
    raw_cells: dict[str, list[dict]] = {}
    for c in cells:
        if c.notebook_id not in raw_cells:
            raw_cells[c.notebook_id] = read_notebook(raw_dir / c.file_name)[0]["cells"]
    by_nb: dict[str, list[CellRecord]] = defaultdict(list)
    for c in cells:
        by_nb[c.notebook_id].append(c)

    resources: list[Resource] = []
    for nb_id, nb_cells in by_nb.items():
        for i, cell in enumerate(nb_cells):
            raw = raw_cells[nb_id][cell.cell_index]
            items: list[dict] = []                                  # pending resources for this cell
            if cell.cell_type == "markdown" and cell.contains_image:
                attachments = raw.get("attachments") or {}
                for n, (alt, src) in enumerate(markdown_images(to_text(raw.get("source", "")))):
                    item = {"n": n, "alt": alt.strip(), "kind": "markdown"}
                    m = DATA_URI_RE.match(src)
                    if m:
                        item.update(location="embedded", mime=m.group(1), data=base64.b64decode(m.group(2)))
                    elif src.startswith("attachment:") and src[11:] in attachments:
                        mime, b64 = next(iter(attachments[src[11:]].items()))
                        item.update(location="embedded", mime=mime, data=base64.b64decode(b64))
                    else:
                        item.update(location="google_drive" if "drive.google" in src else "url", url=src)
                    items.append(item)
            elif cell.cell_type == "code":
                n = 0
                for o in raw.get("outputs") or []:
                    for mime, payload in sorted((o.get("data") or {}).items()):
                        if mime.startswith("image/"):
                            data = to_text(payload).encode() if mime == "image/svg+xml" \
                                else base64.b64decode(to_text(payload))
                            items.append({"n": n, "alt": "", "kind": "plot", "location": "embedded",
                                          "mime": mime, "data": data})
                            n += 1
                            break                                   # one image per output
            if not items:
                continue

            # Nearby markdown: this cell's own text, else the closest markdown in the same section
            nearby = plain_text(cell.content) if cell.cell_type == "markdown" else ""
            if len(nearby) < 30:
                for j in [i - 1, i + 1, i - 2, i + 2]:
                    if 0 <= j < len(nb_cells) and nb_cells[j].cell_type == "markdown" \
                            and nb_cells[j].section_path == cell.section_path:
                        text = plain_text(nb_cells[j].content)
                        if len(text) >= 30:
                            nearby = text
                            break
            nearby = first_sentences(nearby) if nearby else ""
            near_tools = [tool_by_cell[c.cell_id] for c in nb_cells[max(0, i - 5):i + 6]
                          if c.cell_id in tool_by_cell and c.section_path == cell.section_path][:3]

            for item in items:
                alt = item["alt"]
                meaningful_alt = alt and not FILENAME_LIKE_RE.match(alt)
                fmt, local_path, width, height, size = None, None, None, None, None
                if item["location"] == "embedded":
                    fmt = item["mime"].split("/")[1].replace("svg+xml", "svg").replace("jpg", "jpeg")
                    width, height = image_size(item["data"])
                    size = len(item["data"])
                    local_path = save_image(images_dir, f"{cell.cell_id}_{item['n']}", fmt, item["data"], root)
                else:
                    ext = re.search(r"\.(png|jpe?g|gif|svg|webp|bmp)(\?|$)", item["url"], re.I)
                    fmt = EXT_FORMAT.get(ext.group(1).lower()) if ext else None
                decorative = bool(width and height and max(width, height) <= DECORATIVE_MAX_PX)
                if item["kind"] == "plot":
                    rtype: ResourceType = "plot"
                elif item["location"] != "embedded":
                    rtype = "external_reference"
                else:
                    rtype = "decorative" if decorative else "unclassified"
                if item["kind"] == "plot":
                    caption = Caption(source="nearby_markdown" if nearby else "none", text=nearby)
                    linked = [tool_by_cell[cell.cell_id]] if cell.cell_id in tool_by_cell else []
                elif meaningful_alt:
                    caption = Caption(source="alt_text", text=alt)
                    linked = near_tools
                else:
                    caption = Caption(source="nearby_markdown" if nearby else "none", text=nearby)
                    linked = near_tools
                available = item["location"] == "embedded"
                resources.append(Resource(
                    resource_id="",
                    cell_id=cell.cell_id,
                    title=alt if meaningful_alt else (f"Plot: {cell.section}" if item["kind"] == "plot" else cell.section),
                    description=nearby,
                    resource_type=rtype,
                    availability="embedded" if available else "external_unavailable",
                    source=Source(notebook_id=nb_id, notebook_title=cell.notebook_title,
                                  section_path=" > ".join(cell.section_path) or config.DEFAULT_SECTION,
                                  cell_ids=[cell.cell_index]),
                    image_reference=ImageReference(
                        location=item["location"], url=item.get("url"), local_path=local_path, format=fmt,
                        width=width, height=height, bytes=size),
                    caption=caption,
                    concepts=concepts_for(cell),
                    topic_ids=mapper.topics(nb_id, " ".join(cell.section_path + [alt])),
                    linked_tool_ids=linked,
                    retrieval_status="unavailable" if not available
                    else "excluded_decorative" if decorative else "excluded_from_v1",
                    quality=ResourceQuality(
                        is_meaningful=not decorative,
                        is_decorative=decorative,
                        contains_formula=False if rtype in ("plot", "decorative") else None,
                        contains_diagram=False if rtype in ("plot", "decorative") else None,
                        contains_worked_example=False if rtype in ("plot", "decorative") else None,
                        requires_vision_model=not decorative,
                    ),
                    created_at=cell.ingested_at,
                ))
    for n, r in enumerate(resources, 1):
        r.resource_id = f"RES_{n:04d}"
    return resources


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def load_cells(path: Path) -> list[CellRecord]:
    with path.open(encoding="utf-8") as f:
        return [CellRecord.model_validate_json(line) for line in f if line.strip()]


def run(processed_dir: Path = config.PROCESSED_DIR, raw_dir: Path = config.RAW_NOTEBOOKS_DIR,
        quiet: bool = False) -> tuple[list[Tool], list[Resource]]:
    cells_path = processed_dir / config.CELLS_JSONL
    if not cells_path.exists():
        raise SystemExit(f"{cells_path} not found; run src/ingestion.py first")
    cells = load_cells(cells_path)
    catalog = json.loads(config.TOPIC_CATALOG.read_text(encoding="utf-8")) if config.TOPIC_CATALOG.exists() else {}
    mapper = TopicMapper(catalog)
    tools = build_tools(cells, mapper)
    resources = build_resources(cells, tools, mapper, raw_dir, processed_dir)
    for name, records in ((TOOLS_JSONL, tools), (RESOURCES_JSONL, resources)):
        (processed_dir / name).write_text(
            "".join(json.dumps(r.model_dump(), ensure_ascii=False) + "\n" for r in records),
            encoding="utf-8", newline="\n")
    if not quiet:
        from collections import Counter
        print(f"{len(tools)} tools: " + ", ".join(f"{k} {v}" for k, v in Counter(t.tool_type for t in tools).most_common()))
        print(f"  answer-eligible: {sum(t.quality.suitable_for_answer for t in tools)}")
        print(f"{len(resources)} resources: " + ", ".join(
            f"{k} {v}" for k, v in Counter(r.resource_type for r in resources).most_common()))
        print("  availability: " + ", ".join(
            f"{k} {v}" for k, v in Counter(r.availability for r in resources).most_common()))
    return tools, resources


if __name__ == "__main__":
    run()
