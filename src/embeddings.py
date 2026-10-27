"""
PH3-EMBED-001 (issue #5): embedding configuration, tokenizer-based token counts, embedders and the
exact text that is embedded for each chunk.

Optional dependencies (only needed to embed for real):
    pip install openai tiktoken
    export OPENAI_API_KEY=...

Nothing here truncates text. A chunk above the model's input limit raises `ChunkTooLong`, so it
is reported, never silently cut.
"""
from __future__ import annotations

import hashlib
import math
import os
import random
import time
from dataclasses import dataclass
from typing import Callable, Optional, Protocol, Sequence



# ----------------------------------------------------------------------------
# Configuration (approved in issue #5)
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class EmbeddingConfig:
    model: str = "text-embedding-3-small"
    provider: str = "openai"
    dimensions: int = 1536
    distance: str = "cosine"
    batch_size: int = 128
    max_input_tokens: int = 8192         # hard limit: above this a chunk is never sent
    safe_input_tokens: int = 1500        # flagged above this (chunks target 300–800 tokens)
    max_request_tokens: int = 250_000    # tokens per API request, kept under the provider's per-request cap
    embedding_version: str = "v1"
    usd_per_million_tokens: float = 0.02  # list price for text-embedding-3-small; check before relying on it

    @property
    def collection(self) -> str:
        """One collection per model + version: changing either means a new collection."""
        return f"revision_agent_{self.embedding_version}"


DEFAULT_CONFIG = EmbeddingConfig()
PIPELINE_VERSION = "phase3-v1"


class ChunkTooLong(ValueError):
    pass


# ----------------------------------------------------------------------------
# Tokenizer
# ----------------------------------------------------------------------------
class Tokenizer(Protocol):
    name: str

    def count(self, text: str) -> int: ...


class TiktokenTokenizer:
    """The tokenizer of the embedding model (cl100k_base for text-embedding-3-*)."""

    def __init__(self, model: str = DEFAULT_CONFIG.model):
        try:
            import tiktoken
        except ImportError as e:                       # never fall back silently to an estimate
            raise RuntimeError("tiktoken is required for token counts: pip install tiktoken") from e
        self._enc = tiktoken.encoding_for_model(model)
        self.name = f"tiktoken:{self._enc.name}"
        self.model = model

    def count(self, text: str) -> int:
        return len(self._enc.encode(text, disallowed_special=()))


def get_tokenizer(cfg: EmbeddingConfig = DEFAULT_CONFIG) -> Tokenizer:
    return TiktokenTokenizer(cfg.model)


# ----------------------------------------------------------------------------
# Embedders
# ----------------------------------------------------------------------------
class Embedder(Protocol):
    model: str
    dimensions: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    """Batched calls to the OpenAI embeddings API with retries on transient errors."""

    def __init__(self, cfg: EmbeddingConfig = DEFAULT_CONFIG, client=None, max_retries: int = 5,
                 sleep: Callable[[float], None] = time.sleep):
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as e:
                raise RuntimeError("openai is required to embed: pip install openai") from e
            if not os.environ.get("OPENAI_API_KEY"):
                raise RuntimeError("OPENAI_API_KEY is not set")
            client = OpenAI()
        self.client = client
        self.model = cfg.model
        self.dimensions = cfg.dimensions
        self.max_retries = max_retries
        self.sleep = sleep

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.client.embeddings.create(model=self.model, input=list(texts), dimensions=self.dimensions)
                data = sorted(resp.data, key=lambda d: d.index)
                vectors = [list(d.embedding) for d in data]
                if len(vectors) != len(texts) or any(len(v) != self.dimensions for v in vectors):
                    raise RuntimeError("embedding response does not match the request")
                return vectors
            except Exception as e:                    # rate limits, timeouts, 5xx
                if attempt == self.max_retries or not _retryable(e):
                    raise
                self.sleep(min(60.0, 2 ** attempt + random.random()))
        raise AssertionError("unreachable")


def _retryable(e: Exception) -> bool:
    name = type(e).__name__
    status = getattr(e, "status_code", None)
    return name in {"RateLimitError", "APITimeoutError", "APIConnectionError", "InternalServerError"} or \
        (isinstance(status, int) and (status == 429 or status >= 500))


