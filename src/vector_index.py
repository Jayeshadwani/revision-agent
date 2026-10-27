"""
PH3-EMBED-001 (issue #5): the dense vector index.

`QdrantIndex` wraps Qdrant in local mode (`pip install qdrant-client`); the data lives in
data/index/qdrant/. `MemoryIndex` has the same interface in plain Python and backs the tests that
must run without Qdrant installed.

Qdrant point IDs must be integers or UUIDs, so each point's ID is a UUIDv5 of the chunk ID and the
chunk ID itself is in the payload (`chunk_id`). Upserting the same chunk ID always hits the same
point, so re-running never creates duplicates.
"""
from __future__ import annotations

import math
import uuid
from typing import Iterable, Optional, Protocol

ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/Jayeshadwani/revision-agent")

# Payload fields that retrieval filters on (issue #5), with their Qdrant schema type.
PAYLOAD_INDEXES = {
    "chunk_type": "keyword",
    "notebook_id": "keyword",
    "content_role": "keyword",
    "contains_math": "bool",
    "embedding_model": "keyword",
    "embedding_version": "keyword",
    "retrieval_eligible": "bool",
}


class IndexConfigMismatch(RuntimeError):
    """The collection exists with other dimensions/distance, or holds vectors of another model."""


def point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(ID_NAMESPACE, chunk_id))


class VectorIndex(Protocol):
    collection: str

    def exists(self) -> bool: ...
    def ensure_collection(self, dimensions: int, distance: str) -> None: ...
    def create_payload_indexes(self) -> list[str]: ...
    def payload_indexes(self) -> list[str]: ...
    def upsert(self, records: list[dict]) -> None: ...          # {"chunk_id", "vector", "payload"}
    def set_payloads(self, records: list[dict]) -> None: ...    # {"chunk_id", "payload"}; vector kept
    def delete(self, chunk_ids: Iterable[str]) -> None: ...
    def payloads(self) -> dict[str, dict]: ...                   # chunk_id -> payload
    def point_ids(self) -> list[str]: ...
    def count(self) -> int: ...
    def search(self, vector: list[float], filters: Optional[dict] = None, limit: int = 5) -> list[tuple[float, dict]]: ...
    def drop(self) -> None: ...


def _matches(payload: dict, filters: Optional[dict]) -> bool:
    for key, want in (filters or {}).items():
        have = payload.get(key)
        if isinstance(have, list):
            if want not in have:
                return False
        elif have != want:
            return False
    return True


# ----------------------------------------------------------------------------
# In-memory implementation (tests, dry runs)
# ----------------------------------------------------------------------------
class MemoryIndex:
    def __init__(self, collection: str):
        self.collection = collection
        self._points: dict[str, tuple[list[float], dict]] = {}
        self._dims: Optional[int] = None
        self._distance: Optional[str] = None
        self._indexes: set[str] = set()

    def exists(self) -> bool:
        return self._dims is not None

    def ensure_collection(self, dimensions: int, distance: str) -> None:
        if self._dims is not None and (self._dims, self._distance) != (dimensions, distance):
            raise IndexConfigMismatch(f"{self.collection}: {self._dims}/{self._distance} != {dimensions}/{distance}")
        self._dims, self._distance = dimensions, distance

    def create_payload_indexes(self) -> list[str]:
        self._indexes |= set(PAYLOAD_INDEXES)
        return sorted(self._indexes)

    def payload_indexes(self) -> list[str]:
        return sorted(self._indexes)

    def upsert(self, records: list[dict]) -> None:
        for r in records:
            if len(r["vector"]) != self._dims:
                raise IndexConfigMismatch(f"{r['chunk_id']}: vector size {len(r['vector'])} != {self._dims}")
            self._points[point_id(r["chunk_id"])] = (list(r["vector"]), dict(r["payload"]))

    def set_payloads(self, records: list[dict]) -> None:
        for r in records:
            vector, _ = self._points[point_id(r["chunk_id"])]
            self._points[point_id(r["chunk_id"])] = (vector, dict(r["payload"]))

    def delete(self, chunk_ids: Iterable[str]) -> None:
        for cid in chunk_ids:
            self._points.pop(point_id(cid), None)

    def payloads(self) -> dict[str, dict]:
        return {p["chunk_id"]: p for _, p in self._points.values()}

    def point_ids(self) -> list[str]:
        return sorted(self._points)

    def vectors(self) -> dict[str, list[float]]:
        return {p["chunk_id"]: v for v, p in self._points.values()}

    def count(self) -> int:
        return len(self._points)

    def search(self, vector, filters=None, limit=5):
        def cos(a, b):
            na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
            return sum(x * y for x, y in zip(a, b)) / ((na * nb) or 1.0)
        hits = [(cos(vector, v), p) for v, p in self._points.values() if _matches(p, filters)]
        return sorted(hits, key=lambda h: (-h[0], h[1]["chunk_id"]))[:limit]

    def drop(self) -> None:
        self._points.clear()
        self._dims = self._distance = None
        self._indexes.clear()


