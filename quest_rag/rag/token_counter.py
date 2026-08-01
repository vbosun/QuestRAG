from quest_rag.core.config import OPENAI_MODEL

_tokenizer = None

_MODEL_MAP = {
    "deepseek-v4-flash": "deepseek-ai/DeepSeek-V3",
    "deepseek-v3": "deepseek-ai/DeepSeek-V3",
    "deepseek-r1": "deepseek-ai/DeepSeek-V3",
    "deepseek-chat": "deepseek-ai/DeepSeek-V3",
}


def _load_tokenizer():
    global _tokenizer
    if _tokenizer is not None:
        return _tokenizer
    from transformers import AutoTokenizer

    model_id = _MODEL_MAP.get(OPENAI_MODEL, "deepseek-ai/DeepSeek-V3")
    _tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    return _tokenizer


def count_tokens(text: str) -> int:
    tok = _load_tokenizer()
    return len(tok.encode(text))
