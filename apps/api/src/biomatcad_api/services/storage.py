"""Adaptador de armazenamento de artefatos (Incremento 2.1, item 7).

LocalStorageAdapter é funcional de verdade (grava/lê arquivos reais em disco). O Protocol
StorageAdapter é o contrato que um adaptador MinIO/S3 real implementaria sem mudar nenhum
código de serviço/router -- não há fila em memória nem storage "simulado" apresentado como
solução de produção.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol


def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class StorageAdapter(Protocol):
    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...


class LocalStorageAdapter:
    """Implementação real em disco, com resolução de caminho segura contra path traversal
    (chave nunca pode escapar de base_dir via '..')."""

    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        resolved_base = self.base_dir.resolve()
        candidate = (resolved_base / key).resolve()
        if resolved_base not in candidate.parents and candidate != resolved_base:
            raise ValueError(f"Chave de armazenamento inválida (fora de base_dir): {key!r}")
        return candidate

    def put(self, key: str, data: bytes) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()
