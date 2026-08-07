"""Regressão: prova que o fixture usado pelo E2E (apps/api/scripts/seed_e2e_user.py) produz um
artefato STL cujo `Artifact.sha256` persistido BATE com o hash real dos bytes gravados no
storage, e cujo conteúdo tem pelo menos um facet válido segundo as MESMAS regras que o parser
ASCII do frontend usa (apps/web/src/lib/stlParser.ts).

Contexto do bug real corrigido nesta rodada ("cobertura E2E do visualizador 3D", 2026-08-06):
antes desta correção, `_FakeWorkerClientForE2ESeed.execute()` gravava um STL ASCII vazio
("solid e2e-seed\nendsolid e2e-seed\n", zero facets) e retornava `stl_sha256="0"*64` -- um
placeholder que não tinha nenhuma relação com os bytes reais. Como
`geometry_job_service.dispatch_job()` faz `sha256=result.stl_sha256 or sha256_of_file(...)`, e
"0"*64 é uma string truthy, o hash fake era persistido tal qual. O frontend
(`fetchArtifactBuffer` em `artifactDownload.ts`) recalcula o SHA-256 real dos bytes baixados e
lança `ArtifactChecksumMismatchError` se não bater com `Artifact.sha256` -- então o StlViewer
NUNCA chegava ao estado "ready" para o job pré-semeado, e isso nunca foi percebido porque o
E2E existente (vertical.spec.ts) só verifica a visibilidade do botão de download, nunca o
estado do visualizador.

Este teste roda o script real via subprocesso (exatamente como documentado no próprio script e
como o E2E do Windows o invoca), contra um SQLite efêmero e um storage local efêmero, e então
verifica de fora (sem confiar em nenhuma lógica do próprio script) que o Artifact persistido é
consistente com os bytes reais no disco.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = Path(__file__).resolve().parents[1]
SEED_SCRIPT = API_ROOT / "scripts" / "seed_e2e_user.py"

# Mesmas expressões regulares usadas por apps/web/src/lib/stlParser.ts (parseAsciiStl) --
# duplicadas aqui deliberadamente (não há runtime JS neste teste Python) para provar que o
# fixture também seria aceito pelo parser real do frontend, não só que ele "tem bytes".
FRONTEND_FACET_RE = re.compile(
    r"facet\s+normal\s+([0-9.eE-]+)\s+([0-9.eE-]+)\s+([0-9.eE-]+)[\s\S]*?outer\s+loop([\s\S]*?)endloop",
    re.IGNORECASE,
)
FRONTEND_VERTEX_RE = re.compile(
    r"vertex\s+([0-9.eE-]+)\s+([0-9.eE-]+)\s+([0-9.eE-]+)", re.IGNORECASE
)


def test_seed_script_produces_checksum_consistent_non_empty_stl(tmp_path):
    db_path = tmp_path / "e2e_seed_fixture_test.db"
    storage_dir = tmp_path / "artifacts"
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["ARTIFACT_STORAGE_DIR"] = str(storage_dir)
    env["ENVIRONMENT"] = "test"
    env["API_SECRET_KEY"] = "test-secret-key-not-for-production-not-for-production"

    result = subprocess.run(
        [sys.executable, str(SEED_SCRIPT)],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"seed_e2e_user.py falhou (rc={result.returncode}).\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["status"] == "seeded"
    job_id = payload["succeeded_job_id"]

    # Verificação independente: abre o MESMO sqlite que o script acabou de popular e lê a
    # linha de Artifact bruta via SQL puro (sem importar nenhum modelo/serviço do próprio
    # projeto), para não reutilizar nenhuma lógica potencialmente cúmplice do bug original.
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute(
        "SELECT storage_key, sha256, size_bytes FROM artifacts WHERE geometry_job_id = ? AND kind = 'STL'",
        (job_id,),
    )
    row = cur.fetchone()
    conn.close()
    assert row is not None, "Nenhum Artifact STL foi persistido para o job pré-semeado."
    storage_key, persisted_sha256, persisted_size_bytes = row

    stl_bytes = (storage_dir / storage_key).read_bytes()
    real_sha256 = hashlib.sha256(stl_bytes).hexdigest()

    # 1) O bug original: hash fake "0"*64 nunca bate com nada real.
    assert persisted_sha256 != "0" * 64, "Regressão do bug original: hash fake ainda sendo persistido."

    # 2) O Artifact.sha256 persistido tem que ser o hash REAL dos bytes gravados -- é
    #    exatamente essa comparação que fetchArtifactBuffer() faz no frontend.
    assert persisted_sha256 == real_sha256

    # 3) Tamanho persistido consistente com os bytes reais (dispatch_job usa len(stl_bytes)).
    assert persisted_size_bytes == len(stl_bytes)

    # 4) O conteúdo não pode ser um "solid ... endsolid" vazio -- tem que ter pelo menos um
    #    facet reconhecível pelas MESMAS regras do parser ASCII do frontend.
    text = stl_bytes.decode("ascii")
    assert re.match(r"^\s*solid", text, re.IGNORECASE)
    facets = FRONTEND_FACET_RE.findall(text)
    assert len(facets) > 0, "STL do fixture ainda está vazio (zero facets) -- parseAsciiStl() rejeitaria."
    for _nx, _ny, _nz, loop_body in facets:
        vertices = FRONTEND_VERTEX_RE.findall(loop_body)
        assert len(vertices) == 3, "Cada facet deveria ter exatamente 3 vértices (triângulo)."


def test_seed_script_is_idempotent_on_rerun(tmp_path):
    """O script já documenta que reexecuções devem retornar status=already_seeded (não deve
    duplicar usuário/artefato) -- proteção contra reexecução acidental durante desenvolvimento
    do E2E."""
    db_path = tmp_path / "e2e_seed_fixture_idempotent.db"
    storage_dir = tmp_path / "artifacts"
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["ARTIFACT_STORAGE_DIR"] = str(storage_dir)
    env["ENVIRONMENT"] = "test"
    env["API_SECRET_KEY"] = "test-secret-key-not-for-production-not-for-production"

    first = subprocess.run(
        [sys.executable, str(SEED_SCRIPT)], cwd=API_ROOT, env=env, capture_output=True, text=True, timeout=120
    )
    assert first.returncode == 0
    second = subprocess.run(
        [sys.executable, str(SEED_SCRIPT)], cwd=API_ROOT, env=env, capture_output=True, text=True, timeout=120
    )
    assert second.returncode == 0
    second_payload = json.loads(second.stdout.strip().splitlines()[-1])
    assert second_payload["status"] == "already_seeded"
