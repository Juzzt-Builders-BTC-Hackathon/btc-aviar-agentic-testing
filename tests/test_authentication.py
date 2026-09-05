import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from qa_agent import config, server
from qa_agent.models import RunRequest
from qa_agent.safety import redact
from qa_agent.store import Store


LOGIN = {"username": "fixture-user-unique", "password": "fixture-password-unique"}


def test_login_defaults_need_only_credentials():
    request = RunRequest(url="https://example.com/protected", authentication=LOGIN)
    assert request.authentication.login_path == ""
    assert request.authentication.username_selector == ""
    assert request.authentication.success_selector == ""


def test_login_errors_have_authentication_remedy():
    from qa_agent.authentication import LoginError
    from qa_agent.runtime import error_details
    detail = error_details(LoginError("Could not identify the username field"), "authentication")
    assert detail['code'] == 'AUTHENTICATION_FAILED'
    assert 'browser channel' not in detail['remedy']


def test_credentials_are_excluded_from_serialization_and_repr():
    request = RunRequest(url="https://example.com/", authentication=LOGIN)
    assert "authentication" not in request.model_dump()
    for secret in LOGIN.values():
        assert secret not in request.model_dump_json()
        assert secret not in repr(request)
    with pytest.raises(ValidationError):
        RunRequest(url="https://example.com/", authentication={**LOGIN, "login_path": "https://other.example/login"})


def test_api_keeps_credentials_ephemeral_and_redacts_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "store", Store(tmp_path))
    monkeypatch.setattr(server, "preflight", AsyncMock(return_value={"ready": True}))
    received = []
    async def pipeline(store, rid, authentication):
        received.append(authentication.password.get_secret_value())
        store.event(rid, "recon", redact(LOGIN["password"]))
        store.update(rid, status="completed")
    monkeypatch.setattr(server, "run_pipeline", pipeline)
    body = {"url": config.DEMO_ORIGIN + "/demo/", "mode": "baseline", "authentication": LOGIN, "scope": LOGIN["password"]}
    with TestClient(server.app) as client:
        client.get("/")
        response = client.post("/api/runs", json=body)
        assert response.status_code == 202
        rid = response.json()["id"]
        detail = client.get(f"/api/runs/{rid}")
        assert received == [LOGIN["password"]]
        for secret in LOGIN.values():
            assert secret not in response.text
            assert secret not in detail.text
            assert secret not in str(server.store.get(rid))
        invalid = client.post("/api/runs", json={**body, "authentication": {**LOGIN, "unexpected": LOGIN["password"]}})
        assert invalid.status_code == 422
        assert LOGIN["password"] not in invalid.text
