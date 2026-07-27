
from biomatcad_api.models.organization import Organization
from biomatcad_api.models.user import User
from biomatcad_api.security import hash_password


def _create_synthetic_user(db_session):
    org = Organization(name="Org Sintética de Teste", slug="org-teste")
    db_session.add(org)
    db_session.flush()
    user = User(
        organization_id=org.id,
        email="teste@biomatcad.example",
        full_name="Usuário de Teste",
        hashed_password=hash_password("senha-sintetica-123"),
        role="researcher",
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_login_rejects_wrong_password(client, db_session):
    _create_synthetic_user(db_session)
    resp = client.post(
        "/api/v1/auth/login", json={"email": "teste@biomatcad.example", "password": "errada"}
    )
    assert resp.status_code == 401


def test_login_succeeds_and_returns_token(client, db_session):
    _create_synthetic_user(db_session)
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "teste@biomatcad.example", "password": "senha-sintetica-123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"

    me_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "teste@biomatcad.example"


def test_operational_state_activation_denied_without_master_key(client, db_session):
    user = _create_synthetic_user(db_session)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "senha-sintetica-123"},
    )
    token = login.json()["access_token"]

    resp = client.post(
        "/api/v1/system/operational-state/activate",
        json={"kind": "laboratory", "master_key": "qualquer-coisa", "justification": "teste automatizado"},
        headers={"Authorization": f"Bearer {token}"},
    )
    # Sem OPERATIONAL_STATE_MASTER_KEY configurada no ambiente de teste, a ativação deve ser
    # recusada (403), nunca aceita por padrão.
    assert resp.status_code == 403


def test_operational_state_activation_succeeds_with_correct_master_key(client, db_session, monkeypatch):
    from biomatcad_api.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("OPERATIONAL_STATE_MASTER_KEY", "chave-mestra-de-teste")
    get_settings.cache_clear()

    user = _create_synthetic_user(db_session)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "senha-sintetica-123"},
    )
    token = login.json()["access_token"]

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
