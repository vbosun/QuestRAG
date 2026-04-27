import os

from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "ollama" )
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1/")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "deepseek-r1")
OPENAI_EMBEDDING_MODEL = os.environ.get("OPENAI_EMBEDDING_MODEL", "bge-m3")
