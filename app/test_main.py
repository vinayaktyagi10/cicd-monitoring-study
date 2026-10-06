from fastapi.testclient import TestClient

import main
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


def test_memory_fill_writes_nonzero_bytes_into_every_page():
    client.post("/memory/reset")
    r = client.get("/memory", params={"mb": 1, "hold": True, "fill": True})
    assert r.status_code == 200
    block = main._memory_ballast[-1]
    assert all(block[i] != 0 for i in range(0, len(block), 4096))
    client.post("/memory/reset")


def test_memory_fill_is_off_by_default():
    client.post("/memory/reset")
    client.get("/memory", params={"mb": 1, "hold": True})
    assert not any(main._memory_ballast[-1])
    client.post("/memory/reset")


def test_memory_reset():
    client.get("/memory", params={"mb": 1, "hold": True})
    r = client.post("/memory/reset")
    assert r.status_code == 200
    assert r.json()["ballast_blocks"] == 0


def test_metrics():
    r = client.get("/metrics")
    assert r.status_code == 200
    assert b"app_requests_total" in r.content
