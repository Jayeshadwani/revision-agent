"""
Tests for src/embeddings.py and the embedding side of src/index_builder.py (PH3-EMBED-001, issue #5).

    python -m unittest discover -s tests

No network and no API key are needed: OpenAI is replaced by fakes and vectors come from
HashEmbedder. Tests that need `tiktoken` skip when it is not installed.
"""
from __future__ import annotations

import builtins
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from index_fixture import CFG, WordTokenizer, concept, corpus, tool  # noqa: E402

import config  # noqa: E402
import embeddings as em  # noqa: E402
import index_builder as ib  # noqa: E402
from vector_index import MemoryIndex  # noqa: E402

HAS_TIKTOKEN = importlib.util.find_spec("tiktoken") is not None


class Tokenizer(unittest.TestCase):                                           # test 1
    @unittest.skipUnless(HAS_TIKTOKEN, "tiktoken not installed")
    def test_uses_model_tokenizer(self):
        import tiktoken
        tok = em.get_tokenizer(em.DEFAULT_CONFIG)
        enc = tiktoken.encoding_for_model("text-embedding-3-small")
        self.assertEqual(tok.name, f"tiktoken:{enc.name}")
        text = "Precision = TP / (TP + FP) — $\\frac{a}{b}$"
        self.assertEqual(tok.count(text), len(enc.encode(text)))

    def test_no_silent_fallback_without_tiktoken(self):
        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name == "tiktoken":
                raise ImportError("no tiktoken")
            return real_import(name, *a, **k)
        with mock.patch("builtins.__import__", fake_import):
            with self.assertRaises(RuntimeError):
                em.get_tokenizer(em.DEFAULT_CONFIG)

    def test_token_counts_recorded_with_tokenizer(self):
        p = ib.plan(corpus(), WordTokenizer(), "test-hash-embedder", CFG)
        for item in p["items"]:
            self.assertEqual(item["payload"]["token_count"], WordTokenizer().count(item["text"]))
            self.assertEqual(item["payload"]["tokenizer"], "test-words")


class Texts(unittest.TestCase):
    def test_concept_text_is_chunk_content(self):
        c = concept(1)
        self.assertEqual(em.embedding_text(c), c["content"])
        self.assertTrue(em.embedding_text(c).startswith("Notebook: Model Evaluation\nSection path: "))

    def test_tool_text_format(self):
        t = em.embedding_text(tool(1))
        self.assertTrue(t.startswith("Tool: Precision\nPurpose: Defines a function for Precision\n"))
        self.assertIn("Notebook: Model Evaluation\nSection path: Model Evaluation > Precision", t)
        self.assertIn("Tool code:\n```python\ndef precision(tp, fp):\n    return tp / (tp + fp)\n```", t)

    def test_resources_are_never_embedded(self):                              # test 4
        with self.assertRaises(ValueError):
            em.embedding_text({"chunk_id": "RESCHUNK_000001", "chunk_type": "resource"})
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "concept_chunks.jsonl").write_text(json.dumps(concept(1)) + "\n")
            (d / "tool_chunks.jsonl").write_text(json.dumps(tool(1)) + "\n" +
                                                 json.dumps({**tool(2), "retrieval_eligible": False,
                                                             "duplicate_of": "TOOLCHUNK_000001"}) + "\n")
            (d / "resource_chunks.jsonl").write_text(json.dumps({"chunk_id": "RESCHUNK_000001"}) + "\n")
            chunks, left_out = ib.load_chunks(d)
        self.assertEqual([c["chunk_id"] for c in chunks], ["CON_000001", "TOOLCHUNK_000001"])
        self.assertEqual(left_out, {"resource: vision pending, never embedded": 1,
                                    "tool: not retrieval-eligible (duplicate)": 1})


