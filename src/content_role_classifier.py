#!/usr/bin/env python3
"""
Content roles for every markdown span and code cell (PH1-ROLE-001).

Stage 1 — deterministic rules give a role, a confidence and a reason. Rules that cannot decide
(mixed instructor/teaching spans, weak quiz signals, unparseable code, ...) mark the record as
*queued* with a proposed role.

Stage 2 — queued records are resolved from a label file (data/labels/role_labels.jsonl). Each
label is keyed by record ID and content hash, so it stops applying when the content changes:
  - method "llm":    labelled offline by an LLM from the record text and section path only
  - method "manual": a human correction (e.g. from the QC sample); overrides any rule
A queued record without a valid label gets role "unknown" and stays in the manual-review queue.

Usage (from the project root):
    python src/content_role_classifier.py                 # classify data/processed/cells.jsonl,
                                                          # write spans.jsonl + content_role_report.md
    python src/content_role_classifier.py --export-queue q.jsonl   # records still needing a label
`python src/ingestion.py` runs the classifier too, so cells.jsonl always carries roles.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402

MARKDOWN_ROLES = (
    "teaching", "instructor_note", "quiz", "rhetorical_question", "agenda",
    "business_context", "preamble", "unknown",
)
CODE_ROLES = (
    "tool_implementation", "tool_demonstration", "tool_function", "tool_workflow", "visualization",
    "data_loading", "environment_setup", "debugging", "non_teaching", "unknown",
)
TOOL_ROLES = {"tool_implementation", "tool_demonstration", "tool_function", "tool_workflow", "visualization"}
LABELS_FILE = config.ROOT / "data" / "labels" / "role_labels.jsonl"
SPANS_JSONL = "spans.jsonl"
REPORT_MD = "content_role_report.md"
QUEUE_CONFIDENCE = 0.5          # records below this go to the manual-review queue


@dataclass
class Decision:
    role: str
    confidence: float
    reason: str
    queued: bool = False            # rules could not decide; needs an LLM/manual label
    flags: tuple = ()               # role_flags, e.g. ("embedded_instructor_note",)


# ----------------------------------------------------------------------------
# Text helpers
# ----------------------------------------------------------------------------
HEADING_LINE_RE = re.compile(r"^ {0,3}#{1,6}(?:[ \t].*)?$|^.*<h[1-6]\b.*</h[1-6]>.*$", re.I)
IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)|<img\b[^>]*>", re.I)
TAG_RE = re.compile(r"<[^>]+>")
LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
URL_RE = re.compile(r"https?://\S+")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def span_body(span) -> str:
    """Span content without its own heading line(s)."""
    text = span.content
    if span.heading_text is None:
        return text
    lines = text.split("\n")
    i = 0
    while i < len(lines) and (not lines[i].strip() or re.match(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$", lines[i])):
        i += 1                                    # blank lines and a leading '---' before the heading
    if i < len(lines) and HEADING_LINE_RE.match(lines[i]):
        i += 1
    elif i + 1 < len(lines) and re.match(r"^ {0,3}(=+|-+)\s*$", lines[i + 1]):   # setext
        i += 2
    else:                                                     # heading inside a wrapper line
        i += 1
    return "\n".join(lines[i:])


def prose(text: str) -> str:
    """Readable text: no images, tags, URLs; link text kept."""
    text = IMG_RE.sub(" ", text)
    text = LINK_RE.sub(r"\1", text)
    text = URL_RE.sub(" ", text)
    text = TAG_RE.sub(" ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def nonws(text: str) -> int:
    return len("".join(text.split()))


THEMATIC_LINE_RE = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$", re.M)


def text_without_rules(text: str) -> str:
    return THEMATIC_LINE_RE.sub("", text)


# ----------------------------------------------------------------------------
# Markdown rules
# ----------------------------------------------------------------------------
INSTRUCTOR_RE = re.compile(
    r"note\s*(to|for)\s*(the\s*)?instructors?|instructor'?s?\s*notes?|\bask\s+(the\s+)?(learners|students)\b"
    r"|with\s+the\s+learners\b|\binstructor\s*:|for\s+the\s+instructor|instructors?\s+(should|can|may)\b",
    re.I,
)
QUIZ_HEADING_RE = re.compile(
    r"^(quiz|mcq|msq|practice\s+(question|problem|exercise)s?|interview\s+questions?(\s+examples?)?"
    r"|homework|exercise|assignment|assessments?(\s+covered)?|compuls\w*\s+task|post\s*read\s*(questions|quiz))\b",
    re.I,
)
QUIZ_START_RE = re.compile(r"^\W*(quiz|mcq)\b[\s\-:#*]*\d*\b", re.I)
LEARNER_TASK_RE = re.compile(r"^\W*(todo|to-do|task|exercise|homework)\s+for\s+(the\s+)?(learners?|students?)\b"
                             r"|^\W*(todo|homework)\s*:", re.I | re.M)
ASSESSMENT_RE = re.compile(r"assessments?\s+covered|\bT-\s*ASSESSMENT\b|scaler\.com/hire/test", re.I)
CHECKBOX_RE = re.compile(r"^\s*[-*]\s*\[[ xX]\]", re.M)
LETTER_OPTION_RE = re.compile(r"^\s*>?\s*\(?[a-dA-D]\)\s+\S|^\s*>?\s*[a-dA-D][.)]\s+\S", re.M)
NUMBER_OPTION_RE = re.compile(r"^\s*>?\s*\(?[1-5][.)]\s+\S", re.M)
ANSWER_RE = re.compile(r"^\W*(ans(wer)?s?|correct\s+answer|solution)\b\W*[:\-*]?|\bcorrect answer\b", re.I | re.M)
MCQ_LABELS = {"question", "questions", "choices", "choice", "options", "answer"}
AGENDA_HEADINGS = {
    "content", "contents", "agenda", "agenda of the lecture", "lecture agenda", "today's agenda",
    "todays agenda", "table of contents", "topics covered", "topics", "outline", "lecture outline",
    "index", "class agenda", "session agenda",
}
TOC_LINE_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])?\s*\[[^\]]+\]\(#[^)]*\)\s*$")
BUSINESS_RE = re.compile(
    r"business\s+(context|case|problem|objective|understanding|use\s*case|scenario)|problem\s+statement"
    r"|\buse\s*case\b|\busecase\b",
    re.I,
)
SCENARIO_RE = re.compile(
    r"^\W*(you\s+are\s+(working|a\s+data\s+scientist|an?\s+analyst|a\s+data\s+analyst)|imagine\s+you\s+are\s+(a|an|the)?\s*"
    r"(data|ml|machine|analyst)|say,?\s+you\s+are\s+working|suppose\s+you\s+are\s+(working|a\s+data))",
    re.I,
)
LOGISTICS_HEADING_RE = re.compile(
    r"^(pre[\s-]*reads?|post[\s-]*reads?|references?(\s+and\s+further\s+reading)?|further\s+reading"
    r"|additional\s+resources|resources|reading\s+material|recording|class\s+notes)\b",
    re.I,
)


def norm_heading(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s']", " ", (text or "").lower())).strip()


def note_block_end(text: str, pos: int) -> int:
    """End of an instructor-note block that starts at `pos`: the rest of the marker's paragraph,
    plus any directly following blockquote ('>') lines or bullet lines of the same paragraph."""
    nl = text.find("\n", pos)
    if nl == -1:
        return len(text)
    end = nl + 1
    while end < len(text):
        nxt = text.find("\n", end)
        line = text[end: nxt if nxt != -1 else len(text)]
        if not line.strip() or not (line.lstrip().startswith((">", "-", "*")) or line.startswith(" ")):
            break
        end = (nxt + 1) if nxt != -1 else len(text)
    return end


def classify_span(span, seen_business: set) -> Decision:
    heading = norm_heading(span.heading_text)
    # Continuation text inherits a role-defining section heading from an earlier cell
    section = norm_heading(span.section_title) if span.kind == "continuation" else ""
    body = span_body(span)
    body_prose = prose(text_without_rules(body))
    body_len = nonws(body_prose)
    first_prose = prose(span.content)[:400]

    if span.kind == "preamble":
        return Decision("preamble", 1.0, "Text before the notebook's first heading.")

    # Instructor notes
    m = INSTRUCTOR_RE.search(span.content)
    if m:
        before = nonws(prose(span.content[: m.start()]))
        lead = nonws(prose(span.heading_text or "")) + 25    # marker near the top of the span
        after = nonws(prose(span.content[note_block_end(span.content, m.end()):]))
        if before <= lead and after < 60:
            return Decision("instructor_note", 0.95, "Instructor marker and note block make up the span.")
        return Decision("instructor_note", 0.4, "Instructor marker mixed with other text; needs review.", queued=True)

    # Quizzes and practice
    if span.kind == "label" and heading in MCQ_LABELS:
        return Decision("quiz", 0.95, f"MCQ block label '{span.heading_text}'.")
    if QUIZ_HEADING_RE.match(heading) or QUIZ_START_RE.match(prose(span_body(span)).lstrip("`\n ")):
        return Decision("quiz", 0.95, "Quiz/practice heading.")
    if LEARNER_TASK_RE.search(prose(span.content)[:300]):
        return Decision("quiz", 0.85, "Practice task for learners.")
    if len(CHECKBOX_RE.findall(body)) >= 2:
        return Decision("quiz", 0.9, "Checkbox answer options.")
    letter_opts = len(LETTER_OPTION_RE.findall(body))
    number_opts = len(NUMBER_OPTION_RE.findall(body))
    has_answer = bool(ANSWER_RE.search(body))
    if (letter_opts >= 2 or number_opts >= 2) and has_answer:
        return Decision("quiz", 0.9, "Answer options with an answer key.")
    if letter_opts >= 2 and "?" in body:
        return Decision("quiz", 0.45, "Lettered options after a question, no answer key.", queued=True)

    if section and QUIZ_HEADING_RE.match(section):
        return Decision("quiz", 0.75, f"Continues the quiz section '{span.section_title}'.")

    # Agenda / outline
    if heading in AGENDA_HEADINGS or heading.startswith("agenda"):
        return Decision("agenda", 0.95, f"Agenda/outline heading '{span.heading_text}'.")
    body_lines = [l for l in span_body(span).split("\n") if l.strip()]
    listy = body_lines and sum(bool(re.match(r"^\s*([-*+]|\d+[.)])\s", l)) for l in body_lines) / len(body_lines) >= 0.5
    if section and (section in AGENDA_HEADINGS or section.startswith("agenda")) and listy:
        return Decision("agenda", 0.85, f"List continuing the agenda section '{span.section_title}'.")
    if ASSESSMENT_RE.search(span.content):
        return Decision("quiz", 0.9, "Links to assessment/practice problems.")
    lines = [l for l in body.split("\n") if l.strip()]
    if lines and sum(bool(TOC_LINE_RE.match(l)) for l in lines) / len(lines) >= 0.6:
        return Decision("agenda", 0.9, "Table of contents (anchor links).")

    # Business framing
    # Own heading only: lessons often continue under a "Business Context" heading.
    if BUSINESS_RE.search(heading):
        first = span.notebook_id not in seen_business
        seen_business.add(span.notebook_id)
        return Decision("business_context", 0.9,
                        "Business/problem framing heading" + (" (first in notebook)." if first else " (repeat)."))

    # Scenario framing without a business heading ("You are working at ...", "Imagine you are a ...")
    if SCENARIO_RE.match(body_prose) and not span.contains_math and "```" not in body and not span.contains_table:
        first = span.notebook_id not in seen_business
        seen_business.add(span.notebook_id)
        return Decision("business_context", 0.8,
                        "Business scenario framing" + (" (first in notebook)." if first else " (repeat)."))

    # Course logistics: reading lists, recordings
    if LOGISTICS_HEADING_RE.match(heading):
        return Decision("instructor_note", 0.8, "Course logistics / reading list for the class.")

    # Structure-only and image-only spans
    if span.heading_text is not None and not body.strip():
        if (span.heading_text or "").rstrip().endswith("?"):
            return Decision("rhetorical_question", 0.9, "Question heading with no content of its own.")
        return Decision("teaching", 0.9, "Heading only; its content follows in later cells.")
    if body.strip() and body_len < 15 and IMG_RE.search(body):
        return Decision("teaching", 0.85, "Image only; content is in the image (handled as a Resource).")
    if not body.strip() or (not nonws(body_prose) and not IMG_RE.search(body)):
        return Decision("teaching", 0.9, "Formatting only (rule, line break); nothing to retrieve.")

    # Question prompts
    if (span.heading_text or "").rstrip().endswith("?") and body_len < 80 and not span.contains_math:
        return Decision("rhetorical_question", 0.8, "Question heading with little explanatory content.")

    # Teaching by default when there is substance
    if span.contains_math or span.contains_table or span.contains_list or body_len >= 200:
        return Decision("teaching", 0.9, "Explanatory text" + (" with math" if span.contains_math else "")
                        + (" with a table" if span.contains_table else "") + ".")
    if body_len >= 40:
        return Decision("teaching", 0.8, "Explanatory text.")
    # Short text (< 40 characters)
    stripped = body_prose.strip()
    if IMG_RE.search(body):
        return Decision("teaching", 0.8, "Short caption with an image; content is in the image (Resource).")
    if re.match(r"^(image\s+)?(source|credits?)\s*:", stripped, re.I):
        return Decision("teaching", 0.8, "Image source credit; nothing to retrieve.")
    if re.fullmatch(r"#{1,6}\S.*", stripped):
        return Decision("teaching", 0.85, "Heading written without a space after '#'; heading only.")
    if re.search(r"newly added section|section (begins|ends) here|^#?\s*todo\b", stripped, re.I):
        return Decision("instructor_note", 0.85, "Authoring marker for course editors.")
    if not nonws(prose(re.sub(r"\]\([^)]*\)", "]", body))) or \
            re.search(r"\bif\s+gdown\b|drive\.google\.com|scaler\.com/meetings", body) and len(stripped) < 40:
        return Decision("instructor_note", 0.75, "Link or setup note for the class, no teaching text.")
    if stripped.endswith("?"):
        return Decision("rhetorical_question", 0.75, "Short question prompt.")
    if stripped.endswith(":"):
        return Decision("teaching", 0.7, "Short lead-in to the next cell.")
    return Decision("teaching", 0.65, "Short caption or lead-in for the next cell.")


def retrieval_for_span(span, d: Decision) -> tuple[bool, str]:
    """(retrieval_eligible for default Concept retrieval, index)."""
    body = span_body(span)
    if d.role == "teaching":
        if not body.strip() or not nonws(prose(text_without_rules(body))) and not IMG_RE.search(body) \
                or re.fullmatch(r"#{1,6}\S.*", prose(body).strip()):
            return False, "concepts"            # heading/formatting only: context for following cells
        if (nonws(prose(body)) < 15 or "caption with an image" in d.reason) and IMG_RE.search(body):
            return False, "resources"           # image only, or a short caption with an image
        if "source credit" in d.reason:
            return False, "resources"
        return True, "concepts"
    if d.role == "business_context":
        return False, "support" if "first in notebook" in d.reason else "none"
    if d.role in ("instructor_note", "quiz", "agenda", "preamble", "rhetorical_question"):
        return False, "support"
    return False, "none"                         # unknown


# ----------------------------------------------------------------------------
# Code rules
# ----------------------------------------------------------------------------
TOOL_TYPE_ROLE = {
    "implementation": "tool_implementation", "demonstration": "tool_demonstration",
    "function": "tool_function", "workflow": "tool_workflow", "visualization": "visualization",
    "data_loading": "data_loading", "environment_setup": "environment_setup",
    "debugging": "debugging", "non_teaching": "non_teaching",
}
TOOL_TYPE_CONFIDENCE = {
    "environment_setup": 0.95, "data_loading": 0.9, "debugging": 0.9, "function": 0.9,
    "non_teaching": 0.85, "visualization": 0.85, "workflow": 0.8, "implementation": 0.75,
    "demonstration": 0.65,
}
TOOL_TYPE_REASON = {
    "environment_setup": "Installs packages or configures the environment.",
    "data_loading": "Loads or downloads data.",
    "debugging": "Produces an error output.",
    "function": "Defines a function or class.",
    "non_teaching": "Imports only or bare inspection (head/shape/info).",
    "visualization": "Creates a plot.",
    "workflow": "Several model/pipeline steps (fit, transform, predict, ...).",
    "implementation": "Computes a formula or loop over data.",
    "demonstration": "Example usage on data.",
}


LOADER_RE = re.compile(r"\.from_pretrained\(|load_model\(|\.load_weights\(|hub\.load\(|spacy\.load\(|pipeline\(")
ENV_CONFIG_RE = re.compile(
    r"\blocale\.\w+\s*=|os\.environ|sys\.path\.(append|insert)|warnings\.(filterwarnings|simplefilter)"
    r"|pd\.set_option|np\.set_printoptions|tf\.get_logger|logging\.(basicConfig|getLogger)|%config\b"
    r"|drive\.mount\(|os\.chdir\(|%cd\b|np\.random\.seed\(|tf\.random\.set_seed\(|\brandom\.seed\("
    r"|torch\.manual_seed\(|set_random_seed\(|%matplotlib\b|%load_ext\b|plt\.rcParams|mpl\.rcParams"
    r"|\bsns\.set(_theme|_style|_context)?\(|plt\.style\.use\(|InteractiveShell"
)
SHELL_INSPECT_RE = re.compile(r"^\s*[!%]\s*(ls|pwd|tree|nvidia-smi|cat|head|du|df|free|whoami|nproc|lscpu)\b")
TIMING_RE = re.compile(r"time\.(time|perf_counter)\(\)|^\s*%%?time\b|print\(f?[\"'](time taken|elapsed|total time)", re.I)


INSPECT_CALLS = {"len", "type", "print", "id", "dir"}
INSPECT_ATTRS = {"shape", "size", "dtype", "dtypes", "columns", "ndim", "index", "nunique", "head", "tail",
                 "info", "describe", "value_counts", "isnull", "isna", "sum", "keys", "values", "unique"}


def is_inspection(tree) -> bool:
    """One or two bare expressions that only look at existing objects (len(x), x.shape, type(y), ...)."""
    import ast
    if not tree.body or len(tree.body) > 2 or not all(isinstance(n, ast.Expr) for n in tree.body):
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if name not in INSPECT_CALLS and name not in INSPECT_ATTRS:
                return False
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            if node.attr not in INSPECT_ATTRS and not isinstance(node.value, ast.Name):
                pass
        elif isinstance(node, (ast.BinOp, ast.Lambda, ast.ListComp, ast.DictComp, ast.GeneratorExp)):
            return False
    calls_or_attrs = [n for n in ast.walk(tree) if isinstance(n, (ast.Call, ast.Attribute))]
    return bool(calls_or_attrs) and all(
        (isinstance(n, ast.Call) and ((n.func.id if isinstance(n.func, ast.Name) else n.func.attr
                                       if isinstance(n.func, ast.Attribute) else "") in INSPECT_CALLS | INSPECT_ATTRS))
        or (isinstance(n, ast.Attribute) and n.attr in INSPECT_ATTRS)
        or isinstance(n, ast.Attribute)
        for n in calls_or_attrs)


STRING_RE = re.compile(r"(\"\"\"[\s\S]*?\"\"\"|'\'\'[\s\S]*?\'\'\'|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*')")


def has_arithmetic(code: str) -> bool:
    """Arithmetic or numeric computation outside string literals and comments."""
    body = STRING_RE.sub('""', code)
    body = "\n".join(l.split("#", 1)[0] for l in body.split("\n"))
    return bool(re.search(r"=[^=].*([+\-*/@]|\*\*|np\.\w+\()", body)) or bool(re.search(r"^\s*(for|while)\b", body, re.M))


LOADER_CALL_RE = re.compile(
    r"\bread_(csv|excel|json|parquet|table|sql|pickle|fwf|html|feather)\(|\bnp\.(load|loadtxt|genfromtxt)\("
    r"|\b(joblib|pickle|torch|json|dill|yaml)\.(load|safe_load)\(|\bload_dataset\(|\bload_data\("
    r"|image_dataset_from_directory\(|text_dataset_from_directory\(|flow_from_(directory|dataframe)\("
    r"|\bfetch_\w+\(|\bload_(iris|digits|breast_cancer|wine|diabetes|boston|files)\(|get_file\("
    r"|urlretrieve\(|requests\.get\(|\bos\.(listdir|walk|scandir)\(|\bglob(\.glob)?\(|\.iterdir\("
    r"|\bopen\([^)]*\)\s*(as|\.read)|\.from_pretrained\(|\bload_model\(|\.load_weights\(|\bspacy\.load\("
    r"|\bhub\.load\(|\bload_metric\(|\bevaluate\.load\("
)
CONFIG_CALL_RE = re.compile(
    r"^\s*(warnings\.(filterwarnings|simplefilter)|sns\.set(_theme|_style|_context|_palette)?|plt\.style\.use"
    r"|np\.random\.seed|tf\.random\.set_seed|random\.seed|torch\.manual_seed|tf\.keras\.utils\.set_random_seed"
    r"|pd\.set_option|np\.set_printoptions|nltk\.download|tf\.get_logger|logging\.\w+|os\.(chdir|makedirs|mkdir)"
    r"|drive\.mount|sys\.path\.(append|insert)|plt\.rcParams\.update|matplotlib\.use|tf\.config\.\w+"
    r"|InteractiveShell|get_ipython|tqdm\.pandas|tf\.debugging\.\w+|torch\.backends\.\w+)\b"
)
CONFIG_TARGET_RE = re.compile(r"rcParams|os\.environ|locale\.\w+|InteractiveShell|pd\.options")


def _is_literal(node) -> bool:
    import ast
    try:
        ast.literal_eval(node)
        return True
    except Exception:
        pass
    if isinstance(node, ast.JoinedStr):
        return True                                           # f-string path
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _is_literal(node.left) or _is_literal(node.right)   # "dir/" + name
    return False


def statement_kind(stmt, source: str) -> str:
    """import | config | loader | constant | display | other — for one top-level statement."""
    import ast
    seg = ast.get_source_segment(source, stmt) or ""
    if isinstance(stmt, (ast.Import, ast.ImportFrom)):
        return "import"
    if CONFIG_CALL_RE.match(seg):
        return "config"
    if isinstance(stmt, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
        targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
        if any(CONFIG_TARGET_RE.search(ast.get_source_segment(source, t) or "") for t in targets):
            return "config"
        value = stmt.value
        if value is not None and LOADER_CALL_RE.search(ast.get_source_segment(source, value) or ""):
            # loader possibly wrapped in sorted()/list()/np.array() etc.
            return "loader"
        if value is not None and _is_literal(value):
            return "constant"
        if value is not None and isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) \
                and value.func.attr in ("copy", "deepcopy") and not value.args \
                and isinstance(value.func.value, ast.Name):
            return "constant"                                 # df1 = df.copy()
        if isinstance(value, ast.Name):
            return "constant"                                 # x = y
        return "other"
    if isinstance(stmt, ast.Expr):
        v = stmt.value
        if LOADER_CALL_RE.search(seg):
            return "loader"
        if isinstance(v, (ast.Name, ast.Attribute, ast.Constant, ast.Subscript)):
            return "display"
        if isinstance(v, ast.Call):
            f = v.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            if name in ("print", "display", "head", "tail", "info", "shape") and all(
                    not isinstance(n, ast.Call) or (getattr(n.func, "id", None) or getattr(n.func, "attr", None))
                    in ("print", "display", "len", "head", "tail", "info", "format", "type",
                        "list_physical_devices", "is_gpu_available", "is_available", "device_count",
                        "get_device_name")
                    for n in ast.walk(v)):
                return "display"
        return "other"
    return "other"


def boilerplate_role(cell, lines: list[str], tree) -> Optional[Decision]:
    """A cell whose every statement is plumbing (imports, config, data loading, literal constants,
    display) is not a teaching tool."""
    if tree is None or not tree.body:
        return None
    kinds = [statement_kind(st, cell.content) for st in tree.body]
    if "other" in kinds:
        return None
    if "loader" in kinds:
        return Decision("data_loading", 0.9, "Only loads data/files/pretrained assets, plus plumbing.")
    if "config" in kinds:
        return Decision("environment_setup", 0.9, "Only configures the runtime, plus imports/constants.")
    if set(kinds) <= {"import"}:
        return None                                           # import block: handled by the shared rules
    if "constant" in kinds and "display" not in kinds:
        return Decision("non_teaching", 0.85, "Only defines constants, paths or copies of objects.")
    return None                                               # display-only cells: inspection rules decide


def taught_method(cell) -> str:
    """An inspection method used in the cell that the section heading is about (e.g. head/tail)."""
    section = " ".join(cell.section_path).lower()
    for name in sorted(INSPECT_ATTRS | {"isnull", "isna", "describe"}):
        if re.search(rf"\.{name}\b", cell.content) and re.search(rf"\b{name}\b", section):
            return f".{name}()" if name not in ("shape", "size", "dtype", "dtypes", "columns", "ndim", "index") else f".{name}"
    if re.search(r"\bmissing|null|nan\b", section) and re.search(r"\.(isna|isnull)\(", cell.content):
        return ".isna()/.isnull()"
    return ""


def classify_code(cell) -> Decision:
    import assets                                     # code rules shared with the Tools builder
    if cell.is_empty:
        return Decision("non_teaching", 1.0, "Empty code cell.")
    lines = [l for l in cell.content.split("\n") if l.strip()]
    if all(l.lstrip().startswith("#") for l in lines):
        return Decision("non_teaching", 0.9, "Only comments / commented-out code.")
    code_lines_ = [l for l in lines if not l.lstrip().startswith("#")]
    imports = [l for l in code_lines_ if re.match(r"\s*(import|from)\s", l)]
    rest = [l for l in code_lines_ if l not in imports]
    if imports and len(imports) >= 3 * max(len(rest), 1) and len(rest) <= 2 and \
            all(LOADER_RE.search(l) or ENV_CONFIG_RE.search(l) or SHELL_INSPECT_RE.match(l) for l in rest) and \
            not re.search(r"^\s*(def|class)\s", cell.content, re.M):
        return Decision("environment_setup", 0.85, "Imports plus loading of pretrained models/tokenizers or config.")
    if code_lines_ and all(ENV_CONFIG_RE.search(l) or re.match(r"\s*(import|from)\s", l) for l in code_lines_) \
            and any(ENV_CONFIG_RE.search(l) for l in code_lines_):
        return Decision("environment_setup", 0.9, "Configures the runtime (locale, environment variables, paths, seeds, warnings).")
    if code_lines_ and all(SHELL_INSPECT_RE.match(l) for l in code_lines_):
        return Decision("non_teaching", 0.9, "Shell inspection of files or hardware (ls, pwd, tree, nvidia-smi).")
    if code_lines_ and all(TIMING_RE.search(l) or re.match(r"\s*(import|from)\s+time", l) for l in code_lines_):
        return Decision("non_teaching", 0.85, "Timing / elapsed-time bookkeeping only.")
    tree = assets.parseable(cell.content)
    boiler = boilerplate_role(cell, code_lines_, tree)
    if boiler:
        return boiler
    if tree is not None and is_inspection(tree):
        taught = taught_method(cell)
        if taught:
            return Decision("tool_demonstration", 0.75, f"Demonstrates {taught}, which this section teaches.")
        return Decision("non_teaching", 0.85, "Inspection only (len/shape/dtype/type of existing objects).")
    if tree is None and not any(l.lstrip().startswith(("!", "%")) for l in lines):
        return Decision("unknown", 0.3, "Not valid Python; role unclear.", queued=True)
    tool_type = assets.classify_tool(cell, tree)
    if tool_type == "implementation" and not has_arithmetic(cell.content):
        tool_type = "demonstration"           # the shared rule also matched '-' or '/' inside strings
    if tool_type == "non_teaching" and taught_method(cell):
        return Decision("tool_demonstration", 0.75, f"Demonstrates {taught_method(cell)}, which this section teaches.")
    return Decision(TOOL_TYPE_ROLE[tool_type], TOOL_TYPE_CONFIDENCE[tool_type], TOOL_TYPE_REASON[tool_type])


def retrieval_for_code(d: Decision) -> tuple[bool, str]:
    if d.role in TOOL_ROLES:
        return ("invalid_syntax" not in d.flags), "tools"
    if d.role in ("data_loading", "environment_setup", "debugging"):
        return False, "support"
    return False, "none"


# ----------------------------------------------------------------------------
# Labels (Stage 2) and application
# ----------------------------------------------------------------------------
def load_labels(path: Path = LABELS_FILE) -> dict[str, dict]:
    labels: dict[str, dict] = {}
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    # later lines win; manual beats llm for the same record
                    prev = labels.get(rec["id"])
                    if prev and prev["method"] == "manual" and rec["method"] != "manual":
                        continue
                    labels[rec["id"]] = rec
    return labels


def _apply(target, d: Decision, method: str, eligible: bool, index: str) -> None:
    target.content_role = d.role
    target.role_confidence = round(d.confidence, 2)
    target.role_method = method
    target.role_reason = d.reason
    target.retrieval_eligible = eligible
    target.retrieval_index = index
    target.role_flags = list(d.flags)


def classify_cells(cells: list, labels: Optional[dict] = None) -> dict:
    """Assign roles in place. Returns {'queue': [...], 'stale_labels': n}."""
    labels = load_labels() if labels is None else labels
    queue, stale, used = [], 0, set()
    seen_business: set = set()
    for c in cells:
        records = [(sp.span_id, sp, "markdown") for sp in c.spans] if c.cell_type == "markdown" else \
            ([(c.cell_id, c, "code")] if c.cell_type == "code" else [])
        for rid, target, kind in records:
            text = target.content
            d = classify_span(target, seen_business) if kind == "markdown" else classify_code(target)
            allowed = MARKDOWN_ROLES if kind == "markdown" else CODE_ROLES
            method = "rule"
            label = labels.get(rid)
            if label and label["content_hash"] != content_hash(text):
                stale += 1
                label = None
            if label and (d.queued or label["method"] == "manual"):
                if label["content_role"] not in allowed:
                    raise ValueError(f"{rid}: label {label['content_role']!r} not in the {kind} taxonomy")
                d = Decision(label["content_role"], label.get("role_confidence", 0.8), label["role_reason"],
                             flags=tuple(label.get("role_flags", [])))
                method = label["method"]
                used.add(rid)
            elif d.queued:
                queue.append({"id": rid, "kind": kind, "proposed_role": d.role, "reason": d.reason,
                              "why_uncertain": d.reason, "section_path": getattr(target, "section_path", c.section_path),
                              "content_hash": content_hash(text), "content": text})
                d = Decision("unknown", 0.0, f"Awaiting review (proposed {d.role}): {d.reason}")
            if kind == "markdown" and d.role == "business_context" and "first in notebook" not in d.reason \
                    and "(repeat)" not in d.reason:
                d.reason += " (first in notebook)." if c.notebook_id not in seen_business else " (repeat)."
                seen_business.add(c.notebook_id)
            eligible, index = retrieval_for_span(target, d) if kind == "markdown" else retrieval_for_code(d)
            _apply(target, d, method, eligible, index)
        for o in c.outputs:
            o.retrieval_eligible = o.output_role in ("teaching_text", "result") and o.content_type != "image"
    return {"queue": queue, "stale_labels": stale, "labels_used": len(used)}


# ----------------------------------------------------------------------------
# Outputs: spans.jsonl and report
# ----------------------------------------------------------------------------
def spans_jsonl(cells: list) -> str:
    out = []
    for c in cells:
        for sp in c.spans:
            rec = {"notebook_id": c.notebook_id, "notebook_title": c.notebook_title, "cell_index": c.cell_index}
            rec.update(sp.model_dump())
            out.append(json.dumps(rec, ensure_ascii=False))
    return "".join(line + "\n" for line in out)


def build_report(cells: list, result: dict, qc_csv: Optional[Path] = None) -> str:
    spans = [sp for c in cells for sp in c.spans]
    code = [c for c in cells if c.cell_type == "code"]
    records = spans + code
    by_method = Counter(r.role_method for r in records)
    unknown = sum(r.content_role == "unknown" for r in records)
    low = [r for r in records if r.role_confidence < QUEUE_CONFIDENCE or r.content_role == "unknown"]
    L = ["# Content Role Report", "",
         f"Pipeline `{config.PIPELINE_VERSION}` · classifier `{Path(__file__).name}` · labels "
         f"`{LABELS_FILE.relative_to(config.ROOT)}`", "",
         "## Summary", "",
         f"- Markdown spans classified: {len(spans):,}",
         f"- Code cells classified: {len(code):,}",
         f"- Rule-based labels: {by_method['rule']:,}",
         f"- LLM-assisted labels: {by_method['llm']:,}",
         f"- Manual labels: {by_method['manual']:,}",
         f"- Manual-review queue: {len(result['queue']):,}",
         f"- Unknown: {unknown:,} ({unknown / len(records):.1%} of {len(records):,} records)",
         f"- Stale labels ignored (content changed): {result['stale_labels']}", ""]
    for title, items, roles in (("Markdown role distribution", spans, MARKDOWN_ROLES),
                                ("Code role distribution", code, CODE_ROLES)):
        cnt = Counter(r.content_role for r in items)
        unit = "Spans" if items is spans else "Cells"
        L += [f"## {title}", "", f"| Role | {unit} | Percentage | Retrieval-eligible |", "|---|---:|---:|---:|"]
        for role in roles:
            elig = sum(r.retrieval_eligible for r in items if r.content_role == role)
            L.append(f"| {role} | {cnt[role]:,} | {cnt[role] / len(items):.1%} | {elig:,} |")
        L.append("")
    outs = [o for c in cells for o in c.outputs]
    L += ["## Retrieval eligibility", "",
          "`retrieval_eligible` means eligible for default Concept/Tool retrieval. `retrieval_index` says "
          "where a record is kept otherwise.", "",
          "| Index | Eligible records | Excluded records |", "|---|---:|---:|"]
    idx = defaultdict(Counter)
    for r in records:
        idx[r.retrieval_index][r.retrieval_eligible] += 1
    for name in ("concepts", "tools", "resources", "support", "none"):
        L.append(f"| {name} | {idx[name][True]:,} | {idx[name][False]:,} |")
    L += ["", f"Outputs: {sum(o.retrieval_eligible for o in outs):,} of {len(outs):,} eligible "
          "(teaching_text and result; logs, dataframe dumps, errors and images excluded).", ""]
    excluded = Counter(r.content_role for r in records if not r.retrieval_eligible)
    L += ["Excluded from default retrieval by role: "
          + ", ".join(f"{k} {v:,}" for k, v in sorted(excluded.items(), key=lambda kv: -kv[1])), ""]
    L += ["## Manual review queue", "",
          "Records the rules could not decide and no valid LLM/manual label resolves. "
          "Low-confidence rule labels (< 0.5) are listed too.", "",
          "| cell_id / span_id | Proposed role | Reason | Why uncertain |", "|---|---|---|---|"]
    for q in result["queue"]:
        L.append(f"| {q['id']} | {q['proposed_role']} | {q['reason']} | no label yet |")
    for r in low:
        rid = getattr(r, "span_id", None) or r.cell_id
        if not any(q["id"] == rid for q in result["queue"]):
            L.append(f"| {rid} | {r.content_role} | {r.role_reason} | confidence {r.role_confidence} |")
    if not result["queue"] and not low:
        L.append("| — | — | — | queue is empty |")
    L += [""] + qc_section(qc_csv)
    return "\n".join(L) + "\n"


QC_CSV = Path("qa") / "content_role_review_sample.csv"


def qc_section(path: Optional[Path]) -> list[str]:
    """Summarise the manual review sample, if it exists."""
    L = ["## Quality-control sample", ""]
    if not path or not path.exists():
        return L + ["No review sample found.", ""]
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    L += [f"Per-record judgements: `data/processed/{QC_CSV.as_posix()}`. A critical false positive is a "
          "non-teaching record labelled teaching/tool and marked retrieval-eligible.", "",
          "| Sample | Reviewed | Correct (first pass) | Correct (current rules) | Critical FP (first pass) |",
          "|---|---:|---:|---:|---:|"]
    for name in dict.fromkeys(r["sample"] for r in rows):
        rr = [r for r in rows if r["sample"] == name]
        n = len(rr)
        first = sum(r["first_pass_correct"] == "Y" for r in rr)
        final = sum(r["final_correct"] == "Y" for r in rr)
        crit = sum(r["critical_false_positive"] == "Y" for r in rr)
        L.append(f"| {name} | {n} | {first} ({first / n:.0%}) | {final} ({final / n:.0%}) | {crit} ({crit / n:.0%}) |")
    L += ["",
          "- `required_stratified_100` is the ticket's stratified sample. Its errors were fixed by new rules, so "
          "the current-rules figure is in-sample and optimistic.",
          "- `validation_frozen_rules_100` was drawn after the rules were frozen, at random from retrieval-eligible "
          "records not reviewed before (69 spans, 31 code cells). It is the unbiased estimate of the critical "
          "false-positive rate; its errors were recorded, not fixed.", ""]
    return L


def run(processed_dir: Path = config.PROCESSED_DIR, export_queue: Optional[Path] = None) -> dict:
    from notebook_parser import CellRecord
    path = processed_dir / config.CELLS_JSONL
    cells = [CellRecord.model_validate_json(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    result = classify_cells(cells)
    write(processed_dir, cells, result)
    if export_queue:
        export_queue.write_text("".join(json.dumps(q, ensure_ascii=False) + "\n" for q in result["queue"]),
                                encoding="utf-8")
    return result


def write(processed_dir: Path, cells: list, result: dict) -> None:
    (processed_dir / config.CELLS_JSONL).write_text(
        "".join(json.dumps(c.model_dump(), ensure_ascii=False) + "\n" for c in cells), encoding="utf-8", newline="\n")
    (processed_dir / SPANS_JSONL).write_text(spans_jsonl(cells), encoding="utf-8", newline="\n")
    (processed_dir / REPORT_MD).write_text(build_report(cells, result, processed_dir / QC_CSV),
                                           encoding="utf-8", newline="\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export-queue", type=Path, help="write records still needing a label to this JSONL file")
    args = ap.parse_args()
    res = run(export_queue=args.export_queue)
    print(f"queue: {len(res['queue'])}  labels used: {res['labels_used']}  stale labels: {res['stale_labels']}")
