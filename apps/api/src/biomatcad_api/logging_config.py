"""Logging estruturado sem dados sensíveis (Prompt Mestre §23.2: nunca logar PHI/segredos)."""
from __future__ import annotations

import logging
import sys

_SENSITIVE_KEYS = {"password", "senha", "token", "secret", "authorization", "master_key", "cpf", "rg"}


class RedactSensitiveFilter(logging.Filter):
    """Redige valores associados a chaves sensíveis presentes na mensagem formatada."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        lowered = msg.lower()
        if any(key in lowered for key in _SENSITIVE_KEYS):
            record.msg = "[mensagem de log suprimida: possível dado sensível]"
            record.args = ()
        return True


def configure_logging(environment: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    fmt = "%(asctime)s | %(levelname)s | %(name)s | env=" + environment + " | %(message)s"
    handler.setFormatter(logging.Formatter(fmt))
    handler.addFilter(RedactSensitiveFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
