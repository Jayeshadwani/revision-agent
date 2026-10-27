"""
PH4-RETRIEVE-001 (issue #9): BM25 keyword search over the retrieval-eligible Concept and Tool chunks.

Pure Python (Okapi BM25, k1=1.5, b=0.75); no extra package. The index is built in memory from the
same texts that were embedded (`embeddings.embedding_text`), so dense and keyword search see
identical documents. 2,174 chunks index in well under a second.

Tokenization keeps code identifiers: `fillna`, `train_test_split` and `np.where` (as `np`, `where`
and `np.where`) are all tokens. A light plural/suffix fold maps "residuals" to "residual"; there is
no stemmer that could mangle identifiers.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional

TOKEN_RE = re.compile(r"[a-z0-9_]+(?:\.[a-z0-9_]+)*")
STOPWORDS = frozenset("""
a an and are as at be been but by can could did do does doing for from had has have how i if in into is it
its me my of on or our so than that the their them then there these this those to was we were what when where
which while who why will with would you your about also am any each just more most not only other own same some
such too very should may might must let lets s t
""".split())


IRREGULAR = {"matrices": "matrix", "indices": "index", "vertices": "vertex", "analyses": "analysis",
             "hypotheses": "hypothesis", "axes": "axis", "data": "data", "bias": "bias", "series": "series"}


def fold(word: str) -> str:
    """Light normalisation: plural and a few suffixes, only on plain alphabetic words."""
    if word in IRREGULAR:
        return IRREGULAR[word]
    if not word.isalpha() or len(word) <= 4:
        return word
    for suffix, repl in (("ies", "y"),):
        if word.endswith(suffix):
            return word[: -len(suffix)] + repl
    if word.endswith("es") and word[:-2].endswith(("ss", "x", "z", "ch", "sh")):
        return word[:-2]                                    # classes -> class, boxes -> box
    if word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def tokenize(text: str) -> list[str]:
    out = []
    for tok in TOKEN_RE.findall(text.lower()):
        parts = tok.split(".")
        if len(parts) > 1:                       # np.where -> np.where, np, where
            out.append(tok)
        for p in parts:
            if p and p not in STOPWORDS and not p.isdigit():
                out.append(fold(p))
    return out


@dataclass
class BM25Index:
    k1: float = 1.5
    b: float = 0.75
    ids: list[str] = field(default_factory=list)
    meta: dict[str, dict] = field(default_factory=dict)       # chunk_id -> filterable metadata
    _tf: list[Counter] = field(default_factory=list)
    _len: list[int] = field(default_factory=list)
    _df: Counter = field(default_factory=Counter)
    _postings: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))

    def add(self, chunk_id: str, text: str, meta: dict) -> None:
        if chunk_id in self.meta:
            raise ValueError(f"duplicate chunk {chunk_id}")
        toks = tokenize(text)
        tf = Counter(toks)
        doc = len(self.ids)
        self.ids.append(chunk_id)
        self.meta[chunk_id] = meta
        self._tf.append(tf)
        self._len.append(len(toks))
        for term in tf:
            self._df[term] += 1
            self._postings[term].append(doc)

    @property
    def avgdl(self) -> float:
        return (sum(self._len) / len(self._len)) if self._len else 0.0

    def idf(self, term: str) -> float:
        n, df = len(self.ids), self._df.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(self, query: str, filters: Optional[dict] = None, limit: int = 50) -> list[tuple[float, str]]:
        """(score, chunk_id), best first. Filters are exact matches on metadata (list fields: membership)."""
        terms = list(dict.fromkeys(tokenize(query)))
        scores: dict[int, float] = defaultdict(float)
        avgdl = self.avgdl or 1.0
        for term in terms:
            idf = self.idf(term)
            for doc in self._postings.get(term, ()):
                tf = self._tf[doc][term]
                denom = tf + self.k1 * (1 - self.b + self.b * self._len[doc] / avgdl)
                scores[doc] += idf * tf * (self.k1 + 1) / denom
        hits = [(s, self.ids[d]) for d, s in scores.items() if matches(self.meta[self.ids[d]], filters)]
        hits.sort(key=lambda h: (-h[0], h[1]))
        return hits[:limit]

    def __len__(self) -> int:
        return len(self.ids)


def matches(meta: dict, filters: Optional[dict]) -> bool:
    for key, want in (filters or {}).items():
        have = meta.get(key)
        if isinstance(have, list):
            if want not in have:
                return False
        elif have != want:
            return False
    return True
