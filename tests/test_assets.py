"""
Tests for the Tools and Resources inventories (src/assets.py).

Synthetic tests always run. Corpus tests run when data/processed/cells.jsonl and the raw
notebooks are present locally.
"""
from __future__ import annotations

import base64
import json
import shutil
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import assets  # noqa: E402
import config  # noqa: E402
import ingestion  # noqa: E402


def png(width: int, height: int) -> bytes:
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


B64_BIG = base64.b64encode(png(200, 120)).decode()
B64_TINY = base64.b64encode(png(16, 16)).decode()


def md(src):
    return {"cell_type": "markdown", "metadata": {}, "source": src}


def code(src, outputs=None):
    return {"cell_type": "code", "metadata": {}, "execution_count": 1, "source": src, "outputs": outputs or []}


CELLS = [
    md("# Setup"),
    code("!pip install -q nrclex"),                                                   # 1 environment_setup
    code("!gdown 1abc\n!unzip data.zip"),                                             # 2 data_loading
    code("import pandas as pd\nimport numpy as np"),                                  # 3 non_teaching
    code("df = pd.read_csv('cars.csv')\ndf.head()"),                                  # 4 data_loading
    md("## Precision\nPrecision is the share of predicted positives that are right, used a lot."),  # 5
    code("def precision(tp, fp):\n    return tp / (tp + fp)"),                        # 6 function
    code("tp, fp = 40, 13\nscore = tp / (tp + fp)\nscore2 = score * 100\nprint(score2)",
         outputs=[{"output_type": "stream", "name": "stdout", "text": "75.4\n"}]),    # 7 implementation
    code("plt.plot(x, y)\nplt.show()",
         outputs=[{"output_type": "display_data", "metadata": {},
                   "data": {"image/png": B64_BIG, "text/plain": "<Figure>"}}]),       # 8 visualization + plot
    code("X_train, X_test, y_train, y_test = train_test_split(X, y)\nm = LogisticRegression()\n"
         "m.fit(X_train, y_train)\npred = m.predict(X_test)"),                         # 9 workflow
    code("a + b",
         outputs=[{"output_type": "error", "ename": "ValueError", "evalue": "shapes", "traceback": []}]),  # 10 debugging
    code("df.head()"),                                                                # 11 non_teaching
    code("df['x'] = pred"),                                                           # 12 trivial demo
    md(f"![Confusion matrix layout](data:image/png;base64,{B64_BIG})\n"
       f"<img src='https://drive.google.com/uc?id=XYZ' width=300>\n"
       f"![image.png](data:image/png;base64,{B64_TINY})"),                            # 13 three images
]


class SyntheticAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.raw, cls.out = base / "raw", base / "out"
        cls.raw.mkdir()
        (cls.raw / "14 - Classification metrics.ipynb").write_text(
            json.dumps({"nbformat": 4, "nbformat_minor": 0, "metadata": {}, "cells": CELLS}), encoding="utf-8")
        ingestion.run(cls.raw, cls.out, quiet=True)
        cls.tools, cls.resources = assets.run(cls.out, cls.raw, quiet=True)
        cls.by_cell = {t.cell_id: t for t in cls.tools}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def tool(self, index):
        return self.by_cell[f"nb_14_cell_{index:03d}"]

    def test_one_tool_per_code_cell(self):
        n_code = sum(c["cell_type"] == "code" for c in CELLS)
        self.assertEqual(len(self.tools), n_code)
        self.assertEqual([t.tool_id for t in self.tools], [f"TOOL_{i:04d}" for i in range(1, n_code + 1)])

    def test_tool_types(self):
        expected = {1: "environment_setup", 2: "data_loading", 3: "non_teaching", 4: "data_loading",
                    6: "function", 7: "implementation", 8: "visualization", 9: "workflow",
                    10: "debugging", 11: "non_teaching", 12: "demonstration"}
        self.assertEqual({i: self.tool(i).tool_type for i in expected}, expected)

    def test_answer_eligibility(self):
        self.assertTrue(self.tool(6).quality.suitable_for_answer)
        self.assertTrue(self.tool(9).quality.suitable_for_answer)
        for i in (1, 2, 3, 10, 11, 12):          # setup, loading, imports, error, inspection, trivial
            self.assertFalse(self.tool(i).quality.suitable_for_answer, i)

    def test_inputs_outputs(self):
        f = self.tool(6)
        self.assertEqual(f.inputs, ["tp", "fp"])
        self.assertEqual(f.outputs, ["precision"])
        self.assertTrue(f.quality.is_self_contained)
        w = self.tool(9)
        self.assertEqual(w.inputs, ["train_test_split", "X", "y", "LogisticRegression"])
        self.assertFalse(w.quality.is_self_contained)
        self.assertIn("pred", w.outputs)

    def test_titles_and_context(self):
        self.assertEqual(self.tool(6).title, "Precision")
        self.assertEqual(self.tool(7).source.section_path, "Setup > Precision")
        self.assertTrue(self.tool(7).quality.has_explanation_nearby)
        self.assertIn("Precision is the share", self.tool(7).description)

    def test_resources(self):
        kinds = [(r.cell_id, r.resource_type, r.availability) for r in self.resources]
        self.assertEqual(kinds, [
            ("nb_14_cell_008", "plot", "embedded"),
            ("nb_14_cell_013", "unclassified", "embedded"),
            ("nb_14_cell_013", "external_reference", "external_unavailable"),
            ("nb_14_cell_013", "decorative", "embedded"),
        ])
        plot, img, ext, tiny = self.resources
        self.assertEqual(plot.linked_tool_ids, [self.tool(8).tool_id])
        self.assertEqual((plot.image_reference.width, plot.image_reference.height), (200, 120))
        self.assertTrue((config.ROOT / plot.image_reference.local_path).exists()
                        or Path(plot.image_reference.local_path).exists())
        self.assertEqual(img.caption.source, "alt_text")
        self.assertEqual(img.title, "Confusion matrix layout")
        self.assertIsNone(img.quality.contains_formula)             # unknown until a vision model looks
        self.assertIsNone(ext.image_reference.local_path)
        self.assertEqual(ext.image_reference.location, "google_drive")
        self.assertEqual(ext.retrieval_status, "unavailable")
        self.assertTrue(tiny.quality.is_decorative)
        self.assertEqual(tiny.retrieval_status, "excluded_decorative")

    def test_image_size_parsing(self):
        self.assertEqual(assets.image_size(png(31, 7)), (31, 7))
        self.assertEqual(assets.image_size(b"not an image"), (None, None))


