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


def _semantic_topology_errors(recipe_body: dict) -> list[dict]:
    """Camada 2 de validação (Incremento 2.1.1, item 2): regras semânticas que o JSON Schema
    Draft 2020-12 não expressa nativamente (comparação entre duas propriedades numéricas
    irmãs). Só roda se a estrutura básica (topology.cell_size_mm e topology.wall_thickness_mm)
    já existir -- validação estrutural (camada 1) roda primeiro e é quem garante isso.

    Regra aplicada aqui: wall_thickness_mm >= cell_size_mm / 2 é fisicamente contraditório --
    a meia-espessura da parede não pode ocupar metade ou mais da própria célula unitária, senão
    não sobra poro nenhum dentro da célula (célula degenerada, sólido maciço). Este é um limite
    estrutural conservador, dimensional, calculado sem depender da geometria real da superfície
    gyroid. Uma segunda checagem, dependente da amplitude real da função implícita e do fator de
    conversão espessura->banda-isovalor, é feita pelo worker C#/PicoGK antes da execução (ver
    apps/geometry-worker/WORKER_STATUS.md) e pode rejeitar combinações que passam nesta camada
    mas ainda assim são inviáveis geometricamente."""
    topology = recipe_body.get("topology")
    if not isinstance(topology, dict):
        return []
    cell_size_mm = topology.get("cell_size_mm")
    wall_thickness_mm = topology.get("wall_thickness_mm")
    if not isinstance(cell_size_mm, int | float) or not isinstance(wall_thickness_mm, int | float):
        return []
    if wall_thickness_mm >= cell_size_mm / 2:
        return [
            {
                "path": "topology/wall_thickness_mm",
                "message": (
                    f"wall_thickness_mm ({wall_thickness_mm}mm) deve ser menor que "
                    f"cell_size_mm/2 ({cell_size_mm / 2}mm) -- caso contrário a célula unitária "
                    "não teria poro algum (sólido maciço, contradiz o objetivo de scaffold "
                    "poroso). Reduza wall_thickness_mm ou aumente cell_size_mm."
                ),
                "validator": "semantic:TOPOLOGY_PARAMETERS_INCONSISTENT",
            }
        ]
    return []


def validate_recipe(recipe_body: dict) -> list[dict]:
    """Retorna a lista de erros estruturados (vazia se válido). Nunca levanta exceção --
    quem chama decide se transforma em erro HTTP.

    Duas camadas: (1) JSON Schema Draft 2020-12 estrutural (tipos, obrigatoriedade, limites,
    additionalProperties:false); (2) regras semânticas entre campos irmãos que o JSON Schema não
    expressa nativamente (ver _semantic_topology_errors). A camada 2 só roda sobre uma receita que
    já passou a camada 1 seria redundante checar -- mas por simplicidade e robustez a função
    roda ambas sempre e concatena os erros, já que _semantic_topology_errors tolera campos
    ausentes/mal-tipados (apenas retorna lista vazia nesse caso, deixando a camada 1 reportar)."""
    errors = sorted(_validator().iter_errors(recipe_body), key=lambda e: list(e.path))
    structural = [
        {
            "path": "/".join(str(p) for p in error.path) or "(raiz)",
            "message": error.message,
            "validator": error.validator,
        }
        for error in errors
    ]
    return structural + _semantic_topology_errors(recipe_body)


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
