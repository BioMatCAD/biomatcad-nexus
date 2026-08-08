"""Regressão permanente do fixture de seed/reconciliação do E2E
(apps/api/scripts/seed_e2e_user.py).

Contexto (bug real, execução Windows 20260807-001756, commit 1be54e3): o script anterior tinha
um `if existing_user is not None: return` logo no início -- em QUALQUER banco onde o script já
tivesse rodado uma vez (como o Postgres real do usuário, semeado em rodadas anteriores ANTES da
correção do STL vazio/hash fake), essa saída antecipada significava que o job/Artifact/Manifest
LEGADOS (STL ASCII vazio, stl_sha256="0"*64) nunca eram corrigidos -- o script só imprimia
`{"status": "already_seeded", ...}` e retornava. A execução real do usuário confirmou
exatamente isso: `global-setup` relatou "already_seeded", e as 12 falhas de viewer.spec.ts
foram todas por ausência do estado "ready" (viewer-triangle-count nunca aparece), consistente
com o StlViewer rejeitando o job por checksum incompatível contra o hash fake legado -- nunca
uma regressão dos testes ou do componente.

Corrigido: o script agora é uma sequência de passos "get-or-create" idempotentes e
reconciliáveis, localizando exclusivamente o fixture E2E (via e-mail único do usuário e
idempotency_key única do design_run) e reparando qualquer componente cujo conteúdo persistido
divirja do esperado -- sem nunca duplicar registros nem tocar em dados alheios ao fixture.

Estes testes rodam o script real via subprocesso (exatamente como e2e/global-setup.ts o invoca)
contra um SQLite efêmero e um storage local efêmero, corrompendo deliberadamente o banco/
storage entre execuções para reproduzir cada cenário relatado, e verificam de fora -- via SQL
puro e leitura direta de arquivos, sem reutilizar nenhuma lógica do próprio script -- que a
reconciliação realmente aconteceu.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
SEED_SCRIPT = API_ROOT / "scripts" / "seed_e2e_user.py"

# Mesmas expressões regulares usadas por apps/web/src/lib/stlParser.ts (parseAsciiStl) --
# duplicadas aqui deliberadamente (não há runtime JS neste teste Python) para provar que o
# fixture também seria aceito pelo parser real do frontend, não só que ele "tem bytes".
FRONTEND_FACET_RE = re.compile(
    r"facet\s+normal\s+([0-9.eE-]+)\s+([0-9.eE-]+)\s+([0-9.eE-]+)[\s\S]*?outer\s+loop([\s\S]*?)endloop",
    re.IGNORECASE,
)
FRONTEND_VERTEX_RE = re.compile(r"vertex\s+([0-9.eE-]+)\s+([0-9.eE-]+)\s+([0-9.eE-]+)", re.IGNORECASE)

E2E_JOB_IDEMPOTENCY_KEY = "e2e-preseeded-succeeded"
LEGACY_FAKE_SHA256 = "0" * 64
LEGACY_EMPTY_STL_BYTES = b"solid e2e-seed\nendsolid e2e-seed\n"


def _run_seed(env_overrides: dict) -> dict:
    env = dict(os.environ)
    env.update(env_overrides)
    env.setdefault("ENVIRONMENT", "test")
    env.setdefault("API_SECRET_KEY", "test-secret-key-not-for-production-not-for-production")
    result = subprocess.run(
        [sys.executable, str(SEED_SCRIPT)],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, (
        f"seed_e2e_user.py falhou (rc={result.returncode}).\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def _make_env(tmp_path: Path, name: str) -> tuple[dict, Path, Path]:
    db_path = tmp_path / f"{name}.db"
    storage_dir = tmp_path / f"{name}-artifacts"
    return {"DATABASE_URL": f"sqlite:///{db_path}", "ARTIFACT_STORAGE_DIR": str(storage_dir)}, db_path, storage_dir


def _fetch_stl_artifact(db_path: Path, job_id: str):
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute(
        "SELECT id, storage_key, sha256, size_bytes FROM artifacts WHERE geometry_job_id = ? AND kind = 'STL'",
        (job_id,),
    )
    row = cur.fetchone()
    conn.close()
    return row


def _fetch_manifest(db_path: Path, job_id: str):
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT id, manifest_json, manifest_sha256 FROM artifact_manifests WHERE geometry_job_id = ?", (job_id,))
    row = cur.fetchone()
    conn.close()
    return row


def _corrupt_stl_to_legacy(db_path: Path, storage_dir: Path, artifact_id: str, storage_key: str) -> None:
    """Reproduz precisamente o bug legado real: hash fake "0"*64 + STL ASCII vazio (zero
    facets) -- o cenário exato encontrado no banco Windows real."""
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute(
        "UPDATE artifacts SET sha256 = ?, size_bytes = ? WHERE id = ?",
        (LEGACY_FAKE_SHA256, len(LEGACY_EMPTY_STL_BYTES), artifact_id),
    )
    conn.commit()
    conn.close()
    (storage_dir / storage_key).write_bytes(LEGACY_EMPTY_STL_BYTES)


def _assert_stl_is_valid_tetrahedron(storage_dir: Path, storage_key: str, expected_sha256: str) -> None:
    stl_bytes = (storage_dir / storage_key).read_bytes()
    assert hashlib.sha256(stl_bytes).hexdigest() == expected_sha256
    text = stl_bytes.decode("ascii")
    assert re.match(r"^\s*solid", text, re.IGNORECASE)
    facets = FRONTEND_FACET_RE.findall(text)
    assert len(facets) == 4, f"Esperado exatamente 4 facets (tetraedro), encontrado {len(facets)}."
    for _nx, _ny, _nz, loop_body in facets:
        vertices = FRONTEND_VERTEX_RE.findall(loop_body)
        assert len(vertices) == 3, "Cada facet deveria ter exatamente 3 vértices (triângulo)."


def test_banco_vazio_cria_fixture_completo(tmp_path):
    """Cenário 1: banco vazio -> fixture criado corretamente (status=created)."""
    env, db_path, storage_dir = _make_env(tmp_path, "empty")
    payload = _run_seed(env)

    assert payload["status"] == "created"
    components = payload["components"]
    assert components["user"] == "created"
    assert components["project"] == "created"
    assert components["recipe"] == "created"
    assert components["design_run"] == "created"
    assert components["job"] == "created"
    # stl_artifact/manifest são criados DENTRO do dispatch do job (não são um passo separado
    # na primeira execução) -- por isso reportam already_valid mesmo na criação: já nascem
    # corretos, nada precisou ser reparado.
    assert components["stl_artifact"] == "already_valid"
    assert components["manifest"] == "already_valid"

    job_id = payload["succeeded_job_id"]
    row = _fetch_stl_artifact(db_path, job_id)
    assert row is not None, "Nenhum Artifact STL foi persistido para o job recém-criado."
    _artifact_id, storage_key, persisted_sha256, persisted_size_bytes = row
    assert persisted_sha256 != LEGACY_FAKE_SHA256
    _assert_stl_is_valid_tetrahedron(storage_dir, storage_key, persisted_sha256)
    assert persisted_size_bytes == (storage_dir / storage_key).stat().st_size


def test_segunda_execucao_nao_duplica_e_reporta_already_valid(tmp_path):
    """Cenário 2/7: reexecução sobre um fixture já correto -> already_valid, sem duplicação."""
    env, db_path, _storage_dir = _make_env(tmp_path, "idempotent")
    first = _run_seed(env)
    second = _run_seed(env)

    assert second["status"] == "already_valid"
    assert all(v == "already_valid" for v in second["components"].values())
    assert first["succeeded_job_id"] == second["succeeded_job_id"]
    assert first["project_id"] == second["project_id"]

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    assert cur.fetchone()[0] == 1, "Reexecução duplicou o usuário E2E."
    cur.execute("SELECT COUNT(*) FROM design_runs")
    assert cur.fetchone()[0] == 1, "Reexecução duplicou o design_run E2E."
    cur.execute("SELECT COUNT(*) FROM geometry_jobs")
    assert cur.fetchone()[0] == 1, "Reexecução duplicou o job E2E."
    cur.execute("SELECT COUNT(*) FROM artifacts WHERE kind = 'STL'")
    assert cur.fetchone()[0] == 1, "Reexecução duplicou o Artifact STL."
    cur.execute("SELECT COUNT(*) FROM artifact_manifests")
    assert cur.fetchone()[0] == 1, "Reexecução duplicou o ArtifactManifest."
    conn.close()


def test_fixture_legado_stl_vazio_e_hash_fake_e_reparado(tmp_path):
    """Cenário 3: reproduz BYTE A BYTE o bug real encontrado no banco Windows (STL ASCII vazio
    + stl_sha256="0"*64 persistido por uma execução anterior à correção) e prova que a
    reexecução do script já corrigido repara -- sem exigir nenhuma limpeza manual do banco."""
    env, db_path, storage_dir = _make_env(tmp_path, "legacy")
    first = _run_seed(env)
    job_id = first["succeeded_job_id"]

    artifact_id, storage_key, sha_before, _size_before = _fetch_stl_artifact(db_path, job_id)
    _corrupt_stl_to_legacy(db_path, storage_dir, artifact_id, storage_key)

    # Confirma que a corrupção manual realmente reproduziu o defeito relatado antes de reparar.
    corrupted_bytes = (storage_dir / storage_key).read_bytes()
    assert corrupted_bytes == LEGACY_EMPTY_STL_BYTES
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT sha256 FROM artifacts WHERE id = ?", (artifact_id,))
    assert cur.fetchone()[0] == LEGACY_FAKE_SHA256
    conn.close()

    second = _run_seed(env)
    assert second["status"] == "repaired"
    assert second["components"]["stl_artifact"] == "repaired"
    assert second["succeeded_job_id"] == job_id, "A reconciliação não deveria criar um job novo."

    _artifact_id2, storage_key2, sha_after, size_after = _fetch_stl_artifact(db_path, job_id)
    assert sha_after != LEGACY_FAKE_SHA256
    assert sha_after == sha_before, "Deveria reparar de volta ao MESMO hash real original."
    _assert_stl_is_valid_tetrahedron(storage_dir, storage_key2, sha_after)
    assert size_after == (storage_dir / storage_key2).stat().st_size


def test_arquivo_fisico_ausente_e_recriado(tmp_path):
    """Cenário 4: Artifact correto no banco, mas o arquivo físico foi apagado do storage
    (ex.: limpeza de disco externa) -> arquivo recriado com os bytes corretos."""
    env, db_path, storage_dir = _make_env(tmp_path, "missing-file")
    first = _run_seed(env)
    job_id = first["succeeded_job_id"]
    _artifact_id, storage_key, sha_before, _size = _fetch_stl_artifact(db_path, job_id)

    file_path = storage_dir / storage_key
    assert file_path.exists()
    file_path.unlink()
    assert not file_path.exists()

    second = _run_seed(env)
    assert second["status"] == "repaired"
    assert second["components"]["stl_artifact"] == "repaired"

    assert file_path.exists()
    _artifact_id2, storage_key2, sha_after, _size2 = _fetch_stl_artifact(db_path, job_id)
    assert sha_after == sha_before
    _assert_stl_is_valid_tetrahedron(storage_dir, storage_key2, sha_after)


def test_artifact_correto_e_manifest_incorreto_e_reconciliado_preservando_id(tmp_path):
    """Cenário 5: Artifact STL já correto, mas o ArtifactManifest ainda referencia um
    stl_sha256/entrada obsoletos (ex.: manifesto legado de antes de uma correção anterior) ->
    reconciliado SEM recriar a linha (mesmo id preservado, resto do conteúdo intacto)."""
    env, db_path, _storage_dir = _make_env(tmp_path, "manifest-stale")
    first = _run_seed(env)
    job_id = first["succeeded_job_id"]

    manifest_id_before, manifest_json_str, _sha_before = _fetch_manifest(db_path, job_id)
    manifest_json = json.loads(manifest_json_str)
    original_git_commit = manifest_json.get("git_commit")
    manifest_json["stl_sha256"] = LEGACY_FAKE_SHA256
    for entry in manifest_json.get("artifacts", []):
        if entry.get("kind") == "stl":
            entry["sha256"] = LEGACY_FAKE_SHA256
            entry["size_bytes"] = len(LEGACY_EMPTY_STL_BYTES)

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute(
        "UPDATE artifact_manifests SET manifest_json = ? WHERE geometry_job_id = ?",
        (json.dumps(manifest_json), job_id),
    )
    conn.commit()
    conn.close()

    second = _run_seed(env)
    assert second["status"] == "repaired"
    assert second["components"]["manifest"] == "repaired"
    assert second["components"]["stl_artifact"] == "already_valid", "STL já estava correto -- só o manifesto precisava reparo."

    manifest_id_after, manifest_json_str_after, _sha_after = _fetch_manifest(db_path, job_id)
    assert manifest_id_after == manifest_id_before, "Reconciliação não deveria criar uma nova linha de manifesto."
    patched = json.loads(manifest_json_str_after)
    assert patched["stl_sha256"] != LEGACY_FAKE_SHA256
    stl_entries = [e for e in patched["artifacts"] if e.get("kind") == "stl"]
    assert len(stl_entries) == 1, "Não deveria duplicar a entrada do artefato STL dentro do manifesto."
    assert stl_entries[0]["sha256"] != LEGACY_FAKE_SHA256
    # Conteúdo não relacionado ao STL permanece intacto (prova que o patch é cirúrgico).
    assert patched.get("git_commit") == original_git_commit


def test_registros_alheios_ao_fixture_permanecem_intactos(tmp_path):
    """Cenário 6: um usuário/organização/job REAL (não pertencente ao fixture E2E) coexistindo
    no mesmo banco -- a reconciliação nunca deve tocar nele, byte a byte e linha a linha."""
    env, db_path, _storage_dir = _make_env(tmp_path, "coexisting")
    _run_seed(env)

    # Insere um registro "alheio" diretamente via SQL puro (simula um usuário/job real de
    # pesquisa que nunca passou pelo script de seed).
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO organizations (id, name, slug, created_at) VALUES (?, ?, ?, datetime('now'))",
        ("real-org-1", "Organização Real de Pesquisa", "org-real-pesquisa"),
    )
    cur.execute(
        "INSERT INTO users (id, organization_id, email, full_name, hashed_password, role, is_active, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))",
        ("real-user-1", "real-org-1", "pesquisador.real@example.com", "Pesquisador Real", "hash-nao-usado", "researcher", 1),
    )
    cur.execute(
        "INSERT INTO biomat_projects (id, organization_id, owner_user_id, name, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'))",
        ("real-project-1", "real-org-1", "real-user-1", "Projeto Real Confidencial", "active"),
    )
    conn.commit()

    def _snapshot():
        cur.execute("SELECT id, name, slug FROM organizations WHERE id = 'real-org-1'")
        org_row = cur.fetchone()
        cur.execute("SELECT id, email, full_name FROM users WHERE id = 'real-user-1'")
        user_row = cur.fetchone()
        cur.execute("SELECT id, name, status FROM biomat_projects WHERE id = 'real-project-1'")
        project_row = cur.fetchone()
        return org_row, user_row, project_row

    before = _snapshot()
    conn.close()

    second = _run_seed(env)
    assert second["status"] == "already_valid"

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT id, name, slug FROM organizations WHERE id = 'real-org-1'")
    org_row = cur.fetchone()
    cur.execute("SELECT id, email, full_name FROM users WHERE id = 'real-user-1'")
    user_row = cur.fetchone()
    cur.execute("SELECT id, name, status FROM biomat_projects WHERE id = 'real-project-1'")
    project_row = cur.fetchone()
    after = (org_row, user_row, project_row)
    conn.close()

    assert after == before, "A reconciliação do fixture E2E alterou dados de uma organização/usuário/projeto alheios."


def test_saida_do_seed_nunca_expoe_a_senha_sintetica_em_texto_claro(tmp_path):
    """Regressão real (2a execução Windows, e2e-output.log, commit f8490d9 -- ver
    TEST_EVIDENCE.md): a linha de log do global-setup continha
    `"password": "e2e-synthetic-password-123"` em texto plano -- mesmo sendo uma senha
    sintética/hardcoded (nunca usada para nenhum dado real), ela não deveria ter sido impressa
    de forma alguma; o relatório deve informar apenas identificação não secreta (email/ids) e o
    estado reconciliado de cada componente. Este teste roda o script real via subprocesso (como
    e2e/global-setup.ts o invoca) e verifica, a partir do stdout bruto e não só do JSON já
    parseado, que nenhuma variação da senha sintética aparece em nenhum lugar da saída."""
    env, _db_path, _storage_dir = _make_env(tmp_path, "no-password-leak")
    seed_env = dict(os.environ)
    seed_env.update(env)
    seed_env.setdefault("ENVIRONMENT", "test")
    seed_env.setdefault("API_SECRET_KEY", "test-secret-key-not-for-production-not-for-production")
    result = subprocess.run(
        [sys.executable, str(SEED_SCRIPT)],
        cwd=API_ROOT,
        env=seed_env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, (
        f"seed_e2e_user.py falhou (rc={result.returncode}).\nstdout={result.stdout}\nstderr={result.stderr}"
    )

    synthetic_password = "e2e-synthetic-password-123"
    assert synthetic_password not in result.stdout, "A senha sintética vazou em texto plano no stdout do seed."
    assert synthetic_password not in result.stderr, "A senha sintética vazou em texto plano no stderr do seed."

    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert "password" not in payload, "A saída JSON do seed ainda contém a chave 'password'."
    # A identificação não secreta continua presente (não é um teste de "não informar nada").
    assert payload["email"]
    assert set(payload["components"]) == {
        "user",
        "project",
        "recipe",
        "design_run",
        "job",
        "stl_artifact",
        "manifest",
    }


def test_download_endpoint_serviria_exatamente_os_bytes_cujo_sha_esta_persistido(tmp_path):
    """Cenário 8: prova, ao nível dos bytes reais em disco (o mesmo que
    routers/artifacts.py:download_artifact serve via storage.get(artifact.storage_key), sem
    nenhuma verificação adicional de hash no próprio endpoint), que Artifact.sha256 sempre bate
    com o conteúdo real do arquivo -- inclusive após uma reconciliação de fixture legado."""
    env, db_path, storage_dir = _make_env(tmp_path, "download-consistency")
    first = _run_seed(env)
    job_id = first["succeeded_job_id"]
    artifact_id, storage_key, _sha, _size = _fetch_stl_artifact(db_path, job_id)
    _corrupt_stl_to_legacy(db_path, storage_dir, artifact_id, storage_key)
    _run_seed(env)

    _artifact_id2, storage_key2, persisted_sha256, persisted_size_bytes = _fetch_stl_artifact(db_path, job_id)
    served_bytes = (storage_dir / storage_key2).read_bytes()  # exatamente o que o endpoint serviria
    assert hashlib.sha256(served_bytes).hexdigest() == persisted_sha256
    assert len(served_bytes) == persisted_size_bytes
