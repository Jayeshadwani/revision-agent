"""Tests for src/reranker.py (PH5-RETRIEVE-002, issue #11, Gate A). No model is loaded or downloaded."""
from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import reranker as rr  # noqa: E402

CANDS = [("a", "alpha text"), ("b", "beta text"), ("c", "gamma text"), ("d", "delta text")]


class Fake:
    def __init__(self, fn, name="fake"):
        self.fn, self.name, self.calls = fn, name, []

    def score(self, query, texts):
        self.calls.append(len(texts))
        return self.fn(query, list(texts))


class SafeRerank(unittest.TestCase):
    def test_reorders_by_score(self):
        r = rr.safe_rerank("q", CANDS, Fake(lambda q, t: [0.1, 0.9, -2.0, 0.5]))
        self.assertEqual((r.status, r.order), ("reranked", ["b", "d", "a", "c"]))

    def test_negative_scores_are_fine(self):
        r = rr.safe_rerank("q", CANDS, Fake(lambda q, t: [-5.0, -1.0, -3.0, -4.0]))
        self.assertEqual(r.order, ["b", "c", "d", "a"])

    def test_ties_keep_baseline_order(self):
        r = rr.safe_rerank("q", CANDS, Fake(lambda q, t: [1.0, 2.0, 2.0, 1.0]))
        self.assertEqual(r.order, ["b", "c", "a", "d"])

    def test_nan_and_inf_go_last_in_baseline_order(self):
        r = rr.safe_rerank("q", CANDS, Fake(lambda q, t: [float("nan"), 0.3, float("inf"), "x"]))
        self.assertEqual(r.order, ["b", "a", "c", "d"])
        self.assertEqual(r.invalid_scores, ["a", "c", "d"])
        self.assertIsNone(r.scores["a"])

    def test_all_invalid_falls_back(self):
        r = rr.safe_rerank("q", CANDS, Fake(lambda q, t: [float("nan")] * len(t)))
        self.assertEqual((r.status, r.order), ("fallback", ["a", "b", "c", "d"]))

    def test_timeout_falls_back(self):
        r = rr.safe_rerank("q", CANDS, Fake(lambda q, t: (time.sleep(0.5), [1.0] * len(t))[1]), timeout_s=0.05)
        self.assertEqual((r.status, r.order), ("fallback", ["a", "b", "c", "d"]))
        self.assertIn("timeout", r.reason)

    def test_exception_and_oom_fall_back(self):
        def crash(q, t):
            raise RuntimeError("corrupt checkpoint")

        def oom(q, t):
            raise MemoryError()
        for fn, why in ((crash, "corrupt checkpoint"), (oom, "out of memory")):
            r = rr.safe_rerank("q", CANDS, Fake(fn))
            self.assertEqual((r.status, r.order), ("fallback", ["a", "b", "c", "d"]))
            self.assertIn(why, r.reason)

    def test_partial_batch_failure_falls_back_whole(self):
        state = {"n": 0}

        def second_fails(q, t):
            state["n"] += 1
            if state["n"] == 2:
                raise RuntimeError("batch 2 failed")
            return [1.0] * len(t)
        fake = Fake(second_fails)
        r = rr.safe_rerank("q", CANDS, fake, batch_size=2)
        self.assertEqual(fake.calls, [2, 2])
        self.assertEqual((r.status, r.order), ("fallback", ["a", "b", "c", "d"]))

    def test_wrong_score_count_falls_back(self):
        r = rr.safe_rerank("q", CANDS, Fake(lambda q, t: [1.0]))
        self.assertEqual(r.status, "fallback")

    def test_no_reranker_or_no_candidates(self):
        self.assertEqual(rr.safe_rerank("q", CANDS, None).order, ["a", "b", "c", "d"])
        self.assertEqual(rr.safe_rerank("q", [], Fake(lambda q, t: [])).order, [])

    def test_duplicates_rejected(self):
        with self.assertRaises(ValueError):
            rr.safe_rerank("q", [("a", "x"), ("a", "y")], Fake(lambda q, t: [1.0, 2.0]))

    def test_inputs_over_model_limit_are_logged(self):
        long = " ".join(["word"] * 600)
        r = rr.safe_rerank("q", [("short", "tiny"), ("long", long)], Fake(lambda q, t: [0.0, 1.0]), max_input_tokens=512)
        self.assertEqual(r.over_limit, ["long"])
        self.assertGreater(r.input_tokens["long"], 512)

    def test_deterministic(self):
        f = lambda q, t: [len(x) % 3 for x in t]                            # noqa: E731
        self.assertEqual(rr.safe_rerank("q", CANDS, Fake(f)).order, rr.safe_rerank("q", CANDS, Fake(f)).order)


class NoDownload(unittest.TestCase):
    def test_missing_model_is_unavailable(self):
        with self.assertRaises(rr.RerankerUnavailable):
            rr.CrossEncoderReranker("/nonexistent/model")
        with tempfile.TemporaryDirectory() as d:                            # an empty directory is not a model
            with self.assertRaises(rr.RerankerUnavailable):
                rr.CrossEncoderReranker(d)


if __name__ == "__main__":
    unittest.main()
