"""
FastAPI Endpoints Integration Tests for ARES.
Verifies all REST API contracts per Section 29 of specification.
"""

import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import init_db
from backend.workflow import workflow_engine

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_api():
    init_db()
    workflow_engine.reset_system()
    yield


def test_system_status_endpoint():
    """Test GET /api/system/status returns telemetry and tokens."""
    response = client.get("/api/system/status")
    assert response.status_code == 200
    data = response.json()
    assert "telemetry" in data
    assert "tokens" in data
    assert data["tokens"]["balance"] == 10000


def test_token_endpoints():
    """Test GET /api/tokens, GET /api/tokens/transactions, POST /api/tokens/add."""
    res = client.get("/api/tokens")
    assert res.status_code == 200
    assert res.json()["balance"] == 10000

    add_res = client.post("/api/tokens/add", json={"amount": 2500})
    assert add_res.status_code == 200
    assert add_res.json()["balance"] == 12500

    tx_res = client.get("/api/tokens/transactions")
    assert tx_res.status_code == 200
    assert len(tx_res.json()) >= 1


def test_inject_incident_endpoint():
    """Test POST /api/incidents/inject."""
    res = client.post("/api/incidents/inject", json={
        "scenario": "database_failure",
        "incident_id": "API-TEST-INC-01"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "INCIDENT_INJECTED"
    assert data["incident"]["id"] == "API-TEST-INC-01"

    # Fetch incident
    get_res = client.get("/api/incidents/API-TEST-INC-01")
    assert get_res.status_code == 200
    assert get_res.json()["scenario_type"] == "database_failure"


def test_system_reset_endpoint():
    """Test POST /api/system/reset returns cluster to healthy baseline."""
    client.post("/api/incidents/inject", json={"scenario": "database_failure"})
    reset_res = client.post("/api/system/reset")
    assert reset_res.status_code == 200
    assert reset_res.json()["telemetry"]["system_status"] == "HEALTHY"
    assert reset_res.json()["tokens"]["balance"] == 10000
