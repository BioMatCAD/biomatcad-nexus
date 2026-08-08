"""Testes da API administrativa de ingestão científica (Incremento 2.3, Rodada 2, Fase H).

Cobre a superfície HTTP (submissão, dry-run, status, listagem, conflitos, cancelamento,
painel de conectores) e sua autorização admin/curador-only -- a lógica de negócio em si já é
coberta por test_scientific_ingestion_service.py; aqui provamos apenas que as rotas expõem
essa lógica corretamente e nunca a um usuário comum."""
from __future__ import annotations

from biomatcad_api.models.scientific_data import RedistributionStatus, ScientificSource, SourceType
from tests.factories import (
    ADMIN_PASSWORD,
    RESEARCHER_PASSWORD,
    create_admin,
    create_researcher,
    login,
)


def _admin_header(client, db_session, email="sci-ing-admin@biomatcad.example"):
    admin = create_admin(db_session, email=email)
    token = login(client, email, ADMIN_PASSWORD)
    return {"Authorization": f"Bearer {token}"}, admin


def _researcher_header(client, db_session, email="sci-ing-researcher@biomatcad.example"):
    user = create_researcher(db_session, email=email)
    token = login(client, email, RESEARCHER_PASSWORD)
    return {"Authorization": f"Bearer {token}"}, user


def _make_source(db_session) -> ScientificSource:
    source = ScientificSource(
        name="PubChem", source_type=SourceType.DATABASE, redistribution_status=RedistributionStatus.UNKNOWN
    )
    db_session.add(source)
    db_session.commit()
    return source


# --- painel de conectores: admin/curador apenas ---------------------------------------------


def test_connectors_panel_requires_admin(client, db_session):
    _, _ = _researcher_header(client, db_session)
    headers, _ = _researcher_header(client, db_session, email="researcher-conn@biomatcad.example")
    resp = client.get("/api/v1/scientific-ingestion/connectors", headers=headers)
    assert resp.status_code == 403


def test_connectors_panel_lists_implemented_and_planned(client, db_session):
    headers, _ = _admin_header(client, db_session)
    resp = client.get("/api/v1/scientific-ingestion/connectors", headers=headers)
    assert resp.status_code == 200
    by_id = {c["connector_id"]: c for c in resp.json()}
    assert by_id["pubchem_pug_rest"]["status"] == "implemented"
    assert by_id["chebi"]["status"] == "planned"


# --- submissão -----------------------------------------------------------------------------


def test_submit_request_requires_admin(client, db_session):
    headers, _ = _researcher_header(client, db_session)
    source = _make_source(db_session)
    resp = client.post(
        "/api/v1/scientific-ingestion/requests",
        headers=headers,
        json={"connector_id": "pubchem_pug_rest", "source_id": source.id, "external_ids": ["2244"]},
    )
    assert resp.status_code == 403


