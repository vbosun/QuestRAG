import pytest

from quest_rag.rag.errors import model_error_message


class ProviderError(Exception):
    def __init__(self, status, body):
        self.status_code = status
        self.body = body


@pytest.mark.parametrize("status,body,expected", [
    (402, {"error": {"message": "Insufficient Balance"}}, "余额或额度不足"),
    (429, {"code": "insufficient_quota"}, "余额或额度不足"),
    (429, {"code": "rate_limit_exceeded"}, "请求过于频繁"),
    (401, {}, "认证失败"),
    (403, {}, "无权访问"),
    (422, {}, "接口参数"),
    (503, {}, "暂时不可用"),
])
def test_provider_failure_classification(status, body, expected):
    assert expected in model_error_message(ProviderError(status, body))


def test_provider_payload_and_unknown_error_are_not_exposed():
    exc = ProviderError(400, {"message": "credential=private-token"})
    assert "private-token" not in model_error_message(exc)
    assert "private-token" not in model_error_message(RuntimeError("private-token"))