class Embedding(unittest.TestCase):
    def sync(self, chunks):
        index, emb = MemoryIndex(CFG.collection), em.HashEmbedder(CFG.dimensions)
        return index, emb, ib.sync(index, chunks, emb, WordTokenizer(), CFG)

    def test_concept_and_tool_chunks_embedded(self):                          # tests 2, 3
        index, emb, r = self.sync(corpus())
        self.assertEqual(sorted(r["embedded"]), sorted(c["chunk_id"] for c in corpus()))
        types = {p["chunk_type"] for p in index.payloads().values()}
        self.assertEqual(types, {"concept", "tool"})
        self.assertEqual(emb.calls, [2, 2, 1])                                # batch_size 2

    def test_payload_metadata(self):                                          # test 5
        index, _, r = self.sync(corpus())
        for cid, p in index.payloads().items():
            for field in ib.REQUIRED_FIELDS[p["chunk_type"]]:
                self.assertIn(field, p, (cid, field))
            self.assertEqual(p["embedding_model"], "test-hash-embedder")
            self.assertEqual(p["embedding_version"], "v1")
            self.assertEqual(p["corpus_fingerprint"], r["fingerprint"])
        c = index.payloads()["CON_000001"]
        self.assertEqual((c["content_role"], c["section_path"], c["contains_math"]),
                         ("teaching", "Model Evaluation > Precision", True))
        t = index.payloads()["TOOLCHUNK_000001"]
        self.assertEqual((t["content_role"], t["tool_type"], t["tool_id"]), ("tool_function", "tool_function", "TOOL_0001"))

    def test_query_uses_same_model_and_dimensions(self):                      # test 6
        emb = em.HashEmbedder(CFG.dimensions)
        self.assertEqual(len(em.embed_query("what is precision?", emb, CFG)), CFG.dimensions)
        with self.assertRaises(ValueError):
            em.embed_query("q", em.HashEmbedder(8), CFG)
        other = SimpleNamespace(model="text-embedding-3-large", dimensions=CFG.dimensions, embed=lambda t: [[0.0]])
        with self.assertRaises(ValueError):
            em.embed_query("q", other, CFG)

    def test_openai_embedder_request_and_retry(self):
        calls = []

        class RateLimitError(Exception):
            pass

        def create(model, input, dimensions):
            calls.append((model, list(input), dimensions))
            if len(calls) == 1:
                raise RateLimitError("slow down")
            return SimpleNamespace(data=[SimpleNamespace(index=i, embedding=[float(i)] * dimensions)
                                         for i in reversed(range(len(input)))])
        client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
        emb = em.OpenAIEmbedder(CFG, client=client, sleep=lambda s: None)
        vectors = emb.embed(["a", "b"])
        self.assertEqual(len(calls), 2)                                       # retried once
        self.assertEqual(calls[-1], ("text-embedding-3-small", ["a", "b"], 16))
        self.assertEqual([v[0] for v in vectors], [0.0, 1.0])                  # restored to input order

    def test_failed_batch_is_reported_not_indexed(self):
        class Broken(em.HashEmbedder):
            def embed(self, texts):
                if any("Recall" in t for t in texts):
                    raise RuntimeError("API down")
                return super().embed(texts)
        index = MemoryIndex(CFG.collection)
        r = ib.sync(index, corpus(), Broken(CFG.dimensions), WordTokenizer(), CFG)
        failed = {f["chunk_id"] for f in r["failed"]}
        self.assertEqual(failed, {"CON_000001", "CON_000002"})               # the batch holding the Recall chunk
        self.assertFalse(failed & set(index.payloads()))

    def test_no_truncation(self):
        long_chunk = concept(9, "word " * 50)
        cfg = em.EmbeddingConfig(dimensions=16, max_input_tokens=40, safe_input_tokens=20)
        index = MemoryIndex(cfg.collection)
        r = ib.sync(index, [long_chunk, concept(1)], em.HashEmbedder(16), WordTokenizer(), cfg)
        self.assertEqual([f["chunk_id"] for f in r["failed"]], ["CON_000009"])
        self.assertIn("model limit", r["failed"][0]["reason"])
        self.assertIn("instead of truncating", r["failed"][0]["reason"])
        self.assertNotIn("CON_000009", index.payloads())
        sent = index.payloads()["CON_000001"]["text"]
        self.assertEqual(sent, concept(1)["content"])                          # full text, as embedded

    def test_batches_respect_size_and_token_cap(self):
        cfg = em.EmbeddingConfig(batch_size=3, max_request_tokens=10)
        self.assertEqual(em.batches(list(range(7)), [4, 4, 4, 1, 1, 1, 1], cfg), [[0, 1], [2, 3, 4], [5, 6]])

    def test_dry_run_calls_nothing(self):
        class NoCalls(em.HashEmbedder):
            def embed(self, texts):
                raise AssertionError("dry run embedded")
        index = MemoryIndex(CFG.collection)
        r = ib.sync(index, corpus(), NoCalls(CFG.dimensions), WordTokenizer(), CFG, dry_run=True)
        self.assertEqual(len(r["to_embed"]), 5)
        self.assertEqual(index.count(), 0)


CHUNKS = config.PROCESSED_DIR / "concept_chunks.jsonl"


@unittest.skipUnless(CHUNKS.exists(), "chunks not built (data/ is kept local)")
class Corpus(unittest.TestCase):
    def test_scope_matches_ticket(self):
        chunks, left_out = ib.load_chunks()
        types = [c["chunk_type"] for c in chunks]
        self.assertEqual(len(types), types.count("concept") + types.count("tool"))
        concept_total = sum(1 for _ in CHUNKS.read_text().splitlines())
        self.assertEqual(types.count("concept"), concept_total)                # all concept chunks
        self.assertTrue(all(c["retrieval_eligible"] for c in chunks))
        self.assertIn("resource: vision pending, never embedded", left_out)

    def test_every_chunk_fits_model_limit(self):
        chunks, _ = ib.load_chunks()
        if not HAS_TIKTOKEN:
            self.skipTest("tiktoken not installed")
        p = ib.plan(chunks, em.get_tokenizer(), em.DEFAULT_CONFIG.model)
        self.assertEqual(p["failed"], [])


if __name__ == "__main__":
    unittest.main()
