#!/usr/bin/env python3
"""Semeia (ou reconcilia) um usuário/organização/projeto/receita/job determinísticos para o
teste E2E (Playwright) do frontend (Incremento 2.1.1, item 12), incluindo um job já 'succeeded'
(via FakeWorkerClient rotulado, nunca PicoGK real) para permitir verificar a página de detalhe
do job / visualizador 3D sem depender do worker real.

Não há endpoint público de registro nesta versão da API (ver routers/auth.py) -- por isso este
script cria os dados diretamente via os modelos SQLAlchemy, como os testes pytest já fazem.

RECONCILIAÇÃO (correção real, rodada "cobertura E2E do visualizador 3D", execução Windows real
20260807-001756): a versão anterior deste script tinha um `if existing_user is not None: return`
logo no início -- em QUALQUER banco onde o script já tivesse rodado uma vez (como o Postgres
real do usuário, que já tinha sido semeado em rodadas anteriores, ANTES da correção do STL
vazio/hash fake), essa saída antecipada significava que o job/Artifact/Manifest legados
(STL ASCII vazio, stl_sha256="0"*64) NUNCA eram corrigidos -- o script só imprimia
`{"status": "already_seeded", ...}` e retornava, deixando o fixture quebrado exatamente como
estava. Isso foi confirmado pela execução real do usuário: `global-setup` relatou
"already_seeded", e as 12 falhas do viewer.spec.ts foram TODAS por ausência do estado "ready"
(viewer-triangle-count nunca aparece) -- consistente com o StlViewer rejeitando o job por
ArtifactChecksumMismatchError contra o hash fake legado, nunca uma regressão nos testes ou no
componente.

Corrigido: o script agora é uma sequência de passos "get-or-create" totalmente idempotentes e
reconciliáveis -- cada camada (organização, usuário, projeto, receita, design_run, job,
artefato STL, artefato/registro de manifesto) é localizada exclusivamente pelo fixture E2E (via
o e-mail único do usuário e a `idempotency_key` única do design_run, nunca por heurística de
nome) e criada apenas se ausente, ou reparada apenas se o conteúdo persistido divergir do
esperado -- nunca duplicada, e nunca tocando em nenhum dado de outro usuário/projeto/job real
que porventura exista no mesmo banco.

Uso:
    DATABASE_URL=postgresql+psycopg2://... python3 scripts/seed_e2e_user.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

E2E_EMAIL = "e2e-playwright@biomatcad.example"
E2E_PASSWORD = "e2e-synthetic-password-123"
# Âncora determinística e ÚNICA (restrição uq_design_run_org_idempotency) usada para localizar
# -- nunca adivinhar por nome -- exclusivamente o design_run/job pertencentes a este fixture,
# mesmo em reexecuções contra um banco que já tenha outros dados reais de pesquisa.
E2E_IDEMPOTENCY_KEY = "e2e-preseeded-succeeded"
E2E_DISPATCHER_ID = "e2e-seed-script"


def _expected_stl_bytes() -> bytes:
    """Tetraedro sintético ASCII válido (4 facets, coordenadas manuais simples -- SEM nenhuma
    relação com PicoGK/TopologyProviders/receitas científicas, é apenas um fixture de teste),
    fonte única da verdade tanto para a criação quanto para a reconciliação do Artifact STL."""
    return (
        b"solid e2e-seed-tetrahedron\n"
        b"facet normal 0 0 -1\n"
        b"  outer loop\n"
        b"    vertex 0 0 0\n"
        b"    vertex 10 0 0\n"
        b"    vertex 0 10 0\n"
        b"  endloop\n"
        b"endfacet\n"
        b"facet normal 0 -1 0\n"
        b"  outer loop\n"
        b"    vertex 0 0 0\n"
        b"    vertex 10 0 0\n"
        b"    vertex 0 0 10\n"
        b"  endloop\n"
        b"endfacet\n"
        b"facet normal -1 0 0\n"
        b"  outer loop\n"
        b"    vertex 0 0 0\n"
        b"    vertex 0 10 0\n"
        b"    vertex 0 0 10\n"
        b"  endloop\n"
        b"endfacet\n"
        b"facet normal 0.577 0.577 0.577\n"
        b"  outer loop\n"
        b"    vertex 10 0 0\n"
        b"    vertex 0 10 0\n"
        b"    vertex 0 0 10\n"
        b"  endloop\n"
        b"endfacet\n"
        b"endsolid e2e-seed-tetrahedron\n"
    )


def _expected_metrics() -> dict:
    return {
        "bounding_box_mm": [[0, 0, 0], [10, 10, 10]],
        "volume_mm3": 400.0,
        "porosity_pct_measured": 60.0,
        "surface_area_mm2": 950.5,
        "vertex_count_unique": 168,
        "triangle_count": 100,
        "is_watertight": True,
        "stl_reload_validation_passed": True,
    }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def main() -> None:
    os.environ.setdefault("ENVIRONMENT", "test")
    os.environ.setdefault("API_SECRET_KEY", "test-secret-key-not-for-production")

    from biomatcad_api import models  # noqa: F401
    from biomatcad_api.db import Base, SessionLocal, engine
    from biomatcad_api.models.artifact import Artifact, ArtifactKind, ArtifactManifest
    from biomatcad_api.models.geometry_job import DesignRun, GeometryJob, JobStatus
    from biomatcad_api.models.geometry_recipe import GeometryRecipe, RecipeStatus
    from biomatcad_api.models.organization import Organization
    from biomatcad_api.models.project import BioMatProject
    from biomatcad_api.models.user import User
    from biomatcad_api.security import hash_password
    from biomatcad_api.services.geometry_job_service import dispatch_job
    from biomatcad_api.services.recipe_service import canonicalize_recipe, validate_and_canonicalize
    from biomatcad_api.services.storage import LocalStorageAdapter, sha256_of_bytes
    from biomatcad_api.services.worker_client import WorkerResult

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    components: dict[str, str] = {}

    # ---- 1. Organização + usuário (âncora: e-mail único) ----
    user = db.query(User).filter(User.email == E2E_EMAIL).first()
    if user is None:
        org = Organization(name="Org E2E Playwright", slug="org-e2e-playwright")
        db.add(org)
        db.flush()
        user = User(
            organization_id=org.id,
            email=E2E_EMAIL,
            full_name="Usuário E2E Playwright",
            hashed_password=hash_password(E2E_PASSWORD),
            role="researcher",
        )
        db.add(user)
        db.commit()
        components["user"] = "created"
    else:
        existing_org = db.get(Organization, user.organization_id)
        if existing_org is None:
            raise RuntimeError(
                f"User E2E ({user.id}) referencia organization_id={user.organization_id!r} que não "
                "existe -- banco inconsistente, requer investigação manual (fora do escopo de "
                "reconciliação automática deste script: não fabricamos uma organização nova para "
                "um usuário já existente, isso quebraria a referência)."
            )
        org = existing_org
        components["user"] = "already_valid"

    # ---- 2. Design run (âncora: idempotency_key única por organização) -- localiza projeto e
    #         receita a partir dele, nunca por nome (nomes não são únicos no schema). ----
    design_run = (
        db.query(DesignRun)
        .filter(DesignRun.organization_id == org.id, DesignRun.idempotency_key == E2E_IDEMPOTENCY_KEY)
        .first()
    )

    if design_run is None:
        project = BioMatProject(organization_id=org.id, owner_user_id=user.id, name="Projeto E2E (pré-semeado)")
        db.add(project)
        db.flush()
        components["project"] = "created"

        recipe_body = {
            "schema_version": "1.0.0",
            "domain": {"shape": "block", "dimensions_mm": {"kind": "block", "x_mm": 10, "y_mm": 10, "z_mm": 10}},
            "topology": {
                "kind": "gyroid",
                "cell_size_mm": 2.0,
                "wall_thickness_mm": 0.4,
                "isovalue": 0.0,
                "target_porosity_pct": 60,
            },
            "resolution": {"voxel_size_mm": 0.2},
            "mode": "preview",
            "seed": 42,
            "compute_limits": {"max_duration_seconds": 60, "max_memory_mb": 512, "max_voxel_count": 1000000},
            "output_formats": ["stl"],
        }
        canonical_str, checksum = validate_and_canonicalize(recipe_body)
        recipe = GeometryRecipe(
            organization_id=org.id,
            project_id=project.id,
            created_by_user_id=user.id,
            name="Receita E2E (pré-semeada)",
            schema_version="1.0.0",
            canonical_json=json.loads(canonical_str),
            checksum_sha256=checksum,
            version=1,
            status=RecipeStatus.VALIDATED,
        )
        db.add(recipe)
        db.flush()
        components["recipe"] = "created"

        design_run = DesignRun(
            organization_id=org.id,
            project_id=project.id,
            recipe_id=recipe.id,
            material_id=None,
            created_by_user_id=user.id,
            idempotency_key=E2E_IDEMPOTENCY_KEY,
        )
        db.add(design_run)
        db.commit()
        components["design_run"] = "created"
    else:
        existing_project = db.get(BioMatProject, design_run.project_id)
        existing_recipe = db.get(GeometryRecipe, design_run.recipe_id)
        if existing_project is None or existing_recipe is None:
            raise RuntimeError(
                f"DesignRun E2E ({design_run.id}) referencia project_id={design_run.project_id!r} "
                f"e/ou recipe_id={design_run.recipe_id!r} ausentes -- banco inconsistente, requer "
                "investigação manual."
            )
        project = existing_project
        recipe = existing_recipe
        components["project"] = "already_valid"
        components["recipe"] = "already_valid"
        components["design_run"] = "already_valid"

    # ---- 3. Job (âncora: único por design_run neste fixture -- sempre attempt_number=1) ----
    job = (
        db.query(GeometryJob)
        .filter(GeometryJob.design_run_id == design_run.id)
        .order_by(GeometryJob.attempt_number.asc())
        .first()
    )
    if job is None:
        job = GeometryJob(design_run_id=design_run.id, attempt_number=1, status=JobStatus.QUEUED)
        db.add(job)
        db.commit()
        components["job"] = "created"
    else:
        components["job"] = "already_valid"

    settings_storage_dir = Path(os.environ.get("ARTIFACT_STORAGE_DIR", "./data/artifacts"))
    storage = LocalStorageAdapter(settings_storage_dir)

    class _FakeWorkerClientForE2ESeed:
        """Test double explícito -- NÃO executa PicoGK real (ver
        apps/geometry-worker/WORKER_STATUS.md). Usado apenas para que a página de detalhe do
        job e o visualizador 3D tenham um job 'succeeded' real para exibir durante o E2E, já
        que a geometria real do PicoGK é o próprio objeto do bloqueio parcial deste incremento
        e é testada separadamente."""

        def execute(self, *, recipe_canonical, job_id, output_dir, cancel_check=None, on_process_started=None):
            output_dir.mkdir(parents=True, exist_ok=True)
            stl_bytes = _expected_stl_bytes()
            stl_path = output_dir / "e2e-seed.stl"
            stl_path.write_bytes(stl_bytes)
            return WorkerResult(
                stl_path=stl_path,
                thumbnail_path=None,
                metrics=_expected_metrics(),
                worker_version="0.1.0-e2e-seed-fake",
                dotnet_version="9.0.0",
                picogk_version="2.2.0",
                duration_seconds=0.1,
                stl_sha256=hashlib.sha256(stl_bytes).hexdigest(),
                platform="fake-platform-for-e2e-seed",
            )

    # ---- 4. Garante que o job chega a SUCCEEDED. NUNCA usa claim_next_queued_job (que
    #         reivindicaria o job mais antigo da FILA INTEIRA do sistema -- em um banco real de
    #         pesquisa, isso arriscaria roubar e fake-executar um job de outro usuário). O claim
    #         abaixo é restrito exclusivamente a job.id, via WHERE ... AND id = :job_id. ----
    if job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
        job.status = JobStatus.QUEUED
        job.error_code = None
        job.error_message = None
        job.attempt_number += 1
        db.commit()
        components["job"] = "repaired"
    elif job.status == JobStatus.RUNNING:
        # Uma execução anterior deste MESMO script foi interrompida antes de concluir --  como
        # este job pertence exclusivamente ao fixture E2E (nunca reivindicado por um dispatcher
        # de produção real, que processaria a receita de verdade e nunca esta identidade
        # sintética de job), é seguro recolocá-lo na fila para nova tentativa.
        job.status = JobStatus.QUEUED
        job.claimed_by_dispatcher_id = None
        job.claimed_at = None
        job.heartbeat_at = None
        job.started_at = None
        db.commit()
        components["job"] = "repaired"

    if job.status == JobStatus.QUEUED:
        claimed = (
            db.query(GeometryJob)
            .filter(GeometryJob.id == job.id, GeometryJob.status == JobStatus.QUEUED)
            .with_for_update(skip_locked=True)
            .first()
        )
        if claimed is None:
            job_id_for_refetch = job.id
            db.expire(job)
            refetched_job = db.get(GeometryJob, job_id_for_refetch)
            assert refetched_job is not None, f"GeometryJob {job_id_for_refetch} desapareceu durante a reivindicação."
            job = refetched_job
        else:
            now = _utcnow()
            claimed.status = JobStatus.RUNNING
            claimed.started_at = now
            claimed.claimed_by_dispatcher_id = E2E_DISPATCHER_ID
            claimed.claimed_at = now
            claimed.heartbeat_at = now
            claimed.progress_pct = 5
            db.commit()
            db.refresh(claimed)
            job = claimed

    if job.status == JobStatus.RUNNING:
        job = dispatch_job(
            db,
            job_id=job.id,
            worker_client=_FakeWorkerClientForE2ESeed(),
            storage=storage,
            output_dir=settings_storage_dir / "_work" / job.id,
            repo_root=REPO_ROOT,
        )
        if components.get("job") != "created":
            components["job"] = "repaired"

    if job.status != JobStatus.SUCCEEDED:
        raise RuntimeError(
            f"Job E2E {job.id} não chegou a SUCCEEDED após reconciliação (estado final: "
            f"{job.status.value}) -- verifique error_code/error_message no banco."
        )

    # ---- 5. Reconcilia o Artifact STL: garante que os BYTES reais no storage e o
    #         Artifact.sha256/size_bytes persistidos batem exatamente com o fixture esperado.
    #         Cobre: artefato ausente, arquivo físico ausente, e o defeito legado confirmado
    #         (STL vazio + stl_sha256="0"*64) -- qualquer conteúdo que não seja BYTE A BYTE o
    #         tetraedro esperado é tratado como precisando reparo, nunca aceito por acidente. ----
    expected_bytes = _expected_stl_bytes()
    expected_sha256 = hashlib.sha256(expected_bytes).hexdigest()
    stl_key = f"jobs/{job.id}/scaffold.stl"

    stl_artifact = (
        db.query(Artifact).filter(Artifact.geometry_job_id == job.id, Artifact.kind == ArtifactKind.STL).first()
    )

    file_matches = False
    if storage.exists(stl_key):
        try:
            file_matches = storage.get(stl_key) == expected_bytes
        except OSError:
            file_matches = False
    if not file_matches:
        storage.put(stl_key, expected_bytes)

    if stl_artifact is None:
        stl_artifact = Artifact(
            geometry_job_id=job.id,
            kind=ArtifactKind.STL,
            storage_key=stl_key,
            sha256=expected_sha256,
            size_bytes=len(expected_bytes),
        )
        db.add(stl_artifact)
        db.commit()
        db.refresh(stl_artifact)
        components["stl_artifact"] = "created"
    else:
        db_matches = (
            stl_artifact.storage_key == stl_key
            and stl_artifact.sha256 == expected_sha256
            and stl_artifact.size_bytes == len(expected_bytes)
        )
        if not db_matches:
            stl_artifact.storage_key = stl_key
            stl_artifact.sha256 = expected_sha256
            stl_artifact.size_bytes = len(expected_bytes)
            db.commit()
            db.refresh(stl_artifact)
        components["stl_artifact"] = "already_valid" if (db_matches and file_matches) else "repaired"

    # ---- 6. Reconcilia ArtifactManifest / Artifact(MANIFEST): patch cirúrgico apenas dos
    #         campos relacionados ao STL (stl_sha256 de topo + a entrada "stl" dentro de
    #         "artifacts"), preservando IDs e todo o restante do conteúdo do manifesto -- nunca
    #         recria do zero (evita duplicar e evita perder git_commit/topology_provider/etc.
    #         de um manifesto já existente e correto no resto). ----
    manifest_row = db.query(ArtifactManifest).filter(ArtifactManifest.geometry_job_id == job.id).first()
    manifest_artifact = (
        db.query(Artifact).filter(Artifact.geometry_job_id == job.id, Artifact.kind == ArtifactKind.MANIFEST).first()
    )

    if manifest_row is None:
        # Não deveria acontecer para um job SUCCEEDED (dispatch_job sempre monta o manifesto na
        # mesma transação lógica) -- se acontecer mesmo assim (banco truncado externamente),
        # sinaliza claramente em vez de fabricar um manifesto incompleto por conta própria.
        components["manifest"] = "missing_requires_manual_review"
    else:
        original_dict = dict(manifest_row.manifest_json or {})
        original_canonical = canonicalize_recipe(original_dict)

        patched_dict = dict(original_dict)
        patched_dict["stl_sha256"] = stl_artifact.sha256
        artifacts_list = list(patched_dict.get("artifacts", []))
        stl_entry = {
            "kind": ArtifactKind.STL.value,
            "logical_path": stl_artifact.storage_key,
            "size_bytes": stl_artifact.size_bytes,
            "sha256": stl_artifact.sha256,
        }
        new_artifacts_list = []
        found = False
        for entry in artifacts_list:
            if isinstance(entry, dict) and entry.get("kind") == ArtifactKind.STL.value:
                new_artifacts_list.append(stl_entry)
                found = True
            else:
                new_artifacts_list.append(entry)
        if not found:
            new_artifacts_list.append(stl_entry)
        patched_dict["artifacts"] = new_artifacts_list

        patched_canonical = canonicalize_recipe(patched_dict)
        if patched_canonical == original_canonical:
            components["manifest"] = "already_valid"
        else:
            new_manifest_sha256 = sha256_of_bytes(patched_canonical.encode("utf-8"))
            manifest_row.manifest_json = json.loads(patched_canonical)
            manifest_row.manifest_sha256 = new_manifest_sha256
            db.commit()

            manifest_key = manifest_artifact.storage_key if manifest_artifact is not None else f"jobs/{job.id}/manifest.json"
            storage.put(manifest_key, patched_canonical.encode("utf-8"))
            if manifest_artifact is not None:
                manifest_artifact.sha256 = new_manifest_sha256
                manifest_artifact.size_bytes = len(patched_canonical.encode("utf-8"))
                db.commit()
            else:
                db.add(
                    Artifact(
                        geometry_job_id=job.id,
                        kind=ArtifactKind.MANIFEST,
                        storage_key=manifest_key,
                        sha256=new_manifest_sha256,
                        size_bytes=len(patched_canonical.encode("utf-8")),
                    )
                )
                db.commit()
            components["manifest"] = "repaired"

    # Status agregado de topo -- prioridade: qualquer componente precisando revisão manual >
    # qualquer componente reparado > qualquer componente criado > tudo já válido. O detalhe
    # completo, por componente, vai em "components".
    component_values = set(components.values())
    if "missing_requires_manual_review" in component_values:
        overall_status = "needs_manual_review"
    elif "repaired" in component_values:
        overall_status = "repaired"
    elif "created" in component_values:
        overall_status = "created"
    else:
        overall_status = "already_valid"

    # NUNCA imprimir a senha sintética (nem qualquer outro segredo) na saída deste script --
    # bug real encontrado na 2a execução Windows real (e2e-output.log, ver TEST_EVIDENCE.md):
    # a senha (mesmo sendo sintética/hardcoded, e_PASSWORD = "e2e-synthetic-password-123")
    # aparecia em texto plano no log do global-setup do E2E. Nenhum consumidor real depende
    # deste campo -- viewer.spec.ts e vertical.spec.ts já têm sua própria cópia hardcoded de
    # E2E_PASSWORD, e global-setup.ts não faz parse do campo "password" desta saída (apenas
    # verifica o exit code / lê "status" para log). O relatório informa somente identificação
    # não secreta (email/ids) e o estado reconciliado de cada componente.
    print(
        json.dumps(
            {
                "status": overall_status,
                "email": E2E_EMAIL,
                "project_id": project.id,
                "recipe_id": recipe.id,
                "succeeded_job_id": job.id,
                "components": components,
            }
        )
    )
    db.close()


if __name__ == "__main__":
    main()
