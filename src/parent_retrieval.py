"""
PH5-RETRIEVE-002 (issue #11), Gate A: parent-document retrieval, local and deterministic.

Search small *children*, answer with their *parent*. Gate A covers only the no-cost parts: the
child -> parent hierarchy, safe expansion and a fixture adapter. Nothing here embeds, downloads or
changes the default retrieval.

Parents
    In the real corpus a parent is an existing Concept chunk (CON_xxxxxx, PH2-CHUNK-001). It is
    already a coherent run of teaching spans in one notebook and section, already stripped of
    instructor notes and quizzes, already within the 800-token budget, and its ID is what every
    evaluation label points at. Tool chunks are their own parents (one child each).
Children
    Windows of at most `child_tokens` estimated tokens cut at paragraph boundaries inside each
    parent segment (fenced code, $$ math and tables are never cut). ID:
    `<parent_id>.c<NN>.s<size>`, e.g. CON_000123.c02.s128. Children never cross a segment, so
    they never cross a span, section or notebook.
Expansion (child hits -> parents), fail closed
    - unknown child / missing parent / parent in another notebook       -> mapping error, dropped
    - parent segment changed since the map was built (sha256 mismatch)  -> stale error, dropped
    - parent role not teaching/mixed, or no eligible segment            -> dropped
    - only eligible segments are ever serialized (a mixed parent's quiz span never is)
    - filters are re-checked on the parent, not only on the child
    - one entry per parent (first-hit rank), keeping every matched child for provenance
    - a parent over the per-parent budget is sliced to whole segments around the matched
      children; parents beyond the total budget are listed as omitted, never silently cut
All expanded text is untrusted source text: generation must quote it, never obey it.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from chunking import content_tokens, split_range  # noqa: E402

CHILD_SIZES = (128, 256)
CHILD_VERSION = "v1"
PARENT_TOKEN_BUDGET = 1200          # one parent, after slicing
CONTEXT_TOKEN_BUDGET = 4000         # all expanded parents together
EXPANDABLE_ROLES = {"teaching", "mixed"}
INJECTION_RE = re.compile(r"ignore (all |any |the )?(previous|preceding|prior|above)? ?(instructions|constraints)|"
                          r"\b(api[_ ]?keys?|secrets?|password|answer key)\b|reveal|leak", re.I)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass
class Segment:
    segment_id: str                  # span_id or fixture child_id
    text: str
    sha: str
    eligible: bool
    content_role: str


@dataclass
class Parent:
    parent_id: str
    notebook_id: str
    section: str
    role: str                        # teaching | mixed | quiz | environment_setup | ...
    chunk_type: str = "concept"
    segments: list[Segment] = field(default_factory=list)
    version: str = CHILD_VERSION


@dataclass
class Child:
    child_id: str
    parent_id: str
    notebook_id: str
    content_role: str
    retrieval_eligible: bool
    text: str
    segment_id: str


@dataclass
class ExpandedParent:
    parent_id: str
    notebook_id: str
    section: str
    chunk_type: str
    rank: int                                    # rank of its best child hit (1-based)
    matched_child_ids: list[str]
    segment_ids: list[str]                       # citations: only eligible segments
    text: str
    tokens: int
    sliced: bool = False
    omitted_segment_ids: list[str] = field(default_factory=list)
    injection_suspected: bool = False
    trust: str = "untrusted_source_text"


@dataclass
class Expansion:
    parents: list[ExpandedParent]
    errors: list[dict]                           # {"child_id", "parent_id", "error"}
    filtered_out: list[str]                      # parent IDs dropped by filters
    omitted_for_budget: list[str]
    context_tokens: int


class ParentStore:
    def __init__(self, parents: Iterable[Parent], children: Iterable[Child], corpus_version: str = ""):
        self.parents = {p.parent_id: p for p in parents}
        self.children = {c.child_id: c for c in children}
        self.corpus_version = corpus_version
        self._built_sha = {(p.parent_id, s.segment_id): s.sha for p in self.parents.values() for s in p.segments}

    # integrity ----------------------------------------------------------------
    def check_child(self, child_id: str) -> Optional[str]:
        child = self.children.get(child_id)
        if child is None:
            return "unknown_child"
        parent = self.parents.get(child.parent_id)
        if parent is None:
            return "missing_parent"
        if parent.notebook_id != child.notebook_id:
            return "cross_notebook_parent"
        if parent.role not in EXPANDABLE_ROLES:
            return "ineligible_parent"
        if not child.retrieval_eligible:
            return "ineligible_child"
        seg = next((s for s in parent.segments if s.segment_id == child.segment_id), None)
        if seg is None:
            return "child_segment_not_in_parent"
        if child.text not in seg.text:
            return "child_text_not_in_parent"
        return None

    def check_parent(self, parent: Parent) -> Optional[str]:
        for s in parent.segments:
            if sha(s.text) != s.sha or self._built_sha.get((parent.parent_id, s.segment_id)) != s.sha:
                return "stale_parent_segment"
        return None

    # expansion ------------------------------------------------------------------
    def expand(self, ranked_child_ids: list[str], filters: Optional[dict] = None,
               parent_budget: int = PARENT_TOKEN_BUDGET, context_budget: int = CONTEXT_TOKEN_BUDGET) -> Expansion:
        filters = filters or {}
        order: list[str] = []
        matched: dict[str, list[str]] = {}
        best: dict[str, int] = {}
        errors, filtered = [], []
        for rank, cid in enumerate(ranked_child_ids, 1):
            err = self.check_child(cid)
            child = self.children.get(cid)
            pid = child.parent_id if child else None
            if err:
                errors.append({"child_id": cid, "parent_id": pid, "error": err})
                continue
            parent = self.parents[pid]
            if pid not in matched:
                perr = self.check_parent(parent)
                if perr:
                    errors.append({"child_id": cid, "parent_id": pid, "error": perr})
                    matched[pid] = []                  # remember: do not retry this parent
                    continue
                if not self._passes(parent, filters):
                    filtered.append(pid)
                    matched[pid] = []
                    continue
                order.append(pid)
                best[pid] = rank
                matched[pid] = []
            if pid in best:
                matched[pid].append(cid)

        out, omitted, used = [], [], 0
        for pid in order:
            ep = self._serialize(self.parents[pid], best[pid], matched[pid], parent_budget)
            if ep is None:
                errors.append({"child_id": matched[pid][0], "parent_id": pid, "error": "no_eligible_segment"})
                continue
            if used + ep.tokens > context_budget:
                omitted.append(pid)
                continue
            used += ep.tokens
            out.append(ep)
        return Expansion(out, errors, filtered, omitted, used)

    @staticmethod
    def _passes(parent: Parent, filters: dict) -> bool:
        meta = {"notebook_id": parent.notebook_id, "chunk_type": parent.chunk_type, "retrieval_eligible": True}
        return all(meta.get(k) == v for k, v in filters.items())

    def _serialize(self, parent: Parent, rank: int, matched_ids: list[str], budget: int) -> Optional[ExpandedParent]:
        segs = [s for s in parent.segments if s.eligible and s.content_role == "teaching"]
        if not segs:
            return None
        hit_segs = {self.children[c].segment_id for c in matched_ids}
        keep, sliced = list(segs), False
        if sum(content_tokens(s.text) for s in segs) > budget:
            # whole segments around the matched ones, nearest first, until the budget is used
            idx = [i for i, s in enumerate(segs) if s.segment_id in hit_segs] or [0]
            chosen = set(idx)
            total = sum(content_tokens(segs[i].text) for i in chosen)
            for dist in range(1, len(segs)):
                for j in (min(idx) - dist, max(idx) + dist):
                    if 0 <= j < len(segs) and j not in chosen:
                        t = content_tokens(segs[j].text)
                        if total + t <= budget:
                            chosen.add(j)
                            total += t
            keep, sliced = [segs[i] for i in sorted(chosen)], True
        text = "\n\n".join(s.text for s in keep)
        return ExpandedParent(
            parent_id=parent.parent_id, notebook_id=parent.notebook_id, section=parent.section,
            chunk_type=parent.chunk_type, rank=rank, matched_child_ids=list(matched_ids),
            segment_ids=[s.segment_id for s in keep], text=text, tokens=content_tokens(text), sliced=sliced,
            omitted_segment_ids=[s.segment_id for s in segs if s not in keep],
            injection_suspected=bool(INJECTION_RE.search(text)))


# ----------------------------------------------------------------------------
# Real corpus: parents = Concept chunks (+ Tool chunks), children = windows
# ----------------------------------------------------------------------------
def build_corpus_store(concepts: list[dict], tools: list[dict], spans: dict[str, dict], child_tokens: int,
                       corpus_version: str = "") -> ParentStore:
    """`spans`: span_id -> span record from spans.jsonl (the text the segment offsets point into)."""
    parents, children = [], []
    for ch in concepts:
        segs = []
        for seg in ch["source_segments"]:
            sp = spans[seg["span_id"]]
            text = sp["content"][seg["char_start"]:seg["char_end"]]
            segs.append(Segment(f"{seg['span_id']}@{seg['char_start']}-{seg['char_end']}", text, sha(text),
                                sp["content_role"] == "teaching" and bool(sp["retrieval_eligible"]),
                                sp["content_role"]))
        parent = Parent(ch["chunk_id"], ch["notebook_id"], " > ".join(ch["section_path"]), "teaching", "concept", segs)
        parents.append(parent)
        n = 0
        for seg in segs:
            if not seg.eligible:
                continue
            for piece in split_range(seg.text, 0, len(seg.text), child_tokens, allow_overlap=False):
                text = seg.text[piece.start:piece.end].strip("\n")
                if not text.strip():
                    continue
                n += 1
                children.append(Child(f"{ch['chunk_id']}.c{n:02d}.s{child_tokens}", ch["chunk_id"], ch["notebook_id"],
                                      "teaching", True, text, seg.segment_id))
    from embeddings import embedding_text
    for t in tools:                                  # a tool is its own parent and its only child
        text = embedding_text(t)
        seg = Segment(t["chunk_id"], text, sha(text), True, "teaching")
        parents.append(Parent(t["chunk_id"], t["notebook_id"], " > ".join(t["section_path"]), "teaching", "tool", [seg]))
        children.append(Child(f"{t['chunk_id']}.c01.s{child_tokens}", t["chunk_id"], t["notebook_id"], "teaching", True,
                              text, seg.segment_id))
    return ParentStore(parents, children, corpus_version)


# ----------------------------------------------------------------------------
# Fixture adapter (evaluation/parent_fixture_*.jsonl, PR #12)
# ----------------------------------------------------------------------------
def load_fixture_store(eval_dir: Path) -> ParentStore:
    """Parents from parent_fixture_documents.jsonl, children from parent_fixture_children.jsonl.

    Segment rule: a teaching parent whose children are all eligible expands to its full verified
    text (one segment; every child text must occur in it). Any other parent expands only to its
    eligible children's texts, so a mixed parent's quiz child is never serialized."""
    docs = [json.loads(l) for l in (eval_dir / "parent_fixture_documents.jsonl").read_text().splitlines() if l.strip()]
    kids = [json.loads(l) for l in (eval_dir / "parent_fixture_children.jsonl").read_text().splitlines() if l.strip()]
    by_parent: dict[str, list[dict]] = {}
    for k in kids:
        by_parent.setdefault(k["parent_id"], []).append(k)
    parents, children = [], []
    for d in docs:
        ks = [k for k in by_parent.get(d["parent_id"], []) if k["child_id"] in d["child_ids"]]
        whole = d["role"] == "teaching" and all(k["retrieval_eligible"] and k["content_role"] == "teaching" for k in ks) \
            and all(k["text"] in d["text"] for k in ks)
        if whole:
            segs = [Segment(d["parent_id"], d["text"], sha(d["text"]), True, "teaching")]
        else:
            segs = [Segment(k["child_id"], k["text"], sha(k["text"]),
                            bool(k["retrieval_eligible"]) and k["content_role"] == "teaching", k["content_role"])
                    for k in ks]
        parents.append(Parent(d["parent_id"], d["notebook_id"], d["section"], d["role"], "concept", segs,
                              d.get("version", "")))
        seg_of = {k["child_id"]: (d["parent_id"] if whole else k["child_id"]) for k in ks}
        for k in ks:
            children.append(Child(k["child_id"], k["parent_id"], k["notebook_id"], k["content_role"],
                                  bool(k["retrieval_eligible"]), k["text"], seg_of[k["child_id"]]))
    known = {c.child_id for c in children}
    for k in kids:                                   # dangling children (parent missing) stay unresolvable
        if k["child_id"] not in known:
            children.append(Child(k["child_id"], k["parent_id"], k["notebook_id"], k["content_role"],
                                  bool(k["retrieval_eligible"]), k["text"], k["child_id"]))
    return ParentStore(parents, children, corpus_version="fixture-v1")
