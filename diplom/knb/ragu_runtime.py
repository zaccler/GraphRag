import asyncio
import base64
import json
import shutil
import uuid
from pathlib import Path

from openai import AsyncOpenAI

from api.config import (
    BASE_URL,
    CHUNK_MAX_SIZE,
    DGRAPH_ADDRESS,
    EMBEDDER_DIM,
    EMBEDDER_MODEL_NAME,
    EMBEDDING_API_KEY,
    EMBEDDING_BASE_URL,
    EMBEDDING_CONNECT_TIMEOUT_SEC,
    EMBEDDING_RATE_MAX_PER_MINUTE,
    EMBEDDING_RATE_MAX_SIMULTANEOUS,
    EMBEDDING_RETRY_TIMES_SEC,
    EMBEDDING_TIMEOUT_SEC,
    LLM_API_KEY,
    LLM_CONNECT_TIMEOUT_SEC,
    LLM_MODEL_NAME,
    LLM_RATE_MAX_PER_MINUTE,
    LLM_RATE_MAX_SIMULTANEOUS,
    LLM_RETRY_TIMES_SEC,
    LLM_TIMEOUT_SEC,
    STORAGE_DIR,
    TOKENIZER_MODEL,
    build_timeout,
)
from knb.dgraph_adapter import DgraphStorage
from knb.dgraph_unified_storage import DgraphKVStorage, DgraphVectorStorage
from ragu import (
    ArtifactsExtractorLLM,
    BuilderArguments,
    KnowledgeGraph,
    LocalSearchEngine,
    Settings,
    SimpleChunker,
)
from ragu.common.global_parameters import DEFAULT_FILENAMES
from ragu.graph.index import StorageArguments
from ragu.models.embedder import EmbedderOpenAI
from ragu.models.llm import LLMOpenAI
from ragu.models.openai import CachedAsyncOpenAI
from ragu.storage.types import Embedding
from ragu.utils.ragu_utils import read_text_from_files


def build_llm_client():
    client = AsyncOpenAI(
        base_url=BASE_URL,
        api_key=LLM_API_KEY,
        timeout=build_timeout(LLM_TIMEOUT_SEC, LLM_CONNECT_TIMEOUT_SEC),
        max_retries=0,
    )
    return CachedAsyncOpenAI(
        client=client,
        rate_max_per_minute=LLM_RATE_MAX_PER_MINUTE,
        rate_max_simultaneous=LLM_RATE_MAX_SIMULTANEOUS,
        retry_times_sec=LLM_RETRY_TIMES_SEC,
        cache=str(STORAGE_DIR.parent / "llm_cache"),
    )


def build_embedding_client():
    client = AsyncOpenAI(
        base_url=EMBEDDING_BASE_URL,
        api_key=EMBEDDING_API_KEY,
        timeout=build_timeout(EMBEDDING_TIMEOUT_SEC, EMBEDDING_CONNECT_TIMEOUT_SEC),
        max_retries=0,
    )
    return CachedAsyncOpenAI(
        client=client,
        rate_max_per_minute=EMBEDDING_RATE_MAX_PER_MINUTE,
        rate_max_simultaneous=EMBEDDING_RATE_MAX_SIMULTANEOUS,
        retry_times_sec=EMBEDDING_RETRY_TIMES_SEC,
        cache=str(STORAGE_DIR.parent / "embed_cache"),
    )


def build_storage_settings():
    return StorageArguments(
        graph_backend_storage=DgraphStorage,
        kv_storage_type=DgraphKVStorage,
        vdb_storage_type=DgraphVectorStorage,
        chunks_kv_storage_kwargs={"address": DGRAPH_ADDRESS},
        summary_kv_storage_kwargs={"address": DGRAPH_ADDRESS},
        communities_kv_storage_kwargs={"address": DGRAPH_ADDRESS},
        vdb_storage_kwargs={"address": DGRAPH_ADDRESS},
        graph_storage_kwargs={
            "address": DGRAPH_ADDRESS,
            "drop_on_start": False,
        },
    )


def build_graph_components(storage_dir=None):
    storage_dir = Path(storage_dir or STORAGE_DIR)
    Settings.storage_folder = str(storage_dir)
    Settings.language = "russian"

    llm = LLMOpenAI(
        client=build_llm_client(),
        model_name=LLM_MODEL_NAME,
        temperature=0,
    )
    embedder = EmbedderOpenAI(
        client=build_embedding_client(),
        model_name=EMBEDDER_MODEL_NAME,
        dim=EMBEDDER_DIM,
    )
    artifact_extractor = ArtifactsExtractorLLM(llm=llm, do_validation=False)

    knowledge_graph = KnowledgeGraph(
        llm=llm,
        embedder=embedder,
        chunker=SimpleChunker(max_chunk_size=CHUNK_MAX_SIZE),
        artifact_extractor=artifact_extractor,
        builder_settings=BuilderArguments(use_llm_summarization=True, vectorize_chunks=True),
        storage_settings=build_storage_settings(),
    )
    search_engine = LocalSearchEngine(
        llm=llm,
        knowledge_graph=knowledge_graph,
        embedder=embedder,
        tokenizer_model=TOKENIZER_MODEL,
        language="russian",
    )
    return llm, embedder, knowledge_graph, search_engine


def reset_storage(storage_dir):
    if storage_dir.exists():
        shutil.rmtree(storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)


