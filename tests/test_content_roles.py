"""
Tests for PH1-ROLE-001: content roles for markdown spans and code cells.

    python -m unittest discover -s tests

Synthetic tests always run. Corpus tests run when data/processed/cells.jsonl exists (built locally
by `python src/ingestion.py`; data/ is not committed).
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
import content_role_classifier as crc  # noqa: E402
from notebook_parser import parse_notebook  # noqa: E402

EXCLUDED_ROLES = {"instructor_note", "quiz", "agenda", "business_context", "preamble", "rhetorical_question",
                  "data_loading", "environment_setup", "debugging", "non_teaching", "unknown"}


def md(src):
    return {"cell_type": "markdown", "metadata": {}, "source": src}


def code(src, outputs=None):
    return {"cell_type": "code", "metadata": {}, "execution_count": 1, "source": src, "outputs": outputs or []}


def parse(cells, name="07 - Roles Fixture.ipynb"):
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / name
        path.write_text(json.dumps({"nbformat": 4, "nbformat_minor": 0, "metadata": {}, "cells": cells}),
                        encoding="utf-8")
        return parse_notebook(path)[1]


def classify(cells, labels=None):
    """Parse a synthetic notebook (with a title so nothing is preamble), classify with no label file."""
    parsed = parse([md("# Lecture\n")] + cells)
    result = crc.classify_cells(parsed, labels if labels is not None else {})
    return parsed[1:], result


def span_role(src):
    cells, _ = classify([md(src)])
    sp = cells[0].spans[-1]
    return sp.content_role, sp.retrieval_eligible


def code_role(src, section="## Section\n"):
    cells, _ = classify([md(section), code(src)])
    c = cells[-1]
    return c.content_role, c.retrieval_eligible


class MarkdownRules(unittest.TestCase):
    def test_preamble(self):
        parsed = parse([md("Intro before any heading.\n"), md("# Title\nBody text that explains things.")])
        crc.classify_cells(parsed, {})
        self.assertEqual(parsed[0].spans[0].content_role, "preamble")
        self.assertFalse(parsed[0].spans[0].retrieval_eligible)

    def test_teaching_definition(self):
        role, elig = span_role("## Precision\nPrecision is the share of predicted positives that are "
                               "actually positive: $\\frac{TP}{TP+FP}$. It matters when false positives are costly.")
        self.assertEqual((role, elig), ("teaching", True))

    def test_instructor_note_block(self):
        role, elig = span_role("**Note to Instructor:**\n> Ask the learners to try this before the reveal.")
        self.assertEqual((role, elig), ("instructor_note", False))

    def test_instructor_note_mixed_with_teaching_is_queued(self):
        src = ("**Note to Instructor:** pause here.\n\nTo summarize, gradient descent moves the weights against "
               "the gradient of the loss, scaled by the learning rate, until the loss stops decreasing much.")
        cells, result = classify([md(src)])
        self.assertEqual(cells[0].spans[-1].content_role, "unknown")
        self.assertEqual([q["proposed_role"] for q in result["queue"]], ["instructor_note"])

    def test_quiz_heading_and_mcq(self):
        self.assertEqual(span_role("## Quiz 1\nWhich of these is a loss function?")[0], "quiz")
        mcq = "Which metric ignores true negatives?\n\na) Accuracy\nb) Precision\nc) Specificity\n\nAnswer: b"
        self.assertEqual(span_role(mcq), ("quiz", False))

    def test_agenda(self):
        self.assertEqual(span_role("## Agenda\n- Bias\n- Variance\n- Regularization"), ("agenda", False))

    def test_business_context_first_and_repeat(self):
        cells, _ = classify([md("## Business Context\nA retailer wants to forecast demand for 500 stores."),
                             md("## Business Context\nA retailer wants to forecast demand for 500 stores.")])
        first, repeat = cells[0].spans[-1], cells[1].spans[-1]
        self.assertEqual((first.content_role, first.retrieval_index), ("business_context", "support"))
        self.assertEqual((repeat.content_role, repeat.retrieval_index), ("business_context", "none"))
        self.assertFalse(first.retrieval_eligible or repeat.retrieval_eligible)

    def test_scenario_framing(self):
        role, elig = span_role("You are working as a data scientist at an e-commerce company that wants to "
                               "reduce churn among its premium subscribers.")
        self.assertEqual((role, elig), ("business_context", False))

    def test_question_heading_only(self):
        self.assertEqual(span_role("### Why do we need regularization?"), ("rhetorical_question", False))

    def test_heading_only_is_context(self):
        cells, _ = classify([md("## Decision Trees")])
        sp = cells[0].spans[-1]
        self.assertEqual((sp.content_role, sp.retrieval_eligible, sp.retrieval_index), ("teaching", False, "concepts"))

    def test_image_only_goes_to_resources(self):
        cells, _ = classify([md("<img src='https://drive.google.com/uc?id=abc' width=600>")])
        sp = cells[0].spans[-1]
        self.assertEqual((sp.content_role, sp.retrieval_eligible, sp.retrieval_index), ("teaching", False, "resources"))

    def test_formatting_only(self):
        cells, _ = classify([md("## Topic\nText that explains the topic in enough words to be teaching."),
                             md("---\n<br>")])
        self.assertFalse(cells[1].spans[-1].retrieval_eligible)

    def test_leading_rule_does_not_make_heading_eligible(self):
        cells, _ = classify([md("---\n## Bagging\n")])
        self.assertFalse(cells[0].spans[-1].retrieval_eligible)

    def test_short_caption_lead_in(self):
        role, elig = span_role("Plotting the residuals:")
        self.assertEqual(role, "teaching")


class CodeRules(unittest.TestCase):
    def test_environment_setup(self):
        self.assertEqual(code_role("!pip install xgboost -q"), ("environment_setup", False))
        self.assertEqual(code_role("import warnings\nwarnings.filterwarnings('ignore')\nnp.random.seed(42)"),
                         ("environment_setup", False))
        self.assertEqual(code_role("import locale\nlocale.getpreferredencoding = lambda: 'UTF-8'"),
                         ("environment_setup", False))

    def test_data_loading(self):
        self.assertEqual(code_role("import pandas as pd\ndf = pd.read_csv('data.csv')\ndf"), ("data_loading", False))
        self.assertEqual(code_role("import joblib\nX = joblib.load('X.joblib')"), ("data_loading", False))
        self.assertEqual(code_role("files = sorted(os.listdir(path))"), ("data_loading", False))

    def test_constants_and_copies_are_not_tools(self):
        self.assertEqual(code_role("DATA_URL = 'https://example.com/data.csv'\nBATCH = 32"), ("non_teaching", False))
        self.assertEqual(code_role("df1 = df.copy()"), ("non_teaching", False))

    def test_feature_selection_copy_is_still_a_tool(self):
        role, elig = code_role("X = df[['age', 'income']].copy()\ny = df['churn']")
        self.assertTrue(elig, role)

    def test_shell_and_timing(self):
        self.assertEqual(code_role("!ls"), ("non_teaching", False))
        self.assertEqual(code_role('print(f"Time taken for fits : {end - start}")'), ("non_teaching", False))

    def test_inspection(self):
        self.assertEqual(code_role("len(df)"), ("non_teaching", False))
        # ... unless the section teaches that method
        self.assertEqual(code_role("df.head()", section="## Viewing data with head and tail\n"),
                         ("tool_demonstration", True))

    def test_tool_roles(self):
        self.assertEqual(code_role("def sigmoid(z):\n    return 1 / (1 + np.exp(-z))")[0], "tool_function")
        self.assertEqual(code_role("import matplotlib.pyplot as plt\nplt.plot(x, y)\nplt.show()"),
                         ("visualization", True))
        role, elig = code_role("model = LogisticRegression()\nmodel.fit(X_train, y_train)\nmodel.score(X_test, y_test)")
        self.assertIn(role, crc.TOOL_ROLES)
        self.assertTrue(elig)

    def test_comments_only(self):
        self.assertEqual(code_role("# model.fit(X, y)\n# TODO"), ("non_teaching", False))

    def test_invalid_python_is_queued(self):
        cells, result = classify([md("## Section\n"), code("for i in range(3)\n    print(i")])
        self.assertEqual(cells[-1].content_role, "unknown")
        self.assertEqual(len(result["queue"]), 1)

    def test_invalid_syntax_flag_blocks_eligibility(self):
        self.assertEqual(crc.retrieval_for_code(crc.Decision("tool_demonstration", 0.8, "x",
                                                             flags=("invalid_syntax",))), (False, "tools"))


class Labels(unittest.TestCase):
    SRC = "for i in range(3)\n    print(i"

    def _label(self, rid, text, role="tool_demonstration", method="llm"):
        return {rid: {"id": rid, "content_hash": crc.content_hash(text), "content_role": role,
                      "role_confidence": 0.8, "role_reason": "test", "role_flags": ["invalid_syntax"],
                      "method": method}}

    def _cells(self, labels):
        cells, result = classify([md("## Section\n"), code(self.SRC)], labels)
        return cells[-1], result

    def test_label_resolves_queued_record(self):
        rid = self._cells({})[0].cell_id
        cell, result = self._cells(self._label(rid, self.SRC))
        self.assertEqual((cell.content_role, cell.role_method), ("tool_demonstration", "llm"))
        self.assertEqual(result["queue"], [])
        self.assertEqual(cell.role_flags, ["invalid_syntax"])
        self.assertFalse(cell.retrieval_eligible)

    def test_stale_label_is_ignored(self):
        rid = self._cells({})[0].cell_id
        cell, result = self._cells(self._label(rid, self.SRC + "\n# edited"))
        self.assertEqual(cell.content_role, "unknown")
        self.assertEqual(result["stale_labels"], 1)

    def test_manual_label_overrides_rule(self):
        cells, _ = classify([md("## Section\n"), code("!pip install xgboost")])
        cell = cells[-1]
        labels = self._label(cell.cell_id, cell.content, role="non_teaching", method="manual")
        cells, _ = classify([md("## Section\n"), code("!pip install xgboost")], labels)
        self.assertEqual((cells[-1].content_role, cells[-1].role_method), ("non_teaching", "manual"))

    def test_label_outside_taxonomy_is_rejected(self):
        rid = self._cells({})[0].cell_id
        with self.assertRaises(ValueError):
            self._cells(self._label(rid, self.SRC, role="teaching"))     # markdown role on a code cell

    def test_label_file_is_valid(self):
        labels = crc.load_labels()
        for rid, rec in labels.items():
            allowed = crc.MARKDOWN_ROLES if "_span_" in rid else crc.CODE_ROLES
            self.assertIn(rec["content_role"], allowed, rid)
            self.assertIn(rec["method"], ("llm", "manual"), rid)
            self.assertEqual(len(rec["content_hash"]), 16, rid)


CELLS = config.PROCESSED_DIR / config.CELLS_JSONL


@unittest.skipUnless(CELLS.exists(), "data/processed/cells.jsonl not built")
class Corpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cells = [json.loads(l) for l in CELLS.read_text(encoding="utf-8").splitlines() if l.strip()]
        cls.spans = [sp for c in cls.cells for sp in c.get("spans", [])]
        cls.code = [c for c in cls.cells if c["cell_type"] == "code"]

    def test_every_record_has_role_fields(self):
        for kind, records, allowed in (("span", self.spans, crc.MARKDOWN_ROLES), ("code", self.code, crc.CODE_ROLES)):
            for r in records:
                rid = r.get("span_id") or r["cell_id"]
                self.assertIn(r["content_role"], allowed, rid)
                self.assertIn(r["role_method"], ("rule", "llm", "manual"), rid)
                self.assertIsInstance(r["role_confidence"], float, rid)
                self.assertTrue(r["role_reason"], rid)
                self.assertIsInstance(r["retrieval_eligible"], bool, rid)

    def test_unknown_rate(self):
        records = self.spans + self.code
        unknown = sum(r["content_role"] == "unknown" for r in records)
        self.assertLessEqual(unknown / len(records), 0.10)

    def test_excluded_roles_never_eligible(self):
        for r in self.spans + self.code:
            if r["content_role"] in EXCLUDED_ROLES:
                self.assertFalse(r["retrieval_eligible"], r.get("span_id") or r["cell_id"])

    def test_outputs_have_eligibility(self):
        for c in self.cells:
            for o in c.get("outputs", []):
                self.assertIsInstance(o["retrieval_eligible"], bool, c["cell_id"])
                if o.get("output_role") in ("log", "error", "dataframe_dump"):
                    self.assertFalse(o["retrieval_eligible"], c["cell_id"])

    def test_spans_jsonl_matches_cells(self):
        path = config.PROCESSED_DIR / crc.SPANS_JSONL
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual([r["span_id"] for r in rows], [sp["span_id"] for sp in self.spans])
        self.assertEqual([r["content_role"] for r in rows], [sp["content_role"] for sp in self.spans])


if __name__ == "__main__":
    unittest.main()
