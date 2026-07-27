def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ready_reports_database_connected(client):
    resp = client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["database"] == "connected"


def test_version(client):
    resp = client.get("/version")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"]
    assert body["environment"] == "test"
