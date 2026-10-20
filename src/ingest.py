#!/usr/bin/env python3
"""
Ingest Jupyter/Colab notebooks into clean, chunked JSONL for the Revision Agent.

Usage (from the project root):
    python src/ingest.py                      # reads data/raw/*.ipynb, writes to data/
    python src/ingest.py --sample 5           # also print 5 random chunks to eyeball

Outputs (in --out, default data/):
    chunks.jsonl            cleaned chunks, one JSON object per line (for RAG / training pairs)
    mcqs.jsonl              multiple-choice questions parsed from the notebooks
    instructor_notes.jsonl  instructor-only blocks, kept separate so the agent never quotes them

Only the Python standard library is needed. Notebook metadata (author name, user id,
execution info) is never read, so it cannot leak into the outputs.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import random
import re
import sys
from pathlib import Path

# ----------------------------------------------------------------------------
# Patterns
# ----------------------------------------------------------------------------
INSTRUCTOR_RE = re.compile(
    r"\[\s*(note to instructor|note for instructor|instructor note|ask learners)[^\]]*\]", re.I
)
# Only strip known HTML tags, so things like `dtype='<U32'` or <class 'int'> survive.
HTML_TAG_RE = re.compile(
    r"</?(?:span|font|img|table|tbody|thead|tr|td|th|div|center|b|i|u|p|sub|sup|"
    r"strong|em|iframe|video|source|a|h[1-6])\b[^>]*>",
    re.I,
)
BR_RE = re.compile(r"<br\s*/?>", re.I)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(https?://[^)]*\)")
HR_RE = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$")
CODE_LABEL_RE = re.compile(r"^#{1,6}\s*code\s*:?\s*$", re.I)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
MCQ_Q_RE = re.compile(r"^#+\s*question\s*$", re.I | re.M)
MCQ_C_RE = re.compile(r"^#+\s*choices?\s*$", re.I | re.M)
OPTION_RE = re.compile(r"^\s*[-*]\s*\[( |x|X)\]\s*(.+?)\s*$")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
NOISE_CODE_LINE_RE = re.compile(r"^\s*(!pip|%pip|%matplotlib|!apt)")
FIGURE_REPR_RE = re.compile(r"^<(Figure|Axes|matplotlib)")
LEFTOVER_HTML_RE = re.compile(r"</?(span|img|font|table|td|tr|div)\b", re.I)

# Sections that add no revision value (title/agenda boilerplate)
SKIP_HEADINGS = {"agenda"}


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def to_text(value) -> str:
    """Notebook fields are either a string or a list of strings."""
    if isinstance(value, list):
        return "".join(value)
    return value or ""


def split_blocks(text: str) -> list[str]:
    """Split on blank lines, but never inside a ``` fence."""
    blocks, cur, in_fence = [], [], False
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and not line.strip():
            if cur:
                blocks.append("\n".join(cur))
                cur = []
        else:
            cur.append(line)
    if cur:
        blocks.append("\n".join(cur))
    return blocks


def clean_markdown(text: str) -> str:
    text = HTML_COMMENT_RE.sub("", text)
    text = BR_RE.sub("\n", text)
    text = MD_IMAGE_RE.sub("", text)
    text = HTML_TAG_RE.sub("", text)
    text = html.unescape(text)
    text = MD_LINK_RE.sub(r"\1", text)
    lines = []
    for line in text.split("\n"):
        line = line.rstrip()
        if HR_RE.match(line) or CODE_LABEL_RE.match(line):
            continue
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_mcq(text: str):
    """Parse '# Question ... # Choices ... - [x] answer' blocks. Returns dict or None."""
    q, c = MCQ_Q_RE.search(text), MCQ_C_RE.search(text)
    if not (q and c and q.end() < c.start()):
        return None
    question = text[q.end():c.start()].strip()
    options, extra = [], []
    for line in text[c.end():].split("\n"):
        m = OPTION_RE.match(line)
        if m:
            options.append((m.group(1).lower() == "x", m.group(2).strip()))
        elif line.strip() and options:
            extra.append(line.strip())
    if len(options) < 2 or not any(ok for ok, _ in options) or not question:
        return None
    return {
        "question": question,
        "options": [o for _, o in options],
        "answers": [o for ok, o in options if ok],
        "explanation": " ".join(extra),
    }


def render_code(cell: dict, max_out: int) -> str | None:
    src = to_text(cell.get("source", ""))
    lines = [l for l in src.split("\n") if not NOISE_CODE_LINE_RE.match(l)]
    src = "\n".join(lines).strip("\n")
    if not src.strip():
        return None
    out_parts = []
    for o in cell.get("outputs", []) or []:
        kind = o.get("output_type")
        if kind == "stream":
            out_parts.append(to_text(o.get("text", "")))
        elif kind in ("execute_result", "display_data"):
            plain = to_text((o.get("data") or {}).get("text/plain", ""))
            if plain and not FIGURE_REPR_RE.match(plain):
                out_parts.append(plain)
        # 'error' outputs are skipped on purpose
    out = ANSI_RE.sub("", "".join(out_parts)).strip()
    if len(out) > max_out:
        out = out[:max_out] + "\n...[truncated]"
    block = f"```python\n{src}\n```"
    if out:
        block += f"\n\nOutput:\n```\n{out}\n```"
    return block


# ----------------------------------------------------------------------------
# Notebook -> units (heading / text / code), plus MCQs and instructor notes
# ----------------------------------------------------------------------------
def notebook_to_units(nb: dict, nb_id: str, max_out: int):
    units, mcqs, notes = [], [], []
    near_heading = ""

    for cell in nb.get("cells", []):
        ctype = cell.get("cell_type")

        if ctype == "code":
            block = render_code(cell, max_out)
            if block:
                units.append({"kind": "code", "text": block})
            continue
        if ctype != "markdown":
            continue

        text = clean_markdown(to_text(cell.get("source", "")))
        if not text:
            continue

        mcq = parse_mcq(text)
        if mcq:
            mcq.update(notebook_id=nb_id, near_heading=near_heading)
            mcqs.append(mcq)
            continue

        # Move instructor-only blocks out (keep any heading lines inside them)
        kept = []
        for block in split_blocks(text):
            if INSTRUCTOR_RE.search(block):
                body = []
                for line in block.split("\n"):
                    if HEADING_RE.match(line):
                        kept.append(line)
                    else:
                        body.append(line)
                notes.append({"notebook_id": nb_id, "near_heading": near_heading,
                              "text": "\n".join(body).strip()})
            else:
                kept.append(block)
        text = "\n\n".join(kept).strip()
        if not text:
            continue

        # Emit heading units and text units, ignoring '#' inside code fences
        buf, in_fence = [], False
        for line in text.split("\n"):
            if line.strip().startswith("```"):
                in_fence = not in_fence
            m = None if in_fence else HEADING_RE.match(line)
            if m:
                if "\n".join(buf).strip():
                    units.append({"kind": "text", "text": "\n".join(buf).strip()})
                buf = []
                heading = m.group(2).replace("**", "").strip()
                near_heading = heading
                units.append({"kind": "heading", "level": len(m.group(1)), "text": heading})
            else:
                buf.append(line)
        if "\n".join(buf).strip():
            units.append({"kind": "text", "text": "\n".join(buf).strip()})

    return units, mcqs, notes