def list_text_files(folder_path):
    exts = {".txt", ".md", ".rst", ".json"}
    return [path for path in folder_path.rglob("*") if path.is_file() and path.suffix.lower() in exts]


def has_persisted_index():
    graph_storage = None
    chunk_storage = None
    try:
        graph_storage = DgraphStorage(address=DGRAPH_ADDRESS, drop_on_start=False)
        chunk_storage = DgraphKVStorage(
            address=DGRAPH_ADDRESS,
            filename=DEFAULT_FILENAMES["chunks_kv_storage_name"],
        )
        graph_data = graph_storage._query("{ nodes(func: type(RaguEntity), first: 1) { uid } }")
        chunk_data = chunk_storage._query(
            """
            query q($kind: string) {
              rows(func: eq(ragu_store_kind, $kind), first: 1) @filter(type(RaguKV)) {
                uid
              }
            }
            """,
            {"$kind": DEFAULT_FILENAMES["chunks_kv_storage_name"]},
        )
        return bool(graph_data.get("nodes") or chunk_data.get("rows"))
    except Exception:
        return False
    finally:
        if graph_storage is not None:
            graph_storage.close()
        if chunk_storage is not None:
            chunk_storage.close()


def _load_json_file(path):
    if not path.exists() or path.stat().st_size == 0:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _decode_nano_matrix(payload):
    embedding_dim = int(payload.get("embedding_dim") or EMBEDDER_DIM)
    matrix_raw = payload.get("matrix")
    if not matrix_raw:
        return []

    import numpy as np

    matrix = np.frombuffer(base64.b64decode(matrix_raw), dtype=np.float32)
    if matrix.size == 0:
        return []
    return matrix.reshape(-1, embedding_dim).astype(float).tolist()


async def migrate_local_runtime_storage_to_dgraph():
    kv_files = (
        DEFAULT_FILENAMES["chunks_kv_storage_name"],
        DEFAULT_FILENAMES["community_kv_storage_name"],
        DEFAULT_FILENAMES["community_summary_kv_storage_name"],
    )
    for file_name in kv_files:
        data = _load_json_file(STORAGE_DIR / file_name)
        if not isinstance(data, dict) or not data:
            continue

        storage = DgraphKVStorage(address=DGRAPH_ADDRESS, filename=file_name)
        try:
            await storage.upsert(data)
        finally:
            storage.close()

    vdb_files = (
        DEFAULT_FILENAMES["entity_vdb_name"],
        DEFAULT_FILENAMES["relation_vdb_name"],
        DEFAULT_FILENAMES["chunk_vdb_name"],
    )
    for file_name in vdb_files:
        payload = _load_json_file(STORAGE_DIR / file_name)
        if not isinstance(payload, dict):
            continue

        rows = payload.get("data") or []
        vectors = _decode_nano_matrix(payload)
        if not rows or not vectors:
            continue

        storage = DgraphVectorStorage(
            address=DGRAPH_ADDRESS,
            filename=file_name,
            embedding_dim=int(payload.get("embedding_dim") or EMBEDDER_DIM),
        )
        try:
            embeddings = []
            for row, vector in zip(rows, vectors):
                item_id = row.get("__id__")
                if not item_id:
                    continue
                metadata = {
                    key: value
                    for key, value in row.items()
                    if key not in {"__id__", "__metrics__", "__vector__"}
                }
                embeddings.append(Embedding(id=str(item_id), vector=vector, metadata=metadata))
            await storage.upsert(embeddings)
        finally:
            storage.close()


async def build_storage_from_folder(folder_path, storage_dir):
    docs = read_text_from_files(str(folder_path))
    if not docs:
        raise ValueError("В указанной папке не найдено документов")

    reset_storage(storage_dir)

    _, _, knowledge_graph, _ = build_graph_components(storage_dir)
    await knowledge_graph.build_from_docs(docs)


def _temp_storage_dir(label):
    path = STORAGE_DIR.parent / f"{STORAGE_DIR.name}.{label}.{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cleanup_storage_dir(storage_dir):
    if storage_dir is not None and storage_dir.exists():
        shutil.rmtree(storage_dir)


def _promote_staged_storage(staged_storage_dir):
    backup_storage_dir = None
    if STORAGE_DIR.exists():
        backup_storage_dir = _temp_storage_dir("backup")
        _cleanup_storage_dir(backup_storage_dir)
        STORAGE_DIR.rename(backup_storage_dir)
    staged_storage_dir.rename(STORAGE_DIR)
    return backup_storage_dir


def _rollback_promoted_storage(backup_storage_dir):
    _cleanup_storage_dir(STORAGE_DIR)
    if backup_storage_dir is not None and backup_storage_dir.exists():
        backup_storage_dir.rename(STORAGE_DIR)


def rebuild_transactionally(folder_path):
    staged_storage_dir = _temp_storage_dir("staging")
    backup_storage_dir = None

    try:
        asyncio.run(build_storage_from_folder(folder_path, staged_storage_dir))
        backup_storage_dir = _promote_staged_storage(staged_storage_dir)
        components = build_graph_components(STORAGE_DIR)
        _cleanup_storage_dir(backup_storage_dir)
        return components
    except Exception:
        if backup_storage_dir is not None:
            _rollback_promoted_storage(backup_storage_dir)
        else:
            _cleanup_storage_dir(staged_storage_dir)
        raise
