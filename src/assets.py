#!/usr/bin/env python3
"""
Phase 1.5: shared code/image helpers and the entry point for the Tools and Resources inventories.

    Concepts explain.  Tools demonstrate.  Resources illustrate.  Prompts ask.

Usage (from the project root, after `python src/ingestion.py`):
    python src/assets.py

Runs, in order:
    src/tools_inventory.py       -> tools.jsonl, tool_exclusions.jsonl
    src/resources_inventory.py   -> resources.jsonl, resources_report.md, images/
    src/tool_concept_linker.py   -> tool_concept_links.jsonl
and writes tools_report.md (tools + links).

The helpers here (code parsing, `classify_tool`, image parsing, topic mapping) are shared by those
modules and by src/content_role_classifier.py. Everything is rule-based and deterministic; image
content is never read.
"""
from __future__ import annotations

import ast
import builtins
import re
import struct
import sys
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Literal, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
from ingestion import candidate_key, content_words  # noqa: E402
from notebook_parser import CellRecord  # noqa: E402

TOOLS_REPORT_MD = "tools_report.md"

ToolType = Literal[
    "implementation", "demonstration", "function", "workflow", "visualization",
    "data_loading", "environment_setup", "debugging", "non_teaching",
]
# Raw tool types from `classify_tool`; content_role_classifier maps them to content roles.
ANSWER_ELIGIBLE = {"implementation", "demonstration", "function", "workflow", "visualization"}


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


# ----------------------------------------------------------------------------
# Main: build both inventories and the links (issue #1)
# ----------------------------------------------------------------------------
def run(processed_dir: Path = config.PROCESSED_DIR, raw_dir: Path = config.RAW_NOTEBOOKS_DIR, quiet: bool = False):
    """Tools -> Resources -> Tool-Concept links, then tools_report.md (resources_report.md is written by
    resources_inventory). Returns (tools, resources, links)."""
    import resources_inventory
    import tool_concept_linker
    import tools_inventory
    from content_role_classifier import TOOL_ROLES

    cells = tools_inventory.load_cells(processed_dir / config.CELLS_JSONL)
    tools, excluded = tools_inventory.run(processed_dir, quiet=quiet, cells=cells)
    resources = resources_inventory.run(processed_dir, raw_dir, quiet=quiet, cells=cells, tools=tools)
    links = tool_concept_linker.run(processed_dir, quiet=quiet, cells=cells, tools=tools)
    eligible = sum(c.cell_type == "code" and c.content_role in TOOL_ROLES and bool(c.retrieval_eligible)
                   for c in cells)
    report = ["# Tools Report", "", f"Pipeline `{config.PIPELINE_VERSION}` · `src/tools_inventory.py`, "
              "`src/tool_concept_linker.py` · issue #1", ""]
    report += tools_inventory.tools_report_section(tools, excluded, eligible)
    report += tool_concept_linker.links_report_section(tools, links)
    report += review_section(processed_dir / REVIEW_CSV, "tools_20")
    (processed_dir / TOOLS_REPORT_MD).write_text("\n".join(report) + "\n", encoding="utf-8", newline="\n")
    res_report = processed_dir / resources_inventory.RESOURCES_REPORT_MD
    res_report.write_text(res_report.read_text(encoding="utf-8")
                          + "\n".join(review_section(processed_dir / REVIEW_CSV, "resources_20")) + "\n",
                          encoding="utf-8", newline="\n")
    return tools, resources, links


REVIEW_CSV = Path("qa") / "inventory_review_sample.csv"


def review_section(path: Path, sample: str) -> list[str]:
    """Summary of the manual review sample (data/processed/qa/inventory_review_sample.csv), if present."""
    import csv
    L = ["## Manual review", ""]
    if not path.exists():
        return L + ["No review sample found.", ""]
    with path.open(encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["sample"] == sample]
    if not rows:
        return L + ["No review sample found.", ""]
    n = len(rows)

    def ok(col: str) -> str:
        judged = [r for r in rows if not r[col].startswith("n/a")]
        good = sum(r[col] == "Y" for r in judged)
        return f"{good}/{len(judged)}"
    L += [f"`data/processed/{REVIEW_CSV.as_posix()}` (`{sample}`, stratified, seed 20261027).", "",
          "| Check | Correct |", "|---|---:|",
          f"| Type | {ok('type_correct')} |", f"| Provenance (notebook, section, cell) | {ok('provenance_correct')} |",
          f"| Quality flags / status | {ok('flags_correct')} |", f"| Links (where present) | {ok('link_correct')} |",
          f"| Critical misclassifications | {sum(r['critical_misclassification'] == 'Y' for r in rows)} of {n} |", ""]
    notes = [f"- {r['item']} {r['record_id']}: {r['notes']}" for r in rows if r["notes"]]
    return L + notes + [""]


if __name__ == "__main__":
    run()
