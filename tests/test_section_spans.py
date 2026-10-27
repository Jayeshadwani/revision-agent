"""
Regression tests for PH1-FIX-001: sections per heading span, and output roles.

    python -m pytest tests/          # or: python -m unittest discover -s tests

Synthetic tests always run. The three real-cell regressions (nb_45_cell_000, nb_30_cell_001,
nb_30_cell_027) run when the notebooks are present in data/raw/notebooks/ (kept local).
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import config  # noqa: E402
import ingestion  # noqa: E402
from notebook_parser import (  # noqa: E402
    classify_output, parse_notebook, parse_output, scan_headings, split_spans,
)


def md(src):
    return {"cell_type": "markdown", "metadata": {}, "source": src}


def code(src, outputs=None):
    return {"cell_type": "code", "metadata": {}, "execution_count": 1, "source": src, "outputs": outputs or []}


def parse_cells(cells, name="05 - Fixture.ipynb"):
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / name
        path.write_text(json.dumps({"nbformat": 4, "nbformat_minor": 0, "metadata": {}, "cells": cells}),
                        encoding="utf-8")
        return parse_notebook(path)


def assert_reconstructs(test: unittest.TestCase, cell) -> None:
    test.assertEqual("".join(sp.content for sp in cell.spans), cell.content, cell.cell_id)
    test.assertEqual(cell.spans[0].char_start, 0)
    test.assertEqual(cell.spans[-1].char_end, len(cell.content))
    for a, b in zip(cell.spans, cell.spans[1:]):
        test.assertEqual(a.char_end, b.char_start, f"gap/overlap in {cell.cell_id}")
    for sp in cell.spans:
        test.assertEqual(cell.content[sp.char_start:sp.char_end], sp.content)


FIXTURE_FIRST = (
    "Course notes on metrics\n"                     # plain title line: must stay preamble
    "\n"
    "Some intro text.\n"
    "\n"
    "## Precision\n"
    "Precision is $\\frac{TP}{TP + FP}$ and costs $5.\n"
    "\n"
    "```python\n"
    "# not a heading, it's a comment\n"
    "## also not a heading\n"
    "```\n"
    "\n"
    "### Worked table\n"
    "| a | b |\n"
    "|---|---|\n"
    "| 1 | 2 |\n"
    "\n"
    "Recall\n"
    "------\n"                                      # setext level 2
    "Recall is $$\\frac{TP}{TP+FN}$$\n"
    "\n"
    "  ## Indented heading\n"                       # ATX with up to 3 leading spaces
    "#nospace is plain text\n"
    "<center><h3>F1 score</h3></center>\n"         # HTML heading wrapped in a tag
    "F1 text\n"
    "\n"
    "# Question\n"                                  # MCQ label: own span, section unchanged
    "Which?\n"
    "# Choices\n"
    "- [x] A\n"
)
FIXTURE_CELLS = [
    md(FIXTURE_FIRST),
    code("x = 1"),
    md("---\n## Leading rule\nText after a leading thematic break."),
    md("Continuation text with no heading.\n\n## Next section\nMore."),
    md("Overview\n========\nSetext level 1 resets the path."),
]


class SyntheticSpanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nb, cls.cells = parse_cells(FIXTURE_CELLS)

    def spans(self, i):
        return self.cells[i].spans

    def test_heading_forms(self):
        found = [(m.style, m.level, m.raw) for m in scan_headings(FIXTURE_FIRST)]
        self.assertEqual(found, [
            ("atx", 2, "Precision"), ("atx", 3, "Worked table"), ("setext", 2, "Recall"),
            ("atx", 2, "Indented heading"), ("html", 3, "F1 score"),
            ("atx", 1, "Question"), ("atx", 1, "Choices"),
        ])

    def test_code_block_hashes_are_not_headings(self):
        texts = [sp.heading_text for sp in self.spans(0)]
        self.assertNotIn("not a heading, it's a comment", texts)
        self.assertNotIn("also not a heading", texts)
        precision = next(sp for sp in self.spans(0) if sp.heading_text == "Precision")
        self.assertIn("## also not a heading", precision.content)          # stays inside the span

    def test_preamble_is_not_promoted(self):
        first = self.spans(0)[0]
        self.assertEqual(first.kind, "preamble")
        self.assertEqual(first.section_path, [])
        self.assertEqual(first.section_title, "Preamble")
        self.assertIn("Course notes on metrics", first.content)
        self.assertIn("Some intro text.", first.content)
        self.assertNotIn("## Precision", first.content)

    def test_paths_and_kinds(self):
        got = [(sp.kind, sp.section_path) for sp in self.spans(0)]
        self.assertEqual(got, [
            ("preamble", []),
            ("heading", ["Precision"]),
            ("heading", ["Precision", "Worked table"]),
            ("heading", ["Recall"]),
            ("heading", ["Indented heading"]),
            ("heading", ["Indented heading", "F1 score"]),
            ("label", ["Indented heading", "F1 score"]),
            ("label", ["Indented heading", "F1 score"]),
        ])

    def test_latex_and_table_stay_in_their_spans(self):
        by_head = {sp.heading_text: sp for sp in self.spans(0)}
        self.assertIn("$\\frac{TP}{TP + FP}$", by_head["Precision"].content)
        self.assertTrue(by_head["Precision"].contains_math)
        self.assertTrue(by_head["Worked table"].contains_table)
        self.assertIn("$$\\frac{TP}{TP+FN}$$", by_head["Recall"].content)
        self.assertIn("#nospace is plain text", by_head["Indented heading"].content)

    def test_leading_rule_is_ignored(self):
        sp = self.spans(2)
        self.assertEqual(len(sp), 1)
        self.assertEqual(sp[0].kind, "heading")
        self.assertEqual(sp[0].heading_text, "Leading rule")
        self.assertTrue(sp[0].content.startswith("---\n## Leading rule"))

    def test_text_before_first_heading_continues_previous_section(self):
        sp = self.spans(3)
        self.assertEqual(sp[0].kind, "continuation")
        self.assertEqual(sp[0].section_path, self.spans(2)[0].section_path)
        self.assertEqual(sp[1].section_title, "Next section")
        self.assertTrue(self.cells[3].has_multiple_sections)
        self.assertEqual(self.cells[3].section_accuracy_status, "fixed")

    def test_setext_level_one(self):
        sp = self.spans(4)
        self.assertEqual((sp[0].heading_level, sp[0].section_path), (1, ["Overview"]))

    def test_code_cells_inherit_governing_section(self):
        self.assertEqual(self.cells[1].spans, [])
        self.assertEqual(self.cells[1].section_path, ["Indented heading", "F1 score"])

    def test_reconstruction_and_ids(self):
        for c in self.cells:
            if c.cell_type == "markdown":
                assert_reconstructs(self, c)
                self.assertEqual([sp.span_id for sp in c.spans],
                                 [f"{c.cell_id}_span_{i:03d}" for i in range(len(c.spans))])

    def test_split_spans_edge_cases(self):
        self.assertEqual(split_spans(""), [])
        self.assertEqual([(s, e, h) for s, e, h in split_spans("plain")], [(0, 5, None)])
        only = split_spans("## A")
        self.assertEqual((only[0][0], only[0][1], only[0][2].text), (0, 4, "A"))

    def test_accuracy_check_is_zero_and_detects_corruption(self):
        acc = ingestion.section_accuracy(self.cells)
        self.assertGreater(acc["total"], 0)
        self.assertEqual(acc["wrong"], 0)
        broken = [c.model_copy(deep=True) for c in self.cells]
        broken[0].spans[2].section_path = ["Precision"]                   # mislabel the table span
        acc2 = ingestion.section_accuracy(broken)
        self.assertGreater(acc2["wrong"], 0)
        self.assertTrue(ingestion.span_integrity_errors(self.cells) == [])
        broken[0].spans[1].content += "x"                                  # break reconstruction
        self.assertTrue(ingestion.span_integrity_errors(broken))


class OutputRoleTests(unittest.TestCase):
    LESSON = "\n".join(["=" * 40, "LOSS FUNCTIONS, SIMPLY EXPLAINED"] + [
        f"• Point {i}: the loss penalizes confident wrong predictions much more than unsure ones"
        for i in range(120)])

    def test_roles(self):
        self.assertEqual(classify_output("error", "error", "ValueError: bad"), "error")
        self.assertEqual(classify_output("stream", "text", "Requirement already satisfied: numpy in /usr"), "log")
        self.assertEqual(classify_output("stream", "text", "Epoch 1/5\n10/10 [====] - loss: 0.3"), "log")
        self.assertEqual(classify_output("stream", "text", "anything", "stderr"), "log")
        self.assertEqual(classify_output("execute_result", "text", "0.85"), "result")
        self.assertEqual(classify_output("execute_result", "text", "Pipeline(steps=[('a', A())])"), "result")
        big = "\n".join(f"{i}  {i * 2}" for i in range(40))
        self.assertEqual(classify_output("execute_result", "table", big), "dataframe_dump")
        self.assertEqual(classify_output("execute_result", "table", "   a  b\n0  1  2"), "result")
        self.assertEqual(classify_output("stream", "text", self.LESSON), "teaching_text")

    def test_teaching_text_kept_beyond_4000_logs_cut(self):
        self.assertGreater(len(self.LESSON), config.MAX_OUTPUT_CHARS)
        lesson = parse_output({"output_type": "stream", "name": "stdout", "text": self.LESSON})
        self.assertEqual((lesson.output_role, lesson.truncated), ("teaching_text", False))
        self.assertEqual(lesson.content, self.LESSON)
        log = parse_output({"output_type": "stream", "name": "stdout",
                            "text": "\n".join(["Collecting x"] + ["  inflating: f.tif"] * 400)})
        self.assertEqual(log.output_role, "log")
        self.assertTrue(log.truncated)
        self.assertEqual(len(log.content), config.MAX_OUTPUT_CHARS)
        self.assertGreater(log.original_length, config.MAX_OUTPUT_CHARS)


@unittest.skipUnless(any(config.RAW_NOTEBOOKS_DIR.glob("*.ipynb")), "corpus not present (kept local)")
class RealCellRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cells = {}
        for name in ("45 - Text Pre-Processing NLTKspaCy.ipynb", "30 - Neural network 1.ipynb"):
            _, cells = parse_notebook(config.RAW_NOTEBOOKS_DIR / name)
            cls.cells.update({c.cell_id: c for c in cells})

    def test_nb_45_cell_000(self):
        c = self.cells["nb_45_cell_000"]
        assert_reconstructs(self, c)
        self.assertGreater(c.span_count, 1)
        self.assertTrue(c.has_multiple_sections)
        pre = c.spans[0]
        self.assertEqual((pre.kind, pre.section_path), ("preamble", []))
        self.assertIn("**Objective:**", pre.content)
        self.assertNotIn("## 1. Introduction", pre.content)          # not given to a later heading
        intro = c.spans[1]
        self.assertEqual(intro.heading_text, "1. Introduction: Why Text Preprocessing?")
        self.assertTrue(intro.content.startswith("## 1. Introduction"))
        table = next(sp for sp in c.spans if "| Feature" in sp.content)
        self.assertEqual(table.heading_text, "Comparison Table")
        self.assertEqual(table.section_path, ["NLTK vs. spaCy: Pros, Cons and Comparison", "Comparison Table"])
        self.assertTrue(table.contains_table)
        self.assertNotIn("| Feature", "".join(sp.content for sp in c.spans if sp is not table))

    def test_nb_30_cell_001(self):
        c = self.cells["nb_30_cell_001"]
        assert_reconstructs(self, c)
        self.assertEqual([sp.heading_text for sp in c.spans], [
            "Neural Networks: A Complete Beginner's Guide", "Table of Contents",
            "1. Why Neural Networks? - Limitations of Classical ML",
            "The Problem with Classical Machine Learning",
            "Logistic Regression", "K-Nearest Neighbors (KNN)", "Decision Trees",
            "Support Vector Machines (SVM)",
        ])
        for sp in c.spans:                                           # every span starts at its heading line
            self.assertTrue(sp.content.lstrip(" ").startswith("#"), sp.span_id)
        self.assertEqual(c.spans[4].section_path[-2:], [
            "The Problem with Classical Machine Learning", "Logistic Regression"])
        raw = json.loads((config.RAW_NOTEBOOKS_DIR / "30 - Neural network 1.ipynb").read_text(encoding="utf-8"))
        raw_text = "".join(raw["cells"][1]["source"])
        self.assertEqual("".join(c.content.split()), "".join(raw_text.split()))   # no text lost

    def test_nb_30_cell_027(self):
        out = self.cells["nb_30_cell_027"].outputs[0]
        self.assertEqual(out.output_role, "teaching_text")
        self.assertFalse(out.truncated)
        self.assertGreater(len(out.content), config.MAX_OUTPUT_CHARS)
        self.assertEqual(len(out.content), out.original_length)
        for needle in ("BINARY CROSS-ENTROPY", "Loss = -[y*log(ŷ) + (1-y)*log(1-ŷ)]", "SOFTMAX",
                       "CROSS-ENTROPY (Multi-class)", "Loss = -log(P_correct)", "WHY LOG?"):
            self.assertIn(needle, out.content)


if __name__ == "__main__":
    unittest.main()
