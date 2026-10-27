"""
Tests for PH2-CHUNK-001 (issue #3): Concept, Tool and Resource chunks.

    python -m unittest discover -s tests

Synthetic tests always run. Corpus tests run when data/processed/ is built locally (data/ is not
committed).
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import assets  # noqa: E402
import chunk_builder as cb  # noqa: E402
import chunking  # noqa: E402
import config  # noqa: E402
import ingestion  # noqa: E402
from tool_concept_linker import Evidence, ToolConceptLink  # noqa: E402
from tools_inventory import load_cells  # noqa: E402


def md(src):
    return {"cell_type": "markdown", "metadata": {}, "source": src}


def code(src, outputs=None):
    return {"cell_type": "code", "metadata": {}, "execution_count": 1, "source": src, "outputs": outputs or []}


LONG = ("Precision is the share of predicted positives that are actually positive. It matters when a false "
        "positive is costly, for example flagging a genuine transaction as fraud. ")
NB_A = [
    md("# Metrics"),                                                                     # 0
    md("## Precision\nPrecision is $\\frac{TP}{TP+FP}$."),                               # 1 tiny span
    md("It is computed only over predicted positives, so it ignores false negatives."),  # 2 same section
    code("def precision(tp, fp):\n    return tp / (tp + fp)"),                           # 3 tool_function
    md("### Worked example\nWith 40 true positives and 10 false positives precision is 0.8."),   # 4 child
    md("## Quiz\nWhich metric ignores false negatives?\na) Recall\nb) Precision\n\nAnswer: b"),  # 5 quiz
    md("**Note to Instructor:**\n> Ask the learners to compute it by hand first."),     # 6 instructor note
    code("!pip install -q scikit-learn"),                                                # 7 setup
    code("import pandas as pd\ndf = pd.read_csv('fraud.csv')"),                          # 8 data loading
    md("# Clustering\nK-means groups points around centroids and repeats assignment and update steps "
       "until the assignments stop changing between iterations."),                      # 9 unrelated section
    md("## Agenda\n- Bias\n- Variance"),                                                 # 10 agenda
    code("y_pred = model.predict(X_test)"),                                              # 11 one line, no output
    md("# Gallery\n<img src='https://drive.google.com/uc?id=ZZZ'>"),                     # 12 image, no prose: pending
]
NB_B = [
    md("# Metrics"),
    md("## Precision\nPrecision again, in another notebook."),
]


class Built:
    _instance = None

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.raw, self.out = base / "raw", base / "out"
        self.raw.mkdir()
        for name, cells in (("21 - Chunk Fixture A.ipynb", NB_A), ("22 - Chunk Fixture B.ipynb", NB_B)):
            (self.raw / name).write_text(json.dumps({"nbformat": 4, "nbformat_minor": 0, "metadata": {},
                                                     "cells": cells}), encoding="utf-8")
        ingestion.run(self.raw, self.out, quiet=True)
        assets.run(self.out, self.raw, quiet=True)
        self.concepts, self.tools, self.resources, self.exclusions = cb.run(self.out, quiet=True)
        self.cells = load_cells(self.out / config.CELLS_JSONL)
        self.spans = {sp.span_id: sp for c in self.cells for sp in c.spans}

    @classmethod
    def get(cls) -> "Built":
        if cls._instance is None:
            cls._instance = Built()
        return cls._instance


def sid(nb: int, cell: int, span: int = 0) -> str:
    return f"nb_{nb:02d}_cell_{cell:03d}_span_{span:03d}"


class ConceptChunks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = Built.get()

    def chunk_of(self, span_id):
        return next(c for c in self.b.concepts if span_id in c.source_span_ids)

    def test_tiny_spans_merge_within_section(self):            # 1
        ch = self.chunk_of(sid(21, 1))
        self.assertIn(sid(21, 2), ch.source_span_ids)          # continuation of the same section
        self.assertIn(sid(21, 4), ch.source_span_ids)          # small child section joins its parent
        self.assertTrue(ch.quality_flags.is_merged)
        self.assertEqual(ch.section_path, ["Metrics", "Precision"])
        self.assertIn("Section path: Metrics > Precision", ch.breadcrumb)
        self.assertTrue(ch.content.startswith("Notebook: Chunk Fixture A\nSection path: Metrics > Precision"))

    def test_no_merge_across_notebooks(self):                   # 2
        for ch in self.b.concepts:
            self.assertEqual(len({s.split("_cell_")[0] for s in ch.source_span_ids}), 1, ch.chunk_id)
        self.assertNotEqual(self.chunk_of(sid(22, 1)).chunk_id, self.chunk_of(sid(21, 1)).chunk_id)

    def test_no_merge_across_unrelated_sections(self):          # 3
        clustering = self.chunk_of(sid(21, 9))
        self.assertEqual(clustering.source_span_ids, [sid(21, 9)])
        self.assertFalse(chunking.related(("Metrics", "Precision"), ("Clustering",)))
        self.assertTrue(chunking.related(("A", "B"), ("A", "C")))
        self.assertTrue(chunking.related(("A",), ("A", "B", "C")))
        self.assertFalse(chunking.related(("A", "B", "X"), ("A", "C")))

    def test_source_reconstruction(self):                       # 4
        for ch in self.b.concepts:
            parts = [self.b.spans[s.span_id].content[s.char_start:s.char_end].strip("\n") for s in ch.source_segments]
            self.assertEqual("\n\n".join(parts), ch.raw_text, ch.chunk_id)
            self.assertEqual(ch.source_span_ids, list(dict.fromkeys(s.span_id for s in ch.source_segments)))
            self.assertTrue(ch.source_cell_ids)

    def test_excludes_support_spans(self):                      # 8 (markdown part)
        chunked = {s for ch in self.b.concepts for s in ch.source_span_ids}
        for span_id in (sid(21, 5), sid(21, 6), sid(21, 10)):  # quiz, instructor note, agenda
            self.assertNotIn(span_id, chunked)
            self.assertIn(self.b.spans[span_id].content_role, cb.EXCLUDED_SPAN_ROLES)
        for ch in self.b.concepts:
            self.assertNotIn("Note to Instructor", ch.raw_text)
            self.assertNotIn("Answer: b", ch.raw_text)

    def test_every_eligible_span_chunked(self):
        eligible = {s for s, sp in self.b.spans.items() if sp.content_role == "teaching" and sp.retrieval_eligible}
        excluded = {e.record_id for e in self.b.exclusions if e.record_type == "span"}
        self.assertEqual(eligible - excluded, eligible & {s for ch in self.b.concepts for s in ch.source_span_ids})


class ToolAndResourceChunks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = Built.get()

    def test_tool_chunk_provenance(self):                       # 5
        self.assertEqual(len(self.b.tools), 1)
        tc = self.b.tools[0]
        self.assertEqual((tc.source_cell_id, tc.source_cell_ids, tc.tool_type), ("nb_21_cell_003", [3], "tool_function"))
        self.assertEqual(tc.code, "def precision(tp, fp):\n    return tp / (tp + fp)")
        self.assertIn(tc.code, tc.content)
        self.assertEqual(tc.section_path, ["Metrics", "Precision"])
        self.assertTrue(tc.purpose and tc.title)
        self.assertEqual(tc.linked_concept_chunk_ids, [next(c for c in self.b.concepts
                                                             if sid(21, 1) in c.source_span_ids).chunk_id])

    def test_excludes_setup_loading_and_unsuitable_code(self):  # 8 (code part)
        cells = {c.cell_id: c for c in self.b.cells}
        chunked = {tc.source_cell_id for tc in self.b.tools}
        self.assertEqual(cells["nb_21_cell_007"].content_role, "environment_setup")
        self.assertEqual(cells["nb_21_cell_008"].content_role, "data_loading")
        self.assertFalse({"nb_21_cell_007", "nb_21_cell_008", "nb_21_cell_011"} & chunked)
        reasons = {e.record_id: e.reason for e in self.b.exclusions if e.record_type == "tool"}
        self.assertTrue(any("not answer-suitable" in r for r in reasons.values()))

    def test_pending_vision_resource_excluded(self):            # 6
        res = [json.loads(l) for l in (self.b.out / "resources.jsonl").read_text().splitlines()]
        pending = [r["resource_id"] for r in res if r["retrieval_status"] == "pending_vision"]
        self.assertTrue(pending)
        chunked = {rc.resource_id for rc in self.b.resources}
        self.assertFalse(set(pending) & chunked)
        excluded = {e.record_id for e in self.b.exclusions if e.record_type == "resource"}
        self.assertTrue(set(pending) <= excluded)
        for rc in self.b.resources:
            self.assertEqual(rc.vision_status, "pending")
            self.assertFalse(rc.retrieval_eligible)
            self.assertIn("not extracted", rc.content)

    def test_ids_unique(self):                                  # 9
        ids = [c.chunk_id for c in self.b.concepts] + [c.chunk_id for c in self.b.tools] + \
              [c.chunk_id for c in self.b.resources]
        self.assertEqual(len(ids), len(set(ids)))

    def test_stable_across_runs(self):                          # 10
        again = cb.run(self.b.out, quiet=True)
        for first, second in zip((self.b.concepts, self.b.tools, self.b.resources, self.b.exclusions), again):
            self.assertEqual([r.model_dump() for r in first], [r.model_dump() for r in second])


class Attachment(unittest.TestCase):                            # 7
    def test_only_allowed_relationships_attach(self):
        b = Built.get()
        concepts = [c.model_copy(deep=True) for c in b.concepts]
        tools = [t.model_copy(deep=True) for t in b.tools]
        for c in concepts:
            c.linked_tool_ids, c.linked_tool_chunk_ids, c.secondary_tool_ids, c.uncertain_tool_ids = [], [], [], []
        for t in tools:
            t.linked_concept_chunk_ids, t.secondary_concept_chunk_ids, t.uncertain_concept_chunk_ids = [], [], []
        target = next(c for c in concepts if sid(21, 1) in c.source_span_ids)
        other = next(c for c in concepts if sid(21, 9) in c.source_span_ids)
        tool = tools[0]

        def link(span_id, rel):
            return ToolConceptLink(link_id="L", tool_id=tool.tool_id, tool_cell_id=tool.source_cell_id,
                                   span_id=span_id, span_cell_id=span_id[:14], relationship=rel, confidence=0.6,
                                   evidence=[Evidence(kind="x", detail="", weight=0.6)], notebook_id="nb_21",
                                   tool_section_path="", span_section_path="")
        cb.attach(concepts, tools, [], [], [link(sid(21, 1), "uncertain"), link(sid(21, 9), "supports")])
        self.assertEqual(target.linked_tool_ids, [])
        self.assertEqual(target.uncertain_tool_ids, [tool.tool_id])
        self.assertEqual(other.linked_tool_ids, [])
        self.assertEqual(other.secondary_tool_ids, [tool.tool_id])
        self.assertEqual(tool.linked_concept_chunk_ids, [])
        cb.attach(concepts, tools, [], [], [link(sid(21, 1), "implements")])
        self.assertEqual(target.linked_tool_ids, [tool.tool_id])
        self.assertEqual(tool.linked_concept_chunk_ids, [target.chunk_id])


class Primitives(unittest.TestCase):
    def test_split_keeps_blocks_whole(self):
        text = "\n\n".join([f"Paragraph {i}. " + "word " * 60 for i in range(6)]
                           + ["$$\nx = 1\n\ny = 2\n$$", "```python\na = 1\n\nb = 2\n```"])
        pieces = chunking.split_range(text, 0, len(text), max_tokens=150, allow_overlap=False)
        self.assertGreater(len(pieces), 1)
        for p in pieces:
            piece = text[p.start:p.end]
            self.assertEqual(piece.count("$$") % 2, 0)
            self.assertEqual(piece.count("```") % 2, 0)
        self.assertEqual(pieces[0].start, 0)
        self.assertEqual(pieces[-1].end, len(text))

    def test_overlap_only_when_allowed(self):
        text = "\n\n".join([f"Step {i}: " + "term " * 14 for i in range(12)])     # ~18 tokens per block
        plain = chunking.split_range(text, 0, len(text), max_tokens=100, allow_overlap=False)
        over = chunking.split_range(text, 0, len(text), max_tokens=100, allow_overlap=True)
        self.assertTrue(all(p.overlap_chars == 0 for p in plain))
        self.assertTrue(any(p.overlap_chars for p in over))

    def test_strip_embedded_note_in_list(self):
        text = ("- Analogy:\n    - We sort food items.\n    - <span>**[Note to Instructor]:**</span> Show the demo.\n"
                "- **Mantra:** Row, Column.\n")
        kept = "".join(text[s:e] for s, e in chunking.kept_ranges(text, ["embedded_instructor_note"]))
        self.assertNotIn("Instructor", kept)
        self.assertIn("Mantra", kept)
        self.assertIn("We sort food items", kept)


CHUNKS = config.PROCESSED_DIR / cb.CONCEPT_CHUNKS


@unittest.skipUnless(CHUNKS.exists(), "chunks not built (data/ is kept local)")
class Corpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = config.PROCESSED_DIR
        cls.concepts = [json.loads(l) for l in (d / cb.CONCEPT_CHUNKS).read_text(encoding="utf-8").splitlines()]
        cls.tools = [json.loads(l) for l in (d / cb.TOOL_CHUNKS).read_text(encoding="utf-8").splitlines()]
        cls.resources = [json.loads(l) for l in (d / cb.RESOURCE_CHUNKS).read_text(encoding="utf-8").splitlines()]
        cls.exclusions = [json.loads(l) for l in (d / cb.CHUNK_EXCLUSIONS).read_text(encoding="utf-8").splitlines()]
        cls.spans = {json.loads(l)["span_id"]: json.loads(l) for l in (d / "spans.jsonl").read_text(encoding="utf-8").splitlines()}
        cls.tool_inv = [json.loads(l) for l in (d / "tools.jsonl").read_text(encoding="utf-8").splitlines()]
        cls.res_inv = [json.loads(l) for l in (d / "resources.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_every_eligible_span_covered(self):
        eligible = {k for k, s in self.spans.items() if s["content_role"] == "teaching" and s["retrieval_eligible"]}
        covered = {s for c in self.concepts for s in c["source_span_ids"]}
        excluded = {e["record_id"] for e in self.exclusions if e["record_type"] == "span"}
        self.assertEqual(eligible - covered, excluded & eligible)
        for s in covered:
            self.assertEqual(self.spans[s]["content_role"], "teaching")

    def test_every_suitable_tool_and_attachable_resource_covered(self):
        excluded = {e["record_id"] for e in self.exclusions}
        tools = {t["tool_id"] for t in self.tools}
        for t in self.tool_inv:
            self.assertTrue(t["tool_id"] in tools or t["tool_id"] in excluded, t["tool_id"])
        res = {r["resource_id"] for r in self.resources}
        for r in self.res_inv:
            self.assertTrue(r["resource_id"] in res or r["resource_id"] in excluded, r["resource_id"])

    def test_no_support_content(self):
        import re
        from content_role_classifier import INSTRUCTOR_RE
        shell = re.compile(r"^\s*[!%]\s*(pip|apt|wget|gdown|curl|unzip|kaggle|conda)\b", re.M)
        for c in self.concepts:
            self.assertIsNone(INSTRUCTOR_RE.search(c["raw_text"]), c["chunk_id"])
        for t in self.tools:
            self.assertIsNone(shell.search(t["code"]), t["chunk_id"])

    def test_unique_ids_and_provenance(self):
        ids = [c["chunk_id"] for c in self.concepts + self.tools + self.resources]
        self.assertEqual(len(ids), len(set(ids)))
        for c in self.concepts:
            self.assertTrue(c["notebook_id"] and c["source_span_ids"] and c["source_cell_ids"] and c["section_path"])
        for t in self.tools:
            self.assertTrue(t["tool_id"] and t["source_cell_ids"] and t["code"])
        for r in self.resources:
            self.assertTrue(r["resource_id"] and r["source_cell_ids"])
            self.assertEqual(r["vision_status"], "pending")

    def test_attachment_uses_allowed_relationships(self):
        links = [json.loads(l) for l in (config.PROCESSED_DIR / "tool_concept_links.jsonl").read_text().splitlines()]
        allowed = {(l["tool_id"], l["span_id"]) for l in links if l["relationship"] in cb.PRIMARY_RELATIONSHIPS}
        for c in self.concepts:
            for tid in c["linked_tool_ids"]:
                self.assertTrue(any((tid, s) in allowed for s in c["source_span_ids"]), (c["chunk_id"], tid))


if __name__ == "__main__":
    unittest.main()
