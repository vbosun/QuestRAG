import httpx
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from quest_rag.core.config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL


def make_llm(
    *,
    model: str | None = None,
    temperature: float = 0.5,
    top_p: float | None = None,
    max_tokens: int = 25000,
):
    kwargs = {
        "base_url": OPENAI_BASE_URL,
        "api_key": SecretStr(OPENAI_API_KEY),
        "model": model or OPENAI_MODEL,
        "temperature": temperature,
        "max_completion_tokens": max_tokens,
        "http_client": httpx.Client(trust_env=False),
    }
    if top_p is not None:
        kwargs["top_p"] = top_p
    return ChatOpenAI(**kwargs)


llm = make_llm()
