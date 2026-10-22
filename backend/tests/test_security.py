import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app import config, security


def _request(headers=None, host="127.0.0.1"):
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/admin/run-pipeline",
        "headers": raw_headers,
        "client": (host, 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "query_string": b"",
    })


def test_admin_loopback_requires_marker(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    monkeypatch.setattr(config, "ADMIN_ALLOW_LOOPBACK", True)
    monkeypatch.setattr(config, "ADMIN_RATE_LIMIT_PER_MIN", 0)

    with pytest.raises(HTTPException) as exc:
        security.require_admin(_request())
    assert exc.value.status_code == 403

    security.require_admin(_request({"X-Requested-With": "mining-admin"}))


def test_admin_token_takes_precedence(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "s3cret")
    monkeypatch.setattr(config, "ADMIN_RATE_LIMIT_PER_MIN", 0)

    with pytest.raises(HTTPException) as exc:
        security.require_admin(_request({"X-Admin-Token": "wrong"}))
    assert exc.value.status_code == 401

    security.require_admin(_request({"X-Admin-Token": "s3cret"}, host="8.8.8.8"))


def test_admin_rejects_remote_without_token(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    monkeypatch.setattr(config, "ADMIN_ALLOW_LOOPBACK", True)
    monkeypatch.setattr(config, "ADMIN_RATE_LIMIT_PER_MIN", 0)

    with pytest.raises(HTTPException) as exc:
        security.require_admin(_request({"X-Requested-With": "mining-admin"}, host="8.8.8.8"))
    assert exc.value.status_code == 403