def test_submit_request_queues_and_defaults_dry_run_false(client, db_session):
    headers, _ = _admin_header(client, db_session)
    source = _make_source(db_session)
    resp = client.post(
        "/api/v1/scientific-ingestion/requests",
        headers=headers,
        json={"connector_id": "pubchem_pug_rest", "source_id": source.id, "external_ids": ["2244", "702"]},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["dry_run"] is False
    assert body["external_ids"] == ["2244", "702"]


def test_submit_request_rejects_more_than_10_cids(client, db_session):
    headers, _ = _admin_header(client, db_session)
    source = _make_source(db_session)
    resp = client.post(
        "/api/v1/scientific-ingestion/requests",
        headers=headers,
        json={
            "connector_id": "pubchem_pug_rest", "source_id": source.id,
            "external_ids": [str(i) for i in range(1, 12)],
        },
    )
    assert resp.status_code == 422  # violação do max_length do schema Pydantic


def test_submit_request_rejects_unknown_connector(client, db_session):
    headers, _ = _admin_header(client, db_session)
    source = _make_source(db_session)
    resp = client.post(
        "/api/v1/scientific-ingestion/requests",
        headers=headers,
        json={"connector_id": "chebi", "source_id": source.id, "external_ids": ["100"]},
    )
    assert resp.status_code == 400
    assert "chebi" in resp.json()["error"]["message"]


def test_dry_run_endpoint_forces_dry_run_true(client, db_session):
    headers, _ = _admin_header(client, db_session)
    source = _make_source(db_session)
    resp = client.post(
        "/api/v1/scientific-ingestion/requests/dry-run",
        headers=headers,
        json={
            "connector_id": "pubchem_pug_rest", "source_id": source.id,
            "external_ids": ["2244"], "dry_run": False,  # ignorado deliberadamente
        },
    )
    assert resp.status_code == 201
    assert resp.json()["dry_run"] is True


# --- status/listagem/conflitos/cancelamento -------------------------------------------------


def test_get_request_status_and_list(client, db_session):
    headers, _ = _admin_header(client, db_session)
    source = _make_source(db_session)
    created = client.post(
        "/api/v1/scientific-ingestion/requests",
        headers=headers,
        json={"connector_id": "pubchem_pug_rest", "source_id": source.id, "external_ids": ["2244"]},
    ).json()

    resp = client.get(f"/api/v1/scientific-ingestion/requests/{created['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]

    resp_list = client.get("/api/v1/scientific-ingestion/requests", headers=headers)
    assert resp_list.status_code == 200
    assert any(r["id"] == created["id"] for r in resp_list.json())


def test_get_request_status_404_for_nonexistent(client, db_session):
    headers, _ = _admin_header(client, db_session)
    resp = client.get("/api/v1/scientific-ingestion/requests/does-not-exist", headers=headers)
    assert resp.status_code == 404


def test_get_request_status_requires_admin(client, db_session):
    admin_headers, _ = _admin_header(client, db_session)
    source = _make_source(db_session)
    created = client.post(
        "/api/v1/scientific-ingestion/requests",
        headers=admin_headers,
        json={"connector_id": "pubchem_pug_rest", "source_id": source.id, "external_ids": ["2244"]},
    ).json()

    researcher_headers, _ = _researcher_header(client, db_session)
    resp = client.get(f"/api/v1/scientific-ingestion/requests/{created['id']}", headers=researcher_headers)
    assert resp.status_code == 403


def test_get_conflicts_empty_for_new_request(client, db_session):
    headers, _ = _admin_header(client, db_session)
    source = _make_source(db_session)
    created = client.post(
        "/api/v1/scientific-ingestion/requests",
        headers=headers,
        json={"connector_id": "pubchem_pug_rest", "source_id": source.id, "external_ids": ["2244"]},
    ).json()
    resp = client.get(f"/api/v1/scientific-ingestion/requests/{created['id']}/conflicts", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_cancel_queued_request(client, db_session):
    headers, _ = _admin_header(client, db_session)
    source = _make_source(db_session)
    created = client.post(
        "/api/v1/scientific-ingestion/requests",
        headers=headers,
        json={"connector_id": "pubchem_pug_rest", "source_id": source.id, "external_ids": ["2244"]},
    ).json()
    resp = client.post(f"/api/v1/scientific-ingestion/requests/{created['id']}/cancel", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_cancel_is_idempotent(client, db_session):
    headers, _ = _admin_header(client, db_session)
    source = _make_source(db_session)
    created = client.post(
        "/api/v1/scientific-ingestion/requests",
        headers=headers,
        json={"connector_id": "pubchem_pug_rest", "source_id": source.id, "external_ids": ["2244"]},
    ).json()
    client.post(f"/api/v1/scientific-ingestion/requests/{created['id']}/cancel", headers=headers)
    resp = client.post(f"/api/v1/scientific-ingestion/requests/{created['id']}/cancel", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_cancel_requires_admin(client, db_session):
    admin_headers, _ = _admin_header(client, db_session)
    source = _make_source(db_session)
    created = client.post(
        "/api/v1/scientific-ingestion/requests",
        headers=admin_headers,
        json={"connector_id": "pubchem_pug_rest", "source_id": source.id, "external_ids": ["2244"]},
    ).json()
    researcher_headers, _ = _researcher_header(client, db_session)
    resp = client.post(
        f"/api/v1/scientific-ingestion/requests/{created['id']}/cancel", headers=researcher_headers
    )
    assert resp.status_code == 403
