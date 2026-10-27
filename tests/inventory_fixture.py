"""Shared synthetic notebook for the Tools / Resources inventory tests (issue #1)."""
from __future__ import annotations

import base64
import json
import struct
import sys
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import assets  # noqa: E402
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


PLOT_OUTPUT = {"output_type": "display_data", "metadata": {}, "data": {"image/png": B64_BIG, "text/plain": "<Figure>"}}

CELLS = [
    md("# Metrics"),                                                                    # 0
    code("!pip install -q nrclex"),                                                     # 1 environment_setup
    code("import pandas as pd\nimport numpy as np"),                                    # 2 non_teaching
    code("df = pd.read_csv('cars.csv')\ndf.head()"),                                    # 3 data_loading
    md("## Precision\nPrecision is the share of predicted positives that are right, used a lot when "
       "false positives are costly. We compute it with `precision_score` below."),       # 4 teaching
    code("def precision(tp, fp):\n    return tp / (tp + fp)"),                          # 5 tool_function
    code("tp, fp = 40, 13\nscore = tp / (tp + fp)\nscore2 = score * 100\nprint(score2)",
         outputs=[{"output_type": "stream", "name": "stdout", "text": "75.4\n"}]),      # 6 tool_implementation
    code("plt.plot(x, y)\nplt.show()", outputs=[PLOT_OUTPUT]),                          # 7 visualization + plot
    code("from sklearn.metrics import precision_score\np = precision_score(y_true, y_pred)\n"
         "m = LogisticRegression()\nm.fit(X_train, y_train)\npred = m.predict(X_test)"),   # 8 tool_workflow
    code("a + b", outputs=[{"output_type": "error", "ename": "ValueError", "evalue": "x", "traceback": []}]),  # 9
    md("## Diagrams\nThe architecture below shows the pipeline from raw data to predictions.\n\n"
       f"![Model architecture diagram](data:image/png;base64,{B64_BIG})\n"
       "<img src='https://drive.google.com/uc?id=XYZ' width=300>\n"
       f"![image.png](data:image/png;base64,{B64_TINY})\n"
       "<img src='https://upload.wikimedia.org/thing.png'>\n"
       "![Screenshot 2023-07-28 at 11.12.39 AM.png](https://d2beiqkhq929f0.cloudfront.net/a/Screenshot_2023.png)"),  # 10
    code("y_hat = model.predict(X)\nerr = y - y_hat"),                                  # 11 tool after the images
    md("## Quiz 1\nWhich chart is this?\n<img src='https://drive.google.com/uc?id=QQQ'>"),   # 12 quiz image
]

NB_NAME = "14 - Classification metrics.ipynb"


class Built:
    """Runs ingestion (with content roles) and the inventories once, in a temp dir."""
    _instance = None

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.raw, self.out = base / "raw", base / "out"
        self.raw.mkdir()
        (self.raw / NB_NAME).write_text(json.dumps({"nbformat": 4, "nbformat_minor": 0, "metadata": {},
                                                    "cells": CELLS}), encoding="utf-8")
        ingestion.run(self.raw, self.out, quiet=True)
        self.tools, self.resources, self.links = assets.run(self.out, self.raw, quiet=True)
        self.tool_by_cell = {t.cell_id: t for t in self.tools}

    @classmethod
    def get(cls) -> "Built":
        if cls._instance is None:
            cls._instance = Built()
        return cls._instance


def cell_id(index: int) -> str:
    return f"nb_14_cell_{index:03d}"
