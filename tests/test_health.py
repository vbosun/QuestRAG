import pytest
from fastapi import HTTPException
from quest_rag.main import health_ready


def test_readiness_does_not_expose_connection_credentials(monkeypatch):
    import psycopg
    import redis

    def unavailable(*args, **kwargs):
        raise RuntimeError("postgresql://user:secret@host/db")

    monkeypatch.setattr(psycopg, "connect", unavailable)
    monkeypatch.setattr(redis.Redis, "from_url", unavailable)
    with pytest.raises(HTTPException) as error:
        health_ready()
    assert error.value.status_code == 503
    assert error.value.detail == {
        "status": "unavailable", "checks": {"postgresql": False, "redis": False},
    }