class HashEmbedder:
    """Deterministic stand-in for tests and dry runs: unit vectors derived from a text hash.

    Its model name ("test-hash-embedder") differs from the real model, so its vectors can never be
    mixed into a real collection (the index refuses vectors of another model)."""

    def __init__(self, dimensions: int = DEFAULT_CONFIG.dimensions, model: str = "test-hash-embedder"):
        self.model = model
        self.dimensions = dimensions
        self.calls: list[int] = []                    # batch sizes, for tests

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(len(texts))
        out = []
        for text in texts:
            seed = hashlib.sha256(text.encode("utf-8")).digest()
            rng = random.Random(seed)
            v = [rng.gauss(0, 1) for _ in range(self.dimensions)]
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / norm for x in v])
        return out


def embed_query(text: str, embedder: Embedder, cfg: EmbeddingConfig = DEFAULT_CONFIG) -> list[float]:
    """Queries go through the same embedder, model and dimensions as the chunks."""
    if embedder.model != cfg.model and not isinstance(embedder, HashEmbedder):
        raise ValueError(f"query embedder {embedder.model} != index model {cfg.model}")
    if embedder.dimensions != cfg.dimensions:
        raise ValueError(f"query dimensions {embedder.dimensions} != index dimensions {cfg.dimensions}")
    return embedder.embed([text])[0]


# ----------------------------------------------------------------------------
# What gets embedded
# ----------------------------------------------------------------------------
def concept_text(chunk: dict) -> str:
    """Breadcrumb + merged teaching text: exactly the chunk's `content` (PH2-CHUNK-001)."""
    return chunk["content"]


def tool_text(chunk: dict) -> str:
    """Tool header, breadcrumb, then the code exactly as stored."""
    crumb_lines = chunk["breadcrumb"].split("\n")
    lines = [f"Tool: {chunk['title']}", f"Purpose: {chunk['purpose']}"]
    if chunk.get("description") and chunk["description"] != chunk["title"] \
            and not chunk["description"].startswith(chunk["purpose"]):
        lines.append(f"Description: {chunk['description']}")
    lines += crumb_lines
    if chunk.get("libraries"):
        lines.append("Libraries: " + ", ".join(chunk["libraries"]))
    return "\n".join(lines) + f"\n\nTool code:\n```{chunk.get('language') or 'python'}\n{chunk['code']}\n```"


def embedding_text(chunk: dict) -> str:
    if chunk["chunk_type"] == "concept":
        return concept_text(chunk)
    if chunk["chunk_type"] == "tool":
        return tool_text(chunk)
    raise ValueError(f"{chunk['chunk_id']}: {chunk['chunk_type']} chunks are not embedded")


def content_hash(text: str, model: str, cfg: EmbeddingConfig = DEFAULT_CONFIG) -> str:
    """Changes when the embedded text, the model, the dimensions or the embedding version change."""
    key = f"{model}|{cfg.dimensions}|{cfg.embedding_version}|{text}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def check_length(chunk_id: str, tokens: int, cfg: EmbeddingConfig = DEFAULT_CONFIG) -> Optional[str]:
    """None if fine, 'above_safe_limit' to flag; raises ChunkTooLong above the hard limit."""
    if tokens > cfg.max_input_tokens:
        raise ChunkTooLong(f"{chunk_id}: {tokens} tokens > model limit {cfg.max_input_tokens}; "
                           "re-chunk it instead of truncating")
    return "above_safe_limit" if tokens > cfg.safe_input_tokens else None


def batches(items: list, token_counts: list[int], cfg: EmbeddingConfig = DEFAULT_CONFIG) -> list[list[int]]:
    """Indexes grouped into API requests of at most batch_size items and max_request_tokens tokens."""
    out, cur, cur_tokens = [], [], 0
    for i, t in enumerate(token_counts):
        if cur and (len(cur) >= cfg.batch_size or cur_tokens + t > cfg.max_request_tokens):
            out.append(cur)
            cur, cur_tokens = [], 0
        cur.append(i)
        cur_tokens += t
    if cur:
        out.append(cur)
    return out

