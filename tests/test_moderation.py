import os
import json
from pathlib import Path
from fastapi.testclient import TestClient

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import baseline_moderation_service as svc

client = TestClient(svc.app)


def _clear_store():
    svc.CONTENTS.clear()
    svc.REVIEW_QUEUE.clear()
    # Reset blacklist to baseline default
    svc.BLACKLIST[:] = ["spam", "scam", "illegal"]


def test_baseline_no_policy_behavior(tmp_path: Path):
    # Ensure no policy file is present
    os.environ.pop("MODERATION_POLICY_FILE", None)
    _clear_store()

    # Non-blacklisted content should be pending review
    resp = client.post("/content/submit", json={"user_id": "user1", "text": "hello world"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "PENDING_REVIEW"
    assert data["reason"] == "Requires manual review"

    # Blacklisted content should be blocked
    resp2 = client.post("/content/submit", json={"user_id": "user2", "text": "this is spam"})
    assert resp2.status_code == 200
    d2 = resp2.json()
    assert d2["status"] == "BLOCKED"
    assert "Blacklisted keyword hit" in d2["reason"]


def _write_policy(policy: dict, path: Path):
    path.write_text(json.dumps(policy))


def test_policy_low_risk_approval(tmp_path: Path):
    policy = {
        "enabled": True,
        "policies": [
            {
                "id": "low1",
                "match": {"any": [{"type": "keyword", "value": "hello"}]},
                "risk": "low"
            }
        ]
    }
    policy_file = tmp_path / "policy.json"
    _write_policy(policy, policy_file)
    os.environ["MODERATION_POLICY_FILE"] = str(policy_file)
    _clear_store()

    resp = client.post("/content/submit", json={"user_id": "u1", "text": "hello there"})
    assert resp.status_code == 200
    d = resp.json()
    assert d["status"] == "APPROVED"
    assert "Policy 'low1' -> APPROVED" in d["reason"]


def test_policy_medium_risk_reviewer_queue(tmp_path: Path):
    policy = {
        "enabled": True,
        "policies": [
            {
                "id": "med1",
                "match": {"any": [{"type": "keyword", "value": "mediumword"}]},
                "risk": "medium"
            }
        ]
    }
    policy_file = tmp_path / "policy.json"
    _write_policy(policy, policy_file)
    os.environ["MODERATION_POLICY_FILE"] = str(policy_file)
    _clear_store()

    resp = client.post("/content/submit", json={"user_id": "u1", "text": "this is mediumword content"})
    assert resp.status_code == 200
    d = resp.json()
    assert d["status"] == "PENDING_REVIEW"
    assert "Policy 'med1' -> PENDING_REVIEW" in d["reason"]


def test_policy_high_risk_reject_and_block(tmp_path: Path):
    policy = {
        "enabled": True,
        "policies": [
            {"id": "high1", "match": {"any": [{"type": "keyword", "value": "badword"}]}, "risk": "high", "action": "reject"},
            {"id": "high2", "match": {"any": [{"type": "keyword", "value": "blockit"}]}, "risk": "high", "action": "block"}
        ]
    }
    policy_file = tmp_path / "policy.json"
    _write_policy(policy, policy_file)
    os.environ["MODERATION_POLICY_FILE"] = str(policy_file)
    _clear_store()

    # reject
    r1 = client.post("/content/submit", json={"user_id": "u1", "text": "this is badword"})
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["status"] == "REJECTED"
    assert "Policy 'high1' -> REJECTED" in d1["reason"]

    # block
    r2 = client.post("/content/submit", json={"user_id": "u1", "text": "trigger blockit now"})
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["status"] == "BLOCKED"
    assert "Policy 'high2' -> BLOCKED" in d2["reason"]


def test_policy_rule_composition_and(tmp_path: Path):
    policy = {
        "enabled": True,
        "policies": [
            {
                "id": "and1",
                "match": {"all": [
                    {"type": "keyword", "value": "special"},
                    {"type": "user", "prefix": "user_"}
                ]},
                "risk": "high",
                "action": "reject"
            }
        ]
    }
    policy_file = tmp_path / "policy.json"
    _write_policy(policy, policy_file)
    os.environ["MODERATION_POLICY_FILE"] = str(policy_file)
    _clear_store()

    resp = client.post("/content/submit", json={"user_id": "user_x", "text": "special content"})
    assert resp.status_code == 200
    d = resp.json()
    assert d["status"] == "REJECTED"
    assert "Policy 'and1' -> REJECTED" in d["reason"]


def test_policy_overrides_blacklist_when_enabled(tmp_path: Path):
    # Policy first, so policy matches may override blacklist
    policy = {
        "enabled": True,
        "policies": [
            {"id": "low1", "match": {"any": [{"type": "keyword", "value": "spam"}]}, "risk": "low"}
        ]
    }
    policy_file = tmp_path / "policy.json"
    _write_policy(policy, policy_file)
    os.environ["MODERATION_POLICY_FILE"] = str(policy_file)
    _clear_store()

    resp = client.post("/content/submit", json={"user_id": "u1", "text": "spam here"})
    assert resp.status_code == 200
    d = resp.json()

    # Policy low risk should approve even though text contains blacklisted keyword
    assert d["status"] == "APPROVED"
    assert "Policy 'low1' -> APPROVED" in d["reason"]