# ----------------------------------------------------------------------------
# Qdrant local mode
# ----------------------------------------------------------------------------
class QdrantIndex:
    """Qdrant in local mode (`path`), or in memory with path=":memory:"."""

    def __init__(self, collection: str, path: str, client=None):
        try:
            from qdrant_client import QdrantClient, models
        except ImportError as e:
            raise RuntimeError("qdrant-client is required for the vector index: pip install qdrant-client") from e
        self.models = models
        self.collection = collection
        self.client = client or (QdrantClient(location=":memory:") if path == ":memory:" else QdrantClient(path=path))
        self._declared: set[str] = set()

    # collection ---------------------------------------------------------------
    def exists(self) -> bool:
        if hasattr(self.client, "collection_exists"):
            return self.client.collection_exists(self.collection)
        return self.collection in {c.name for c in self.client.get_collections().collections}

    def ensure_collection(self, dimensions: int, distance: str) -> None:
        m = self.models
        dist = {"cosine": m.Distance.COSINE, "dot": m.Distance.DOT, "euclid": m.Distance.EUCLID}[distance]
        if not self.exists():
            self.client.create_collection(self.collection, vectors_config=m.VectorParams(size=dimensions, distance=dist))
            return
        params = self.client.get_collection(self.collection).config.params.vectors
        if params.size != dimensions or params.distance != dist:
            raise IndexConfigMismatch(f"{self.collection} has {params.size}/{params.distance}; "
                                      f"wanted {dimensions}/{dist}. Use a new embedding_version.")

    def create_payload_indexes(self) -> list[str]:
        m = self.models
        kinds = {"keyword": m.PayloadSchemaType.KEYWORD, "bool": m.PayloadSchemaType.BOOL}
        import warnings
        for field, kind in PAYLOAD_INDEXES.items():
            with warnings.catch_warnings():
                # Local mode warns that payload indexes have no effect there (it filters by scanning);
                # they are declared anyway so the same collection works on a Qdrant server.
                warnings.filterwarnings("ignore", message="Payload indexes have no effect")
                self.client.create_payload_index(self.collection, field_name=field, field_schema=kinds[kind])
            self._declared.add(field)
        return self.payload_indexes()

    def payload_indexes(self) -> list[str]:
        # Qdrant server reports the schema; local mode accepts the call but may not report it.
        schema = getattr(self.client.get_collection(self.collection), "payload_schema", None) or {}
        return sorted(set(schema) | self._declared)

    # points ---------------------------------------------------------------------
    def upsert(self, records: list[dict]) -> None:
        if not records:
            return
        points = [self.models.PointStruct(id=point_id(r["chunk_id"]), vector=r["vector"], payload=r["payload"])
                  for r in records]
        self.client.upsert(self.collection, points=points, wait=True)

    def set_payloads(self, records: list[dict]) -> None:
        for r in records:
            self.client.overwrite_payload(self.collection, payload=r["payload"], points=[point_id(r["chunk_id"])],
                                          wait=True)

    def delete(self, chunk_ids: Iterable[str]) -> None:
        ids = [point_id(c) for c in chunk_ids]
        if ids:
            self.client.delete(self.collection, points_selector=self.models.PointIdsList(points=ids), wait=True)

    def _scroll(self, with_payload=True):
        offset = None
        while True:
            points, offset = self.client.scroll(self.collection, limit=512, offset=offset, with_payload=with_payload,
                                                with_vectors=False)
            yield from points
            if offset is None:
                break

    def payloads(self) -> dict[str, dict]:
        return {p.payload["chunk_id"]: p.payload for p in self._scroll()}

    def point_ids(self) -> list[str]:
        return sorted(str(p.id) for p in self._scroll(with_payload=False))

    def count(self) -> int:
        return self.client.count(self.collection, exact=True).count

    def search(self, vector, filters=None, limit=5):
        m = self.models
        flt = None
        if filters:
            flt = m.Filter(must=[m.FieldCondition(key=k, match=m.MatchValue(value=v)) for k, v in filters.items()])
        if hasattr(self.client, "query_points"):
            hits = self.client.query_points(self.collection, query=vector, query_filter=flt, limit=limit,
                                            with_payload=True).points
        else:
            hits = self.client.search(self.collection, query_vector=vector, query_filter=flt, limit=limit,
                                      with_payload=True)
        return [(h.score, h.payload) for h in hits]

    def drop(self) -> None:
        if self.exists():
            self.client.delete_collection(self.collection)
        self._declared.clear()
