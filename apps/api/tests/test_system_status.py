def test_system_status_defaults_only_research_enabled(client):
    resp = client.get("/api/v1/system/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["clinical_suite_enabled"] is False

    states = {item["kind"]: item["enabled"] for item in body["operational_states"]}
    assert states["research"] is True
    assert states["laboratory"] is False
    assert states["clinical_pilot"] is False
    assert states["clinical_production"] is False
