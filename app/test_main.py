from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_cpu():
    r = client.get("/cpu", params={"iterations": 1000})
    assert r.status_code == 200
    assert r.json()["iterations"] == 1000


def test_memory():
    r = client.get("/memory", params={"mb": 1, "hold": False})
    assert r.status_code == 200
    assert r.json()["allocated_mb"] == 1


def test_memory_reset():
    client.get("/memory", params={"mb": 1, "hold": True})
    r = client.post("/memory/reset")
    assert r.status_code == 200
    assert r.json()["ballast_blocks"] == 0


def test_metrics():
    r = client.get("/metrics")
    assert r.status_code == 200
    assert b"app_requests_total" in r.content