# ----------------------------------------------------------------------------
# Units -> chunks
# ----------------------------------------------------------------------------
def chunk_units(units: list[dict], max_chars: int, min_chars: int):
    chunks, buf, size = [], [], 0
    path: dict[int, str] = {}
    title, skipping = None, False

    def current_path() -> list[str]:
        return [path[l] for l in sorted(path)]

    def flush():
        nonlocal buf, size
        text = "\n\n".join(t for _, t in buf).strip()
        if text:
            chunks.append({
                "heading_path": current_path(),
                "text": text,
                "has_code": any(k == "code" for k, _ in buf),
            })
        buf, size = [], 0

    for u in units:
        if u["kind"] == "heading":
            level, name = u["level"], u["text"]
            if level <= 2:
                if name.lower() in SKIP_HEADINGS:
                    if size >= min_chars:
                        flush()
                    skipping = True
                    continue
                skipping = False
                if size >= min_chars:
                    flush()
                path[level] = name
                for l in [l for l in path if l > level]:
                    del path[l]
                if title is None and level == 1:
                    title = name
                line = "#" * level + " " + name
                buf.append(("text", line))
                size += len(line)
            elif not skipping:
                line = "#" * level + " " + name
                buf.append(("text", line))
                size += len(line)
            continue

        if skipping:
            continue
        if buf and size + len(u["text"]) > max_chars and size >= min_chars:
            flush()
        buf.append((u["kind"], u["text"]))
        size += len(u["text"])
    flush()

    # Merge a tiny trailing chunk into the previous one
    if len(chunks) >= 2 and len(chunks[-1]["text"]) < min_chars:
        last = chunks.pop()
        chunks[-1]["text"] += "\n\n" + last["text"]
        chunks[-1]["has_code"] = chunks[-1]["has_code"] or last["has_code"]

    return chunks, title


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def norm_hash(text: str) -> str:
    return hashlib.sha1(re.sub(r"\s+", " ", text.lower()).strip().encode()).hexdigest()[:12]


