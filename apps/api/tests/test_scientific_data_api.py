"""Testes da API mínima de pesquisa do banco de dados científico (Incremento 2.3, Rodada 1,
Fase D). Cobertura completa de mutação/deduplicação/organização fica na Fase F -- aqui apenas
prova-se que a superfície de API descrita na Fase D funciona: leitura com escopo por
organização (global vs. privado), escrita/revisão restritas a administrador, e dados não
revisados continuam visíveis e rotulados via `review_status`."""
from __future__ import annotations

from biomatcad_api.models.organization import Organization
from biomatcad_api.models.scientific_data import (
    CurationState,
    ScientificEntity,
    ScientificEntityType,
)
from tests.factories import (
    ADMIN_PASSWORD,
    RESEARCHER_PASSWORD,
    create_admin,
    create_org,
    create_researcher,
    login,
)


def _admin_header(client, db_session, email, org: Organization | None = None):
    admin = create_admin(db_session, email=email, org=org)
    token = login(client, email, ADMIN_PASSWORD)
    return {"Authorization": f"Bearer {token}"}, admin


def _researcher_header(client, db_session, email, org: Organization | None = None):
    user = create_researcher(db_session, email=email, org=org)
    token = login(client, email, RESEARCHER_PASSWORD)
    return {"Authorization": f"Bearer {token}"}, user


