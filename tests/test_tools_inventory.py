"""
Tests for the Tools inventory and Tool–Concept links (issue #1).

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

sys.path.insert(0, str(Path(__file__).resolve().parent))

from inventory_fixture import ROOT, Built, cell_id  # noqa: E402

import assets  # noqa: E402
import config  # noqa: E402
import tool_concept_linker  # noqa: E402
import tools_inventory  # noqa: E402
from content_role_classifier import CODE_ROLES, TOOL_ROLES  # noqa: E402

RELATIONSHIPS = {"implements", "demonstrates", "visualizes", "supports", "uncertain"}


class SyntheticTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = Built.get()

    def tool(self, index):
        return self.b.tool_by_cell[cell_id(index)]

    def test_only_eligible_tool_roles(self):
        self.assertEqual(sorted(self.b.tool_by_cell), [cell_id(i) for i in (5, 6, 7, 8, 11)])
        for t in self.b.tools:
            self.assertIn(t.tool_type, TOOL_ROLES)
            self.assertTrue(t.retrieval_eligible)
        self.assertEqual([t.tool_id for t in self.b.tools], [f"TOOL_{i:04d}" for i in range(1, 6)])

    def test_tool_types_follow_content_roles(self):
        expected = {5: "tool_function", 6: "tool_implementation", 7: "visualization", 8: "tool_workflow"}
        self.assertEqual({i: self.tool(i).tool_type for i in expected}, expected)

    def test_exclusions_documented(self):
        rows = [json.loads(l) for l in (self.b.out / tools_inventory.TOOL_EXCLUSIONS_JSONL).read_text().splitlines()]
        excluded = {r["cell_id"]: r["content_role"] for r in rows}
        self.assertEqual(excluded[cell_id(1)], "environment_setup")
        self.assertEqual(excluded[cell_id(3)], "data_loading")
        self.assertEqual(excluded[cell_id(9)], "debugging")
        for r in rows:
            self.assertTrue(r["reason"])

    def test_metadata(self):
        f = self.tool(5)
        self.assertEqual((f.title, f.inputs, f.outputs), ("Precision", ["tp", "fp"], ["precision"]))
        self.assertTrue(f.quality.is_self_contained)
        self.assertEqual(f.source.section_path, "Metrics > Precision")
        self.assertEqual(f.source.cell_ids, [cell_id(5)])
        self.assertEqual(f.explanation_span_ids, [f"{cell_id(4)}_span_000"])
        self.assertIn("Precision is the share", f.description)
        self.assertEqual(f.description_source, "nearby_explanation")
        impl = self.tool(6)
        self.assertTrue(impl.quality.has_output)
        self.assertEqual(impl.output_roles, ["result"])

    def test_links_have_evidence(self):
        self.assertTrue(self.b.links)
        for link in self.b.links:
            self.assertIn(link.relationship, RELATIONSHIPS)
            self.assertTrue(link.evidence)
            self.assertAlmostEqual(link.confidence, min(1.0, sum(e.weight for e in link.evidence)), places=2)
        by_tool = {}
        for link in self.b.links:
            by_tool.setdefault(link.tool_id, []).append(link)
        f = by_tool[self.tool(5).tool_id][0]
        self.assertEqual((f.relationship, f.span_id), ("implements", f"{cell_id(4)}_span_000"))
        w = by_tool[self.tool(8).tool_id][0]                    # mentions `precision_score`, as the span does
        self.assertEqual(w.span_id, f"{cell_id(4)}_span_000")
        self.assertIn("shared_identifier", {e.kind for e in w.evidence})

    def test_reports_written(self):
        text = (self.b.out / assets.TOOLS_REPORT_MD).read_text()
        for heading in ("## Tools", "### By tool type", "### Excluded code cells", "## Tool–Concept links"):
            self.assertIn(heading, text)


class LinkRules(unittest.TestCase):
    def test_relationship_needs_structure(self):
        tool = Built.get().tool_by_cell[cell_id(6)]
        E = tool_concept_linker.Evidence
        near_only = [E(kind="precedes_tool", detail="1", weight=0.3), E(kind="shared_identifier", detail="x", weight=0.35)]
        self.assertEqual(tool_concept_linker.relationship_for(tool, near_only, 0.65), "supports")
        same = [E(kind="same_section", detail="s", weight=0.4), E(kind="precedes_tool", detail="1", weight=0.3)]
        self.assertEqual(tool_concept_linker.relationship_for(tool, same, 0.7), "implements")
        self.assertEqual(tool_concept_linker.relationship_for(tool, same[:1], 0.4), "uncertain")

    def test_common_identifiers_ignored(self):
        tool = Built.get().tool_by_cell[cell_id(8)]
        idents = tool_concept_linker.tool_identifiers(tool)
        self.assertIn("precision_score", idents)
        self.assertNotIn("fit", idents)
        self.assertNotIn("predict", idents)


CELLS_PATH = config.PROCESSED_DIR / config.CELLS_JSONL


@unittest.skipUnless(CELLS_PATH.exists() and any(config.RAW_NOTEBOOKS_DIR.glob("*.ipynb")),
                     "processed corpus not present (kept local)")
class CorpusTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        shutil.copy(CELLS_PATH, cls.out / config.CELLS_JSONL)
        cls.tools, cls.resources, cls.links = assets.run(cls.out, config.RAW_NOTEBOOKS_DIR, quiet=True)
        cls.cells = [json.loads(l) for l in CELLS_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
        cls.excluded = [json.loads(l) for l in
                        (cls.out / tools_inventory.TOOL_EXCLUSIONS_JSONL).read_text(encoding="utf-8").splitlines()]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_eligible_tool_cell_is_a_tool(self):
        eligible = {c["cell_id"] for c in self.cells if c["cell_type"] == "code"
                    and c["content_role"] in TOOL_ROLES and c["retrieval_eligible"]}
        self.assertEqual({t.cell_id for t in self.tools}, eligible)

    def test_every_other_code_cell_has_exclusion_reason(self):
        code = {c["cell_id"] for c in self.cells if c["cell_type"] == "code"}
        self.assertEqual({t.cell_id for t in self.tools} | {e["cell_id"] for e in self.excluded}, code)
        self.assertFalse({t.cell_id for t in self.tools} & {e["cell_id"] for e in self.excluded})
        for e in self.excluded:
            self.assertIn(e["content_role"], CODE_ROLES)
            self.assertTrue(e["reason"])

    def test_tool_fields(self):
        cells = {c["cell_id"]: c for c in self.cells}
        for t in self.tools:
            self.assertIn(t.tool_type, TOOL_ROLES)
            self.assertEqual(t.source.cell_ids, [t.cell_id])
            self.assertEqual(t.code, cells[t.cell_id]["content"])
            self.assertEqual(t.quality.suitable_for_answer, not t.quality.unsuitable_reasons)

    def test_links_reference_eligible_teaching_spans(self):
        spans = {sp["span_id"]: sp for c in self.cells for sp in c.get("spans", [])}
        tool_ids = {t.tool_id for t in self.tools}
        for link in self.links:
            self.assertIn(link.tool_id, tool_ids)
            sp = spans[link.span_id]
            self.assertEqual(sp["content_role"], "teaching")
            self.assertTrue(sp["retrieval_eligible"])
            self.assertIn(link.relationship, RELATIONSHIPS)
            self.assertTrue(link.evidence)
            if link.relationship == "uncertain":
                self.assertLess(link.confidence, tool_concept_linker.LINK_THRESHOLD)
            else:
                self.assertGreaterEqual(link.confidence, tool_concept_linker.LINK_THRESHOLD)

    def test_deterministic(self):
        tools2, _ = tools_inventory.build_tools(tools_inventory.load_cells(CELLS_PATH), tools_inventory.load_mapper())
        self.assertEqual([t.model_dump() for t in self.tools], [t.model_dump() for t in tools2])

    def test_golden_prompt_tool_links_resolve(self):
        tools = {t.tool_id: t for t in self.tools}
        for line in (ROOT / "evaluation" / "golden_prompts.jsonl").read_text(encoding="utf-8").splitlines():
            p = json.loads(line)
            cited = {f"{s['notebook_id']}_cell_{i:03d}" for s in p["expected_sources"] for i in s["cell_ids"]}
            for tid in p["expected_tool_ids"]:
                self.assertIn(tools[tid].cell_id, cited, p["prompt_id"])


if __name__ == "__main__":
    unittest.main()
