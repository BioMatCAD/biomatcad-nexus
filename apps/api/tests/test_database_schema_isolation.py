"""Regressão real (rodada Voronoi 20260806-133141, itens 10-17): prova que a suíte de testes
roda em ISOLAMENTO real de qualquer dado pré-existente no banco -- mesmo quando TEST_DATABASE_URL
aponta para a MESMA instância Postgres usada para validação manual real (gate HTTP real,
dispatcher real via scripts/Run-VoronoiWindowsValidation*.ps1).

Contexto (ver TEST_EVIDENCE.md, seção da rodada 20260806-133141): a execução real Windows desta
rodada relatou 3 falhas de pytest genuinamente causadas por contaminação: um teste de
cancelamento reivindicou um job REAL antigo (8f572e95...), um teste de concorrência reivindicou
32 jobs em vez dos 24 que ele mesmo criou, e um teste de observabilidade encontrou 10 jobs
"processing" que não eram seus. Isso não era uma falha do padrão "uma transação por teste,
rollback ao final" (usado pela fixture `db_session`) -- esse padrão sempre funcionou para o que
CADA teste escreve. A causa real é que linhas JÁ COMMITADAS por uma sessão totalmente diferente
(a validação manual real, via HTTP, fora de qualquer transação de teste) continuam visíveis a
qualquer NOVA conexão/transação contra o MESMO banco -- inclusive para consultas legitimamente
amplas que em produção precisam mesmo ser amplas (claim_next_queued_job deve poder reivindicar
QUALQUER job da fila, de qualquer organização; restringir isso quebraria o comportamento real
de um dispatcher).

A correção real (conftest.py) roda a suíte inteira dentro de um SCHEMA Postgres exclusivo e
efêmero (nunca "public"), injetado via `options=-c search_path=...` na própria connection
string -- efetivo para QUALQUER conexão aberta a partir de DATABASE_URL, incluindo
`biomatcad_api.db.SessionLocal` usado por test_geometry_job_concurrency.py com conexões
verdadeiramente independentes.

Este arquivo prova essa garantia de forma automatizada e permanente: insere linhas
"contaminantes" REAIS diretamente no schema "public" (bypassando conftest.py -- simula
literalmente uma validação manual anterior), depois confirma que claim_next_queued_job e as
contagens de observabilidade (executadas através da fixture `db_session`, que é
schema-isolada) NUNCA veem essas linhas -- e que elas permanecem intocadas no schema "public"
depois (nunca apagadas, nunca reivindicadas, nunca modificadas -- item 13: jamais resolver isto
apagando o banco de pesquisa real do usuário).

Em SQLite (o default local, sem conceito de schema/search_path e sem nenhum dado real
compartilhado por padrão), estes testes são pulados -- a garantia que eles provam só faz
sentido, e só é necessária, contra um Postgres real potencialmente compartilhado.
"""
from __future__ import annotations

import json
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from biomatcad_api.db import Base
from biomatcad_api.models.geometry_job import DesignRun, GeometryJob, JobStatus
from biomatcad_api.models.geometry_recipe import GeometryRecipe, RecipeStatus
from biomatcad_api.models.project import BioMatProject
from biomatcad_api.services.geometry_job_service import claim_next_queued_job
from biomatcad_api.services.observability_service import check_queue
from biomatcad_api.services.recipe_service import validate_and_canonicalize

from .conftest import _IS_POSTGRES_TEST_DB, _RAW_TEST_DATABASE_URL
from .factories import create_researcher

pytestmark = pytest.mark.skipif(
    not _IS_POSTGRES_TEST_DB,
    reason="isolamento de schema só se aplica/é necessário contra Postgres real (ver conftest.py)",
)

GOOD_RECIPE_BODY = {
    "schema_version": "1.0.0",
    "domain": {"shape": "block", "dimensions_mm": {"kind": "block", "x_mm": 10, "y_mm": 10, "z_mm": 10}},
    "topology": {"kind": "gyroid", "cell_size_mm": 2.0, "wall_thickness_mm": 0.4, "isovalue": 0.0, "target_porosity_pct": 60},
    "resolution": {"voxel_size_mm": 0.2},
    "mode": "preview",
    "seed": 42,
    "compute_limits": {"max_duration_seconds": 60, "max_memory_mb": 512, "max_voxel_count": 1000000},
    "output_formats": ["stl"],
}


