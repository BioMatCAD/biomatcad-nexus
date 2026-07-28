from tests.factories import (
    ADMIN_PASSWORD,
    RESEARCHER_PASSWORD,
    create_admin,
    create_researcher,
    login,
)


def test_login_rejects_wrong_password(client, db_session):
    create_researcher(db_session)
    resp = client.post(
        "/api/v1/auth/login", json={"email": "teste@biomatcad.example", "password": "errada"}
    )
    assert resp.status_code == 401


def test_login_succeeds_and_returns_token(client, db_session):
    create_researcher(db_session)
    token = login(client, "teste@biomatcad.example", RESEARCHER_PASSWORD)

    me_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "teste@biomatcad.example"


def test_logout_is_audited(client, db_session):
    from sqlalchemy import text

    create_researcher(db_session, email="logout@biomatcad.example")
    token = login(client, "logout@biomatcad.example", RESEARCHER_PASSWORD)

    resp = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "logged_out_client_side_only"

    count = db_session.execute(
        text("SELECT COUNT(*) FROM audit_events WHERE event_type = 'logout'")
    ).scalar()
    assert count == 1


def test_laboratory_activation_denied_without_master_key(client, db_session):
    admin = create_admin(db_session, email="admin-lab-1@biomatcad.example")
    token = login(client, admin.email, ADMIN_PASSWORD)

    resp = client.post(
        "/api/v1/system/operational-state/activate",
        json={"kind": "laboratory", "master_key": "qualquer-coisa", "justification": "teste automatizado"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_laboratory_activation_denied_for_non_admin(client, db_session, monkeypatch):
    from biomatcad_api.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("OPERATIONAL_STATE_MASTER_KEY", "chave-mestra-de-teste")
    get_settings.cache_clear()

    researcher = create_researcher(db_session, email="pesquisador-lab@biomatcad.example")
    token = login(client, researcher.email, RESEARCHER_PASSWORD)

    resp = client.post(
        "/api/v1/system/operational-state/activate",
        json={"kind": "laboratory", "master_key": "chave-mestra-de-teste", "justification": "teste automatizado"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    get_settings.cache_clear()


def test_laboratory_activation_succeeds_for_admin_with_correct_master_key(client, db_session, monkeypatch):
    from biomatcad_api.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("OPERATIONAL_STATE_MASTER_KEY", "chave-mestra-de-teste")
    get_settings.cache_clear()

    admin = create_admin(db_session, email="admin-lab-2@biomatcad.example")
    token = login(client, admin.email, ADMIN_PASSWORD)

    resp = client.post(
        "/api/v1/system/operational-state/activate",
        json={
            "kind": "laboratory",
            "master_key": "chave-mestra-de-teste",
            "justification": "teste automatizado com chave correta",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True
    get_settings.cache_clear()


def test_clinical_kinds_rejected_on_independent_endpoint(client, db_session, monkeypatch):
    """Corrige o bug do Incremento 1: os três flags clínicos NÃO podem mais ser ativados
    individualmente pelo endpoint de contexto independente — apenas pela suíte clínica atômica."""
    from biomatcad_api.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("OPERATIONAL_STATE_MASTER_KEY", "chave-mestra-de-teste")
    get_settings.cache_clear()

    admin = create_admin(db_session, email="admin-lab-3@biomatcad.example")
    token = login(client, admin.email, ADMIN_PASSWORD)

    for kind in ("clinical_test", "clinical_pilot", "clinical_production"):
        resp = client.post(
            "/api/v1/system/operational-state/activate",
            json={"kind": kind, "master_key": "chave-mestra-de-teste", "justification": "tentativa indevida"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400, f"{kind} deveria ser rejeitado neste endpoint"
    get_settings.cache_clear()
