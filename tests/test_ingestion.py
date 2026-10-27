"""
Tests for Phase 1 ingestion.

    python -m pytest tests/          # or: python -m unittest discover -s tests

Synthetic-notebook tests always run. Corpus tests run only when the real notebooks are in
data/raw/notebooks/ (they are kept local and never committed).
"""
from __future__ import annotations

import filecmp
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import config  # noqa: E402
import ingestion  # noqa: E402
from notebook_parser import clean_heading, math_signals, parse_notebook  # noqa: E402


def md(src):
    return {"cell_type": "markdown", "metadata": {}, "source": src}


def code(src, outputs=None, n=1):
    return {"cell_type": "code", "metadata": {}, "execution_count": n, "source": src, "outputs": outputs or []}


def write_nb(folder: Path, name: str, cells: list[dict]) -> Path:
    path = folder / name
    path.write_text(json.dumps({"nbformat": 4, "nbformat_minor": 0, "metadata": {}, "cells": cells}), encoding="utf-8")
    return path


SAMPLE_CELLS = [
    code("import numpy as np"),                                                     # 0 before any heading
    md("## <span style='color:red'>Precision and **Recall**</span> 📈"),           # 1
    md("Precision is $\\frac{TP}{TP + FP}$.\n\n\n\nIt costs $5 and $10."),         # 2
    md("# Question\nWhich is right?\n# Choices\n- [x] A\n- [ ] B"),                 # 3 MCQ labels
    md("| a | b |\n|---|---|\n| 1 | 2 |"),                                         # 4
    code("from sklearn.metrics import precision_score\n\nfor i in range(3):\n    print(i)   ",
         outputs=[{"output_type": "stream", "name": "stdout", "text": ["0\n1\n2\n"]}]),  # 5
    md(""),                                                                         # 6 empty
    md("### Recall\n- point one\n- point two"),                                     # 7
    md("![diagram](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB)"),       # 8
    code("plt.plot(x)", outputs=[{"output_type": "display_data", "metadata": {},
                                  "data": {"image/png": "iVBOR...", "text/plain": "<Figure>"}}]),  # 9
    md("[Note to instructor: ask learners first] Recall is coverage."),            # 10
    code("1/0", outputs=[{"output_type": "error", "ename": "ZeroDivisionError",
                          "evalue": "division by zero", "traceback": ["\x1b[31m..."]}]),  # 11
]


class SyntheticNotebookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        folder = Path(cls.tmp.name)
        cls.path = write_nb(folder, "07 - Sample metrics.ipynb", SAMPLE_CELLS)
        cls.nb, cls.cells = parse_notebook(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_identity_and_cell_ids(self):
        self.assertEqual(self.nb.notebook_id, "nb_07")
        self.assertEqual(self.nb.notebook_title, "Sample metrics")
        self.assertEqual([c.cell_index for c in self.cells], list(range(len(SAMPLE_CELLS))))
        self.assertEqual(self.cells[5].cell_id, "nb_07_cell_005")
        self.assertTrue(all(c.source_hash.startswith("sha256:") for c in self.cells))

    def test_every_cell_kept_including_empty(self):
        self.assertEqual(len(self.cells), len(SAMPLE_CELLS))
        self.assertTrue(self.cells[6].is_empty)
        self.assertIn("empty_cell", self.cells[6].warnings)

    def test_sections_and_hierarchy(self):
        self.assertEqual(self.cells[0].section, config.DEFAULT_SECTION)
        self.assertEqual(self.cells[1].section, "Precision and Recall")      # html, bold, emoji removed
        self.assertEqual(self.cells[2].section, "Precision and Recall")
        self.assertEqual(self.cells[7].section_path, ["Precision and Recall", "Recall"])
        self.assertEqual(self.cells[8].section, "Recall")

    def test_mcq_labels_do_not_change_sections(self):
        self.assertTrue(self.cells[3].contains_mcq)
        self.assertEqual(self.cells[4].section, "Precision and Recall")
        self.assertFalse(any(h.structural for h in self.cells[3].headings))

    def test_math_detection_ignores_currency(self):
        self.assertTrue(self.cells[2].contains_latex)
        self.assertEqual(self.cells[2].math_block_count, 1)
        self.assertFalse(math_signals("It costs $5 and $10.")["contains_math"])
        self.assertTrue(math_signals("$$a^2 + b^2$$")["formula_heavy"])
        self.assertFalse(self.cells[5].contains_math)                         # code cells never math

    def test_conservative_cleaning(self):
        self.assertNotIn("\n\n\n", self.cells[2].content)                     # blank lines collapsed
        self.assertIn("$\\frac{TP}{TP + FP}$", self.cells[2].content)          # LaTeX untouched
        self.assertIn("\n    print(i)", self.cells[5].content)                # indentation kept
        self.assertFalse(self.cells[5].content.endswith(" "))                 # trailing spaces removed
        self.assertIn("<span", self.cells[1].content)                         # markup kept in content
        self.assertTrue(self.cells[10].contains_instructor_note)
        self.assertIn("Note to instructor", self.cells[10].content)           # flagged, not removed

    def test_tables_lists_images(self):
        self.assertTrue(self.cells[4].contains_table)
        self.assertTrue(self.cells[7].contains_list)
        self.assertEqual(self.cells[8].image_refs, ["data:image/png;base64"])
        self.assertNotIn("iVBOR", self.cells[8].content)                      # base64 payload omitted

    def test_code_outputs_libraries_plots(self):
        c = self.cells[5]
        self.assertTrue(c.contains_code)
        self.assertEqual(c.libraries, ["sklearn"])
        self.assertEqual(c.outputs[0].content, "0\n1\n2")
        self.assertNotIn("0\n1\n2", c.content)                                # outputs kept separate
        self.assertTrue(self.cells[9].contains_plot)
        self.assertEqual(self.cells[9].outputs[0].content_type, "image")
        self.assertEqual(self.cells[11].outputs[0].content, "ZeroDivisionError: division by zero")
        self.assertIn("error_output", self.cells[11].warnings)
        self.assertEqual(self.nb.libraries, ["numpy", "sklearn"])

    def test_heading_cleanup(self):
        self.assertEqual(clean_heading("**1️⃣ Forward Pass** {#fp}:"), "1 Forward Pass")
        self.assertEqual(clean_heading("<span style='color: violet;'> What is EDA? </span>"), "What is EDA?")
        self.assertEqual(clean_heading("Churn using [SMOTE](https://imbalanced-learn.org/x.html)"), "Churn using SMOTE")

    def test_malformed_notebook_is_flagged_not_crashed(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "99 - Broken.ipynb"
            bad.write_text("{not json", encoding="utf-8")
            nb, cells = parse_notebook(bad)
        self.assertEqual(nb.parse_status, "failed")
        self.assertTrue(nb.parse_error)
        self.assertEqual(cells, [])

    def test_pipeline_is_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            raw, out1, out2 = Path(d) / "raw", Path(d) / "o1", Path(d) / "o2"
            raw.mkdir()
            write_nb(raw, "01 - One.ipynb", SAMPLE_CELLS)
            write_nb(raw, "02 - Two.ipynb", SAMPLE_CELLS[:4])
            ingestion.run(raw, out1, quiet=True)
            ingestion.run(raw, out2, quiet=True)
            for name in (config.CELLS_JSONL, config.NOTEBOOKS_JSONL, config.INVENTORY_CSV,
                         config.TOPIC_CANDIDATES_CSV, config.REPORT_MD):
                self.assertTrue(filecmp.cmp(out1 / name, out2 / name, shallow=False), name)


@unittest.skipUnless(any(config.RAW_NOTEBOOKS_DIR.glob("*.ipynb")), "corpus not present (kept local)")
class CorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out1, cls.out2 = Path(cls.tmp.name) / "run1", Path(cls.tmp.name) / "run2"
        cls.result = ingestion.run(config.RAW_NOTEBOOKS_DIR, cls.out1, quiet=True)
        ingestion.run(config.RAW_NOTEBOOKS_DIR, cls.out2, quiet=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_acceptance_checks_pass(self):
        failed = [(n, d) for n, ok, d in self.result["checks"] if not ok]
        self.assertEqual(failed, [])

    def test_all_notebooks_parsed(self):
        nbs = self.result["notebooks"]
        self.assertEqual(len(nbs), config.EXPECTED_NOTEBOOKS)
        self.assertTrue(all(n.parse_status == "success" for n in nbs))
        self.assertTrue(all(n.total_cells > 0 for n in nbs))

    def test_cell_counts_match_source(self):
        cells = self.result["cells"]
        for path in sorted(config.RAW_NOTEBOOKS_DIR.glob("*.ipynb")):
            n_src = len(json.loads(path.read_text(encoding="utf-8"))["cells"])
            self.assertEqual(sum(c.file_name == path.name for c in cells), n_src, path.name)

    def test_ids_unique_and_ordered(self):
        cells = self.result["cells"]
        self.assertEqual(len({c.cell_id for c in cells}), len(cells))
        for a, b in zip(cells, cells[1:]):
            if a.notebook_id == b.notebook_id:
                self.assertEqual(b.cell_index, a.cell_index + 1)

    def test_no_embedded_base64_left(self):
        self.assertFalse(any(";base64,iVBOR" in c.content or ";base64,/9j/" in c.content
                             for c in self.result["cells"]))

    def test_reproducible_output(self):
        for name in (config.CELLS_JSONL, config.NOTEBOOKS_JSONL, config.INVENTORY_CSV,
                     config.TOPIC_CANDIDATES_CSV, config.REPORT_MD):
            self.assertTrue(filecmp.cmp(self.out1 / name, self.out2 / name, shallow=False), name)

    def test_golden_set_sources_exist(self):
        """Every cell cited by the golden set exists, in the stated notebook."""
        golden = ROOT / "evaluation" / "golden_set.jsonl"
        ids = {c.cell_id for c in self.result["cells"]}
        for line in golden.read_text(encoding="utf-8").splitlines():
            q = json.loads(line)
            for s in q["expected_sources"]:
                for i in s["cell_ids"]:
                    self.assertIn(f"{s['notebook_id']}_cell_{i:03d}", ids, q["question_id"])


if __name__ == "__main__":
    unittest.main()
