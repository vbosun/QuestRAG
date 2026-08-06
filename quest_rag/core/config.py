import os

from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "ollama" )
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1/")
EMBEDDING_BASE_URL = os.environ.get("EMBEDDING_BASE_URL", "http://localhost:11434/v1/")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "deepseek-r1")
OPENAI_EMBEDDING_MODEL = os.environ.get("OPENAI_EMBEDDING_MODEL", "bge-m3")
VECTOR_BACKEND = os.environ.get("VECTOR_BACKEND", "milvus").lower()
MILVUS_HOST = os.environ.get("MILVUS_HOST", "localhost")
MILVUS_PORT = os.environ.get("MILVUS_PORT", "19530")
MILVUS_COLLECTION_NAME = os.environ.get("MILVUS_COLLECTION_NAME", "questrag_chunks")
MILVUS_USER = os.environ.get("MILVUS_USER", "")
MILVUS_PASSWORD = os.environ.get("MILVUS_PASSWORD", "")
ELASTICSEARCH_URL = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
ELASTICSEARCH_INDEX = os.environ.get("ELASTICSEARCH_INDEX", "questrag_chunks")
ELASTICSEARCH_JOBS_INDEX = os.environ.get("ELASTICSEARCH_JOBS_INDEX", "questrag_jobs")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Auth
REDIS_URL = os.environ.get("REDIS_URL", "")
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
AUTH_ACCESS_TOKEN_MINUTES = int(os.environ.get("AUTH_ACCESS_TOKEN_MINUTES", "30"))
AUTH_REFRESH_TOKEN_HOURS = int(os.environ.get("AUTH_REFRESH_TOKEN_HOURS", "8"))
AUTH_LOGIN_FAIL_LIMIT = int(os.environ.get("AUTH_LOGIN_FAIL_LIMIT", "5"))
AUTH_LOGIN_LOCK_MINUTES = int(os.environ.get("AUTH_LOGIN_LOCK_MINUTES", "15"))
AUTH_ID_NUMBER_PEPPER = os.environ.get("AUTH_ID_NUMBER_PEPPER", "")
SM2_PRIVATE_KEY = os.environ.get("SM2_PRIVATE_KEY", "")

DEFAULT_RETRIEVAL_CONFIG = {
    "top_k": 5,
    "recall_k": 15,
    "mode": "hybrid",
    "rrf_k": 60,
}

DEFAULT_GENERATION_CONFIG = {
    "temperature": 0.3,
    "top_p": 0.9,
}

_config_cache: dict = {}


def load_system_config():
    """Startup hook: load all system config from DB into memory."""
    global _config_cache
    try:
        from quest_rag.rag.pg_store import list_system_configs

        _config_cache = {item["key"]: item for item in list_system_configs()}
    except Exception:
        _config_cache = {}


def get_retrieval_config() -> dict:
    """Return retrieval config dict with defaults for missing keys."""
    entry = _config_cache.get("retrieval")
    value = entry["value"] if entry else None
    if isinstance(value, dict):
        return {**DEFAULT_RETRIEVAL_CONFIG, **value}
    return dict(DEFAULT_RETRIEVAL_CONFIG)


def get_generation_config() -> dict:
    """Return generation config dict with defaults for missing keys."""
    entry = _config_cache.get("generation")
    value = entry["value"] if entry else None
    if isinstance(value, dict):
        return {**DEFAULT_GENERATION_CONFIG, **value}
    return dict(DEFAULT_GENERATION_CONFIG)


def set_config_cache(key: str, value):
    """Update in-memory cache for a single config key."""
    _config_cache[key] = {"key": key, "value": value}
