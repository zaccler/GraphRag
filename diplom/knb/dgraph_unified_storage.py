from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pydgraph

from ragu.storage.base_storage import BaseKVStorage, BaseVectorStorage
from ragu.storage.types import Embedding, EmbeddingHit


KV_TYPE = "RaguKV"
EMBEDDING_TYPE = "RaguEmbedding"
GRPC_MAX_MESSAGE_BYTES = 128 * 1024 * 1024
GRPC_OPTIONS = [
    ("grpc.max_receive_message_length", GRPC_MAX_MESSAGE_BYTES),
    ("grpc.max_send_message_length", GRPC_MAX_MESSAGE_BYTES),
]
VECTOR_QUERY_PAGE_SIZE = 100

DGRAPH_UNIFIED_SCHEMA = """
ragu_store_kind: string @index(exact) .
ragu_key: string @index(exact) .
ragu_value_json: string @index(term) .
ragu_vector_json: string .
ragu_metadata_json: string .

type RaguKV {
  ragu_store_kind
  ragu_key
  ragu_value_json
}

type RaguEmbedding {
  ragu_store_kind
  ragu_key
  ragu_vector_json
  ragu_metadata_json
}
"""


def _namespace_name(filename: str) -> str:
    return Path(str(filename)).name


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value: Any, default: Any) -> Any:
    if not isinstance(value, str):
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return -1.0

    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return -1.0
    return dot / (left_norm * right_norm)


class _DgraphStoreBase:
    def __init__(self, address: str = "localhost:9080", **kwargs: Any):
        self._address = str(kwargs.get("address", address))
        self._stub = pydgraph.DgraphClientStub(self._address, options=GRPC_OPTIONS)
        self._client = pydgraph.DgraphClient(self._stub)
        self._schema_ready = False
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        self._client.alter(pydgraph.Operation(schema=DGRAPH_UNIFIED_SCHEMA))
        self._schema_ready = True

    def _query(self, query: str, variables: dict[str, str] | None = None) -> dict[str, Any]:
        self._ensure_schema()
        txn = self._client.txn(read_only=True)
        try:
            response = txn.query(query, variables=variables or {})
            return json.loads(response.json)
        finally:
            txn.discard()

    def _mutate(self, set_obj: Any | None = None, delete_nquads: str | None = None) -> None:
        self._ensure_schema()
        txn = self._client.txn()
        try:
            if set_obj is not None:
                txn.mutate(set_obj=set_obj)
            if delete_nquads:
                txn.mutate(del_nquads=delete_nquads)
            txn.commit()
        finally:
            txn.discard()

    def close(self) -> None:
        self._stub.close()

    async def index_start_callback(self) -> None:
        self._ensure_schema()

    async def index_done_callback(self) -> None:
        return None

    async def query_done_callback(self) -> None:
        return None


class DgraphKVStorage(_DgraphStoreBase, BaseKVStorage[Any]):
    def __init__(
        self,
        storage_folder: str | None = None,
        filename: str = "kv_store",
        address: str = "localhost:9080",
        **kwargs: Any,
    ):
        super().__init__(address=address, **kwargs)
        self.namespace = _namespace_name(filename)

    def _find_uid(self, key: str) -> str | None:
        query = """
        query q($kind: string, $key: string) {
          rows(func: eq(ragu_store_kind, $kind)) @filter(type(RaguKV) AND eq(ragu_key, $key)) {
            uid
          }
        }
        """
        rows = self._query(query, {"$kind": self.namespace, "$key": key}).get("rows", [])
        return rows[0]["uid"] if rows else None

    async def all_keys(self) -> list[str]:
        query = """
        query q($kind: string) {
          rows(func: eq(ragu_store_kind, $kind)) @filter(type(RaguKV)) {
            ragu_key
          }
        }
        """
        rows = self._query(query, {"$kind": self.namespace}).get("rows", [])
        return [str(row["ragu_key"]) for row in rows if row.get("ragu_key")]

    async def get_by_id(self, id: str) -> Any | None:
        query = """
        query q($kind: string, $key: string) {
          rows(func: eq(ragu_store_kind, $kind)) @filter(type(RaguKV) AND eq(ragu_key, $key)) {
            ragu_value_json
          }
        }
        """
        rows = self._query(query, {"$kind": self.namespace, "$key": id}).get("rows", [])
        if not rows:
            return None
        return _json_loads(rows[0].get("ragu_value_json"), None)

    async def get_by_ids(self, ids: list[str], fields: set[str] | None = None) -> list[Any | None]:
        values = [await self.get_by_id(item_id) for item_id in ids]
        if fields is None:
            return values
        return [
            {key: value for key, value in item.items() if key in fields}
            if isinstance(item, dict)
            else item
            for item in values
        ]

    def search_text_rows(self, terms, limit=6):
        terms = " ".join(str(terms or "").split())
        if not terms:
            return []

        limit = max(1, min(int(limit), 50))
        query = f"""
        query q($kind: string, $terms: string) {{
          rows(func: anyofterms(ragu_value_json, $terms), first: {limit}) @filter(type(RaguKV) AND eq(ragu_store_kind, $kind)) {{
            ragu_key
            ragu_value_json
          }}
        }}
        """
        return self._query(query, {"$kind": self.namespace, "$terms": terms}).get("rows", [])

    async def filter_keys(self, data: list[str]) -> set[str]:
        existing = set(await self.all_keys())
        return {key for key in data if key not in existing}

    async def upsert(self, data: dict[str, Any]) -> None:
        for key, value in data.items():
            obj = {
                "dgraph.type": KV_TYPE,
                "ragu_store_kind": self.namespace,
                "ragu_key": key,
                "ragu_value_json": _json_dumps(value),
            }
            uid = self._find_uid(key)
            if uid:
                obj["uid"] = uid
            self._mutate(set_obj=obj)

    async def delete(self, ids: list[str]) -> None:
        delete_lines = []
        for item_id in ids:
            uid = self._find_uid(item_id)
            if uid:
                delete_lines.append(f"<{uid}> * * .")
        if delete_lines:
            self._mutate(delete_nquads="\n".join(delete_lines))

    async def drop(self) -> None:
        keys = await self.all_keys()
        await self.delete(keys)