class _PublicSchemaContamination:
    """Escreve e limpa linhas REAIS (commitadas de verdade) no schema "public" -- uma conexão
    totalmente à parte da fixture `engine`/`db_session` (que já está isolada em um schema
    próprio), usando a URL SEM o `search_path` customizado. Representa, o mais fielmente
    possível dentro deste sandbox, uma validação manual anterior que já rodou de verdade contra
    o banco de pesquisa do usuário."""

    def __init__(self) -> None:
        self.engine = create_engine(_RAW_TEST_DATABASE_URL)
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, future=True)
        self.job_ids: list[tuple[str, str]] = []

    def seed(self, *, n_running: int, n_queued: int) -> None:
        session = self.Session()
        try:
            # E-mail/slug único por chamada (uuid4) -- este helper pode ser instanciado por
            # MAIS DE UM teste na mesma sessão de suíte, todos escrevendo no MESMO schema
            # "public" físico (que nunca é limpo entre testes, propositalmente, para provar
            # que o isolamento vem do lado do teste/schema, não de uma limpeza manual aqui).
            import uuid as _uuid

            unique_email = f"contaminacao-real-{_uuid.uuid4().hex}@biomatcad.example"
            user = create_researcher(session, email=unique_email)
            project = BioMatProject(organization_id=user.organization_id, owner_user_id=user.id, name="Projeto Real Pre-Existente")
            session.add(project)
            session.flush()
            canonical_str, checksum = validate_and_canonicalize(GOOD_RECIPE_BODY)
            recipe = GeometryRecipe(
                organization_id=user.organization_id, project_id=project.id, created_by_user_id=user.id,
                name="Receita Real Pre-Existente", schema_version=GOOD_RECIPE_BODY["schema_version"],
                canonical_json=json.loads(canonical_str), checksum_sha256=checksum, version=1,
                status=RecipeStatus.VALIDATED,
            )
            session.add(recipe)
            session.flush()

            statuses = [JobStatus.RUNNING] * n_running + [JobStatus.QUEUED] * n_queued
            for i, status in enumerate(statuses):
                dr = DesignRun(
                    organization_id=user.organization_id, project_id=project.id, recipe_id=recipe.id,
                    material_id=None, created_by_user_id=user.id,
                    idempotency_key=f"contaminacao-real-{os.getpid()}-{i}",
                )
                session.add(dr)
                session.flush()
                job = GeometryJob(design_run_id=dr.id, attempt_number=1, status=status)
                session.add(job)
                session.flush()
                self.job_ids.append((job.id, status.value))
            session.commit()
        finally:
            session.close()

    def assert_untouched(self) -> None:
        session = self.Session()
        try:
            for job_id, expected_status in self.job_ids:
                row = session.get(GeometryJob, job_id)
                assert row is not None, f"job real pre-existente {job_id} desapareceu do schema public"
                assert row.status.value == expected_status, (
                    f"job real pre-existente {job_id} teve status alterado por um teste isolado: "
                    f"{row.status.value} (esperado {expected_status})"
                )
        finally:
            session.close()

    def dispose(self) -> None:
        session = self.Session()
        try:
            for job_id, _ in self.job_ids:
                row = session.get(GeometryJob, job_id)
                if row is not None:
                    session.delete(row)
            session.commit()
        finally:
            session.close()
        self.engine.dispose()


@pytest.fixture()
def public_schema_contamination():
    contamination = _PublicSchemaContamination()
    yield contamination
    contamination.dispose()


def test_claim_next_queued_job_nunca_reivindica_jobs_pre_existentes_do_schema_public(
    db_session, public_schema_contamination
):
    """Reproduz o sintoma exato reportado (rodada 20260806-133141): "concorrência reivindicou 32
    jobs em vez dos 24 criados" -- prova que jobs QUEUED pré-existentes no schema "public" (uma
    validação manual anterior simulada) nunca são vistos por claim_next_queued_job quando
    chamado através da sessão isolada do teste (`db_session`, schema exclusivo)."""
    public_schema_contamination.seed(n_running=3, n_queued=4)

    user = create_researcher(db_session, email="cenario-isolado@biomatcad.example")
    project = BioMatProject(organization_id=user.organization_id, owner_user_id=user.id, name="Projeto Isolado")
    db_session.add(project)
    db_session.flush()
    canonical_str, checksum = validate_and_canonicalize(GOOD_RECIPE_BODY)
    recipe = GeometryRecipe(
        organization_id=user.organization_id, project_id=project.id, created_by_user_id=user.id,
        name="Receita Isolada", schema_version=GOOD_RECIPE_BODY["schema_version"],
        canonical_json=json.loads(canonical_str), checksum_sha256=checksum, version=1,
        status=RecipeStatus.VALIDATED,
    )
    db_session.add(recipe)
    db_session.flush()

    created_job_ids = []
    for i in range(3):
        dr = DesignRun(
            organization_id=user.organization_id, project_id=project.id, recipe_id=recipe.id,
            material_id=None, created_by_user_id=user.id, idempotency_key=f"cenario-isolado-{i}",
        )
        db_session.add(dr)
        db_session.flush()
        job = GeometryJob(design_run_id=dr.id, attempt_number=1, status=JobStatus.QUEUED)
        db_session.add(job)
        db_session.flush()
        created_job_ids.append(job.id)

    claimed = []
    while True:
        job = claim_next_queued_job(db_session, dispatcher_id="teste-isolado")
        if job is None:
            break
        claimed.append(job.id)

    assert len(claimed) == 3, (
        f"esperado reivindicar exatamente os 3 jobs criados por este teste, obtido {len(claimed)} "
        "-- indica contaminação por jobs queued pré-existentes no schema public"
    )
    assert set(claimed) == set(created_job_ids)

    public_schema_contamination.assert_untouched()


def test_check_queue_nao_conta_jobs_running_pre_existentes_do_schema_public(
    db_session, public_schema_contamination
):
    """Reproduz o sintoma exato reportado: "observabilidade encontrou 10 jobs processing" --
    prova que check_queue (usado pelo endpoint de observabilidade) nunca conta jobs RUNNING
    pré-existentes no schema "public" quando chamado através da sessão isolada do teste."""
    public_schema_contamination.seed(n_running=6, n_queued=0)

    status = check_queue(db_session)
    assert status.processing_count == 0, (
        f"esperado 0 jobs 'processing' na sessão isolada do teste (nenhum job real foi criado "
        f"nesta sessão), obtido {status.processing_count} -- indica contaminação por jobs "
        "running pré-existentes no schema public"
    )

    public_schema_contamination.assert_untouched()