def write_jsonl(path: Path, rows: list[dict]):
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Ingest notebooks into chunked JSONL.")
    ap.add_argument("--raw", default="data/raw", help="folder with .ipynb files")
    ap.add_argument("--out", default="data", help="output folder")
    ap.add_argument("--max-chars", type=int, default=2000, help="target max chunk size (~500 tokens)")
    ap.add_argument("--min-chars", type=int, default=250, help="merge chunks smaller than this")
    ap.add_argument("--max-output-chars", type=int, default=1200, help="truncate long code outputs")
    ap.add_argument("--sample", type=int, default=0, help="print N random chunks for review")
    args = ap.parse_args()

    raw, out = Path(args.raw), Path(args.out)
    files = sorted(p for p in raw.rglob("*.ipynb") if ".ipynb_checkpoints" not in p.parts)
    if not files:
        sys.exit(f"No .ipynb files found in {raw}/")
    out.mkdir(parents=True, exist_ok=True)

    all_chunks, all_mcqs, all_notes = [], [], []
    seen, dups, failed = set(), 0, []

    for p in files:
        nb_id = str(p.relative_to(raw).with_suffix(""))
        try:
            nb = json.loads(p.read_text(encoding="utf-8"))
            if "cells" not in nb:
                raise ValueError("no 'cells' key (old nbformat?)")
        except Exception as e:  # keep going on bad files
            failed.append((nb_id, str(e)))
            continue

        units, mcqs, notes = notebook_to_units(nb, nb_id, args.max_output_chars)
        chunks, title = chunk_units(units, args.max_chars, args.min_chars)
        title = title or p.stem

        for i, ch in enumerate(chunks):
            h = norm_hash(ch["text"])
            if h in seen:
                dups += 1
                continue
            seen.add(h)
            all_chunks.append({
                "chunk_id": f"{nb_id}::{i:03d}",
                "notebook_id": nb_id,
                "notebook_title": title,
                "heading_path": " > ".join(ch["heading_path"]),
                "text": ch["text"],
                "has_code": ch["has_code"],
                "n_chars": len(ch["text"]),
                "text_hash": h,
            })
        for j, m in enumerate(mcqs):
            m["mcq_id"] = f"{nb_id}::q{j:02d}"
        all_mcqs.extend(mcqs)
        all_notes.extend(n for n in notes if n["text"])

    write_jsonl(out / "chunks.jsonl", all_chunks)
    write_jsonl(out / "mcqs.jsonl", all_mcqs)
    write_jsonl(out / "instructor_notes.jsonl", all_notes)

    # ---- report ----
    sizes = [c["n_chars"] for c in all_chunks] or [0]
    print(f"Notebooks processed : {len(files) - len(failed)} / {len(files)}")
    print(f"Chunks written      : {len(all_chunks)}  (avg {sum(sizes) // len(sizes)} chars, "
          f"min {min(sizes)}, max {max(sizes)})")
    print(f"MCQs extracted      : {len(all_mcqs)}")
    print(f"Instructor blocks   : {len(all_notes)} (moved to instructor_notes.jsonl)")
    print(f"Duplicate chunks    : {dups} dropped")
    print(f"Output folder       : {out}/")

    for nb_id, err in failed:
        print(f"[warn] could not read {nb_id}: {err}")
    short = [c for c in all_chunks if c["n_chars"] < args.min_chars // 2]
    long_ = [c for c in all_chunks if c["n_chars"] > args.max_chars * 1.5]
    html_left = [c for c in all_chunks if LEFTOVER_HTML_RE.search(c["text"])]
    for label, items in (("very short chunks", short), ("very long chunks", long_),
                         ("chunks with leftover HTML", html_left)):
        if items:
            ids = ", ".join(c["chunk_id"] for c in items[:3])
            print(f"[warn] {len(items)} {label}, e.g. {ids}")

    if args.sample and all_chunks:
        for c in random.sample(all_chunks, min(args.sample, len(all_chunks))):
            print("\n" + "=" * 72)
            print(f"{c['chunk_id']}  |  {c['heading_path']}")
            print("-" * 72)
            print(c["text"])


if __name__ == "__main__":
    main()