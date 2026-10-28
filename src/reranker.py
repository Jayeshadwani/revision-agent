"""
PH5-RETRIEVE-002 (issue #11), Gate A: cross-encoder reranking with a safe fallback.

Gate A ships the wrapper and its failure handling only. No model is downloaded: the cross-encoder
loads from a local directory, and only when a model path is given explicitly (Gate B, after the
PO approves the model, RAM/CPU budget and latency target).

`safe_rerank` never makes retrieval worse than the baseline by failing:
  - a timeout, missing/corrupt model, MemoryError or any exception -> baseline order, reason logged
  - a batch failing part-way -> baseline order (no half-reranked list)
  - NaN/inf scores -> those candidates go after all valid ones, in baseline order; if none are valid,
    baseline order
  - ties -> baseline order
  - a wrong number of scores -> baseline order
Cross-encoder scores are model logits, used only to order candidates. They are not calibrated
relevance probabilities, so nothing downstream should threshold on them.
"""
from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol, Sequence

from chunking import content_tokens

DEFAULT_TIMEOUT_S = 2.0
DEFAULT_BATCH = 16
DEFAULT_MAX_INPUT_TOKENS = 512        # typical cross-encoder limit (query + passage)


class Reranker(Protocol):
    name: str

    def score(self, query: str, texts: Sequence[str]) -> list[float]: ...


class RerankerUnavailable(RuntimeError):
    pass


@dataclass
class RerankResult:
    order: list[str]                          # candidate IDs, best first
    scores: dict[str, Optional[float]]        # raw model scores (None if invalid or not scored)
    status: str                               # "reranked" | "fallback"
    reason: str = ""
    invalid_scores: list[str] = field(default_factory=list)
    over_limit: list[str] = field(default_factory=list)   # inputs the model would truncate (logged)
    input_tokens: dict[str, int] = field(default_factory=dict)
    seconds: float = 0.0
    model: str = ""


def _valid(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def safe_rerank(query: str, candidates: list[tuple[str, str]], reranker: Optional[Reranker],
                timeout_s: float = DEFAULT_TIMEOUT_S, batch_size: int = DEFAULT_BATCH,
                max_input_tokens: int = DEFAULT_MAX_INPUT_TOKENS) -> RerankResult:
    """`candidates`: (id, text) in baseline order. Returns the reranked order or the baseline."""
    ids = [cid for cid, _ in candidates]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate candidate IDs; deduplicate (e.g. by parent) before reranking")
    q_tokens = content_tokens(query)
    tokens = {cid: q_tokens + content_tokens(text) for cid, text in candidates}
    over = [cid for cid in ids if tokens[cid] > max_input_tokens]
    base = RerankResult(order=list(ids), scores={cid: None for cid in ids}, status="fallback",
                        over_limit=over, input_tokens=tokens, model=getattr(reranker, "name", ""))
    if not candidates:
        base.status, base.reason = "reranked", "no candidates"
        return base
    if reranker is None:
        base.reason = "no reranker configured"
        return base
    start = time.perf_counter()

    def run() -> list:
        out = []
        for i in range(0, len(candidates), batch_size):
            batch = candidates[i:i + batch_size]
            scores = reranker.score(query, [t for _, t in batch])
            if scores is None or len(scores) != len(batch):
                raise ValueError(f"batch {i // batch_size}: got {0 if scores is None else len(scores)} scores "
                                 f"for {len(batch)} inputs")
            out.extend(scores)
        return out

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        raw = pool.submit(run).result(timeout=timeout_s)
    except FutureTimeout:
        base.reason = f"timeout after {timeout_s}s"
        return _done(base, start)
    except MemoryError:
        base.reason = "out of memory"
        return _done(base, start)
    except Exception as e:                                        # missing/corrupt model, partial batch, ...
        base.reason = f"{type(e).__name__}: {e}"
        return _done(base, start)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    scores = {cid: (float(s) if _valid(s) else None) for cid, s in zip(ids, raw)}
    invalid = [cid for cid in ids if scores[cid] is None]
    if len(invalid) == len(ids):
        base.reason, base.invalid_scores = "all scores invalid (NaN/inf/non-numeric)", invalid
        return _done(base, start)
    pos = {cid: i for i, cid in enumerate(ids)}
    order = sorted(ids, key=lambda c: (scores[c] is None, -(scores[c] or 0.0), pos[c]))
    return _done(RerankResult(order=order, scores=scores, status="reranked", invalid_scores=invalid,
                              over_limit=over, input_tokens=tokens, model=getattr(reranker, "name", "")), start)


def _done(r: RerankResult, start: float) -> RerankResult:
    r.seconds = round(time.perf_counter() - start, 4)
    return r


class CrossEncoderReranker:
    """sentence-transformers CrossEncoder loaded from a local directory only (no download).

    Gate B: the approved checkpoint is placed in `model_dir` deliberately; this class never fetches
    weights from the network (local_files_only)."""

    def __init__(self, model_dir: str, max_length: int = DEFAULT_MAX_INPUT_TOKENS, device: str = "cpu"):
        path = Path(model_dir)
        if not path.is_dir() or not any(path.iterdir()):
            raise RerankerUnavailable(f"no local model at {model_dir}; downloading needs PO approval (issue #11 Gate B)")
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as e:
            raise RerankerUnavailable("sentence-transformers is not installed") from e
        self.name = f"cross-encoder:{path.name}"
        self._model = CrossEncoder(str(path), max_length=max_length, device=device, local_files_only=True)

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        return [float(s) for s in self._model.predict([(query, t) for t in texts])]
