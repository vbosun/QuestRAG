"""Safe, actionable messages for model failures without leaking provider payloads."""


def model_error_message(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    error = body.get("error", body) if isinstance(body, dict) else {}
    code = str(error.get("code", "")) if isinstance(error, dict) else ""
    message = str(error.get("message", "")) if isinstance(error, dict) else ""
    if status == 402 or code == "insufficient_quota" or "insufficient balance" in message.lower():
        return "模型服务余额或额度不足，请管理员检查服务商账户余额与用量限制后重试。"
    if status == 401:
        return "模型服务认证失败，请管理员检查模型凭证配置。"
    if status == 403:
        return "当前账号无权访问该模型，请管理员检查服务商授权。"
    if status == 429:
        return "模型服务请求过于频繁，请稍后重试。"
    if status in (400, 404, 422):
        return "模型服务不接受当前请求，请管理员检查模型名称及接口参数。"
    if status and status >= 500:
        return "模型服务暂时不可用，请稍后重试。"
    return "智能助手暂时未能完成请求，请稍后重试；持续失败请联系管理员检查模型服务及业务依赖。"
