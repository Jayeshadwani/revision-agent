"""
Tests for src/retrieval.py and src/retrieval_eval.py (PH4-RETRIEVE-001, issue #9).

    python -m unittest discover -s tests

Dense search runs on MemoryIndex with the deterministic HashEmbedder, so no API key or Qdrant is
needed. A query identical to a chunk's embedded text finds that chunk, which makes dense results
checkable.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import embeddings as em  # noqa: E402
import index_builder as ib  # noqa: E402
import retrieval as rt  # noqa: E402
import retrieval_eval as ev  # noqa: E402
from vector_index import MemoryIndex  # noqa: E402

CFG = em.EmbeddingConfig(dimensions=32)


class Words:
    name = "test-words"

    def count(self, text):
        return len(text.split())


def concept(n, nb, path, text, tools=(), resources=(), math=False, cell=None):
    cell = n if cell is None else cell
    return {"chunk_id": f"CON_{n:06d}", "chunk_type": "concept", "notebook_id": nb, "notebook_title": nb.upper(),
            "section_path": path, "source_cell_ids": [cell], "source_span_ids": [f"{nb}_cell_{cell:03d}_span_000"],
            "content": f"Notebook: {nb.upper()}\nSection path: {' > '.join(path)}\n\n{text}",
            "contains_math": math, "contains_latex": math, "contains_table": False, "contains_code": False,
            "linked_tool_ids": list(tools), "linked_tool_chunk_ids": [], "linked_resource_ids": [],
            "linked_resource_chunk_ids": list(resources), "quality_flags": {"is_tiny": False, "is_oversized": False},
            "retrieval_eligible": True}


def tool(n, nb, path, title, code, cell, tool_type="tool_demonstration"):
    return {"chunk_id": f"TOOLCHUNK_{n:06d}", "chunk_type": "tool", "tool_id": f"TOOL_{n:04d}", "notebook_id": nb,
            "notebook_title": nb.upper(), "section_path": path,
            "breadcrumb": f"Notebook: {nb.upper()}\nSection path: {' > '.join(path)}",
            "source_cell_id": f"{nb}_cell_{cell:03d}", "source_cell_ids": [cell], "tool_type": tool_type,
            "title": title, "purpose": f"Demonstrates {title}", "description": title, "language": "python",
            "libraries": [], "code": code, "linked_concept_chunk_ids": [], "linked_resource_ids": [],
            "repeats_code_of": None, "retrieval_eligible": True}


CHUNKS = [
    concept(1, "nb_14", ["Metrics", "Precision"], "Precision is TP / (TP + FP), the share of predicted positives that "
            "are correct.", tools=["TOOL_0001", "TOOL_0002", "TOOL_0003"], resources=["RESCHUNK_000001"], math=True,
            cell=5),
    concept(2, "nb_14", ["Metrics", "Recall"], "Recall is TP / (TP + FN), the share of actual positives found.",
            math=True, cell=8),
    concept(3, "nb_24", ["PCA", "Curse of dimensionality"], "The curse of dimensionality: as features grow, "
            "distances lose meaning and data becomes sparse.", cell=2),
    concept(4, "nb_06", ["Missing values"], "Missing values can be filled with a constant or the column mean.", cell=11),
    tool(1, "nb_14", ["Metrics", "Precision"], "Precision function", "def precision(tp, fp):\n    return tp / (tp + fp)",
         cell=6, tool_type="tool_function"),
    tool(2, "nb_14", ["Metrics", "Precision"], "Precision with sklearn",
         "from sklearn.metrics import precision_score\nprecision_score(y, y_hat)", cell=7),
    tool(3, "nb_14", ["Metrics", "Precision"], "Precision plot", "plt.bar(['p'], [p])", cell=9, tool_type="visualization"),
    tool(4, "nb_06", ["Missing values"], "Fill missing ratings", "df['rating'].fillna(df['rating'].mean())", cell=14),
]
LINKS = {
    ("TOOL_0001", "nb_14_cell_005_span_000"): {"relationship": "implements", "confidence": 0.9},
    ("TOOL_0002", "nb_14_cell_005_span_000"): {"relationship": "demonstrates", "confidence": 0.7},
    ("TOOL_0003", "nb_14_cell_005_span_000"): {"relationship": "visualizes", "confidence": 0.6},
}
RESOURCES = {"RESCHUNK_000001": {"chunk_id": "RESCHUNK_000001", "resource_id": "RES_0001", "resource_type": "unclassified",
                                 "availability": "google_drive", "caption": "Confusion matrix", "image_url": "https://x",
                                 "local_path": None, "vision_status": "pending", "attachable": True}}


def make_retriever(chunks=CHUNKS):
    index, emb = MemoryIndex(CFG.collection), em.HashEmbedder(CFG.dimensions)
    ib.sync(index, chunks, emb, Words(), CFG)
    corpus = rt.Corpus.from_parts(chunks, LINKS, RESOURCES)
    return rt.Retriever(corpus, index, emb, embed_cfg=CFG), index, emb


class Search(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r, cls.index, cls.emb = make_retriever()

    def test_dense_returns_eligible_concepts_and_tools(self):                 # test 1
        text = em.embedding_text(CHUNKS[2])
        pkg = self.r.search(text, "dense")
        self.assertEqual(pkg["retrieved_chunks"][0]["chunk_id"], "CON_000003")
        self.assertEqual({r["chunk_type"] for r in pkg["retrieved_chunks"]}, {"concept", "tool"})

    def test_bm25_keyword_match(self):                                       # test 2
        pkg = self.r.search("fillna missing ratings", "bm25")
        self.assertEqual(pkg["ranking"][0]["chunk_id"], "TOOLCHUNK_000004")

    def test_hybrid_fuses_both(self):
        pkg = self.r.search("curse of dimensionality", "hybrid_rrf")
        sources = {r["chunk_id"]: r["source"] for r in pkg["ranking"]}
        self.assertEqual(sources["CON_000003"], "bm25+dense")
        self.assertEqual(pkg["retrieval_mode"], "hybrid_rrf")

    def test_metadata_filters(self):                                         # test 4
        for mode in rt.MODES:
            pkg = self.r.search("precision", mode, {"chunk_type": "tool"})
            self.assertTrue(pkg["ranking"])
            self.assertEqual({self.r.corpus.chunks[x["chunk_id"]]["chunk_type"] for x in pkg["ranking"]}, {"tool"})
            pkg = self.r.search("precision recall", mode, {"contains_math": True})
            self.assertEqual({x["chunk_id"] for x in pkg["ranking"]} - {"CON_000001", "CON_000002"}, set())
            pkg = self.r.search("values", mode, {"notebook_id": "nb_06"})
            self.assertTrue(all(self.r.corpus.chunks[x["chunk_id"]]["notebook_id"] == "nb_06" for x in pkg["ranking"]))
        with self.assertRaises(ValueError):
            self.r.search("x", "bm25", {"text": "nope"})

    def test_default_filter_and_guard(self):                                 # tests 5, 8
        pkg = self.r.search("precision", "bm25")
        self.assertEqual(pkg["filters_applied"], {"retrieval_eligible": True})
        # A stale vector for an excluded chunk (a quiz) and for a removed chunk must never come back.
        quiz = {"chunk_id": "CON_000099", "chunk_type": "concept", "notebook_id": "nb_14", "content_role": "quiz",
                "retrieval_eligible": True, "text": "precision quiz"}
        self.index.upsert([{"chunk_id": "CON_000099", "vector": self.emb.embed(["precision quiz"])[0], "payload": quiz}])
        try:
            before = self.r.guard_dropped
            pkg = self.r.search("precision quiz", "dense")
            self.assertNotIn("CON_000099", [x["chunk_id"] for x in pkg["ranking"]])
            self.assertGreater(self.r.guard_dropped, before)
        finally:
            self.index.delete(["CON_000099"])
        self.assertIn("quiz", rt.EXCLUDED_ROLES)

    def test_linked_tools_attach(self):                                      # test 6
        pkg = self.r.search("precision TP FP predicted positives", "bm25", {"chunk_type": "concept"})
        concept_hit = [t for t in pkg["attached_tools"] if t["concept_chunk_id"] == "CON_000001"]
        self.assertEqual(len(concept_hit), 2)                                # at most 2 per concept
        self.assertTrue(all(t["relationship"] in rt.PRIMARY_RELATIONSHIPS for t in concept_hit))
        self.assertEqual(concept_hit[0]["tool_id"], "TOOL_0001")             # higher link confidence first

    def test_tools_already_ranked_are_preferred(self):
        pkg = self.r.search("precision_score sklearn precision", "bm25")
        attached = [t["tool_id"] for t in pkg["attached_tools"] if t["concept_chunk_id"] == "CON_000001"]
        self.assertEqual(attached[0], "TOOL_0002")                           # ranked by BM25, so preferred

    def test_resources_are_not_text_evidence(self):                          # test 7
        pkg = self.r.search("precision TP FP", "bm25")
        self.assertTrue(pkg["attached_resources"])
        for res in pkg["attached_resources"]:
            self.assertEqual(res["vision_status"], "pending")
            self.assertTrue(res["not_usable_as_text_evidence"])
            self.assertNotIn("text", res)
        self.assertFalse(any(r["chunk_id"].startswith("RESCHUNK") for r in pkg["retrieved_chunks"]))

    def test_context_caps(self):
        pkg = self.r.search("precision recall values dimensionality fillna", "bm25")
        kinds = [r["chunk_type"] for r in pkg["retrieved_chunks"]]
        self.assertLessEqual(kinds.count("concept"), 5)
        self.assertLessEqual(kinds.count("tool"), 3)
        self.assertLessEqual(len(kinds), 8)

    def test_dense_requires_index(self):
        r = rt.Retriever(rt.Corpus.from_parts(CHUNKS, LINKS, RESOURCES))
        self.assertEqual(r.search("precision", "bm25")["retrieval_mode"], "bm25")
        with self.assertRaises(RuntimeError):
            r.search("precision", "dense")


class Evaluation(unittest.TestCase):
    PROMPTS = [
        {"prompt_id": "P1", "prompt": "What is precision?", "_file": "t",
         "expected_sources": [{"notebook_id": "nb_14", "cell_ids": [5], "source_type": "markdown"}]},
        {"prompt_id": "P2", "prompt": "curse of dimensionality", "_file": "t", "category": "broad_short",
         "expected_sources": [{"notebook_id": "nb_24", "cell_ids": [2], "source_type": "markdown"}]},
        {"prompt_id": "P3", "prompt": "fill missing values", "_file": "t", "category": "tool",
         "expected_sources": [{"notebook_id": "nb_06", "cell_ids": [14], "source_type": "code"}]},
        {"prompt_id": "P4", "prompt": "HNSW efSearch", "_file": "t", "expected_sources": []},
        {"prompt_id": "P5", "prompt": "precision image", "_file": "t",
         "expected_sources": [{"notebook_id": "nb_14", "cell_ids": [99], "source_type": "markdown"}]},
    ]

    def test_metrics(self):                                                  # test 9
        chunks = {c["chunk_id"]: c for c in CHUNKS}
        reach = {("nb_14", 5), ("nb_14", 8)}
        pkg = {"attached_tools": []}
        s = ev.score_prompt(["CON_000003", "CON_000002", "CON_000001"], pkg, chunks, reach, reach, set())
        self.assertEqual((s["hit_at_1"], s["first_relevant_rank"], s["mrr"]), (0.0, 2, 0.5))
        self.assertEqual((s["recall_at_5"], s["recall_at_10"]), (1.0, 1.0))
        s = ev.score_prompt(["CON_000002"] + ["CON_000003"] * 0, pkg, chunks, reach, reach, set())
        self.assertEqual((s["recall_at_5"], s["hit_at_1"], s["mrr"]), (0.5, 1.0, 1.0))
        s = ev.score_prompt([], pkg, chunks, reach, reach, set())
        self.assertEqual((s["recall_at_5"], s["mrr"], s["hit_at_1"]), (0.0, 0.0, 0.0))

    def test_all_modes_on_same_prompts(self):                                # test 10
        r, _, _ = make_retriever()
        res = ev.evaluate(r, self.PROMPTS, list(rt.MODES))
        by_mode = {}
        for row in res["rows"]:
            by_mode.setdefault(row["retrieval_mode"], []).append(row["prompt_id"])
        self.assertEqual(set(by_mode), set(rt.MODES))
        self.assertTrue(all(v == ["P1", "P2", "P3", "P4", "P5"] for v in by_mode.values()))
        for mode in rt.MODES:
            s = res["summary"][mode]["all"]
            self.assertEqual(s["n"], 3)                                      # P4 refusal, P5 unreachable: not scored
            self.assertIsNotNone(s["recall_at_5"])
        self.assertEqual(res["violations"], 0)
        self.assertEqual([u[0] for u in res["unreachable"]], ["P5"])
        self.assertEqual([p for p, _ in res["refusals"]["bm25"]], ["P4"])
        bm25_p3 = next(x for x in res["rows"] if x["prompt_id"] == "P3" and x["retrieval_mode"] == "bm25")
        self.assertTrue(bm25_p3["tool_hit"])
        self.assertEqual(bm25_p3["recall_at_5"], 1.0)

    def test_decision_rule(self):
        mk = lambda r, m: {"all": {"recall_at_5": r, "mrr": m}}             # noqa: E731
        self.assertEqual(ev.decide({"dense": mk(0.6, 0.5), "hybrid_rrf": mk(0.7, 0.5)})["default_mode"], "hybrid_rrf")
        self.assertEqual(ev.decide({"dense": mk(0.6, 0.5), "hybrid_rrf": mk(0.7, 0.4)})["default_mode"], "dense")
        self.assertEqual(ev.decide({"dense": mk(0.6, 0.5), "hybrid_rrf": mk(0.6, 0.5)})["default_mode"], "dense")
        self.assertIsNone(ev.decide({"bm25": mk(0.6, 0.5)}))

    def test_categories(self):
        cats = ev.categories({"prompt": "Compare PCA and autoencoders", "category": "multi_notebook",
                              "expected_sources": [{"notebook_id": "nb_24", "source_type": "markdown", "cell_ids": [8]},
                                                   {"notebook_id": "nb_35", "source_type": "markdown", "cell_ids": [35]}]})
        self.assertIn("multi_notebook", cats)
        self.assertIn("formula_keyword", cats)                               # "PCA"
        self.assertIn("broad_short", ev.categories({"prompt": "stationarity", "expected_sources": []}))
        self.assertNotIn("formula_keyword", ev.categories({"prompt": "what is a dendrogram for", "expected_sources": []}))


LABELS = Path(__file__).resolve().parent.parent / "evaluation" / "retrieval_qa_set.jsonl"


class LabelledSet(unittest.TestCase):
    def test_qa_set_shape(self):
        rows = [json.loads(l) for l in LABELS.read_text(encoding="utf-8").splitlines() if l.strip()]
        from collections import Counter
        self.assertEqual(Counter(r["category"] for r in rows),
                         {"concept": 10, "math": 5, "tool": 5, "broad_short": 5, "multi_notebook": 5})
        self.assertEqual(len({r["prompt_id"] for r in rows}), 30)
        for r in rows:
            self.assertTrue(r["expected_sources"])
            if r["category"] == "multi_notebook":
                self.assertGreater(len({s["notebook_id"] for s in r["expected_sources"]}), 1)


@unittest.skipUnless((rt.config.PROCESSED_DIR / "concept_chunks.jsonl").exists(), "chunks not built (data/ is local)")
class CorpusBM25(unittest.TestCase):
    def test_bm25_eval_runs_clean(self):
        r = rt.build_retriever(dense=False)
        res = ev.evaluate(r, ev.load_prompts(), ["bm25"])
        self.assertEqual(res["violations"], 0)
        self.assertGreater(res["summary"]["bm25"]["all"]["n"], 40)


if __name__ == "__main__":
    unittest.main()
