from __future__ import annotations

import os

import pydgraph


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

DGRAPH_UNIFIED_SCHEMA = """
ragu_store_kind: string @index(exact) .
ragu_key: string @index(exact) .
ragu_value_json: string .
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


def main() -> None:
    address = os.getenv("DGRAPH_ADDRESS", "localhost:9080")
    stub = pydgraph.DgraphClientStub(address)
    client = pydgraph.DgraphClient(stub)
    try:
        client.alter(pydgraph.Operation(drop_all=True))
        client.alter(pydgraph.Operation(schema=DGRAPH_SCHEMA))
        client.alter(pydgraph.Operation(schema=DGRAPH_UNIFIED_SCHEMA))
        print(f"Dgraph reset complete: {address}")
    finally:
        stub.close()


if __name__ == "__main__":
    main()