def test_create_and_get_scientific_entity(client, db_session):
    headers, _ = _admin_header(client, db_session, "sci-admin1@biomatcad.example")
    resp = client.post(
        "/api/v1/scientific-entities",
        headers=headers,
        json={
            "entity_type": "biomaterial",
            "preferred_name": "Hidroxiapatita sintética (teste)",
            "description": "Entidade sintética de teste, sem dado real.",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["entity_type"] == "biomaterial"
    assert body["review_status"] == "draft"
    assert body["identifiers"] == []

    get_resp = client.get(f"/api/v1/scientific-entities/{body['id']}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["preferred_name"] == "Hidroxiapatita sintética (teste)"


def test_create_scientific_entity_requires_admin(client, db_session):
    headers, _ = _researcher_header(client, db_session, "sci-researcher1@biomatcad.example")
    resp = client.post(
        "/api/v1/scientific-entities",
        headers=headers,
        json={"entity_type": "chemical_substance", "preferred_name": "Substância sintética"},
    )
    assert resp.status_code == 403


def test_scientific_entities_endpoint_requires_auth(client):
    resp = client.get("/api/v1/scientific-entities")
    assert resp.status_code == 401


def test_private_entity_not_visible_to_other_organization(client, db_session):
    org_a = create_org(db_session, slug="org-sci-a")
    org_b = create_org(db_session, slug="org-sci-b")
    headers_a, _ = _admin_header(client, db_session, "sci-a@biomatcad.example", org=org_a)
    headers_b, _ = _researcher_header(client, db_session, "sci-b@biomatcad.example", org=org_b)

    resp = client.post(
        "/api/v1/scientific-entities",
        headers=headers_a,
        json={"entity_type": "drug", "preferred_name": "Fármaco privado de teste"},
    )
    assert resp.status_code == 201
    entity_id = resp.json()["id"]

    resp_b = client.get(f"/api/v1/scientific-entities/{entity_id}", headers=headers_b)
    assert resp_b.status_code == 404

    resp_a = client.get(f"/api/v1/scientific-entities/{entity_id}", headers=headers_a)
    assert resp_a.status_code == 200


def test_global_entity_visible_across_organizations(client, db_session):
    """Registro global (organization_id NULL) -- criado diretamente via SQLAlchemy, já que a
    criação de entidade GLOBAL não é exposta via API nesta rodada (apenas privada, por design)."""
    org_a = create_org(db_session, slug="org-sci-global-a")
    org_b = create_org(db_session, slug="org-sci-global-b")
    _, _ = _admin_header(client, db_session, "sci-global-a@biomatcad.example", org=org_a)
    headers_b, _ = _researcher_header(client, db_session, "sci-global-b@biomatcad.example", org=org_b)

    global_entity = ScientificEntity(
        organization_id=None,
        entity_type=ScientificEntityType.NANOMATERIAL,
        preferred_name="Nanomaterial global de teste",
    )
    db_session.add(global_entity)
    db_session.commit()

    resp = client.get(f"/api/v1/scientific-entities/{global_entity.id}", headers=headers_b)
    assert resp.status_code == 200
    assert resp.json()["organization_id"] is None


def test_review_decision_updates_status_and_is_admin_only(client, db_session):
    headers, admin = _admin_header(client, db_session, "sci-reviewer@biomatcad.example")
    create_resp = client.post(
        "/api/v1/scientific-entities",
        headers=headers,
        json={"entity_type": "formulation", "preferred_name": "Formulação de teste"},
    )
    entity_id = create_resp.json()["id"]

    same_org = db_session.get(Organization, admin.organization_id)
    researcher_headers, _ = _researcher_header(
        client, db_session, "sci-nonadmin-reviewer@biomatcad.example", org=same_org
    )
    denied = client.post(
        f"/api/v1/scientific-entities/{entity_id}/review-decisions",
        headers=researcher_headers,
        json={"decision": "approved", "justification": "Tentativa sem permissão."},
    )
    assert denied.status_code == 403

    approved = client.post(
        f"/api/v1/scientific-entities/{entity_id}/review-decisions",
        headers=headers,
        json={"decision": "approved", "justification": "Revisão sintética de teste aprovada."},
    )
    assert approved.status_code == 201, approved.text
    decision_body = approved.json()
    assert decision_body["previous_state"] == "draft"
    assert decision_body["new_state"] == "reviewed"

    entity = db_session.get(ScientificEntity, entity_id)
    db_session.refresh(entity)
    assert entity.review_status == CurationState.REVIEWED

    history = client.get(f"/api/v1/scientific-entities/{entity_id}/review-history", headers=headers)
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert history.json()[0]["decision"] == "approved"


def test_related_subresource_endpoints_return_empty_lists_when_no_data(client, db_session):
    """As sub-rotas de identificadores/observações/proveniência/produtos/estruturas devem
    responder 200 com lista vazia (nunca erro) quando a entidade não tem dados relacionados
    ainda -- o povoamento real destas sub-tabelas é feito no seed sintético da Fase E."""
    headers, _ = _admin_header(client, db_session, "sci-empty@biomatcad.example")
    resp = client.post(
        "/api/v1/scientific-entities",
        headers=headers,
        json={"entity_type": "other", "preferred_name": "Entidade sem dados relacionados"},
    )
    entity_id = resp.json()["id"]

    for suffix in (
        "identifiers",
        "property-observations",
        "provenance",
        "supplier-products",
        "crystal-structures",
        "review-history",
        "biological-evidence",
        "raw-source-records",
        "conflicts",
    ):
        sub_resp = client.get(f"/api/v1/scientific-entities/{entity_id}/{suffix}", headers=headers)
        assert sub_resp.status_code == 200, f"{suffix}: {sub_resp.text}"
        assert sub_resp.json() == []


def test_unknown_entity_id_returns_404_for_all_subresources(client, db_session):
    headers, _ = _admin_header(client, db_session, "sci-404@biomatcad.example")
    fake_id = "00000000-0000-0000-0000-000000000000"
    for suffix in (
        "",
        "/identifiers",
        "/property-observations",
        "/provenance",
        "/supplier-products",
        "/crystal-structures",
        "/review-history",
        "/biological-evidence",
        "/raw-source-records",
        "/conflicts",
    ):
        resp = client.get(f"/api/v1/scientific-entities/{fake_id}{suffix}", headers=headers)
        assert resp.status_code == 404


def test_property_definitions_endpoint_lists_canonical_vocabulary(client, db_session):
    """`/property-definitions` (Adendo de Interface Científica Mínima, Fase L) -- vocabulário
    global, acessível a qualquer usuário autenticado (não exige admin, ao contrário de criação/
    revisão de entidade), e declarado ANTES de `/{entity_id}` para nunca ser capturado como um
    valor de entity_id (prova de regressão de ordenação de rotas)."""
    from biomatcad_api.models.scientific_data import PropertyDefinition

    headers, _ = _researcher_header(client, db_session, "sci-propdefs@biomatcad.example")
    prop_def = PropertyDefinition(
        canonical_key="test_prop_defs_endpoint",
        name="Propriedade de teste (endpoint)",
        dimension="mechanical",
        canonical_unit="GPa",
        value_type="numeric",
        applicable_domain="generic",
    )
    db_session.add(prop_def)
    db_session.commit()

    resp = client.get("/api/v1/scientific-entities/property-definitions", headers=headers)
    assert resp.status_code == 200
    keys = [p["canonical_key"] for p in resp.json()]
    assert "test_prop_defs_endpoint" in keys


def test_entity_conflicts_endpoint_shows_conflict_where_entity_is_either_side(client, db_session):
    """Conflitos aparecem tanto quando a entidade é `entity_id` quanto quando é
    `other_entity_id` do IngestionConflict (Adendo de Interface Científica Mínima, Fase L)."""
    from biomatcad_api.models.scientific_ingestion import (
        IngestionConflict as IngestionConflictModel,
    )
    from biomatcad_api.models.scientific_ingestion import (
        IngestionConflictType,
        IngestionRequestStatus,
        ScientificIngestionRequest,
    )

    headers, admin = _admin_header(client, db_session, "sci-conflict@biomatcad.example")

    resp_a = client.post(
        "/api/v1/scientific-entities",
        headers=headers,
        json={"entity_type": "chemical_substance", "preferred_name": "Entidade Conflito A"},
    )
    resp_b = client.post(
        "/api/v1/scientific-entities",
        headers=headers,
        json={"entity_type": "chemical_substance", "preferred_name": "Entidade Conflito B"},
    )
    entity_a_id = resp_a.json()["id"]
    entity_b_id = resp_b.json()["id"]

    from biomatcad_api.models.scientific_data import ScientificSource, SourceType

    source = ScientificSource(name="Fonte de teste conflito", source_type=SourceType.DATABASE)
    db_session.add(source)
    db_session.flush()

    request = ScientificIngestionRequest(
        organization_id=None,
        requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest",
        source_id=source.id,
        external_ids=["9999"],
        dry_run=False,
        status=IngestionRequestStatus.PARTIAL,
    )
    db_session.add(request)
    db_session.flush()

    conflict = IngestionConflictModel(
        ingestion_request_id=request.id,
        external_record_id="9999",
        conflict_type=IngestionConflictType.INCHIKEY_SHARED_WITH_OTHER_ENTITY,
        entity_id=entity_a_id,
        other_entity_id=entity_b_id,
        details={"nota": "conflito de teste"},
    )
    db_session.add(conflict)
    db_session.commit()

    resp_a_conflicts = client.get(f"/api/v1/scientific-entities/{entity_a_id}/conflicts", headers=headers)
    resp_b_conflicts = client.get(f"/api/v1/scientific-entities/{entity_b_id}/conflicts", headers=headers)
    assert resp_a_conflicts.status_code == 200
    assert resp_b_conflicts.status_code == 200
    assert len(resp_a_conflicts.json()) == 1
    assert len(resp_b_conflicts.json()) == 1
    assert resp_a_conflicts.json()[0]["id"] == conflict.id
    assert resp_b_conflicts.json()[0]["id"] == conflict.id
