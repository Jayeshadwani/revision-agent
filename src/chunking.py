"""
Chunking primitives for PH2-CHUNK-001 (issue #3): token estimates, safe split points, stripping
embedded instructor notes and quizzes, and the section-aware merge of teaching spans.

Everything here is pure and deterministic; src/chunk_builder.py loads the corpus, calls these and
writes the chunk files.

Token counts are estimates (no tokenizer is installed): one token per word piece of up to
8 characters plus one per punctuation mark. On this corpus that tracks the usual ~4 characters
per token. The embedding ticket can swap in the embedding model's tokenizer.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from content_role_classifier import INSTRUCTOR_RE, note_block_end  # noqa: E402

TARGET_MIN_TOKENS = 300        # chunks below this may absorb a related neighbouring section
TARGET_MAX_TOKENS = 800        # chunks are not grown past this (breadcrumb included)
BREADCRUMB_ALLOWANCE = 40      # tokens reserved for the "Notebook: ... / Section path: ..." header
TEXT_MAX_TOKENS = TARGET_MAX_TOKENS - BREADCRUMB_ALLOWANCE
TINY_TOKENS = 100              # flagged is_tiny
OVERSIZED_TOKENS = 1200        # flagged is_oversized (an unsplittable block)
MAX_OVERLAP_SHARE = 0.20       # overlap carried between split pieces, at most this share of the max

WORD_RE = re.compile(r"\w+|[^\w\s]")
STYLE_TAG_RE = re.compile(r"</?(span|font|center|div|p|br|b|i|u|strong|em|s|hr)\b[^>]*/?>", re.I)
FENCE_RE = re.compile(r"(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]+`)")
MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
HTML_IMAGE_RE = re.compile(r"<img\b[^>]*>", re.I)


def estimate_tokens(text: str) -> int:
    return sum(1 + (len(t) - 1) // 8 if t[0].isalnum() or t[0] == "_" else 1 for t in WORD_RE.findall(text))


def clean_for_content(text: str) -> str:
    """Drop HTML styling tags outside code (their inner text stays); collapse the blank lines left."""
    parts = FENCE_RE.split(text)
    text = "".join(p if i % 2 else STYLE_TAG_RE.sub("", p) for i, p in enumerate(parts))
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def content_tokens(text: str) -> int:
    """Tokens the text will have in a chunk: styling removed, each image reduced to a placeholder."""
    text = HTML_IMAGE_RE.sub("[Image RES_0000]", MD_IMAGE_RE.sub("[Image RES_0000]", text))
    return estimate_tokens(clean_for_content(text))


# ----------------------------------------------------------------------------
# Stripping embedded support content from teaching spans
# ----------------------------------------------------------------------------
LIST_ITEM_RE = re.compile(r"^(\s*>?\s*)([-*+]|\d+[.)])\s")
QUIZ_CUE_RE = re.compile(r"^\W*(some\s+)?(practice\s+questions?|quiz|mcq|exercise|try\s+it\s+yourself)\b", re.I | re.M)


def _line_bounds(text: str, pos: int) -> tuple[int, int]:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    return start, (len(text) if end == -1 else end + 1)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def support_ranges(text: str, flags: list[str]) -> list[tuple[int, int, str]]:
    """(start, end, kind) ranges of `text` that are instructor notes or quiz content, for spans whose
    content role is teaching but carry an embedded_* flag (PH1-ROLE-001)."""
    ranges: list[tuple[int, int, str]] = []
    if "embedded_instructor_note" in flags or "instructor_optional_teaching" in flags:
        for m in INSTRUCTOR_RE.finditer(text):
            start, line_end = _line_bounds(text, m.start())
            line = text[start:line_end]
            if "instructor_optional_teaching" in flags:
                end = line_end                                    # only the "optional" marker line
            elif LIST_ITEM_RE.match(line):
                # The note is one bullet inside a teaching list: drop it and its deeper-indented lines.
                end, base = line_end, _indent(line)
                while end < len(text):
                    nxt_start, nxt_end = _line_bounds(text, end)
                    nxt = text[nxt_start:nxt_end]
                    if not nxt.strip() or _indent(nxt) <= base:
                        break
                    end = nxt_end
            else:
                end = max(line_end, note_block_end(text, m.end()))
            ranges.append((start, end, "instructor_note"))
    if "embedded_quiz" in flags:
        m = QUIZ_CUE_RE.search(text)
        if m:
            ranges.append((_line_bounds(text, m.start())[0], len(text), "quiz"))
    ranges.sort()
    merged: list[tuple[int, int, str]] = []
    for s, e, k in ranges:
        if merged and s <= merged[-1][1]:
            ps, pe, pk = merged[-1]
            merged[-1] = (ps, max(pe, e), pk if pk == k else "instructor_note+quiz")
        else:
            merged.append((s, e, k))
    return merged


def kept_ranges(text: str, flags: list[str]) -> list[tuple[int, int]]:
    """Complement of support_ranges: the parts of the span that are teaching text."""
    out, pos = [], 0
    for s, e, _ in support_ranges(text, flags):
        if s > pos:
            out.append((pos, s))
        pos = max(pos, e)
    if pos < len(text):
        out.append((pos, len(text)))
    return [(s, e) for s, e in out if text[s:e].strip()]


# ----------------------------------------------------------------------------
# Splitting long text at safe boundaries
# ----------------------------------------------------------------------------
def blocks(text: str, start: int = 0, end: Optional[int] = None) -> list[tuple[int, int]]:
    """Paragraph blocks of text[start:end] as (start, end) offsets. Blank lines separate blocks,
    except inside ``` fences and $$ math blocks, which always stay whole."""
    end = len(text) if end is None else end
    out: list[tuple[int, int]] = []
    pos, block_start, in_fence, in_math = start, start, False, False
    while pos < end:
        nl = text.find("\n", pos, end)
        line_end = end if nl == -1 else nl + 1
        line = text[pos:line_end]
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
        elif not in_fence and stripped.count("$$") % 2 == 1:
            in_math = not in_math
        if not stripped and not in_fence and not in_math:
            if text[block_start:pos].strip():
                out.append((block_start, line_end))
                block_start = line_end
        pos = line_end
    if text[block_start:end].strip():
        out.append((block_start, end))
    elif out:
        out[-1] = (out[-1][0], end)
    return out


@dataclass
class Piece:
    start: int
    end: int
    overlap_chars: int = 0       # leading characters repeated from the previous piece


def split_range(text: str, start: int, end: int, max_tokens: int, allow_overlap: bool) -> list[Piece]:
    """Split text[start:end] into pieces of at most max_tokens at block boundaries. A block larger
    than max_tokens stays whole (flagged oversized later). With allow_overlap, each piece after the
    first repeats the previous piece's last block when it is small, so a derivation or explanation
    that runs across the cut keeps its context."""
    if content_tokens(text[start:end]) <= max_tokens:
        return [Piece(start, end)]
    bl = blocks(text, start, end)
    pieces: list[Piece] = []
    cur_start, cur_tokens, overlap = bl[0][0], 0, 0
    last_block: Optional[tuple[int, int]] = None
    for b_start, b_end in bl:
        t = content_tokens(text[b_start:b_end])
        if cur_tokens and cur_tokens + t > max_tokens:
            pieces.append(Piece(cur_start, b_start, overlap))
            overlap = 0
            cur_start, cur_tokens = b_start, 0
            if allow_overlap and last_block is not None:
                lt = content_tokens(text[last_block[0]:last_block[1]])
                if lt <= MAX_OVERLAP_SHARE * max_tokens and lt + t <= max_tokens:
                    cur_start, cur_tokens, overlap = last_block[0], lt, last_block[1] - last_block[0]
        cur_tokens += t
        last_block = (b_start, b_end)
    pieces.append(Piece(cur_start, end, overlap))
    return pieces


# ----------------------------------------------------------------------------
# Section-aware merging
# ----------------------------------------------------------------------------
@dataclass
class Unit:
    """One piece of teaching text: a kept range of a span (or of a split span)."""
    span_id: str
    cell_index: int
    section_path: tuple
    text: str
    char_start: int              # offsets into the span's content
    char_end: int
    tokens: int
    overlap_chars: int = 0
    split_index: Optional[int] = None    # set when the span was split into several units
    stripped: list = field(default_factory=list)


@dataclass
class Group:
    units: list
    tokens: int = 0

    @property
    def sections(self) -> list[tuple]:
        return list(dict.fromkeys(u.section_path for u in self.units))


def related(a: tuple, b: tuple) -> bool:
    """Same section, parent/child, or siblings under the same parent (not just the notebook root)."""
    if a == b:
        return True
    n = min(len(a), len(b))
    if a[:n] == b[:n] and n >= 1:
        return True                                  # one contains the other
    return len(a) == len(b) and len(a) >= 2 and a[:-1] == b[:-1]


def common_prefix(paths: list[tuple]) -> tuple:
    if not paths:
        return ()
    prefix = list(paths[0])
    for p in paths[1:]:
        k = 0
        while k < min(len(prefix), len(p)) and prefix[k] == p[k]:
            k += 1
        prefix = prefix[:k]
    return tuple(prefix)


def group_units(units: list[Unit], min_tokens: int = TARGET_MIN_TOKENS, max_tokens: int = TEXT_MAX_TOKENS
                ) -> list[Group]:
    """Greedy, order-preserving grouping of one notebook's units.

    - Same section: keep adding while the group stays within max_tokens.
    - Different but related section (parent/child/sibling): add only while the group is still
      below min_tokens, so tiny subsections join their neighbours instead of standing alone.
    - Unrelated section: always start a new group (a major section boundary).
    - Pieces of one split span never share a group with each other.
    """
    groups: list[Group] = []
    for u in units:
        g = groups[-1] if groups else None
        if g is not None:
            last = g.units[-1]
            same_split = u.split_index is not None and last.span_id == u.span_id
            fits = g.tokens + u.tokens <= max_tokens
            if not same_split and fits and (
                    u.section_path == last.section_path or
                    (g.tokens < min_tokens and related(u.section_path, last.section_path)
                     and related(u.section_path, common_prefix(g.sections) or u.section_path))):
                g.units.append(u)
                g.tokens += u.tokens
                continue
        groups.append(Group(units=[u], tokens=u.tokens))
    return absorb_small_groups(groups, min_tokens, max_tokens)


def _joinable(a: Group, b: Group, max_tokens: int) -> bool:
    last, first = a.units[-1], b.units[0]
    if last.span_id == first.span_id and first.split_index is not None:
        return False                                 # never re-join pieces of one split span
    return a.tokens + b.tokens <= max_tokens and related(last.section_path, first.section_path)


def absorb_small_groups(groups: list[Group], min_tokens: int, max_tokens: int) -> list[Group]:
    """A group still below min_tokens joins the previous group, else the next one, when the two
    sections are related and the result fits max_tokens. Unrelated neighbours never merge."""
    out: list[Group] = []
    for g in groups:
        if out and (g.tokens < min_tokens or out[-1].tokens < min_tokens) and _joinable(out[-1], g, max_tokens):
            out[-1].units += g.units
            out[-1].tokens += g.tokens
        else:
            out.append(g)
    return out
