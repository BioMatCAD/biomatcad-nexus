"""Testes de `AllowlistedHttpsClient` (Incremento 2.3, Rodada 2 -- Fases E/J).

Nenhum destes testes toca a rede -- `httpx.Client` é substituído (monkeypatch) por um fake que
nunca abre um socket real, permitindo exercitar cada política de segurança/robustez descrita na
docstring do módulo (allowlist de host, rejeição de redirecionamento, limite de tamanho de
resposta, retry/backoff, rate limit, respeito a Retry-After) de forma determinística."""
from __future__ import annotations

from typing import ClassVar

import httpx
import pytest

from biomatcad_api.services.connectors import http_client as http_client_module
from biomatcad_api.services.connectors.http_client import (
    AllowlistedHttpsClient,
    DisallowedHostError,
    ResponseTooLargeError,
    UnexpectedRedirectError,
)


class _FakeResponse:
    def __init__(self, status_code: int, headers: dict | None = None, content: bytes = b"{}"):
        self.status_code = status_code
        self.headers = headers or {}
        self.content = content


class _FakeHttpxClient:
    """Substitui `httpx.Client` -- consome uma fila de respostas/exceções pré-programadas pelo
    teste, uma por chamada a `.get()`, e registra a URL/headers de cada chamada real feita."""

    queue: ClassVar[list] = []
    calls: ClassVar[list] = []

    def __init__(self, *args, **kwargs):
        self._closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, headers=None):
        _FakeHttpxClient.calls.append({"url": url, "headers": headers})
        item = _FakeHttpxClient.queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


@pytest.fixture(autouse=True)
def _reset_fake_client(monkeypatch):
    _FakeHttpxClient.queue = []
    _FakeHttpxClient.calls = []
    monkeypatch.setattr(http_client_module.httpx, "Client", _FakeHttpxClient)
    monkeypatch.setattr(http_client_module.time, "sleep", lambda *_a, **_k: None)


def _make_client(**overrides) -> AllowlistedHttpsClient:
    kwargs: dict = {
        "allowed_host": "pubchem.ncbi.nlm.nih.gov",
        "user_agent": "TestAgent/0.1",
        "contact_email": None,
        "rate_limit_per_second": 2.0,
        "timeout_seconds": 15.0,
        "max_retries": 3,
        "max_response_bytes": 200_000,
    }
    kwargs.update(overrides)
    return AllowlistedHttpsClient(**kwargs)


# --- construtor -------------------------------------------------------------------------


def test_constructor_rejects_zero_rate_limit():
    with pytest.raises(ValueError):
        _make_client(rate_limit_per_second=0)


def test_constructor_rejects_rate_limit_above_4():
    with pytest.raises(ValueError):
        _make_client(rate_limit_per_second=4.1)


def test_constructor_never_hardcodes_contact_email_in_user_agent_when_absent():
    client = _make_client(contact_email=None)
    assert "contato" not in client._headers["User-Agent"]


def test_constructor_includes_contact_email_when_provided():
    client = _make_client(contact_email="pesquisa@example.org")
    assert "pesquisa@example.org" in client._headers["User-Agent"]


# --- allowlist de host (nunca contornável) -----------------------------------------------


def test_rejects_path_with_embedded_absolute_url():
    client = _make_client()
    with pytest.raises(DisallowedHostError):
        client.get("https://evil.example.com/steal")
    assert _FakeHttpxClient.calls == []  # nunca chega a abrir uma conexão


def test_rejects_path_starting_with_protocol_relative_url():
    client = _make_client()
    with pytest.raises(DisallowedHostError):
        client.get("//evil.example.com/steal")
    assert _FakeHttpxClient.calls == []


def test_builds_url_from_allowed_host_only_never_from_path():
    _FakeHttpxClient.queue = [_FakeResponse(200, content=b'{"ok":true}')]
    client = _make_client(allowed_host="pubchem.ncbi.nlm.nih.gov")
    client.get("/rest/pug/compound/cid/2244/property/MolecularWeight/JSON")
    assert _FakeHttpxClient.calls[0]["url"] == (
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/2244/property/MolecularWeight/JSON"
    )


# --- redirecionamento nunca seguido -------------------------------------------------------


def test_redirect_response_raises_never_followed():
    _FakeHttpxClient.queue = [_FakeResponse(302, headers={"location": "https://evil.example.com"})]
    client = _make_client()
    with pytest.raises(UnexpectedRedirectError):
        client.get("/rest/pug/compound/cid/2244/JSON")


# --- limite de tamanho de resposta ---------------------------------------------------------


