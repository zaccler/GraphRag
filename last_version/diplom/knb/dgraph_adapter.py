from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List, Optional

import pydgraph

from ragu.graph.types import Entity, Relation
from ragu.storage.base_storage import BaseGraphStorage, EdgeSpec

ENTITY_TYPE = "RaguEntity"
RELATION_TYPE = "RaguRelation"
GRPC_MAX_MESSAGE_BYTES = 128 * 1024 * 1024
GRPC_OPTIONS = [
    ("grpc.max_receive_message_length", GRPC_MAX_MESSAGE_BYTES),
    ("grpc.max_send_message_length", GRPC_MAX_MESSAGE_BYTES),
]

DGRAPH_SCHEMA = """
ragu_id: string @index(exact) .
entity_name: string @index(exact, term) .
entity_type: string @index(exact, term) .
description: string .
source_chunk_id: string .
documents_id: string .
clusters: string .

subject_name: string @index(exact, term) .
object_name: string @index(exact, term) .
relation_type: string @index(exact, term) .
relation_strength: float .

ragu_from: uid @reverse .
ragu_to: uid @reverse .

type RaguEntity {
  ragu_id
  entity_name
  entity_type
  description
  source_chunk_id
  documents_id
  clusters
}

type RaguRelation {
  ragu_id
  subject_name
  object_name
  relation_type
  description
  relation_strength
  source_chunk_id
  ragu_from
  ragu_to
}
"""


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value: Any) -> list:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return []
    if isinstance(value, list):
        return value
    return []


def _uid_alias(prefix: str, raw: str) -> str:
    return f"_:{prefix}_{hashlib.md5(raw.encode('utf-8')).hexdigest()}"


def _entity_to_obj(entity: Entity, uid: Optional[str] = None) -> Dict[str, Any]:
    obj = {
        "dgraph.type": ENTITY_TYPE,
        "ragu_id": entity.id,
        "entity_name": entity.entity_name,
        "entity_type": entity.entity_type,
        "description": entity.description or "",
        "source_chunk_id": _json_dumps(list(entity.source_chunk_id)),
        "documents_id": _json_dumps(list(entity.documents_id)),
        "clusters": _json_dumps(entity.clusters),
    }
    obj["uid"] = uid or _uid_alias("ent", entity.id)
    return obj


def _entity_from_row(row: Dict[str, Any]) -> Entity:
    return Entity(
        id=str(row.get("ragu_id", "")),
        entity_name=row.get("entity_name", "") or "",
        entity_type=row.get("entity_type", "") or "",
        description=row.get("description", "") or "",
        source_chunk_id=_json_loads(row.get("source_chunk_id", "[]")),
        documents_id=_json_loads(row.get("documents_id", "[]")),
        clusters=_json_loads(row.get("clusters", "[]")),
    )


def _relation_to_obj(
    relation: Relation,
    subject_uid: str,
    object_uid: str,
    uid: Optional[str] = None,
) -> Dict[str, Any]:
    obj = {
        "dgraph.type": RELATION_TYPE,
        "ragu_id": relation.id,
        "subject_name": relation.subject_name,
        "object_name": relation.object_name,
        "relation_type": relation.relation_type,
        "description": relation.description or "",
        "relation_strength": float(relation.relation_strength),
        "source_chunk_id": _json_dumps(list(relation.source_chunk_id)),
        "ragu_from": {"uid": subject_uid},
        "ragu_to": {"uid": object_uid},
    }
    obj["uid"] = uid or _uid_alias("rel", relation.id)
    return obj


