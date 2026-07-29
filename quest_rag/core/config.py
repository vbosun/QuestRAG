import os

from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "ollama" )
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1/")
EMBEDDING_BASE_URL = os.environ.get("EMBEDDING_BASE_URL", "http://localhost:11434/v1/")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "deepseek-r1")
OPENAI_EMBEDDING_MODEL = os.environ.get("OPENAI_EMBEDDING_MODEL", "bge-m3")
VECTOR_BACKEND = os.environ.get("VECTOR_BACKEND", "memory").lower()
ELASTICSEARCH_URL = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
ELASTICSEARCH_INDEX = os.environ.get("ELASTICSEARCH_INDEX", "questrag_chunks")
ELASTICSEARCH_JOBS_INDEX = os.environ.get("ELASTICSEARCH_JOBS_INDEX", "questrag_jobs")
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:difyai123456@192.168.1.43:5432/quest_rag",
)
