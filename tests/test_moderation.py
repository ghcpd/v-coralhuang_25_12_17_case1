import pytest
from fastapi.testclient import TestClient
from baseline_moderation_service import app, ENABLE_POLICIES, POLICIES, ContentStatus
import os
import json

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}

def test_baseline_blacklist_block():
    # Test baseline behavior when policies disabled
    if ENABLE_POLICIES and POLICIES:
        pytest.skip("Policies enabled, skipping baseline test")
    response = client.post("/content/submit", json={"user_id": "user1", "text": "This is spam content"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "BLOCKED"
    assert "spam" in data["reason"]

def test_baseline_manual_review():
    if ENABLE_POLICIES and POLICIES:
        pytest.skip("Policies enabled, skipping baseline test")
    response = client.post("/content/submit", json={"user_id": "user1", "text": "This is normal content"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "PENDING_REVIEW"
    assert data["reason"] == "Requires manual review"

@pytest.mark.skipif(not ENABLE_POLICIES or not POLICIES, reason="Policies not enabled")
def test_policy_low_risk_approve():
    response = client.post("/content/submit", json={"user_id": "user1", "text": "This is good content"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "APPROVED"
    assert "low_risk_keyword" in data["reason"]

@pytest.mark.skipif(not ENABLE_POLICIES or not POLICIES, reason="Policies not enabled")
def test_policy_high_risk_block():
    response = client.post("/content/submit", json={"user_id": "bad_user", "text": "Some content"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "BLOCKED"
    assert "high_risk_user" in data["reason"]

@pytest.mark.skipif(not ENABLE_POLICIES or not POLICIES, reason="Policies not enabled")
def test_policy_medium_risk_pending():
    response = client.post("/content/submit", json={"user_id": "unknown_user", "text": "Normal text"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "PENDING_REVIEW"
    assert "medium_risk_composite" in data["reason"]

@pytest.mark.skipif(not ENABLE_POLICIES or not POLICIES, reason="Policies not enabled")
def test_policy_high_risk_reject():
    response = client.post("/content/submit", json={"user_id": "suspicious_user", "text": "This is bad content"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "REJECTED"
    assert "high_risk_and" in data["reason"]

@pytest.mark.skipif(not ENABLE_POLICIES or not POLICIES, reason="Policies not enabled")
def test_policy_no_match_fallback():
    response = client.post("/content/submit", json={"user_id": "user1", "text": "This is spam content"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "BLOCKED"
    assert "Blacklisted keyword hit" in data["reason"]

def test_blacklist_endpoints():
    # Test blacklist management
    response = client.get("/blacklist")
    assert response.status_code == 200
    assert "keywords" in response.json()

    response = client.post("/blacklist", params={"keyword": "test"})
    assert response.status_code == 200

    response = client.get("/blacklist")
    assert "test" in response.json()["keywords"]

    response = client.delete("/blacklist", params={"keyword": "test"})
    assert response.status_code == 200
    assert "test" not in response.json()["keywords"]