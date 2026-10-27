"""Tests for src/hybrid_fusion.py and src/bm25_index.py (PH4-RETRIEVE-001, issue #9)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bm25_index import BM25Index, fold, tokenize  # noqa: E402
from hybrid_fusion import rrf  # noqa: E402


class RRF(unittest.TestCase):                                                  # test 3
    def test_formula(self):
        fused = rrf({"dense": ["A", "B", "C"], "bm25": ["B", "D"]}, k=60)
        scores = {f.chunk_id: f.score for f in fused}
        self.assertAlmostEqual(scores["B"], 1 / 62 + 1 / 61)
        self.assertAlmostEqual(scores["A"], 1 / 61)
        self.assertAlmostEqual(scores["C"], 1 / 63)
        self.assertAlmostEqual(scores["D"], 1 / 62)
        self.assertEqual([f.chunk_id for f in fused], ["B", "A", "D", "C"])

    def test_sources_and_ranks(self):
        fused = {f.chunk_id: f for f in rrf({"dense": ["A", "B"], "bm25": ["B"]})}
        self.assertEqual((fused["B"].source, fused["B"].ranks), ("bm25+dense", {"dense": 2, "bm25": 1}))
        self.assertEqual(fused["A"].source, "dense")

    def test_agreement_beats_single_top_rank(self):
        # found at rank 2 by both retrievers beats rank 1 in only one of them
        fused = rrf({"dense": ["X", "Y"], "bm25": ["Z", "Y"]})
        self.assertEqual(fused[0].chunk_id, "Y")

    def test_ties_are_deterministic(self):
        a = rrf({"dense": ["P"], "bm25": ["Q"]})
        b = rrf({"bm25": ["Q"], "dense": ["P"]})
        self.assertEqual([f.chunk_id for f in a], [f.chunk_id for f in b])
        self.assertEqual([f.chunk_id for f in a], ["P", "Q"])

    def test_single_list_keeps_order(self):
        self.assertEqual([f.chunk_id for f in rrf({"bm25": ["C", "A", "B"]})], ["C", "A", "B"])

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            rrf({"dense": ["A", "A"]})
        with self.assertRaises(ValueError):
            rrf({"dense": ["A"]}, k=0)
        self.assertEqual(rrf({"dense": [], "bm25": []}), [])


class BM25(unittest.TestCase):                                                 # test 2
    def setUp(self):
        self.idx = BM25Index()
        docs = {
            "C1": ("Precision is TP / (TP + FP); recall is TP / (TP + FN).", "concept"),
            "C2": ("The curse of dimensionality: distances lose meaning as dimensions grow.", "concept"),
            "T1": ("df['rating'].fillna(df['rating'].mean())  # fill missing values", "tool"),
            "T2": ("from sklearn.model_selection import train_test_split", "tool"),
        }
        for cid, (text, kind) in docs.items():
            self.idx.add(cid, text, {"chunk_type": kind, "notebook_id": "nb_01"})

    def test_keyword_matches(self):
        self.assertEqual(self.idx.search("curse of dimensionality")[0][1], "C2")
        self.assertEqual(self.idx.search("fillna")[0][1], "T1")
        self.assertEqual(self.idx.search("train_test_split")[0][1], "T2")
        self.assertEqual(self.idx.search("precision and recall")[0][1], "C1")

    def test_filters(self):
        self.assertEqual([c for _, c in self.idx.search("missing values recall", {"chunk_type": "tool"})], ["T1"])
        self.assertEqual(self.idx.search("fillna", {"notebook_id": "nb_99"}), [])

    def test_no_match_returns_nothing(self):
        self.assertEqual(self.idx.search("quantum chromodynamics"), [])

    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            self.idx.add("C1", "again", {})

    def test_tokenizer_keeps_identifiers(self):
        toks = tokenize("Use df.fillna and train_test_split on the matrices of residuals.")
        for t in ("df.fillna", "df", "fillna", "train_test_split", "matrix", "residual"):
            self.assertIn(t, toks)
        self.assertNotIn("the", toks)
        self.assertEqual(fold("analysis"), "analysis")
        self.assertEqual(fold("classes"), "class")
        self.assertEqual(fold("boxes"), "box")
        self.assertEqual(fold("probabilities"), "probability")


if __name__ == "__main__":
    unittest.main()