def _relation_from_row(row: Dict[str, Any]) -> Relation:
    subject = row.get("ragu_from", [])
    target = row.get("ragu_to", [])

    subject_id = ""
    object_id = ""
    subject_name = row.get("subject_name", "") or ""
    object_name = row.get("object_name", "") or ""

    if isinstance(subject, list) and subject:
        subject_id = str(subject[0].get("ragu_id", ""))
        subject_name = subject[0].get("entity_name", subject_name)

    if isinstance(target, list) and target:
        object_id = str(target[0].get("ragu_id", ""))
        object_name = target[0].get("entity_name", object_name)

    return Relation(
        id=str(row.get("ragu_id", "")),
        subject_id=subject_id,
        object_id=object_id,
        subject_name=subject_name,
        object_name=object_name,
        relation_type=row.get("relation_type", "") or "",
        description=row.get("description", "") or "",
        relation_strength=float(row.get("relation_strength", 1.0)),
        source_chunk_id=_json_loads(row.get("source_chunk_id", "[]")),
    )


class DgraphStorage(BaseGraphStorage):
    def __init__(
        self,
        address: str = "localhost:9080",
        drop_on_start: bool = False,
        **kwargs: Any,
    ):
        self._address = str(kwargs.get("address", address))
        self._drop_on_start = bool(kwargs.get("drop_on_start", drop_on_start))
        self._stub = pydgraph.DgraphClientStub(self._address, options=GRPC_OPTIONS)
        self._client = pydgraph.DgraphClient(self._stub)
        self._schema_ready = False
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        if self._drop_on_start:
            self._client.alter(pydgraph.Operation(drop_all=True))
            self._drop_on_start = False
        self._client.alter(pydgraph.Operation(schema=DGRAPH_SCHEMA))
        self._schema_ready = True

    async def index_start_callback(self) -> None:
        self._ensure_schema()

    async def index_done_callback(self) -> None:
        return None

    async def query_done_callback(self) -> None:
        return None

    def close(self) -> None:
        self._stub.close()

    def _query(self, query: str, variables: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        self._ensure_schema()
        txn = self._client.txn(read_only=True)
        try:
            res = txn.query(query, variables=variables or {})
            return json.loads(res.json)
        except Exception as e:
            if "not indexed" in str(e).lower():
                self._schema_ready = False
                self._ensure_schema()
                res = txn.query(query, variables=variables or {})
                return json.loads(res.json)
            raise
        finally:
            txn.discard()

    def _mutate(self, set_obj: Optional[Any] = None, delete_nquads: Optional[str] = None) -> None:
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

    def _find_entity_uid(self, entity_id: str) -> Optional[str]:
        q = """
        query q($id: string) {
          nodes(func: eq(ragu_id, $id)) @filter(type(RaguEntity)) {
            uid
          }
        }
        """
        data = self._query(q, {"$id": entity_id})
        rows = data.get("nodes", [])
        if not rows:
            return None
        return rows[0]["uid"]

    def _find_relation_uid_by_id(self, relation_id: str) -> Optional[str]:
        q = """
        query q($id: string) {
          rels(func: eq(ragu_id, $id)) @filter(type(RaguRelation)) {
            uid
          }
        }
        """
        data = self._query(q, {"$id": relation_id})
        rows = data.get("rels", [])
        if not rows:
            return None
        return rows[0]["uid"]

    def _ensure_placeholder_node(self, node_id: str, node_name: str = "") -> str:
        uid = self._find_entity_uid(node_id)
        if uid:
            return uid

        placeholder = Entity(
            id=node_id,
            entity_name=node_name or node_id,
            entity_type="UNKNOWN",
            description="",
            source_chunk_id=[],
            documents_id=[],
            clusters=[],
        )
        self._mutate(set_obj=_entity_to_obj(placeholder))
        uid = self._find_entity_uid(node_id)
        if uid is None:
            raise RuntimeError(f"Failed to create node {node_id}")
        return uid

    def _get_node_degree(self, node_id: str) -> int:
        q = """
        query q($id: string) {
          nodes(func: eq(ragu_id, $id)) @filter(type(RaguEntity)) {
            a: count(~ragu_from)
            b: count(~ragu_to)
          }
        }
        """
        data = self._query(q, {"$id": node_id})
        rows = data.get("nodes", [])
        if not rows:
            return 0
        row = rows[0]
        return int(row.get("a", 0)) + int(row.get("b", 0))

    def _get_relation_uid_by_spec(
        self,
        subject_id: str,
        object_id: str,
        relation_id: Optional[str],
    ) -> Optional[str]:
        if relation_id:
            return self._find_relation_uid_by_id(relation_id)

        q = """
        query q($sid: string, $oid: string) {
          src(func: eq(ragu_id, $sid)) @filter(type(RaguEntity)) {
            rels: ~ragu_from @filter(type(RaguRelation)) {
              uid
              ragu_to @filter(eq(ragu_id, $oid)) {
                uid
              }
            }
          }
        }
        """
        data = self._query(q, {"$sid": subject_id, "$oid": object_id})
        src = data.get("src", [])
        if not src:
            return None
        for rel in src[0].get("rels", []):
            if rel.get("ragu_to"):
                return rel["uid"]
        return None

    async def edges_degrees(self, edge_specs: List[EdgeSpec]) -> List[int]:
        result: List[int] = []
        for subject_id, object_id, _ in edge_specs:
            result.append(self._get_node_degree(subject_id) + self._get_node_degree(object_id))
        return result

    async def get_nodes(self, node_ids: List[str]) -> List[Optional[Entity]]:
        result: List[Optional[Entity]] = []
        q = """
        query q($id: string) {
          nodes(func: eq(ragu_id, $id)) @filter(type(RaguEntity)) {
            ragu_id
            entity_name
            entity_type
            description
            source_chunk_id
            documents_id
            clusters
          }
        }
        """
        for node_id in node_ids:
            data = self._query(q, {"$id": node_id})
            rows = data.get("nodes", [])
            result.append(_entity_from_row(rows[0]) if rows else None)
        return result

    async def upsert_nodes(self, nodes: Iterable[Entity]) -> None:
        for node in nodes:
            uid = self._find_entity_uid(node.id)
            self._mutate(set_obj=_entity_to_obj(node, uid=uid))

    async def delete_nodes(self, node_ids: List[str]) -> None:
        for node_id in node_ids:
            q = """
            query q($id: string) {
              nodes(func: eq(ragu_id, $id)) @filter(type(RaguEntity)) {
                uid
                out_rels: ~ragu_from { uid }
                in_rels: ~ragu_to { uid }
              }
            }
            """
            data = self._query(q, {"$id": node_id})
            rows = data.get("nodes", [])
            if not rows:
                continue

            node_uid = rows[0]["uid"]
            relation_uids = set()

            for rel in rows[0].get("out_rels", []):
                relation_uids.add(rel["uid"])

            for rel in rows[0].get("in_rels", []):
                relation_uids.add(rel["uid"])

            delete_lines = [f"<{uid}> * * ." for uid in relation_uids]
            delete_lines.append(f"<{node_uid}> * * .")
            self._mutate(delete_nquads="\n".join(delete_lines))

    async def get_edges(self, edge_specs: List[EdgeSpec]) -> List[Optional[Relation]]:
        result: List[Optional[Relation]] = []

        q_by_id = """
        query q($id: string) {
          rels(func: eq(ragu_id, $id)) @filter(type(RaguRelation)) {
            ragu_id
            subject_name
            object_name
            relation_type
            description
            relation_strength
            source_chunk_id
            ragu_from {
              ragu_id
              entity_name
            }
            ragu_to {
              ragu_id
              entity_name
            }
          }
        }
        """

        q_by_spec = """
        query q($sid: string, $oid: string) {
          src(func: eq(ragu_id, $sid)) @filter(type(RaguEntity)) {
            rels: ~ragu_from @filter(type(RaguRelation)) {
              ragu_id
              subject_name
              object_name
              relation_type
              description
              relation_strength
              source_chunk_id
              ragu_from {
                ragu_id
                entity_name
              }
              ragu_to @filter(eq(ragu_id, $oid)) {
                ragu_id
                entity_name
              }
            }
          }
        }
        """

        for subject_id, object_id, relation_id in edge_specs:
            if relation_id:
                data = self._query(q_by_id, {"$id": relation_id})
                rows = data.get("rels", [])
                result.append(_relation_from_row(rows[0]) if rows else None)
                continue

            data = self._query(q_by_spec, {"$sid": subject_id, "$oid": object_id})
            src = data.get("src", [])
            if not src:
                result.append(None)
                continue

            found = None
            for rel in src[0].get("rels", []):
                if rel.get("ragu_to"):
                    found = rel
                    break

            result.append(_relation_from_row(found) if found else None)

        return result

    async def upsert_edges(self, edges: List[Relation]) -> None:
        for edge in edges:
            subject_uid = self._ensure_placeholder_node(edge.subject_id, edge.subject_name)
            object_uid = self._ensure_placeholder_node(edge.object_id, edge.object_name)
            rel_uid = self._find_relation_uid_by_id(edge.id)
            self._mutate(
                set_obj=_relation_to_obj(
                    relation=edge,
                    subject_uid=subject_uid,
                    object_uid=object_uid,
                    uid=rel_uid,
                )
            )

    async def delete_edges(self, edge_specs: List[EdgeSpec]) -> None:
        for subject_id, object_id, relation_id in edge_specs:
            rel_uid = self._get_relation_uid_by_spec(subject_id, object_id, relation_id)
            if rel_uid:
                self._mutate(delete_nquads=f"<{rel_uid}> * * .")

    async def get_all_edges_for_nodes(self, node_ids: List[str]) -> List[List[Relation]]:
        result: List[List[Relation]] = []

        q = """
        query q($id: string) {
          nodes(func: eq(ragu_id, $id)) @filter(type(RaguEntity)) {
            out_rels: ~ragu_from @filter(type(RaguRelation)) {
              ragu_id
              subject_name
              object_name
              relation_type
              description
              relation_strength
              source_chunk_id
              ragu_from {
                ragu_id
                entity_name
              }
              ragu_to {
                ragu_id
                entity_name
              }
            }
            in_rels: ~ragu_to @filter(type(RaguRelation)) {
              ragu_id
              subject_name
              object_name
              relation_type
              description
              relation_strength
              source_chunk_id
              ragu_from {
                ragu_id
                entity_name
              }
              ragu_to {
                ragu_id
                entity_name
              }
            }
          }
        }
        """

        for node_id in node_ids:
            data = self._query(q, {"$id": node_id})
            rows = data.get("nodes", [])
            if not rows:
                result.append([])
                continue

            merged: Dict[str, Relation] = {}

            for rel in rows[0].get("out_rels", []):
                relation = _relation_from_row(rel)
                merged[relation.id] = relation

            for rel in rows[0].get("in_rels", []):
                relation = _relation_from_row(rel)
                merged[relation.id] = relation

            result.append(list(merged.values()))

        return result

    async def get_all_nodes(self) -> List[Entity]:
        q = """
        {
          nodes(func: type(RaguEntity)) {
            ragu_id
            entity_name
            entity_type
            description
            source_chunk_id
            documents_id
            clusters
          }
        }
        """
        data = self._query(q)
        return [_entity_from_row(row) for row in data.get("nodes", [])]

    async def get_all_edges(self) -> List[Relation]:
        q = """
        {
          rels(func: type(RaguRelation)) {
            ragu_id
            subject_name
            object_name
            relation_type
            description
            relation_strength
            source_chunk_id
            ragu_from {
              ragu_id
              entity_name
            }
            ragu_to {
              ragu_id
              entity_name
            }
          }
        }
        """
        data = self._query(q)
        return [_relation_from_row(row) for row in data.get("rels", [])]
