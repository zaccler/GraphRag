import os
from pathlib import Path

import httpx
from dotenv import load_dotenv


load_dotenv()


def _retry_schedule(env_name, default):
    raw_value = os.getenv(env_name, "").strip()
    if not raw_value:
        return tuple(default)

    values = tuple(float(chunk.strip()) for chunk in raw_value.split(",") if chunk.strip())
    if not values:
        raise ValueError(f"{env_name} must contain at least one retry delay")
    return values


def build_timeout(total_sec, connect_sec):
    return httpx.Timeout(timeout=total_sec, connect=connect_sec)


LLM_API_KEY = os.getenv("OPENAI_API_KEY", "")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", LLM_API_KEY)

BASE_URL = os.getenv("BASE_URL", "https://api.mistral.ai/v1")
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://api.mistral.ai/v1")

LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "mistral-small-latest")
EMBEDDER_MODEL_NAME = os.getenv("EMBEDDER_MODEL_NAME", "mistral-embed")
TOKENIZER_MODEL = os.getenv("TOKENIZER_MODEL", "gpt-4o-mini")

RAW_LIT_DIR = Path(os.getenv("RAW_LIT_DIR", "raw/lit"))
GENERATED_DIR = Path(os.getenv("GENERATED_DIR", "raw/generated"))
DOCS_REGISTRY_PATH = Path(os.getenv("DOCS_REGISTRY_PATH", "xdt/rpo/docs_registry.json"))
PACKAGE_REGISTRY_PATH = Path(os.getenv("PACKAGE_REGISTRY_PATH", "xdt/rpo/packages.txt"))
REGISTRY_PATH = Path(os.getenv("REGISTRY_PATH", str(DOCS_REGISTRY_PATH)))
DOCS_RAW_DIR = Path(os.getenv("DOCS_RAW_DIR", str(RAW_LIT_DIR / "docs")))
PACKAGE_RAW_DIR = Path(os.getenv("PACKAGE_RAW_DIR", str(RAW_LIT_DIR / "packages")))
DHB_DIR = Path(os.getenv("DHB_DIR", "dhb/data"))
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "storage/ragu_graph"))

EMBEDDER_DIM = int(os.getenv("EMBEDDER_DIM", "1024"))
DGRAPH_ADDRESS = os.getenv("DGRAPH_ADDRESS", "localhost:9080")

PYTHON_DOCS_ROOT = os.getenv("PYTHON_DOCS_ROOT", "https://docs.python.org/3.12/")
CRAWL_MAX_PAGES = int(os.getenv("CRAWL_MAX_PAGES", "300"))
CRAWL_DELAY_SEC = float(os.getenv("CRAWL_DELAY_SEC", "0.15"))

DEFAULT_LLM_RETRY_TIMES_SEC = (10.0, 30.0, 60.0, 120.0, 300.0, 600.0, 900.0, 1200.0)
DEFAULT_EMBEDDING_RETRY_TIMES_SEC = (5.0, 15.0, 30.0, 60.0, 120.0, 300.0)

LLM_RETRY_TIMES_SEC = _retry_schedule("LLM_RETRY_TIMES_SEC", DEFAULT_LLM_RETRY_TIMES_SEC)
EMBEDDING_RETRY_TIMES_SEC = _retry_schedule(
    "EMBEDDING_RETRY_TIMES_SEC",
    DEFAULT_EMBEDDING_RETRY_TIMES_SEC,
)

LLM_TIMEOUT_SEC = float(os.getenv("LLM_TIMEOUT_SEC", "120"))
EMBEDDING_TIMEOUT_SEC = float(os.getenv("EMBEDDING_TIMEOUT_SEC", "120"))
LLM_CONNECT_TIMEOUT_SEC = float(os.getenv("LLM_CONNECT_TIMEOUT_SEC", "15"))
EMBEDDING_CONNECT_TIMEOUT_SEC = float(os.getenv("EMBEDDING_CONNECT_TIMEOUT_SEC", "15"))
LLM_RATE_MAX_PER_MINUTE = int(os.getenv("LLM_RATE_MAX_PER_MINUTE", "10"))
EMBEDDING_RATE_MAX_PER_MINUTE = int(os.getenv("EMBEDDING_RATE_MAX_PER_MINUTE", "20"))
LLM_RATE_MAX_SIMULTANEOUS = int(os.getenv("LLM_RATE_MAX_SIMULTANEOUS", "1"))
EMBEDDING_RATE_MAX_SIMULTANEOUS = int(os.getenv("EMBEDDING_RATE_MAX_SIMULTANEOUS", "1"))
CHUNK_MAX_SIZE = int(os.getenv("CHUNK_MAX_SIZE", "4000"))
ASK_TIMEOUT_SEC = float(os.getenv("ASK_TIMEOUT_SEC", "90"))
SEARCH_TOP_K = int(os.getenv("SEARCH_TOP_K", "8"))
FAST_CONTEXT_LIMIT = int(os.getenv("FAST_CONTEXT_LIMIT", "6"))
FAST_CONTEXT_CHAR_LIMIT = int(os.getenv("FAST_CONTEXT_CHAR_LIMIT", "12000"))
