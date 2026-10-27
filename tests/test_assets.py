"""
Tests for the shared code/image helpers in src/assets.py.

The inventories themselves are tested in test_tools_inventory.py and test_resources_inventory.py.
"""
from __future__ import annotations

import base64
import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import assets  # noqa: E402
from notebook_parser import parse_notebook  # noqa: E402


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


class ClassifyToolTests(unittest.TestCase):
    """`assets.classify_tool` is the raw code rule the content-role classifier builds on."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        path = Path(cls.tmp.name) / "14 - Classification metrics.ipynb"
        path.write_text(json.dumps({"nbformat": 4, "nbformat_minor": 0, "metadata": {}, "cells": CELLS}),
                        encoding="utf-8")
        cls.cells = parse_notebook(path)[1]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_tool_types(self):
        expected = {1: "environment_setup", 2: "data_loading", 3: "non_teaching", 4: "data_loading",
                    6: "function", 7: "implementation", 8: "visualization", 9: "workflow",
                    10: "debugging", 11: "non_teaching", 12: "demonstration"}
        got = {i: assets.classify_tool(self.cells[i], assets.parseable(self.cells[i].content)) for i in expected}
        self.assertEqual(got, expected)

    def test_inputs_outputs(self):
        tree = assets.parseable(self.cells[6].content)
        self.assertEqual(assets.names_io(tree), (["tp", "fp"], ["precision"], True))
        inputs, outputs, self_contained = assets.names_io(assets.parseable(self.cells[9].content))
        self.assertEqual(inputs, ["train_test_split", "X", "y", "LogisticRegression"])
        self.assertIn("pred", outputs)
        self.assertFalse(self_contained)

    def test_image_size_parsing(self):
        self.assertEqual(assets.image_size(png(31, 7)), (31, 7))
        self.assertEqual(assets.image_size(b"not an image"), (None, None))


if __name__ == "__main__":
    unittest.main()
