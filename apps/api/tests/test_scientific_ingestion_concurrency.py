"""Teste de concorrência real da fila de ingestão científica (Incremento 2.3, Rodada 2, Fase J
-- mutação "claim"). Mesmo padrão de test_geometry_job_concurrency.py: duas conexões
INDEPENDENTES (SessionLocal() direto, nunca a fixture db_session) competem simultaneamente por
`N_REQUESTS` solicitações na fila -- prova real de que `claim_next_queued_request` (SELECT ...
FOR UPDATE SKIP LOCKED) nunca deixa duas conexões reivindicarem a mesma solicitação.

Esta prova é o alvo de mutação "claim" exigido pela Fase J: remover `.with_for_update(
skip_locked=True)` de `claim_next_queued_request` faz este teste falhar de forma real (duas
"threads"/conexões reivindicando a mesma solicitação, ou uma contagem total diferente de
N_REQUESTS) -- não apenas um teste sequencial que passaria de qualquer forma."""
from __future__ import annotations

import threading

from biomatcad_api.db import SessionLocal
from biomatcad_api.models.scientific_data import RedistributionStatus, ScientificSource, SourceType
from biomatcad_api.models.scientific_ingestion import (
    IngestionRequestStatus,
    ScientificIngestionRequest,
)
from biomatcad_api.services.scientific_ingestion_service import claim_next_queued_request

from .factories import create_admin

N_REQUESTS = 24


def test_two_concurrent_dispatchers_never_claim_the_same_ingestion_request(engine):
    setup_session = SessionLocal()
    created_request_ids: list[str] = []
    created_source_id = None
    try:
        user = create_admin(setup_session, email="ingestion-concurrency1@biomatcad.example")
        source = ScientificSource(
            name="PubChem Concorrência", source_type=SourceType.DATABASE,
            redistribution_status=RedistributionStatus.UNKNOWN,
        )
        setup_session.add(source)
        setup_session.flush()
        created_source_id = source.id

        for i in range(N_REQUESTS):
            request = ScientificIngestionRequest(
                organization_id=user.organization_id,
                requested_by_user_id=user.id,
                connector_id="pubchem_pug_rest",
                source_id=source.id,
                external_ids=[str(1000 + i)],
                dry_run=True,  # dry_run=True apenas para nunca depender de rede caso algo mais
                              # processe esta fila concorrentemente -- este teste avalia SOMENTE
                              # o claim, nunca chama process_request.
                status=IngestionRequestStatus.QUEUED,
            )
            setup_session.add(request)
            setup_session.flush()
            created_request_ids.append(request.id)

        # COMMIT real -- essencial para que as conexões concorrentes abaixo enxerguem estas linhas.
        setup_session.commit()

        claimed_by: dict[str, list[str]] = {"dispatcher-a": [], "dispatcher-b": []}
        errors: list[Exception] = []

        def run_dispatcher(name: str) -> None:
            session = SessionLocal()
            try:
                while True:
                    request = claim_next_queued_request(session, dispatcher_id=name)
                    if request is None:
                        break
                    if request.id not in created_request_ids:
                        # Nunca reivindicar solicitações de outros testes/execuções -- se isso
                        # acontecer, para e conta apenas as nossas ao final.
                        continue
                    claimed_by[name].append(request.id)
            except Exception as exc:  # noqa: BLE001 -- captura ampla proposital, reportada no teste principal
                errors.append(exc)
            finally:
                session.close()

        t_a = threading.Thread(target=run_dispatcher, args=("dispatcher-a",))
        t_b = threading.Thread(target=run_dispatcher, args=("dispatcher-b",))
        t_a.start()
        t_b.start()
        t_a.join(timeout=30)
        t_b.join(timeout=30)

        assert not errors, f"Dispatcher(s) levantaram exceção: {errors}"

        all_claimed = claimed_by["dispatcher-a"] + claimed_by["dispatcher-b"]
        assert len(all_claimed) == N_REQUESTS, (
            f"Esperado {N_REQUESTS} solicitações reivindicadas ao todo, obtido {len(all_claimed)} "
            f"(a={len(claimed_by['dispatcher-a'])}, b={len(claimed_by['dispatcher-b'])})"
        )
        assert len(set(all_claimed)) == N_REQUESTS, (
            "Pelo menos uma solicitação foi reivindicada por AMBOS os dispatchers -- "
            "falha de exclusão mútua"
        )
        assert set(all_claimed) == set(created_request_ids)

        verify_session = SessionLocal()
        try:
            for name, ids in claimed_by.items():
                for request_id in ids:
                    row = verify_session.get(ScientificIngestionRequest, request_id)
                    assert row is not None
                    assert row.status == IngestionRequestStatus.RUNNING
                    assert row.claimed_by_dispatcher_id == name
        finally:
            verify_session.close()
    finally:
        cleanup_session = SessionLocal()
        try:
            if created_request_ids:
                cleanup_session.query(ScientificIngestionRequest).filter(
                    ScientificIngestionRequest.id.in_(created_request_ids)
                ).delete(synchronize_session=False)
            if created_source_id:
                cleanup_session.query(ScientificSource).filter(
                    ScientificSource.id == created_source_id
                ).delete(synchronize_session=False)
            cleanup_session.commit()
        finally:
            cleanup_session.close()
        setup_session.close()
