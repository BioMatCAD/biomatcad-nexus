#!/usr/bin/env python3
"""Constrói um job.json real (mesmo formato exato usado por
biomatcad_api.services.worker_client.DotnetPicoGkWorkerClient.execute -- ver
apps/api/src/biomatcad_api/services/worker_client.py) para invocar o geometry-worker
DIRETAMENTE via CLI, sem API e sem dispatcher (Incremento 2.2, rodada de prova direta
"FASE A" -- ver scripts/Run-VoronoiDirectWorkerProbe.ps1).

Por que isto existe: o worker espera um job.json cujo campo "recipe" é o corpo CANÔNICO da
receita (mesmo resultado de validate_and_canonicalize, o que a API de fato grava em
GeometryRecipe.canonical_json e envia ao worker em produção) -- não o arquivo golden-recipe
bruto lido do disco sem qualquer processamento. Este script usa a MESMA função de
validação/canonicalização real do backend (nenhuma reimplementação paralela), para garantir que
a prova direta desta rodada invoque o worker com um job.json byte-a-byte equivalente ao que a
API real enviaria -- nenhuma golden recipe é alterada, apenas canonicalizada como sempre foi.

Uso:
    python build_worker_job_json.py --recipe block-voronoi-preview-v1 \\
        --job-id <uuid> --output-dir /caminho/para/saida
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recipe", required=True, help="Nome da golden recipe (sem .json), ex.: block-voronoi-preview-v1.")
    parser.add_argument("--job-id", default=None, help="job_id a usar (default: um novo UUID4).")
    parser.add_argument("--output-dir", required=True, help="Diretório onde o worker deve gravar scaffold.stl e onde job.json será escrito.")
    parser.add_argument("--repo-root", default=None, help="Raiz do repositório (default: calculada a partir deste arquivo).")
    args = parser.parse_args()

    repo_root = Path(args.repo_root) if args.repo_root else Path(__file__).resolve().parents[3]
    recipe_path = repo_root / "schemas" / "biomatcem" / "golden-recipes" / f"{args.recipe}.json"
    if not recipe_path.exists():
        print(f"ERRO: golden recipe não encontrada: {recipe_path}", file=sys.stderr)
        return 1

    api_src = repo_root / "apps" / "api" / "src"
    sys.path.insert(0, str(api_src))
    from biomatcad_api.services.recipe_service import validate_and_canonicalize

    with open(recipe_path, encoding="utf-8") as f:
        recipe_body = json.load(f)

    canonical_str, checksum = validate_and_canonicalize(recipe_body)
    recipe_canonical = json.loads(canonical_str)

    job_id = args.job_id or str(uuid.uuid4())
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    job_json_path = output_dir / "job.json"
    # Mesma construção EXATA de worker_client.py::execute -- job_id, recipe (canônico),
    # output_dir -- para que o worker receba um insumo indistinguível do que a API real envia.
    job_json_path.write_text(
        json.dumps(
            {"job_id": job_id, "recipe": recipe_canonical, "output_dir": str(output_dir)},
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    print(json.dumps({
        "job_id": job_id,
        "job_json_path": str(job_json_path),
        "output_dir": str(output_dir),
        "recipe_checksum_sha256": checksum,
        "recipe_name": args.recipe,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
