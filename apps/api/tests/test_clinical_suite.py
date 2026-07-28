"""Suíte clínica (CLINICAL_TEST + CLINICAL_PILOT + CLINICAL_PRODUCTION) — Incremento 1.1.

Cobre os sete cenários exigidos: estado inicial desabilitado, ativação conjunta, desativação
conjunta, tentativa por usuário sem permissão, rollback integral em falha, expiração e
independência do contexto Laboratório.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tests.factories import (
    ADMIN_PASSWORD,
    RESEARCHER_PASSWORD,
    create_admin,
    create_researcher,
    login,
)

MASTER_KEY = "chave-mestra-de-teste-suite-clinica"


def _set_master_key(monkeypatch):
    from biomatcad_api.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("OPERATIONAL_STATE_MASTER_KEY", MASTER_KEY)
    get_settings.cache_clear()


def _clinical_flags(status_body: dict) -> dict[str, bool]:
    return {
        item["kind"]: item["enabled"]
        for item in status_body["operational_states"]
        if item["kind"] in ("clinical_test", "clinical_pilot", "clinical_production")
    }


# 1. Estado inicial: os três flags desabilitados.
def test_initial_state_all_three_clinical_flags_disabled(client):
    resp = client.get("/api/v1/system/status")
    body = resp.json()
    flags = _clinical_flags(body)
    assert flags == {"clinical_test": False, "clinical_pilot": False, "clinical_production": False}
    assert body["clinical_suite_enabled"] is False


# 2. Ativação conjunta: uma chamada habilita os três, na mesma transação, sem segunda chave.
def test_activation_enables_all_three_flags_atomically(client, db_session, monkeypatch):
    _set_master_key(monkeypatch)
    admin = create_admin(db_session, email="admin-suite-1@biomatcad.example")
    token = login(client, admin.email, ADMIN_PASSWORD)

    resp = client.post(
        "/api/v1/system/clinical-suite/activate",
        json={"master_key": MASTER_KEY, "justification": "ativação conjunta para teste automatizado"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["clinical_test_enabled"] is True
    assert body["clinical_pilot_enabled"] is True
    assert body["clinical_production_enabled"] is True

    status_resp = client.get("/api/v1/system/status")
    status_body = status_resp.json()
    assert _clinical_flags(status_body) == {
        "clinical_test": True,
        "clinical_pilot": True,
        "clinical_production": True,
    }
    assert status_body["clinical_suite_enabled"] is True


# 3. Desativação conjunta: reverte os três de uma vez.
def test_deactivation_disables_all_three_flags_atomically(client, db_session, monkeypatch):
    _set_master_key(monkeypatch)
    admin = create_admin(db_session, email="admin-suite-2@biomatcad.example")
    token = login(client, admin.email, ADMIN_PASSWORD)
    headers = {"Authorization": f"Bearer {token}"}

    activate = client.post(
        "/api/v1/system/clinical-suite/activate",
        json={"master_key": MASTER_KEY, "justification": "ativação antes da desativação"},
        headers=headers,
    )
    assert activate.status_code == 200

    deactivate = client.post(
        "/api/v1/system/clinical-suite/deactivate",
        json={"master_key": MASTER_KEY, "justification": "desativação conjunta para teste automatizado"},
        headers=headers,
    )
    assert deactivate.status_code == 200
    body = deactivate.json()
    assert body["clinical_test_enabled"] is False
    assert body["clinical_pilot_enabled"] is False
    assert body["clinical_production_enabled"] is False
    # previous_state deve refletir que, antes desta chamada, os três estavam habilitados.
    assert body["previous_state"] == {
        "clinical_test": True,
        "clinical_pilot": True,
        "clinical_production": True,
    }

    status_body = client.get("/api/v1/system/status").json()
    assert status_body["clinical_suite_enabled"] is False


# 4. Tentativa por usuário sem permissão (não administrador) é recusada.
def test_activation_denied_for_non_admin_user(client, db_session, monkeypatch):
    _set_master_key(monkeypatch)
    researcher = create_researcher(db_session, email="pesquisador-suite@biomatcad.example")
    token = login(client, researcher.email, RESEARCHER_PASSWORD)

    resp = client.post(
        "/api/v1/system/clinical-suite/activate",
        json={"master_key": MASTER_KEY, "justification": "tentativa sem permissão"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403

    status_body = client.get("/api/v1/system/status").json()
    assert status_body["clinical_suite_enabled"] is False

    from sqlalchemy import text

    audited = db_session.execute(
        text("SELECT COUNT(*) FROM audit_events WHERE event_type = 'admin_action_denied'")
    ).scalar()
    assert audited == 1


# 5. Rollback integral em falha: nenhum dos três flags fica parcialmente alterado.
def test_activation_rolls_back_completely_on_failure(client, db_session, monkeypatch):
    _set_master_key(monkeypatch)
    admin = create_admin(db_session, email="admin-suite-3@biomatcad.example")
    token = login(client, admin.email, ADMIN_PASSWORD)

    def _boom(*args, **kwargs):
        raise RuntimeError("falha simulada de persistência")

    monkeypatch.setattr(db_session, "flush", _boom)

    resp = client.post(
        "/api/v1/system/clinical-suite/activate",
        json={"master_key": MASTER_KEY, "justification": "deve falhar e não deixar estado parcial"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 500
    monkeypatch.undo()  # restaura flush real antes de consultar o estado

    from sqlalchemy import text

    rows = db_session.execute(
        text("SELECT kind, enabled FROM operational_states WHERE kind LIKE 'clinical_%'")
    ).fetchall()
    # Ou a linha não existe (nunca chegou a ser criada) ou existe com enabled=False — em nenhum
    # caso deve haver enabled=True, o que caracterizaria estado parcialmente aplicado.
    assert all(not enabled for _kind, enabled in rows), rows


# 6. Expiração: um estado com expires_at no passado deve ser lido como desabilitado.
def test_clinical_suite_expiration_is_respected(client, db_session, monkeypatch):
    _set_master_key(monkeypatch)
    admin = create_admin(db_session, email="admin-suite-4@biomatcad.example")
    token = login(client, admin.email, ADMIN_PASSWORD)

    almost_now = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
    resp = client.post(
        "/api/v1/system/clinical-suite/activate",
        json={
            "master_key": MASTER_KEY,
            "justification": "ativação com expiração quase imediata para teste",
            "expires_at": almost_now,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    import time

    time.sleep(1.2)

    status_body = client.get("/api/v1/system/status").json()
    assert _clinical_flags(status_body) == {
        "clinical_test": False,
        "clinical_pilot": False,
        "clinical_production": False,
    }
    assert status_body["clinical_suite_enabled"] is False


# 7. Independência do contexto Laboratório: ativar/desativar a suíte clínica não afeta
# Laboratório, e vice-versa.
def test_clinical_suite_is_independent_from_laboratory(client, db_session, monkeypatch):
    _set_master_key(monkeypatch)
    admin = create_admin(db_session, email="admin-suite-5@biomatcad.example")
    token = login(client, admin.email, ADMIN_PASSWORD)
    headers = {"Authorization": f"Bearer {token}"}

    lab_resp = client.post(
        "/api/v1/system/operational-state/activate",
        json={"kind": "laboratory", "master_key": MASTER_KEY, "justification": "ativar laboratório isoladamente"},
        headers=headers,
    )
    assert lab_resp.status_code == 200

    status_after_lab = client.get("/api/v1/system/status").json()
    states = {item["kind"]: item["enabled"] for item in status_after_lab["operational_states"]}
    assert states["laboratory"] is True
    assert status_after_lab["clinical_suite_enabled"] is False  # laboratório não conta como suíte clínica

    activate_resp = client.post(
        "/api/v1/system/clinical-suite/activate",
        json={"master_key": MASTER_KEY, "justification": "ativar suíte clínica depois do laboratório"},
        headers=headers,
    )
    assert activate_resp.status_code == 200

    status_after_suite = client.get("/api/v1/system/status").json()
    states_after = {item["kind"]: item["enabled"] for item in status_after_suite["operational_states"]}
    assert states_after["laboratory"] is True  # continua True, suíte clínica não o desligou
    assert status_after_suite["clinical_suite_enabled"] is True
