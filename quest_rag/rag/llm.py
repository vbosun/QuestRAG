from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from quest_rag.core.config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL

llm = ChatOpenAI(
    base_url=OPENAI_BASE_URL,
    api_key=SecretStr(OPENAI_API_KEY),
    model=OPENAI_MODEL,
    temperature=0.5,
    max_completion_tokens=25000,
)
