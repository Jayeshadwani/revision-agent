"""
Tests for the Resources inventory (issue #1).

    python -m unittest discover -s tests

Synthetic tests always run. Corpus tests run when data/processed/ and the raw notebooks are present
locally (data/ is not committed).
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import get_args

sys.path.insert(0, str(Path(__file__).resolve().parent))

from inventory_fixture import ROOT, Built, cell_id  # noqa: E402

import assets  # noqa: E402
import config  # noqa: E402
import resources_inventory as ri  # noqa: E402


class SyntheticResources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = Built.get()
        cls.by_key = {(r.cell_id, r.image_index): r for r in cls.b.resources}

    def r(self, index, n=0):
        return self.by_key[(cell_id(index), n)]

    def test_one_resource_per_image(self):
        self.assertEqual(sorted(self.by_key), [(cell_id(7), 0)] + [(cell_id(10), n) for n in range(5)]
                         + [(cell_id(12), 0)])
        self.assertEqual([r.resource_id for r in self.b.resources], [f"RES_{i:04d}" for i in range(1, 8)])

    def test_plot_output(self):
        plot = self.r(7)
        self.assertEqual((plot.resource_type, plot.availability, plot.span_id), ("plot", "embedded", None))
        self.assertEqual(plot.linked_tool_ids, [self.b.tool_by_cell[cell_id(7)].tool_id])
        self.assertEqual((plot.image_reference.width, plot.image_reference.height), (200, 120))
        self.assertTrue((config.ROOT / plot.image_reference.local_path).exists()
                        or Path(plot.image_reference.local_path).exists())
        self.assertEqual(plot.vision_priority, "low")

    def test_types_only_from_evidence(self):
        diagram, drive, tiny, wiki, shot = (self.r(10, n) for n in range(5))
        self.assertEqual((diagram.resource_type, diagram.caption.source, diagram.title),
                         ("diagram", "alt_text", "Model architecture diagram"))
        self.assertEqual((drive.resource_type, drive.availability), ("unclassified", "google_drive"))
        self.assertIsNone(drive.image_reference.local_path)
        self.assertEqual((tiny.resource_type, tiny.retrieval_status, tiny.vision_priority),
                         ("decorative", "excluded_decorative", "none"))
        self.assertEqual((wiki.resource_type, wiki.availability), ("external_reference", "external_url"))
        # A screenshot filename is a capture hint, not a type; course CDN is not a third-party site
        self.assertEqual((shot.resource_type, shot.capture_hint, shot.availability),
                         ("unclassified", "screenshot_filename", "external_url"))

    def test_no_image_content_is_invented(self):
        for r in self.b.resources:
            self.assertFalse(r.content_extracted)
            self.assertIsNone(r.ocr_text)
            self.assertIsNone(r.vlm_caption)
            self.assertTrue(r.description.endswith("(Image content not extracted.)"))

    def test_span_context_and_links(self):
        drive = self.r(10, 1)
        self.assertEqual(drive.span_id, f"{cell_id(10)}_span_000")
        self.assertEqual(drive.span_role, "teaching")
        self.assertEqual(drive.linked_concept_span_ids, [drive.span_id])
        self.assertEqual(drive.linked_tool_ids, [self.b.tool_by_cell[cell_id(11)].tool_id])
        self.assertEqual(drive.vision_priority, "high")
        self.assertIn("diagram_mentioned_nearby", drive.context_hints)
        quiz = self.r(12)
        self.assertEqual((quiz.span_role, quiz.vision_priority), ("quiz", "normal"))

    def test_report(self):
        text = (self.b.out / ri.RESOURCES_REPORT_MD).read_text()
        for heading in ("## Resource type", "## Availability", "## Retrieval status", "## OCR/VLM queue"):
            self.assertIn(heading, text)


class Rules(unittest.TestCase):
    def test_availability(self):
        self.assertEqual(ri.availability_of("data:image/png;base64,xx", True), "embedded")
        self.assertEqual(ri.availability_of("attachment:a.png", False), "missing")
        self.assertEqual(ri.availability_of("https://docs.google.com/x", False), "google_drive")
        self.assertEqual(ri.availability_of("https://example.com/a.png", False), "external_url")
        self.assertEqual(ri.availability_of("images/local.png", False), "missing")

    def test_alt_text_is_meaningful(self):
        for alt in ("", "image.png", "picture", "Screenshot 2022-03-16 153746.png", "1", "image (2)"):
            self.assertFalse(ri.meaningful_alt(alt), alt)
        self.assertTrue(ri.meaningful_alt("Gradient descent formula"))


CELLS_PATH = config.PROCESSED_DIR / config.CELLS_JSONL


@unittest.skipUnless(CELLS_PATH.exists() and any(config.RAW_NOTEBOOKS_DIR.glob("*.ipynb")),
                     "processed corpus not present (kept local)")
class CorpusResources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        shutil.copy(CELLS_PATH, cls.out / config.CELLS_JSONL)
        cls.tools, cls.resources, cls.links = assets.run(cls.out, config.RAW_NOTEBOOKS_DIR, quiet=True)
        cls.cells = [json.loads(l) for l in CELLS_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_image_referencing_cell_is_covered(self):
        md = {c["cell_id"] for c in self.cells if c["cell_type"] == "markdown" and c["contains_image"]}
        self.assertTrue(md <= {r.cell_id for r in self.resources})
        image_outputs = sum(sum(o["content_type"] == "image" for o in c["outputs"]) for c in self.cells)
        markdown_refs = sum(len(c["image_refs"]) for c in self.cells if c["cell_type"] == "markdown")
        self.assertEqual(len(self.resources), image_outputs + markdown_refs)

    def test_valid_fields(self):
        cells = {c["cell_id"]: c for c in self.cells}
        spans = {sp["span_id"] for c in self.cells for sp in c.get("spans", [])}
        tools = {t.tool_id for t in self.tools}
        for r in self.resources:
            self.assertIn(r.resource_type, get_args(ri.ResourceType))
            self.assertIn(r.availability, get_args(ri.Availability))
            self.assertEqual(r.source.cell_ids, [r.cell_id])
            self.assertIn(r.cell_id, cells)
            self.assertFalse(r.content_extracted)
            self.assertTrue(r.type_evidence)
            if r.span_id is not None:
                self.assertIn(r.span_id, spans)
            self.assertTrue(set(r.linked_concept_span_ids) <= spans)
            self.assertTrue(set(r.linked_tool_ids) <= tools)
            if r.resource_type == "unclassified":
                self.assertEqual(r.type_confidence, 0.0)

    def test_embedded_saved_external_not(self):
        for r in self.resources:
            if r.availability == "embedded":
                self.assertTrue((config.ROOT / r.image_reference.local_path).exists()
                                or Path(r.image_reference.local_path).exists(), r.resource_id)
            else:
                self.assertIsNone(r.image_reference.local_path)
                self.assertTrue(r.image_reference.url)

    def test_golden_prompt_resource_links_resolve(self):
        resources = {r.resource_id: r for r in self.resources}
        for line in (ROOT / "evaluation" / "golden_prompts.jsonl").read_text(encoding="utf-8").splitlines():
            p = json.loads(line)
            cited = {f"{s['notebook_id']}_cell_{i:03d}" for s in p["expected_sources"] for i in s["cell_ids"]}
            for rid in p["expected_resource_ids"]:
                self.assertIn(resources[rid].cell_id, cited, p["prompt_id"])


if __name__ == "__main__":
    unittest.main()
