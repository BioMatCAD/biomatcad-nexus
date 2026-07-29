"""Validação, canonicalização e checksum da receita BioMatCEM (Incremento 2.1, item 2, ADR-0006).

Este módulo é a ÚNICA fonte de verdade sobre se uma receita é válida -- a validação offline em
JS do frontend (recipeValidationOffline.ts, modo demo) reimplementa as mesmas regras mas nunca
substitui esta validação real.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

_SCHEMA_RELATIVE_PATH = "schemas/biomatcem/geometry-recipe-v1.schema.json"


class RecipeValidationError(ValueError):
    """Levantado quando a receita não passa na validação do JSON Schema. Carrega a lista
    estruturada de erros (não apenas uma mensagem única) para que a API devolva
    error.details navegável pelo frontend."""

    def __init__(self, errors: list[dict]) -> None:
        self.errors = errors
        super().__init__(f"Receita inválida: {len(errors)} erro(s) de schema.")


def _find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__)).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / _SCHEMA_RELATIVE_PATH).exists():
            return candidate
    raise FileNotFoundError(
        f"Não foi possível localizar {_SCHEMA_RELATIVE_PATH} a partir de {current}."
    )


@lru_cache
def _load_schema() -> dict:
    root = _find_repo_root()
    with open(root / _SCHEMA_RELATIVE_PATH, encoding="utf-8") as f:
        return json.load(f)


@lru_cache
def _validator() -> Draft202012Validator:
    return Draft202012Validator(_load_schema())


def schema_version() -> str:
    return _load_schema()["properties"]["schema_version"]["const"]


def validate_recipe(recipe_body: dict) -> list[dict]:
    """Retorna a lista de erros estruturados (vazia se válido). Nunca levanta exceção --
    quem chama decide se transforma em erro HTTP."""
    errors = sorted(_validator().iter_errors(recipe_body), key=lambda e: list(e.path))
    return [
        {
            "path": "/".join(str(p) for p in error.path) or "(raiz)",
            "message": error.message,
            "validator": error.validator,
        }
        for error in errors
    ]


def canonicalize_recipe(recipe_body: dict) -> str:
    """Forma canônica: chaves ordenadas, separadores compactos -- determinística para o mesmo
    conteúdo lógico, base do checksum e da persistência."""
    return json.dumps(recipe_body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_checksum(canonical_json_str: str) -> str:
    return hashlib.sha256(canonical_json_str.encode("utf-8")).hexdigest()


def validate_and_canonicalize(recipe_body: dict) -> tuple[str, str]:
    """Valida a receita e retorna (canonical_json_str, checksum_sha256). Levanta
    RecipeValidationError se inválida -- nunca retorna um checksum de receita inválida."""
    errors = validate_recipe(recipe_body)
    if errors:
        raise RecipeValidationError(errors)
    canonical = canonicalize_recipe(recipe_body)
    return canonical, compute_checksum(canonical)
