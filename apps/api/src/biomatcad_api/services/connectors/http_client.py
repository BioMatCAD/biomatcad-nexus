"""Cliente HTTP seguro para conectores de ingestão científica (Incremento 2.3, Rodada 2 --
Fase E). Não é um cliente HTTP genérico -- é deliberadamente restrito a UM host permitido por
instância, sem nenhuma forma de o chamador fornecer uma URL arbitrária. Políticas aplicadas:

1. allowlist de host: qualquer tentativa de requisitar um host diferente do configurado é
   rejeitada antes de qualquer conexão de rede.
2. TLS sempre verificado (nunca `verify=False`).
3. Nenhuma URL fornecida por usuário final chega até aqui -- o chamador (o conector) monta o
   path a partir de um identificador validado (ex.: CID numérico), nunca de texto livre.
4. Nenhum redirecionamento é seguido automaticamente (`follow_redirects=False`) -- qualquer
   resposta 3xx é tratada como falha estruturada, nunca seguida silenciosamente para outro host.
5. Timeout local configurável (padrão 15s), sempre aplicado.
6. Taxa máxima de requisições por segundo aplicada localmente (padrão 2/s, nunca configurável
   acima de 4/s -- ver config.py::validate_pubchem_rate_limit).
7. Respeita 429 e o cabeçalho `Retry-After` (aguarda o tempo indicado antes de tentar de novo).
8. Retry apenas para falhas transitórias (429, 500, 502, 503, timeout, erro de conexão) --
   nunca para 4xx que não seja 429 (erro do cliente, permanente).
9. Backoff exponencial com jitter limitado entre tentativas.
10. Número máximo de tentativas configurável.
11. Limite de tamanho de resposta em bytes -- respostas maiores são rejeitadas (nunca lidas
    até o fim silenciosamente).
12. User-Agent identificável e configurável; e-mail de contato institucional OPCIONAL via
    configuração, nunca hardcoded.
13. Logs estruturados sem conteúdo sensível (nunca corpo de cabeçalhos, cookies, ou payload
    completo -- apenas método, host, path, status, duração, tentativa).
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

import httpx

logger = logging.getLogger("biomatcad_api.connectors.http_client")

_TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503})
_BACKOFF_BASE_SECONDS = 0.5
_BACKOFF_MAX_SECONDS = 8.0
_BACKOFF_JITTER_MAX_SECONDS = 0.25
_MAX_RETRY_AFTER_SECONDS = 30.0


class DisallowedHostError(Exception):
    """Levantado quando o chamador tenta requisitar um host fora da allowlist -- nunca deveria
    acontecer em uso normal (o conector monta a URL internamente), mas é uma checagem explícita
    de defesa em profundidade, nunca contornável por configuração externa."""


class UnexpectedRedirectError(Exception):
    """Levantado quando a fonte responde com um redirecionamento (3xx) -- nunca seguido
    automaticamente, mesmo que aponte para o mesmo host."""


class ResponseTooLargeError(Exception):
    """Levantado quando a resposta excede o limite configurado de bytes."""


@dataclass(frozen=True)
class HttpFetchResult:
    status_code: int
    content_type: str | None
    body_bytes: bytes
    attempt_count: int
    final_url_path: str


class AllowlistedHttpsClient:
    """Cliente HTTPS restrito a um único host, com rate limiting, retry/backoff e limite de
    tamanho de resposta. Uma instância = um host permitido (ex.: PubChem) -- nunca reutilizado
    para requisitar outro host."""

    def __init__(
        self,
        *,
        allowed_host: str,
        user_agent: str,
        contact_email: str | None,
        rate_limit_per_second: float,
        timeout_seconds: float,
        max_retries: int,
        max_response_bytes: int,
    ) -> None:
        if rate_limit_per_second <= 0 or rate_limit_per_second > 4.0:
            raise ValueError("rate_limit_per_second deve estar em (0, 4.0].")
        self._allowed_host = allowed_host
        self._min_interval_seconds = 1.0 / rate_limit_per_second
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._max_response_bytes = max_response_bytes
        user_agent_full = user_agent if not contact_email else f"{user_agent} (contato: {contact_email})"
        self._headers = {"User-Agent": user_agent_full, "Accept": "application/json"}
        self._last_request_at: float | None = None

    def _throttle(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = time.monotonic() - self._last_request_at
        wait = self._min_interval_seconds - elapsed
        if wait > 0:
            time.sleep(wait)

    def _backoff_delay(self, attempt: int) -> float:
        base = min(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), _BACKOFF_MAX_SECONDS)
        jitter = random.uniform(0, _BACKOFF_JITTER_MAX_SECONDS)
        return base + jitter

    def _parse_retry_after(self, header_value: str | None) -> float | None:
        if not header_value:
            return None
        try:
            return min(float(header_value), _MAX_RETRY_AFTER_SECONDS)
        except ValueError:
            pass
        try:
            dt = parsedate_to_datetime(header_value)
            delay = (dt.timestamp() - time.time())
            return max(0.0, min(delay, _MAX_RETRY_AFTER_SECONDS))
        except (TypeError, ValueError):
            return None

    def get(self, path: str) -> HttpFetchResult:
        """`path` deve ser um path relativo já validado pelo chamador (ex.:
        "/rest/pug/compound/cid/2244/property/.../JSON") -- nunca uma URL completa fornecida
        por texto livre externo."""
        if "://" in path or path.lower().startswith("//"):
            raise DisallowedHostError(
                f"Path deve ser relativo ao host permitido ({self._allowed_host}); "
                "URLs/hosts embutidos no path nunca são aceitos."
            )
        url = f"https://{self._allowed_host}{path}"

        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            self._throttle()
            self._last_request_at = time.monotonic()
            start = time.monotonic()
            try:
                with httpx.Client(follow_redirects=False, timeout=self._timeout_seconds, verify=True) as client:
                    response = client.get(url, headers=self._headers)
            except httpx.TimeoutException as exc:
                last_exc = exc
                logger.warning(
                    "pubchem_http_timeout host=%s path=%s attempt=%d", self._allowed_host, path, attempt
                )
                if attempt < self._max_retries:
                    time.sleep(self._backoff_delay(attempt))
                    continue
                raise
            except httpx.ConnectError as exc:
                last_exc = exc
                logger.warning(
                    "pubchem_http_connect_error host=%s path=%s attempt=%d", self._allowed_host, path, attempt
                )
                if attempt < self._max_retries:
                    time.sleep(self._backoff_delay(attempt))
                    continue
                raise

            duration_ms = (time.monotonic() - start) * 1000
            logger.info(
                "pubchem_http_response host=%s path=%s status=%d attempt=%d duration_ms=%.1f",
                self._allowed_host, path, response.status_code, attempt, duration_ms,
            )

            if 300 <= response.status_code < 400:
                raise UnexpectedRedirectError(
                    f"Resposta {response.status_code} (redirecionamento) nunca é seguida automaticamente."
                )

            content_length = response.headers.get("content-length")
            if content_length is not None and int(content_length) > self._max_response_bytes:
                raise ResponseTooLargeError(
                    f"Resposta declara {content_length} bytes, acima do limite de {self._max_response_bytes}."
                )
            body = response.content
            if len(body) > self._max_response_bytes:
                raise ResponseTooLargeError(
                    f"Resposta com {len(body)} bytes, acima do limite de {self._max_response_bytes}."
                )

            if response.status_code == 429 and attempt < self._max_retries:
                retry_after = self._parse_retry_after(response.headers.get("retry-after"))
                delay = retry_after if retry_after is not None else self._backoff_delay(attempt)
                logger.warning(
                    "pubchem_http_rate_limited host=%s path=%s attempt=%d retry_after=%.1f",
                    self._allowed_host, path, attempt, delay,
                )
                time.sleep(delay)
                continue

            if response.status_code in _TRANSIENT_STATUS_CODES and attempt < self._max_retries:
                time.sleep(self._backoff_delay(attempt))
                continue

            return HttpFetchResult(
                status_code=response.status_code,
                content_type=response.headers.get("content-type"),
                body_bytes=body,
                attempt_count=attempt,
                final_url_path=path,
            )

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Loop de retry terminou sem resposta nem exceção -- estado inesperado.")  # pragma: no cover
