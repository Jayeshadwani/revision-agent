"""
Parse one Jupyter/Colab notebook into structured, traceable cell records (Phase 1).

Cleaning here is deliberately conservative: Unicode and whitespace are normalized, and
nothing else is removed.

Sections are assigned per heading span (phase1-v2, PH1-FIX-001): every markdown cell is split
at its headings into contiguous spans that reproduce the cell's `content` exactly, and each span
carries its own section path. Text before a cell's first heading continues the previous section,
or is `Preamble` when the notebook has no heading yet. Headings, LaTeX, tables, lists, code comments, instructor notes
and MCQ blocks are kept in `content` and only *flagged*. Heavier cleaning and chunking
belong to Phase 2. Outputs are stored separately from the cell source.

Detection is rule-based (no LLM) so runs are reproducible and failures are debuggable.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

import config

try:  # nbformat is preferred; fall back to a strict JSON reader if it is not installed
    import nbformat
except ImportError:  # pragma: no cover - depends on the environment
    nbformat = None


# ----------------------------------------------------------------------------
# Record schemas
# ----------------------------------------------------------------------------
OutputRole = Literal["teaching_text", "result", "log", "dataframe_dump", "error"]


class Output(BaseModel):
    output_type: str                 # stream | execute_result | display_data | error
    content_type: str                # text | table | html | image | error | widget | javascript | other
    content: str                     # text form ('' for images/widgets)
    mime_types: list[str] = []
    output_role: OutputRole = "result"
    truncated: bool = False          # content was cut at the limit for its role
    original_length: int = 0         # characters before truncation


class Heading(BaseModel):
    level: int
    text: str                        # cleaned display text
    structural: bool                 # False for block labels such as "Question" / "Choices"


SpanKind = Literal["heading", "label", "continuation", "preamble"]


class Span(BaseModel):
    """A contiguous slice of a markdown cell's `content` under one section.

    kind: heading      starts at a structural heading
          label        starts at a block label (Question / Choices / Code); section unchanged
          continuation text before the cell's first heading, continuing the previous section
          preamble     text before the notebook's first heading (section_path is [])
    char_start/char_end index into the cell's `content`; spans are contiguous and their
    contents concatenate to `content` exactly.
    """
    span_id: str
    cell_id: str
    notebook_id: str
    span_index: int
    kind: SpanKind
    heading_level: Optional[int]
    heading_text: Optional[str]
    section_title: str
    section_path: list[str]
    content: str
    char_start: int
    char_end: int
    contains_math: bool
    contains_table: bool
    contains_list: bool


class CellRecord(BaseModel):
    cell_id: str
    notebook_id: str
    notebook_title: str
    file_name: str
    cell_index: int                  # 0-based position in the notebook (Colab shows index + 1)
    cell_type: Literal["markdown", "code", "raw"]
    section: str
    section_path: list[str]          # heading hierarchy, outermost first
    headings: list[Heading]          # headings defined inside this cell
    spans: list[Span]                # markdown cells only; empty for code cells and empty cells
    span_count: int
    has_multiple_sections: bool
    section_accuracy_status: Literal["ok", "fixed", "preamble"]
    content: str
    content_length_chars: int
    is_empty: bool
    is_short: bool
    contains_math: bool
    contains_latex: bool
    formula_heavy: bool
    math_block_count: int
    contains_code: bool
    contains_table: bool
    contains_list: bool
    contains_image: bool             # markdown image reference (diagram, screenshot, formula image)
    image_refs: list[str]
    contains_plot: bool              # image output or plotting call
    contains_instructor_note: bool
    contains_mcq: bool
    outputs: list[Output]
    has_output: bool
    libraries: list[str]
    execution_count: Optional[int]
    warnings: list[str]
    ingested_at: str
    source_hash: str


class NotebookRecord(BaseModel):
    notebook_id: str
    file_name: str
    notebook_title: str
    file_sha256: str
    nbformat: str
    parse_status: Literal["success", "failed"]
    parse_error: str = ""
    reader: str = ""                 # nbformat | json
    total_cells: int = 0
    markdown_cells: int = 0
    code_cells: int = 0
    raw_cells: int = 0
    empty_cells: int = 0
    math_cells: int = 0
    code_with_output_cells: int = 0
    plot_cells: int = 0
    table_cells: int = 0
    image_ref_cells: int = 0
    instructor_note_cells: int = 0
    mcq_cells: int = 0
    error_output_cells: int = 0
    heading_count: int = 0
    span_count: int = 0
    multi_section_cells: int = 0     # markdown cells split into more than one section
    preamble_only_cells: int = 0     # non-empty markdown cells entirely before the first heading
    section_mislabel_rate: Optional[float] = None         # filled by ingestion's accuracy check
    legacy_section_mislabel_rate: Optional[float] = None  # same check, phase1-v1 cell-level rule
    teaching_outputs: int = 0
    libraries: list[str] = []
    outline: list[dict] = []         # [{cell_index, level, text}] for structural headings
    warnings: list[str] = []
    ingested_at: str = ""


# ----------------------------------------------------------------------------
# Patterns
# ----------------------------------------------------------------------------
FILE_NAME_RE = re.compile(r"^(\d+)\s*-\s*(.+?)\.ipynb$")
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
# ATX heading (CommonMark): up to 3 leading spaces, 1-6 '#', then a space/tab or end of line.
# "#text" without a space is not a heading (78 such lines in the corpus stay plain text).
MD_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
CLOSING_HASHES_RE = re.compile(r"(?:^|[ \t]+)#+[ \t]*$")
SETEXT_UNDERLINE_RE = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
THEMATIC_BREAK_RE = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
BLOCK_START_RE = re.compile(r"^ {0,3}(#|>|[-*+][ \t]|\d{1,9}[.)][ \t]|\||<|`{3,}|~{3,})")
HTML_HEADING_RE = re.compile(r"<h([1-6])\b[^>]*>(.*?)</h\1>", re.I | re.S)

DISPLAY_MATH_RE = re.compile(r"\$\$(.+?)\$\$", re.S)
INLINE_MATH_RE = re.compile(r"(?<![\\$])\$(?![\s$])([^$\n]+?)(?<![\s\\])\$(?!\$|\d)")
MATH_CHARS_RE = re.compile(r"[\\^_{}=]")
LATEX_ENV_RE = re.compile(r"\\begin\{(equation|align|gather|eqnarray|matrix|bmatrix|pmatrix|cases)\*?\}")
LATEX_CMD_RE = re.compile(
    r"\\(frac|dfrac|sum|int|prod|sqrt|partial|nabla|cdot|times|hat|bar|vec|log|exp|mathbf|mathrm|"
    r"mathcal|left|right|leq|geq|neq|approx|infty|alpha|beta|gamma|delta|epsilon|theta|lambda|mu|"
    r"sigma|pi|rho|tau|phi|omega|Sigma|Delta|Theta|Lambda|Omega)\b"
)
# Arrows and "×" are left out: in these notes they are mostly prose arrows and sizes like 3×3.
UNICODE_MATH_RE = re.compile(r"[α-ωΑ-Ω∑∏∫√∂∇≤≥≠≈∞±÷∈∉⊂∪∩∝₀-₉⁰-⁹ᵢⱼₙ]")

PIPE_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$", re.M)
HTML_TABLE_RE = re.compile(r"<table\b", re.I)
LIST_RE = re.compile(r"^\s*([-*+]|\d+[.)])\s+\S", re.M)
MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(\s*<?([^)\s>]+)")
HTML_IMG_RE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"']?([^\"'\s>]+)", re.I)

INSTRUCTOR_RE = re.compile(
    r"\[\s*(note to instructor|note for instructor|instructor note|ask learners)[^\]]*\]|\binstructors?\b", re.I
)
MCQ_Q_RE = re.compile(r"^#+\s*question\s*$", re.I | re.M)
MCQ_C_RE = re.compile(r"^#+\s*choices?\s*$", re.I | re.M)

IMPORT_RE = re.compile(r"^\s*import\s+([\w.]+(?:\s+as\s+\w+)?(?:\s*,\s*[\w.]+(?:\s+as\s+\w+)?)*)", re.M)
FROM_IMPORT_RE = re.compile(r"^\s*from\s+([\w.]+)\s+import\b", re.M)
PLOT_CALL_RE = re.compile(
    r"\b(plt|sns|px|go|ax|axes|axs|fig)\.\w+\(|\.plot\(|\.hist\(|\bimshow\(|\.heatmap\(|\bplot_\w+\("
)

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
TAG_RE = re.compile(r"<[^>]+>")
ZERO_WIDTH_RE = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
DATA_URI_RE = re.compile(r"data:(image/[\w.+-]+);base64,[A-Za-z0-9+/=\s]+")
EMPHASIS_RE = re.compile(r"(\*\*|__|\*|`)")
ANCHOR_RE = re.compile(r"\{#[^}]*\}")
MD_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def to_text(value) -> str:
    """Notebook text fields are a string or a list of strings."""
    if isinstance(value, list):
        return "".join(value)
    return value or ""


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def clean_text(text: str, strip_data_uris: bool = False) -> str:
    """Conservative normalization: Unicode NFC, newlines, trailing spaces, repeated blank lines.

    With strip_data_uris, base64 image payloads embedded in markdown are replaced by a short
    placeholder (alt text and image type are kept). Leading indentation, LaTeX, markup,
    tables and comments are untouched.
    """
    if strip_data_uris:
        text = DATA_URI_RE.sub(lambda m: f"data:{m.group(1)};base64,<embedded image omitted>", text)
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = ZERO_WIDTH_RE.sub("", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n")


def is_emoji_like(ch: str) -> bool:
    return unicodedata.category(ch) == "So" or ch in "\ufe0f\u20e3"


def clean_heading(text: str) -> str:
    """Display text for a heading: no HTML, emphasis, emoji or anchors."""
    text = ANCHOR_RE.sub("", text)
    text = MD_LINK_RE.sub(r"\1", text)
    text = html.unescape(TAG_RE.sub("", text))
    text = EMPHASIS_RE.sub("", text)
    text = "".join(ch for ch in text if not is_emoji_like(ch))
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip(" :-–—|").strip()


def outside_fences(text: str) -> list[str]:
    """Markdown lines that are not inside ``` / ~~~ fences (fence lines themselves excluded)."""
    return [line for line, fenced in fence_states(text.split("\n")) if not fenced]


def fence_states(lines: list[str]) -> list[tuple[str, bool]]:
    """(line, is_fenced_or_fence_line) per line. A fence closes on the same character with at
    least the opening length (CommonMark); an unclosed fence runs to the end of the cell."""
    out, fence = [], None
    for line in lines:
        m = FENCE_RE.match(line)
        if fence is None:
            if m:
                fence = m.group(1)
                out.append((line, True))
            else:
                out.append((line, False))
        else:
            out.append((line, True))
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) \
                    and not line.strip()[len(m.group(1)):].strip():
                fence = None
    return out


class HeadingMatch(BaseModel):
    start: int                       # offset of the first line of the heading block in the text
    level: int
    raw: str                         # heading text as written (before clean_heading)
    style: Literal["atx", "setext", "html"]


def _is_paragraph_line(line: str) -> bool:
    return bool(line.strip()) and not BLOCK_START_RE.match(line) and not THEMATIC_BREAK_RE.match(line) \
        and not SETEXT_UNDERLINE_RE.match(line)


def scan_headings(text: str) -> list[HeadingMatch]:
    """All headings in a markdown text with their character offsets, in order.

    Supported: ATX (`#`-`######`, up to 3 leading spaces, optional closing #s), Setext
    (a paragraph underlined with `===` -> level 1 or `---` -> level 2) and HTML <h1>-<h6>.
    Lines inside fenced code blocks are never headings. A `---` line that does not follow a
    paragraph line is a thematic break, not a heading.
    """
    lines = text.split("\n")
    offsets, pos = [], 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1
    states = fence_states(lines)
    found: list[HeadingMatch] = []
    para_start: Optional[int] = None             # line index where the current paragraph began
    for i, (line, fenced) in enumerate(states):
        if fenced:
            para_start = None
            continue
        m = MD_HEADING_RE.match(line)
        if m:
            body = CLOSING_HASHES_RE.sub("", m.group(2) or "")
            found.append(HeadingMatch(start=offsets[i], level=len(m.group(1)), raw=body.strip(), style="atx"))
            para_start = None
            continue
        u = SETEXT_UNDERLINE_RE.match(line)
        if u and para_start is not None:
            raw = " ".join(l.strip() for l in lines[para_start:i])
            level = 1 if u.group(1)[0] == "=" else 2
            found.append(HeadingMatch(start=offsets[para_start], level=level, raw=raw, style="setext"))
            para_start = None
            continue
        h = HTML_HEADING_RE.search(line)
        if h and not TAG_RE.sub("", line[: h.start()]).strip():     # e.g. "<center><h3>…</h3>"
            found.append(HeadingMatch(start=offsets[i], level=int(h.group(1)), raw=h.group(2), style="html"))
            para_start = None
            continue
        if _is_paragraph_line(line):
            if para_start is None:
                para_start = i
        else:
            para_start = None
    return found


def to_heading(m: HeadingMatch) -> Heading:
    cleaned = clean_heading(m.raw)
    structural = bool(cleaned) and cleaned.lower().rstrip("?.") not in config.NON_STRUCTURAL_HEADINGS
    return Heading(level=m.level, text=cleaned, structural=structural)


def find_headings(text: str) -> list[Heading]:
    return [to_heading(m) for m in scan_headings(text)]


def is_trivial(text: str) -> bool:
    """Only blank lines and thematic breaks (e.g. a leading '---')."""
    return all(not line.strip() or THEMATIC_BREAK_RE.match(line) for line in text.split("\n"))


def split_spans(text: str) -> list[tuple[int, int, Optional[Heading]]]:
    """(start, end, heading) slices of a markdown text, cut at each heading.

    The slices are contiguous and cover the text exactly. A leading slice that holds only
    blank lines or thematic breaks is merged into the first heading's slice.
    """
    matches = scan_headings(text)
    cuts = [m.start for m in matches]
    heads = [to_heading(m) for m in matches]
    if not text:
        return []
    bounds: list[tuple[int, Optional[Heading]]] = []
    if not cuts or cuts[0] > 0:
        bounds.append((0, None))
    bounds += list(zip(cuts, heads))
    if len(bounds) > 1 and bounds[0][1] is None and is_trivial(text[: bounds[1][0]]):
        bounds = [(0, bounds[1][1])] + bounds[2:]
    out = []
    for i, (start, head) in enumerate(bounds):
        end = bounds[i + 1][0] if i + 1 < len(bounds) else len(text)
        out.append((start, end, head))
    return out


def unescaped_dollars(text: str) -> int:
    lines = outside_fences(text)
    body = "\n".join(lines)
    body = re.sub(r"`[^`\n]*`", "", body)              # inline code spans
    return len(re.findall(r"(?<!\\)\$", body))


def math_signals(text: str) -> dict:
    display = DISPLAY_MATH_RE.findall(text)
    no_display = DISPLAY_MATH_RE.sub(" ", text)
    inline = [m for m in INLINE_MATH_RE.findall(no_display) if MATH_CHARS_RE.search(m) or LATEX_CMD_RE.search(m)]
    envs = LATEX_ENV_RE.findall(text)
    cmds = LATEX_CMD_RE.findall(text)
    contains_latex = bool(display or inline or envs or cmds)
    unicode_math = bool(UNICODE_MATH_RE.search(text))
    blocks = len(display) + len(envs) + len(inline)
    return {
        "contains_latex": contains_latex,
        "contains_math": contains_latex or unicode_math,
        "math_block_count": blocks,
        "formula_heavy": (len(display) + len(envs)) >= 1 or len(inline) >= 3,
        "unbalanced": unescaped_dollars(text) % 2 == 1,
    }


def libraries_in(code: str) -> list[str]:
    libs = set()
    for m in IMPORT_RE.finditer(code):
        for part in m.group(1).split(","):
            name = part.strip().split()[0].split(".")[0]
            if name:
                libs.add(name)
    for m in FROM_IMPORT_RE.finditer(code):
        name = m.group(1).split(".")[0]
        if name:
            libs.add(name)
    return sorted(libs)


LOG_LINE_RE = re.compile(
    r"^\s*(Requirement already satisfied|Collecting |Downloading|Installing collected|Successfully "
    r"|Building wheel|Using cached|Attempting uninstall|Found existing|Uninstalling|inflating:|creating:"
    r"|extracting:|Archive:|--\d{4}-\d\d-\d\d|Resolving |Connecting to|HTTP request sent|Length: |Saving to"
    r"|Epoch \d+|\d+/\d+ \[|\[nltk_data\]|WARNING|Cloning into|Get:\d|Hit:\d|Ign:\d|Reading package"
    r"|Building dependency|Reading state|Selecting previously|Preparing to unpack|Unpacking |Setting up "
    r"|Processing triggers|From: |To: |\S+\.py:\d+: \w*Warning|  warnings\.warn|\d+%\||\[t-SNE\]"
    r"|total \d+$|[d-][rwx-]{9}\.?\s|UNRAR |Extracting from|Extracting  )"
    r"|━|\[=+>?\.*\]|\d+/\d+ [━=]|[kMG]B/s|\beta \d+:\d\d"
)
DUMP_HINT_RE = re.compile(r"^\[\d+ rows x \d+ columns\]$|^Name: .*dtype: |^dtype: |^\s*array\(\[", re.M)
STRONG_LOG_START_RE = re.compile(
    r"^\s*(Requirement already satisfied|Collecting |Downloading|Looking in indexes|Streaming output truncated"
    r"|Archive:|inflating:|Epoch \d+|--\d{4}-\d\d-\d\d|Cloning into|Reading package lists|\[nltk_data\]"
    r"|Get:\d|Hit:\d|\S+\.py:\d+: \w*Warning)"
)
REPR_START_RE = re.compile(
    r"^\s*(\[\{|\[\(|\{['\"\d]|\(|\[\[|\[\d|\[['\"<]|<\w+[ .]|[A-Z]\w*\(|array\(|tensor\(|Index\(|tf\.Tensor|Model: |[┏┃│])"
)
SEPARATOR_LINE_RE = re.compile(r"^[\s=\-_*#~.·•━─│┃┏┳┓┗┻┛╇╈╍┄]+$")
WORD_RE = re.compile(r"[A-Za-z]{2,}")


def classify_output(kind: str, content_type: str, text: str, stream_name: str = "") -> OutputRole:
    """Rule-based role of an output, decided on the full text before any truncation.

    error          error outputs
    log            stderr, installs/downloads/unzips, training progress, warnings
    dataframe_dump table or pandas/numpy repr longer than LARGE_TABLE_LINES lines
    result         short tables, values, metrics, object reprs, model summaries
    teaching_text  printed prose: most lines are sentences/phrases (e.g. a printed lesson)
    """
    if kind == "error" or content_type == "error":
        return "error"
    lines = [l for l in text.split("\n") if l.strip() and not SEPARATOR_LINE_RE.match(l)]
    if stream_name == "stderr" or not lines:
        return "log" if stream_name == "stderr" else "result"
    if STRONG_LOG_START_RE.match(lines[0]) or \
            sum(bool(LOG_LINE_RE.search(l)) for l in lines) / len(lines) >= 0.3:
        return "log"
    if content_type == "table" or DUMP_HINT_RE.search(text):
        return "dataframe_dump" if len(lines) > config.LARGE_TABLE_LINES else "result"
    if REPR_START_RE.match(lines[0]) or "Total params:" in text or \
            sum(l.lstrip()[:1] in "┏┃│┡└├" for l in lines) / len(lines) >= 0.3:
        return "result"                                  # object reprs, model summaries
    body = "".join(text.split())
    if body and sum(ch.isdigit() for ch in body) / len(body) > 0.15:
        return "result"                                  # number-heavy printouts: metrics, scores
    words = sum(len(WORD_RE.findall(l)) for l in lines)
    wordy = sum(len(WORD_RE.findall(l)) >= 3 for l in lines)
    if words >= 25 and wordy / len(lines) >= 0.5:
        return "teaching_text"
    return "result"


def parse_output(o: dict) -> Output:
    kind = o.get("output_type", "")
    if kind == "stream":
        return _text_output(kind, "text", to_text(o.get("text", "")), ["text/plain"], o.get("name", ""))
    if kind == "error":
        text = f"{o.get('ename', '')}: {o.get('evalue', '')}"
        return _text_output(kind, "error", text, [])
    data = o.get("data") or {}
    mimes = sorted(data)
    plain = to_text(data.get("text/plain", ""))
    html_text = to_text(data.get("text/html", ""))
    if any(m.startswith("image/") for m in mimes):
        return Output(output_type=kind, content_type="image", content="", mime_types=mimes)
    if html_text and HTML_TABLE_RE.search(html_text):
        return _text_output(kind, "table", plain or html.unescape(TAG_RE.sub(" ", html_text)), mimes)
    if plain:
        return _text_output(kind, "text", plain, mimes)
    if html_text:
        return _text_output(kind, "html", html.unescape(TAG_RE.sub(" ", html_text)), mimes)
    if "application/vnd.jupyter.widget-view+json" in data:
        return Output(output_type=kind, content_type="widget", content="", mime_types=mimes)
    if "application/javascript" in data:
        return Output(output_type=kind, content_type="javascript", content="", mime_types=mimes)
    return Output(output_type=kind, content_type="other", content="", mime_types=mimes)


def _text_output(kind: str, content_type: str, text: str, mimes: list[str], stream_name: str = "") -> Output:
    text = clean_text(ANSI_RE.sub("", text))
    role = classify_output(kind, content_type, text, stream_name)
    limit = config.MAX_TEACHING_OUTPUT_CHARS if role in ("teaching_text", "result") else config.MAX_OUTPUT_CHARS
    original_length = len(text)
    truncated = original_length > limit
    if truncated:
        text = text[:limit]
    return Output(output_type=kind, content_type=content_type, content=text, mime_types=mimes,
                  output_role=role, truncated=truncated, original_length=original_length)


# ----------------------------------------------------------------------------
# Reading
# ----------------------------------------------------------------------------
def read_notebook(path: Path) -> tuple[dict, str]:
    """Return (notebook dict, reader name). Raises ValueError on a malformed notebook."""
    if nbformat is not None:
        nb = nbformat.read(str(path), as_version=4)
        nbformat.validate(nb)
        return json.loads(nbformat.writes(nb)), "nbformat"
    with path.open(encoding="utf-8") as f:
        nb = json.load(f)
    if nb.get("nbformat") != 4:
        raise ValueError(f"unsupported nbformat {nb.get('nbformat')}")
    if not isinstance(nb.get("cells"), list):
        raise ValueError("notebook has no 'cells' list")
    for i, cell in enumerate(nb["cells"]):
        if cell.get("cell_type") not in ("markdown", "code", "raw"):
            raise ValueError(f"cell {i}: unknown cell_type {cell.get('cell_type')!r}")
        if "source" not in cell:
            raise ValueError(f"cell {i}: missing 'source'")
    return nb, "json"


def notebook_identity(path: Path) -> tuple[str, str]:
    m = FILE_NAME_RE.match(path.name)
    if m:
        return f"nb_{int(m.group(1)):02d}", re.sub(r"\s+", " ", m.group(2)).strip()
    stem = re.sub(r"\W+", "_", path.stem).strip("_").lower()
    return f"nb_{stem}", path.stem


# ----------------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------------
def parse_notebook(path: Path) -> tuple[NotebookRecord, list[CellRecord]]:
    raw_bytes = path.read_bytes()
    nb_id, title = notebook_identity(path)
    ingested_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = NotebookRecord(
        notebook_id=nb_id, file_name=path.name, notebook_title=title,
        file_sha256="sha256:" + hashlib.sha256(raw_bytes).hexdigest(),
        nbformat="", parse_status="success", ingested_at=ingested_at,
    )
    try:
        nb, reader = read_notebook(path)
    except Exception as exc:  # documented failure, not a crash
        record.parse_status = "failed"
        record.parse_error = f"{type(exc).__name__}: {exc}"
        record.warnings.append("parse_failed")
        return record, []
    record.reader = reader
    record.nbformat = f"{nb.get('nbformat')}.{nb.get('nbformat_minor')}"

    cells: list[CellRecord] = []
    stack: list[tuple[int, str]] = []
    libraries: set[str] = set()

    def push(h: Heading) -> None:
        while stack and stack[-1][0] >= h.level:
            stack.pop()
        stack.append((h.level, h.text))

    for idx, cell in enumerate(nb["cells"]):
        ctype = cell.get("cell_type")
        raw_source = to_text(cell.get("source", ""))
        is_text = ctype in ("markdown", "raw")
        content = clean_text(raw_source, strip_data_uris=is_text)
        cell_id = f"{nb_id}_cell_{idx:03d}"
        headings: list[Heading] = []
        spans: list[Span] = []
        if ctype == "markdown" and content.strip():
            for start, end, head in split_spans(content):
                if head is not None:
                    headings.append(head)
                    if head.structural:
                        push(head)
                span_path = [t for _, t in stack]
                if head is None:
                    kind = "continuation" if span_path else "preamble"
                else:
                    kind = "heading" if head.structural else "label"
                piece = content[start:end]
                sig = math_signals(piece)
                spans.append(Span(
                    span_id=f"{cell_id}_span_{len(spans):03d}", cell_id=cell_id, notebook_id=nb_id,
                    span_index=len(spans), kind=kind,
                    heading_level=head.level if head else None, heading_text=head.text if head else None,
                    section_title=span_path[-1] if span_path else config.DEFAULT_SECTION, section_path=span_path,
                    content=piece, char_start=start, char_end=end,
                    contains_math=sig["contains_math"],
                    contains_table=bool(PIPE_TABLE_SEP_RE.search(piece) or HTML_TABLE_RE.search(piece)),
                    contains_list=bool(LIST_RE.search("\n".join(outside_fences(piece)))),
                ))
        if spans:
            # Cell-level section (kept for compatibility): the span holding the most text.
            primary = max(spans, key=lambda sp: (len(sp.content.strip()), -sp.span_index))
            section_path = primary.section_path
        else:
            section_path = [t for _, t in stack]       # code / empty cells: the governing section
        section = section_path[-1] if section_path else config.DEFAULT_SECTION
        sections_in_cell = {tuple(sp.section_path) for sp in spans if not is_trivial(sp.content)}
        multiple = len(sections_in_cell) > 1
        if multiple:
            accuracy_status = "fixed"
        elif spans and all(sp.kind == "preamble" for sp in spans):
            accuracy_status = "preamble"
        else:
            accuracy_status = "ok"

        warnings: list[str] = []
        math = math_signals(content) if is_text else {
            "contains_latex": False, "contains_math": False, "math_block_count": 0,
            "formula_heavy": False, "unbalanced": False,
        }
        if math["unbalanced"]:
            warnings.append("unbalanced_math_delimiters")
        if "\ufffd" in content:
            warnings.append("encoding_replacement_char")

        outputs = [parse_output(o) for o in (cell.get("outputs") or [])] if ctype == "code" else []
        if any(o.truncated for o in outputs):
            warnings.append("output_truncated")
        if any(o.content_type == "error" for o in outputs):
            warnings.append("error_output")

        image_refs = [
            ref.split(",", 1)[0] if ref.startswith("data:") else ref     # "data:image/png;base64" or URL
            for ref in MD_IMAGE_RE.findall(content) + HTML_IMG_RE.findall(content)
        ] if is_text else []
        libs = libraries_in(content) if ctype == "code" else []
        libraries.update(libs)

        is_empty = not content.strip()
        if is_empty:
            warnings.append("empty_cell")
        cells.append(CellRecord(
            cell_id=cell_id,
            notebook_id=nb_id,
            notebook_title=title,
            file_name=path.name,
            cell_index=idx,
            cell_type=ctype,
            section=section,
            section_path=section_path,
            headings=headings,
            spans=spans,
            span_count=len(spans),
            has_multiple_sections=multiple,
            section_accuracy_status=accuracy_status,
            content=content,
            content_length_chars=len(content),
            is_empty=is_empty,
            is_short=(not is_empty) and len(content.strip()) < config.SHORT_CELL_CHARS,
            contains_math=math["contains_math"],
            contains_latex=math["contains_latex"],
            formula_heavy=math["formula_heavy"],
            math_block_count=math["math_block_count"],
            contains_code=ctype == "code",
            contains_table=is_text and bool(PIPE_TABLE_SEP_RE.search(content) or HTML_TABLE_RE.search(content)),
            contains_list=is_text and bool(LIST_RE.search("\n".join(outside_fences(content)))),
            contains_image=bool(image_refs),
            image_refs=image_refs,
            contains_plot=any(o.content_type == "image" for o in outputs)
            or (ctype == "code" and bool(PLOT_CALL_RE.search(content))),
            contains_instructor_note=is_text and bool(INSTRUCTOR_RE.search(content)),
            contains_mcq=is_text and bool(MCQ_Q_RE.search(content) and MCQ_C_RE.search(content)),
            outputs=outputs,
            has_output=bool(outputs),
            libraries=libs,
            execution_count=cell.get("execution_count") if ctype == "code" else None,
            warnings=warnings,
            ingested_at=ingested_at,
            source_hash=sha256_text(raw_source),
        ))
        for h in headings:
            if h.structural:
                record.outline.append({"cell_index": idx, "level": h.level, "text": h.text})

    _summarize(record, cells, libraries)
    return record, cells


def _summarize(record: NotebookRecord, cells: list[CellRecord], libraries: set[str]) -> None:
    record.total_cells = len(cells)
    record.markdown_cells = sum(c.cell_type == "markdown" for c in cells)
    record.code_cells = sum(c.cell_type == "code" for c in cells)
    record.raw_cells = sum(c.cell_type == "raw" for c in cells)
    record.empty_cells = sum(c.is_empty for c in cells)
    record.math_cells = sum(c.contains_math for c in cells)
    record.code_with_output_cells = sum(c.cell_type == "code" and c.has_output for c in cells)
    record.plot_cells = sum(c.contains_plot for c in cells)
    record.table_cells = sum(c.contains_table or any(o.content_type == "table" for o in c.outputs) for c in cells)
    record.image_ref_cells = sum(c.contains_image for c in cells)
    record.instructor_note_cells = sum(c.contains_instructor_note for c in cells)
    record.mcq_cells = sum(c.contains_mcq for c in cells)
    record.error_output_cells = sum("error_output" in c.warnings for c in cells)
    record.heading_count = len(record.outline)
    record.libraries = sorted(libraries)
    record.span_count = sum(c.span_count for c in cells)
    record.multi_section_cells = sum(c.has_multiple_sections for c in cells)
    record.preamble_only_cells = sum(c.section_accuracy_status == "preamble" for c in cells)
    record.teaching_outputs = sum(o.output_role == "teaching_text" for c in cells for o in c.outputs)

    non_empty = [c for c in cells if not c.is_empty]

    w = record.warnings
    if record.total_cells == 0:
        w.append("no_cells")
    elif not non_empty:
        w.append("no_content")
    if record.heading_count == 0:
        w.append("no_headings")
    if record.total_cells < config.SMALL_NOTEBOOK_CELLS:
        w.append("small_notebook")
    if record.empty_cells:
        w.append(f"empty_cells:{record.empty_cells}")
    unbalanced = sum("unbalanced_math_delimiters" in c.warnings for c in cells)
    if unbalanced:
        w.append(f"unbalanced_math_cells:{unbalanced}")
    if record.error_output_cells:
        w.append(f"error_output_cells:{record.error_output_cells}")
    truncated = sum("output_truncated" in c.warnings for c in cells)
    if truncated:
        w.append(f"truncated_output_cells:{truncated}")
    if any("encoding_replacement_char" in c.warnings for c in cells):
        w.append("encoding_replacement_chars")
