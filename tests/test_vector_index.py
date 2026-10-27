"""
Tests for src/vector_index.py and idempotent syncing in src/index_builder.py (PH3-EMBED-001, issue #5).

    python -m unittest discover -s tests

Every test runs against MemoryIndex, and again against Qdrant in-memory mode when
`qdrant-client` is installed.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from index_fixture import CFG, WordTokenizer, concept, corpus  # noqa: E402

import embeddings as em  # noqa: E402
import index_builder as ib  # noqa: E402
import vector_index as vi  # noqa: E402

HAS_QDRANT = importlib.util.find_spec("qdrant_client") is not None


class IndexContract:
    """Shared tests; subclasses provide make_index()."""

    def make_index(self, collection: str = CFG.collection):
        raise NotImplementedError

    def setUp(self):
        self.index = self.make_index()
        self.emb = em.HashEmbedder(CFG.dimensions)

    def sync(self, chunks, **kw):
        return ib.sync(self.index, chunks, self.emb, WordTokenizer(), CFG, **kw)

    def test_upsert_existing_creates_no_duplicate(self):                    # test 7
        self.sync(corpus())
        n = self.index.count()
        r = self.sync(corpus())
        self.assertEqual((self.index.count(), r["embedded"], r["skipped_unchanged"]), (n, [], 5))
        self.index.upsert([{"chunk_id": "CON_000001", "vector": [1.0] * CFG.dimensions,
                            "payload": self.index.payloads()["CON_000001"]}])
        self.assertEqual(self.index.count(), n)
        ids = self.index.point_ids()
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ib.health(self.index, r)["duplicate_ids"], 0)

    def test_changed_content_is_reembedded(self):                           # test 8
        self.sync(corpus())
        changed = corpus()
        changed[1] = concept(2, "Recall is TP / (TP + FN), the share of actual positives found.", notebook="nb_13")
        r = self.sync(changed)
        self.assertEqual(r["embedded"], ["CON_000002"])
        self.assertEqual((r["changed"], r["new"], r["skipped_unchanged"]), (1, 0, 4))
        self.assertIn("share of actual positives", self.index.payloads()["CON_000002"]["text"])
        self.assertEqual(r["payload_refreshed"], 4)                         # new corpus fingerprint, no re-embed

    def test_deleted_chunk_removes_vector(self):                            # tests 9, 12
        self.sync(corpus())
        r = self.sync(corpus()[1:])
        self.assertEqual(r["deleted"], ["CON_000001"])
        self.assertNotIn("CON_000001", self.index.payloads())
        self.assertEqual(self.index.count(), 4)
        h = ib.health(self.index, r)
        self.assertEqual((h["orphans"], h["duplicate_ids"], h["missing_metadata"]), ([], 0, []))

    def test_filter_fields_indexed_and_filters_work(self):                  # test 10
        self.sync(corpus())
        self.assertTrue(set(vi.PAYLOAD_INDEXES) <= set(self.index.payload_indexes()))
        q = em.embed_query("precision", self.emb, CFG)
        tools = self.index.search(q, {"chunk_type": "tool"}, limit=10)
        self.assertEqual({p["chunk_type"] for _, p in tools}, {"tool"})
        math = self.index.search(q, {"contains_math": True}, limit=10)
        self.assertEqual(sorted(p["chunk_id"] for _, p in math), ["CON_000001", "CON_000002"])
        nb = self.index.search(q, {"notebook_id": "nb_13"}, limit=10)
        self.assertEqual([p["chunk_id"] for _, p in nb], ["CON_000002"])

    def test_rebuild_is_deterministic(self):                                # test 11
        self.sync(corpus())
        first = (self.index.point_ids(), self.index.payloads())
        self.sync(corpus(), rebuild=True)
        self.assertEqual((self.index.point_ids(), self.index.payloads()), first)
        other = self.make_index("revision_agent_other")
        ib.sync(other, corpus(), em.HashEmbedder(CFG.dimensions), WordTokenizer(), CFG)
        self.assertEqual(other.point_ids(), first[0])
        q = em.embed_query("recall", self.emb, CFG)
        self.assertEqual([p["chunk_id"] for _, p in self.index.search(q, limit=5)],
                         [p["chunk_id"] for _, p in other.search(q, limit=5)])

    def test_exact_text_finds_itself(self):
        self.sync(corpus())
        text = self.index.payloads()["TOOLCHUNK_000002"]["text"]
        top = self.index.search(self.emb.embed([text])[0], limit=1)
        self.assertEqual(top[0][1]["chunk_id"], "TOOLCHUNK_000002")

    def test_no_mixing_models_or_dimensions(self):
        self.sync(corpus())
        with self.assertRaises(vi.IndexConfigMismatch):
            ib.sync(self.index, corpus(), em.HashEmbedder(CFG.dimensions, model="other-model"), WordTokenizer(), CFG)
        with self.assertRaises(vi.IndexConfigMismatch):
            self.index.ensure_collection(CFG.dimensions * 2, "cosine")
        r = ib.sync(self.index, corpus(), em.HashEmbedder(CFG.dimensions, model="other-model"), WordTokenizer(), CFG,
                    rebuild=True)
        self.assertEqual(len(r["embedded"]), 5)
        self.assertEqual({p["embedding_model"] for p in self.index.payloads().values()}, {"other-model"})

    def test_new_version_means_new_collection(self):
        v2 = em.EmbeddingConfig(dimensions=CFG.dimensions, embedding_version="v2")
        self.assertNotEqual(v2.collection, CFG.collection)
        self.assertEqual(CFG.collection, "revision_agent_v1")


class MemoryIndexTests(IndexContract, unittest.TestCase):
    def make_index(self, collection: str = CFG.collection):
        return vi.MemoryIndex(collection)


@unittest.skipUnless(HAS_QDRANT, "qdrant-client not installed")
class QdrantIndexTests(IndexContract, unittest.TestCase):
    def setUp(self):
        from qdrant_client import QdrantClient
        self.client = QdrantClient(location=":memory:")
        super().setUp()

    def make_index(self, collection: str = CFG.collection):
        return vi.QdrantIndex(collection, ":memory:", client=self.client)


class PointIds(unittest.TestCase):
    def test_stable_uuid_per_chunk(self):
        a, b = vi.point_id("CON_000001"), vi.point_id("CON_000001")
        self.assertEqual(a, b)
        self.assertNotEqual(a, vi.point_id("CON_000002"))
        self.assertEqual(len(a), 36)

    def test_payload_not_shared_between_calls(self):
        idx = vi.MemoryIndex("x")
        idx.ensure_collection(2, "cosine")
        payload = {"chunk_id": "A", "tags": ["a"]}
        idx.upsert([{"chunk_id": "A", "vector": [1.0, 0.0], "payload": payload}])
        payload["chunk_id"] = "B"                                          # caller mutates its dict afterwards
        self.assertEqual(list(idx.payloads()), ["A"])


if __name__ == "__main__":
    unittest.main()