class DgraphVectorStorage(_DgraphStoreBase, BaseVectorStorage):
    def __init__(
        self,
        embedding_dim: int,
        cosine_threshold: float = 0.2,
        storage_folder: str | None = None,
        filename: str = "vdb",
        address: str = "localhost:9080",
        **kwargs: Any,
    ):
        super().__init__(address=address, **kwargs)
        self.namespace = _namespace_name(filename)
        self.embedding_dim = embedding_dim
        self.cosine_threshold = cosine_threshold

    def _find_uid(self, key: str) -> str | None:
        query = """
        query q($kind: string, $key: string) {
          rows(func: eq(ragu_store_kind, $kind)) @filter(type(RaguEmbedding) AND eq(ragu_key, $key)) {
            uid
          }
        }
        """
        rows = self._query(query, {"$kind": self.namespace, "$key": key}).get("rows", [])
        return rows[0]["uid"] if rows else None

    def _all_rows(self) -> list[dict[str, Any]]:
        return list(self._iter_rows())

    def _iter_rows(self):
        offset = 0
        while True:
            query = f"""
            query q($kind: string) {{
              rows(func: eq(ragu_store_kind, $kind), first: {VECTOR_QUERY_PAGE_SIZE}, offset: {offset}) @filter(type(RaguEmbedding)) {{
                ragu_key
                ragu_vector_json
                ragu_metadata_json
              }}
            }}
            """
            rows = self._query(query, {"$kind": self.namespace}).get("rows", [])
            if not rows:
                break
            yield from rows
            if len(rows) < VECTOR_QUERY_PAGE_SIZE:
                break
            offset += VECTOR_QUERY_PAGE_SIZE

    def _all_rows_legacy(self) -> list[dict[str, Any]]:
        query = """
        query q($kind: string) {
          rows(func: eq(ragu_store_kind, $kind)) @filter(type(RaguEmbedding)) {
            ragu_key
            ragu_vector_json
            ragu_metadata_json
          }
        }
        """
        return self._query(query, {"$kind": self.namespace}).get("rows", [])

    async def query(self, vector: Embedding, top_k: int) -> list[EmbeddingHit]:
        query_vector = [float(value) for value in vector.vector]
        hits: list[EmbeddingHit] = []

        for row in self._iter_rows():
            stored_vector = _json_loads(row.get("ragu_vector_json"), [])
            if not isinstance(stored_vector, list):
                continue

            score = _cosine_similarity(query_vector, [float(value) for value in stored_vector])
            if score < self.cosine_threshold:
                continue

            metadata = _json_loads(row.get("ragu_metadata_json"), {})
            hits.append(
                EmbeddingHit(
                    id=str(row["ragu_key"]),
                    distance=score,
                    metadata=metadata if isinstance(metadata, dict) else {},
                )
            )

        hits.sort(key=lambda hit: hit.distance, reverse=True)
        return hits[:top_k]

    async def upsert(self, data: list[Embedding]) -> None:
        for embedding in data:
            if embedding.id is None:
                continue
            obj = {
                "dgraph.type": EMBEDDING_TYPE,
                "ragu_store_kind": self.namespace,
                "ragu_key": embedding.id,
                "ragu_vector_json": _json_dumps([float(value) for value in embedding.vector]),
                "ragu_metadata_json": _json_dumps(embedding.metadata),
            }
            uid = self._find_uid(embedding.id)
            if uid:
                obj["uid"] = uid
            self._mutate(set_obj=obj)

    async def delete(self, ids: list[str]) -> None:
        delete_lines = []
        for item_id in ids:
            uid = self._find_uid(item_id)
            if uid:
                delete_lines.append(f"<{uid}> * * .")
        if delete_lines:
            self._mutate(delete_nquads="\n".join(delete_lines))
