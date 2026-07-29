"""Testes de API HTTP para materiais/projetos/receitas (Incremento 2.1, item 8)."""
from __future__ import annotations

from .factories import RESEARCHER_PASSWORD, create_researcher, login

GOOD_RECIPE = {
    "schema_version": "1.0.0",
    "domain": {"shape": "block", "dimensions_mm": {"kind": "block", "x_mm": 10, "y_mm": 10, "z_mm": 10}},
    "topology": {"kind": "gyroid", "cell_size_mm": 2.0, "isovalue": 0.0, "target_porosity_pct": 60},
    "resolution": {"voxel_size_mm": 0.2},
    "mode": "preview",
    "seed": 42,
    "compute_limits": {"max_duration_seconds": 60, "max_memory_mb": 512, "max_voxel_count": 1000000},
    "output_formats": ["stl"],
}


def _auth_header(client, db_session, email):
    create_researcher(db_session, email=email)
    token = login(client, email, RESEARCHER_PASSWORD)
    return {"Authorization": f"Bearer {token}"}


def test_create_material_with_properties_and_references(client, db_session):
    headers = _auth_header(client, db_session, "mat1@biomatcad.example")
    payload = {
        "name": "beta-TCP sintético",
        "category": "ceramic",
        "source_type": "synthetic",
        "description": "Material sintético rotulado para fins de teste.",
        "properties": [
            {
                "property_name": "compressive_strength",
                "value": 12.5,
                "unit": "MPa",
                "source": "dado sintético de teste, não medido experimentalmente",
                "method": "sintético",
                "review_status": "draft",
            }
        ],
        "references": [{"citation_text": "Referência sintética de teste, sem DOI real."}],
    }
    resp = client.post("/api/v1/materials", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "beta-TCP sintético"
    assert len(body["properties"]) == 1
    assert body["properties"][0]["unit"] == "MPa"
    assert len(body["references"]) == 1


def test_invalid_source_type_is_rejected(client, db_session):
    headers = _auth_header(client, db_session, "mat2@biomatcad.example")
    payload = {"name": "Material Inválido", "category": "ceramic", "source_type": "made_up"}
    resp = client.post("/api/v1/materials", headers=headers, json=payload)
    assert resp.status_code == 422


def test_materials_endpoint_requires_auth(client):
    resp = client.get("/api/v1/materials")
    assert resp.status_code == 401


def test_project_listing_is_scoped_to_organization(client, db_session):
    headers_a = _auth_header(client, db_session, "proja@biomatcad.example")
    headers_b = _auth_header(client, db_session, "projb@biomatcad.example")

    client.post("/api/v1/projects", headers=headers_a, json={"name": "Projeto A"})
    client.post("/api/v1/projects", headers=headers_b, json={"name": "Projeto B"})

    resp_a = client.get("/api/v1/projects", headers=headers_a)
    names_a = {p["name"] for p in resp_a.json()}
    assert "Projeto A" in names_a
    assert "Projeto B" not in names_a


def test_project_cross_organization_access_denied_and_audited(client, db_session):
    headers_a = _auth_header(client, db_session, "projc1@biomatcad.example")
    headers_b = _auth_header(client, db_session, "projc2@biomatcad.example")

    create_resp = client.post("/api/v1/projects", headers=headers_a, json={"name": "Projeto Privado"})
    project_id = create_resp.json()["id"]

    resp = client.get(f"/api/v1/projects/{project_id}", headers=headers_b)
    assert resp.status_code == 403

    from biomatcad_api.models.audit_event import AuditEvent

    events = db_session.query(AuditEvent).filter(AuditEvent.event_type == "cross_organization_access_denied").all()
    assert len(events) >= 1


def test_recipe_validate_create_clone_flow(client, db_session):
    headers = _auth_header(client, db_session, "rec1@biomatcad.example")
    project_id = client.post("/api/v1/projects", headers=headers, json={"name": "Projeto Receita"}).json()["id"]

    validate_resp = client.post("/api/v1/recipes/validate", json={"recipe_body": GOOD_RECIPE})
    assert validate_resp.status_code == 200
    assert validate_resp.json()["valid"] is True
    assert validate_resp.json()["checksum_sha256"] is not None

    create_resp = client.post(
        f"/api/v1/projects/{project_id}/recipes",
        headers=headers,
        json={"name": "Receita Bloco", "recipe_body": GOOD_RECIPE},
    )
    assert create_resp.status_code == 201, create_resp.text
    recipe = create_resp.json()
    assert recipe["version"] == 1
    assert recipe["checksum_sha256"] == validate_resp.json()["checksum_sha256"]

    clone_resp = client.post(f"/api/v1/recipes/{recipe['id']}/clone", headers=headers)
    assert clone_resp.status_code == 201
    clone = clone_resp.json()
    assert clone["version"] == 2
    assert clone["parent_recipe_id"] == recipe["id"]
    assert clone["canonical_json"] == recipe["canonical_json"]

    original_again = client.get(f"/api/v1/recipes/{recipe['id']}", headers=headers).json()
    assert original_again["canonical_json"] == recipe["canonical_json"], "clonar não deve alterar a receita original"


def test_invalid_recipe_body_is_rejected_with_structured_details(client, db_session):
    headers = _auth_header(client, db_session, "rec2@biomatcad.example")
    project_id = client.post("/api/v1/projects", headers=headers, json={"name": "Projeto Receita Inválida"}).json()["id"]

    bad_recipe = dict(GOOD_RECIPE)
    bad_recipe["arbitrary_field"] = "not allowed"

    resp = client.post(
        f"/api/v1/projects/{project_id}/recipes",
        headers=headers,
        json={"name": "Receita Ruim", "recipe_body": bad_recipe},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert "details" in body["error"]
    assert body["error"]["details"] is not None