def test_response_too_large_by_content_length_header():
    _FakeHttpxClient.queue = [_FakeResponse(200, headers={"content-length": "999999999"})]
    client = _make_client(max_response_bytes=200_000)
    with pytest.raises(ResponseTooLargeError):
        client.get("/rest/pug/compound/cid/2244/JSON")


def test_response_too_large_by_actual_body_size_without_content_length_header():
    big_body = b"x" * 300_000
    _FakeHttpxClient.queue = [_FakeResponse(200, headers={}, content=big_body)]
    client = _make_client(max_response_bytes=200_000)
    with pytest.raises(ResponseTooLargeError):
        client.get("/rest/pug/compound/cid/2244/JSON")


# --- retry/backoff: apenas falhas transitórias -------------------------------------------


def test_no_retry_on_permanent_404():
    _FakeHttpxClient.queue = [_FakeResponse(404)]
    client = _make_client(max_retries=3)
    result = client.get("/rest/pug/compound/cid/999999999/JSON")
    assert result.status_code == 404
    assert result.attempt_count == 1
    assert len(_FakeHttpxClient.calls) == 1


def test_retries_on_transient_500_then_succeeds():
    _FakeHttpxClient.queue = [_FakeResponse(500), _FakeResponse(200, content=b'{"ok":true}')]
    client = _make_client(max_retries=3)
    result = client.get("/rest/pug/compound/cid/2244/JSON")
    assert result.status_code == 200
    assert result.attempt_count == 2
    assert len(_FakeHttpxClient.calls) == 2


def test_exhausts_retries_and_returns_last_transient_status():
    _FakeHttpxClient.queue = [_FakeResponse(503), _FakeResponse(503), _FakeResponse(503)]
    client = _make_client(max_retries=3)
    result = client.get("/rest/pug/compound/cid/2244/JSON")
    assert result.status_code == 503
    assert result.attempt_count == 3
    assert len(_FakeHttpxClient.calls) == 3


def test_connect_error_retried_then_raised_after_max_attempts():
    _FakeHttpxClient.queue = [
        httpx.ConnectError("connection refused"),
        httpx.ConnectError("connection refused"),
        httpx.ConnectError("connection refused"),
    ]
    client = _make_client(max_retries=3)
    with pytest.raises(httpx.ConnectError):
        client.get("/rest/pug/compound/cid/2244/JSON")
    assert len(_FakeHttpxClient.calls) == 3


def test_timeout_retried_then_succeeds():
    _FakeHttpxClient.queue = [httpx.TimeoutException("timed out"), _FakeResponse(200, content=b'{"ok":true}')]
    client = _make_client(max_retries=3)
    result = client.get("/rest/pug/compound/cid/2244/JSON")
    assert result.status_code == 200
    assert result.attempt_count == 2


# --- 429 + Retry-After ---------------------------------------------------------------------


def test_429_respects_retry_after_header_then_succeeds(monkeypatch):
    sleep_calls = []
    monkeypatch.setattr(http_client_module.time, "sleep", lambda s: sleep_calls.append(s))
    _FakeHttpxClient.queue = [
        _FakeResponse(429, headers={"retry-after": "3"}),
        _FakeResponse(200, content=b'{"ok":true}'),
    ]
    client = _make_client(max_retries=3)
    result = client.get("/rest/pug/compound/cid/2244/JSON")
    assert result.status_code == 200
    assert any(abs(s - 3.0) < 0.01 for s in sleep_calls)


# --- rate limiting local -------------------------------------------------------------------


def test_throttle_sleeps_when_called_too_soon_after_previous_request(monkeypatch):
    client = _make_client(rate_limit_per_second=2.0)  # intervalo minimo de 0.5s
    sleep_calls = []
    monkeypatch.setattr(http_client_module.time, "sleep", lambda s: sleep_calls.append(s))

    fake_now = {"t": 100.0}
    monkeypatch.setattr(http_client_module.time, "monotonic", lambda: fake_now["t"])

    client._last_request_at = 100.0
    fake_now["t"] = 100.1  # apenas 0.1s depois -- deveria dormir ~0.4s para respeitar 2 req/s
    client._throttle()
    assert len(sleep_calls) == 1
    assert sleep_calls[0] == pytest.approx(0.4, abs=0.01)


def test_throttle_does_not_sleep_when_enough_time_has_passed(monkeypatch):
    client = _make_client(rate_limit_per_second=2.0)
    sleep_calls = []
    monkeypatch.setattr(http_client_module.time, "sleep", lambda s: sleep_calls.append(s))
    fake_now = {"t": 100.0}
    monkeypatch.setattr(http_client_module.time, "monotonic", lambda: fake_now["t"])

    client._last_request_at = 100.0
    fake_now["t"] = 101.0  # 1s depois, acima do intervalo minimo de 0.5s
    client._throttle()
    assert sleep_calls == []