@unittest.skipUnless((config.PROCESSED_DIR / config.CELLS_JSONL).exists()
                     and any(config.RAW_NOTEBOOKS_DIR.glob("*.ipynb")), "processed corpus not present (kept local)")
class CorpusAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        shutil.copy(config.PROCESSED_DIR / config.CELLS_JSONL, cls.out / config.CELLS_JSONL)
        cls.tools, cls.resources = assets.run(cls.out, config.RAW_NOTEBOOKS_DIR, quiet=True)
        cls.cells = [json.loads(l) for l in (cls.out / config.CELLS_JSONL).read_text(encoding="utf-8").splitlines()]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_code_cell_is_a_tool(self):
        code_cells = {c["cell_id"] for c in self.cells if c["cell_type"] == "code" and not c["is_empty"]}
        self.assertEqual({t.cell_id for t in self.tools}, code_cells)

    def test_only_eligible_types_are_suitable(self):
        for t in self.tools:
            if t.quality.suitable_for_answer:
                self.assertIn(t.tool_type, assets.ANSWER_ELIGIBLE, t.tool_id)

    def test_every_image_is_a_resource(self):
        cells = {c["cell_id"]: c for c in self.cells}
        image_outputs = sum(sum(o["content_type"] == "image" for o in c["outputs"]) for c in self.cells)
        markdown_refs = sum(len(c["image_refs"]) for c in self.cells if c["cell_type"] == "markdown")
        self.assertEqual(len(self.resources), image_outputs + markdown_refs)
        for r in self.resources:
            self.assertIn(r.cell_id, cells)

    def test_embedded_images_saved_external_not(self):
        for r in self.resources:
            if r.availability == "embedded":
                self.assertTrue(Path(r.image_reference.local_path).exists()
                                or (config.ROOT / r.image_reference.local_path).exists(), r.resource_id)
            else:
                self.assertIsNone(r.image_reference.local_path)

    def test_deterministic_ids(self):
        tools2, resources2 = assets.run(self.out, config.RAW_NOTEBOOKS_DIR, quiet=True)
        self.assertEqual([t.model_dump() for t in self.tools], [t.model_dump() for t in tools2])
        self.assertEqual([r.model_dump() for r in self.resources], [r.model_dump() for r in resources2])

    def test_golden_prompt_links_resolve(self):
        tools = {t.tool_id: t for t in self.tools}
        resources = {r.resource_id: r for r in self.resources}
        for line in (ROOT / "evaluation" / "golden_prompts.jsonl").read_text(encoding="utf-8").splitlines():
            p = json.loads(line)
            cited = {f"{s['notebook_id']}_cell_{i:03d}" for s in p["expected_sources"] for i in s["cell_ids"]}
            for tid in p["expected_tool_ids"]:
                self.assertIn(tools[tid].cell_id, cited, p["prompt_id"])
            for rid in p["expected_resource_ids"]:
                self.assertIn(resources[rid].cell_id, cited, p["prompt_id"])


if __name__ == "__main__":
    unittest.main()
