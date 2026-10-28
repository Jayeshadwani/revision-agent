"""
Tests for src/parent_retrieval.py (PH5-RETRIEVE-002, issue #11, Gate A).

The fixture cases E01-E20 (evaluation/parent_rerank_edge_cases.jsonl, PR #12) are checked with
injected, deterministic child rankings, so each test asserts an exact expansion outcome without
depending on a retriever or a model. The fixture is a contract test, not an accuracy benchmark.
"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import parent_retrieval as pr  # noqa: E402
import reranker as rr  # noqa: E402
from bm25_index import BM25Index  # noqa: E402

EVAL = ROOT / "evaluation"
CASES = {c["case_id"]: c for c in map(json.loads, (EVAL / "parent_rerank_edge_cases.jsonl").read_text().splitlines())}
FORBIDDEN = ("answer key", "teacher-only", "print secret", "configure secrets")


def ids(expansion):
    return [p.parent_id for p in expansion.parents]


class FixtureCases(unittest.TestCase):
    def setUp(self):
        self.store = pr.load_fixture_store(EVAL)

    def assertNoLeak(self, expansion):
        for p in expansion.parents:
            for bad in FORBIDDEN:
                self.assertNotIn(bad, p.text.lower(), p.parent_id)
            self.assertEqual(p.trust, "untrusted_source_text")

    def test_fixture_integrity(self):
        self.assertEqual(len(CASES), 20)
        self.assertEqual(len(self.store.parents), 12)
        self.assertEqual(len(self.store.children), 19)
        dangling = [c for c in self.store.children.values() if c.parent_id not in self.store.parents]
        self.assertEqual([c.child_id for c in dangling], ["C019"])

    def test_fixture_children_are_paraphrases(self):
        """Fixture finding: most children paraphrase their parent, so only P001 expands to full parent
        text; the others expand to their eligible children. A fixture v2 with verbatim children (or
        offsets) would exercise full-parent expansion everywhere."""
        whole = sorted(p.parent_id for p in self.store.parents.values()
                       if [s.segment_id for s in p.segments] == [p.parent_id])
        self.assertEqual(whole, ["P001"])

    def test_E01_normal_one_parent_both_formulas(self):
        e = self.store.expand(["C001", "C002"])
        self.assertEqual(ids(e), CASES["E01"]["expected_parent_ids"])
        self.assertIn("TP/(TP+FP)", e.parents[0].text)
        self.assertIn("TP/(TP+FN)", e.parents[0].text)

    def test_E02_math_intact(self):
        e = self.store.expand(["C003"])
        self.assertEqual(ids(e), ["P002"])
        self.assertIn("2PR/(P+R)", e.parents[0].text)
        # C004 paraphrases P002 instead of quoting it, so P002 cannot be verified as a whole and only its
        # verified child segments are served (fail closed). See test_fixture_children_are_paraphrases.
        self.assertEqual(e.parents[0].segment_ids, ["C003", "C004"])

    def test_E03_code_no_neighbour_merge(self):
        e = self.store.expand(["C006", "C007"])
        self.assertEqual(ids(e), ["P004"])
        self.assertIn("fillna", e.parents[0].text)
        self.assertNotIn("dropna", e.parents[0].text)

    def test_E04_two_distinct_parents(self):
        e = self.store.expand(["C006", "C008"])
        self.assertEqual(set(ids(e)), set(CASES["E04"]["expected_parent_ids"]))

    def test_E05_insufficient_evidence_kept_visible(self):
        e = self.store.expand(["C009", "C010"])
        self.assertEqual(ids(e), ["P006"])
        self.assertIn("P(A|B)=P(B|A)P(A)/P(B)", e.parents[0].text)

    def test_E06_concept(self):
        self.assertEqual(ids(self.store.expand(["C011"])), ["P007"])

    def test_E07_distractor_keeps_primary_rank(self):
        e = self.store.expand(["C001", "C017"])
        self.assertEqual(ids(e)[0], "P001")
        self.assertEqual([p.rank for p in e.parents], [1, 2])

    def test_E08_refusal_no_quiz_or_setup_parent(self):
        e = self.store.expand(["C005", "C013"])
        self.assertEqual(ids(e), [])
        self.assertEqual({x["error"] for x in e.errors}, {"ineligible_parent"})

    def test_E09_dedup_one_citation(self):
        e = self.store.expand(["C001", "C002"])
        self.assertEqual(ids(e), ["P001"])
        self.assertEqual(e.parents[0].matched_child_ids, ["C001", "C002"])

    def test_E10_mixed_parent_omits_quiz_span(self):
        e = self.store.expand(["C001", "C014", "C015", "C016"])
        self.assertEqual(ids(e), ["P001", "P010"])
        p010 = e.parents[1]
        self.assertEqual(p010.segment_ids, ["C014", "C016"])
        self.assertNotIn("QUIZ", p010.text)
        self.assertIn({"child_id": "C015", "parent_id": "P010", "error": "ineligible_child"}, e.errors)
        self.assertNoLeak(e)

    def test_E11_injection_is_flagged_untrusted(self):
        e = self.store.expand(["C018"])
        self.assertEqual(ids(e), ["P012"])
        self.assertTrue(e.parents[0].injection_suspected)
        self.assertEqual(e.parents[0].trust, "untrusted_source_text")

    def test_E12_short_query(self):
        self.assertEqual(ids(self.store.expand(["C012"])), ["P008"])

    def test_E13_notebook_filter_applies_to_parent(self):
        e = self.store.expand(["C006", "C002"], filters={"notebook_id": "nb_fixture_a"})
        self.assertEqual(ids(e), ["P001"])
        self.assertEqual(e.filtered_out, ["P004"])

    def test_E14_missing_parent_fails_closed(self):
        e = self.store.expand(["C019"])
        self.assertEqual(ids(e), [])
        self.assertEqual(e.errors, [{"child_id": "C019", "parent_id": "P_DOES_NOT_EXIST", "error": "missing_parent"}])

    def test_E15_no_candidates(self):
        e = self.store.expand([])
        self.assertEqual((ids(e), e.errors, e.context_tokens), ([], [], 0))

    def test_E16_budget_limits_are_reported(self):
        full = self.store.expand(["C001", "C003", "C002"])
        self.assertEqual(ids(full), ["P001", "P002"])
        first = full.parents[0].tokens
        tight = self.store.expand(["C001", "C003", "C002"], context_budget=first)
        self.assertEqual(ids(tight), ["P001"])
        self.assertEqual(tight.omitted_for_budget, ["P002"])                  # reported, not silently dropped

    def test_E17_reranker_failure_keeps_baseline(self):
        class Boom:
            name = "boom"

            def score(self, q, texts):
                raise RuntimeError("model crashed")
        e = self.store.expand(["C011", "C017"])
        res = rr.safe_rerank(CASES["E17"]["query"], [(p.parent_id, p.text) for p in e.parents], Boom())
        self.assertEqual((res.status, res.order), ("fallback", ["P007", "P011"]))

    def test_E18_typo_probe_is_safe(self):
        bm = BM25Index()
        for c in self.store.children.values():
            bm.add(c.child_id, c.text, {"notebook_id": c.notebook_id})
        hits = [cid for _, cid in bm.search(CASES["E18"]["query"], limit=10)]
        e = self.store.expand(hits)                                         # robustness probe: no hard relevance check
        self.assertNoLeak(e)

    def test_E19_ambiguity_both_sources(self):
        e = self.store.expand(["C001", "C017"])
        self.assertEqual(set(ids(e)), {"P001", "P011"})

    def test_E20_unknown_notebook_filter_never_expands_others(self):
        e = self.store.expand(["C001", "C006", "C012"], filters={"notebook_id": "nb_fixture_unknown"})
        self.assertEqual(ids(e), [])
        self.assertEqual(e.filtered_out, ["P001", "P004", "P008"])

    def test_no_forbidden_text_for_any_ranking(self):
        everything = list(self.store.children)
        for perm in (everything, list(reversed(everything))):
            e = self.store.expand(perm)
            self.assertNoLeak(e)
            self.assertFalse({"P003", "P009"} & set(ids(e)))
            self.assertEqual(len(ids(e)), len(set(ids(e))))


def corpus_fixture():
    long_para = ("Gradient descent updates each weight against the gradient of the loss. " * 12).strip()
    spans = {
        "nb_01_cell_001_span_000": {"content": "## Precision\nPrecision is TP / (TP + FP).\n\n" + long_para,
                                    "content_role": "teaching", "retrieval_eligible": True},
        "nb_01_cell_002_span_000": {"content": "Recall is TP / (TP + FN).", "content_role": "teaching",
                                    "retrieval_eligible": True},
        "nb_01_cell_003_span_000": {"content": "Quiz: which is right? Answer key: b", "content_role": "quiz",
                                    "retrieval_eligible": False},
    }
    s0 = spans["nb_01_cell_001_span_000"]["content"]
    concepts = [{
        "chunk_id": "CON_000001", "notebook_id": "nb_01", "section_path": ["Metrics", "Precision"],
        "source_segments": [{"span_id": "nb_01_cell_001_span_000", "char_start": 0, "char_end": len(s0)},
                            {"span_id": "nb_01_cell_002_span_000", "char_start": 0, "char_end": 25},
                            {"span_id": "nb_01_cell_003_span_000", "char_start": 0, "char_end": 35}]}]
    tools = [{"chunk_id": "TOOLCHUNK_000001", "chunk_type": "tool", "notebook_id": "nb_01", "section_path": ["Metrics"],
              "title": "Precision", "purpose": "Defines precision", "description": "", "breadcrumb": "Notebook: x\nSection path: y",
              "libraries": [], "language": "python", "code": "def precision(tp, fp):\n    return tp / (tp + fp)",
              "tool_type": "tool_function"}]
    return concepts, tools, spans


class CorpusHierarchy(unittest.TestCase):
    def build(self, size=32, spans=None):
        concepts, tools, base_spans = corpus_fixture()
        return pr.build_corpus_store(concepts, tools, spans or base_spans, size), base_spans

    def test_children_stay_inside_segments_and_are_versioned(self):
        store, spans = self.build()
        con = [c for c in store.children.values() if c.parent_id == "CON_000001"]
        self.assertGreater(len(con), 2)                                       # the long span was windowed
        for c in con:
            self.assertRegex(c.child_id, r"^CON_000001\.c\d{2}\.s32$")
            seg = next(s for s in store.parents["CON_000001"].segments if s.segment_id == c.segment_id)
            self.assertIn(c.text, seg.text)
        self.assertFalse(any("Answer key" in c.text for c in con))            # no child from the quiz span
        self.assertEqual(store.children["TOOLCHUNK_000001.c01.s32"].parent_id, "TOOLCHUNK_000001")

    def test_deterministic(self):
        a, _ = self.build()
        b, _ = self.build()
        self.assertEqual([(c.child_id, c.text) for c in a.children.values()],
                         [(c.child_id, c.text) for c in b.children.values()])

    def test_quiz_segment_never_serialized(self):
        store, _ = self.build()
        e = store.expand(list(store.children))
        con = next(p for p in e.parents if p.parent_id == "CON_000001")
        self.assertNotIn("Answer key", con.text)
        self.assertNotIn("nb_01_cell_003_span_000@0-35", con.segment_ids)

    def test_stale_source_fails_closed(self):
        store, _ = self.build()
        seg = store.parents["CON_000001"].segments[1]
        seg.text = seg.text.replace("FN", "FP")                               # source changed after the map was built
        e = store.expand([c for c in store.children if c.startswith("CON_000001")])
        self.assertNotIn("CON_000001", ids(e))
        self.assertTrue(any(x["error"] in ("stale_parent_segment", "child_text_not_in_parent") for x in e.errors))

    def test_cross_notebook_child_rejected(self):
        store, _ = self.build()
        child = copy.copy(next(iter(store.children.values())))
        child.child_id, child.notebook_id = "X.c01.s32", "nb_99"
        store.children[child.child_id] = child
        e = store.expand([child.child_id])
        self.assertEqual(e.errors[0]["error"], "cross_notebook_parent")

    def test_oversized_parent_is_sliced_with_report(self):
        store, _ = self.build()
        recall_child = next(c for c in store.children.values() if "Recall" in c.text)
        e = store.expand([recall_child.child_id], parent_budget=20)
        p = e.parents[0]
        self.assertTrue(p.sliced)
        self.assertIn("Recall is TP / (TP + FN).", p.text)                   # the matched segment is kept whole
        self.assertTrue(p.omitted_segment_ids)                                # what was left out is listed

    def test_filters_on_parent_type(self):
        store, _ = self.build()
        e = store.expand(list(store.children), filters={"chunk_type": "tool"})
        self.assertEqual(ids(e), ["TOOLCHUNK_000001"])

    def test_unknown_child(self):
        store, _ = self.build()
        self.assertEqual(store.expand(["nope"]).errors[0]["error"], "unknown_child")


if __name__ == "__main__":
    unittest.main()
