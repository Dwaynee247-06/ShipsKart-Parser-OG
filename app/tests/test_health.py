"""Smoke test for the health endpoint."""
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

with patch("app.db.init_db.create_tables"):
    from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data
