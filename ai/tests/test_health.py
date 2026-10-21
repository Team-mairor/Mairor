def test_health_returns_up(client):
    res = client.get("/health")

    assert res.status_code == 200
    assert res.json() == {"status": "UP"}
