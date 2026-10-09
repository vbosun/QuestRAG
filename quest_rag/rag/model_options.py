def non_thinking_options(model: str) -> dict:
    """Disable DeepSeek thinking through the Chat Completions request body."""
    if model.lower().rsplit("/", 1)[-1].startswith("deepseek"):
        return {"extra_body": {"thinking": {"type": "disabled"}}}
    return {}
