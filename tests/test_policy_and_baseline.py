import json
import os
from fastapi.testclient import TestClient
import baseline_moderation_service as svc

client = TestClient(svc.app)


def setup_function():
    # clear state before each test
    svc.CONTENTS.clear()
    svc.REVIEW_QUEUE.clear()


def test_baseline_blacklist_blocks():
    # disable policies by pointing to a non-existent file
    svc.policy_engine.load(policy_file="nonexistent-policy.json")
    resp = client.post("/content/submit", json={"user_id": "u1", "text": "this is spam content"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "BLOCKED"
    assert "Blacklisted keyword hit" in body["reason"]


def test_baseline_pending_review():
    svc.policy_engine.load(policy_file="nonexistent-policy.json")
    resp = client.post("/content/submit", json={"user_id": "u2", "text": "harmless content"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "PENDING_REVIEW"
    # ensure it's queued
    q = client.get("/review/queue")
    assert q.json()["count"] >= 1


def test_policy_auto_approve_low_risk(tmp_path):
    # create a policy that auto-approves keyword 'safe'
    policy = [
        {"id": "p1", "priority": 10, "type": "keyword", "keywords": ["safe"], "outcome": "APPROVE", "description": "auto-approve safe"}
    ]
    pfile = tmp_path / "policy.json"
    pfile.write_text(json.dumps(policy))

    svc.policy_engine.load(policy_file=str(pfile))
    resp = client.post("/content/submit", json={"user_id": "alice", "text": "this is safe content"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "APPROVED"
    assert "p1" in body["reason"]


def test_policy_pending_review_medium_risk(tmp_path):
    policy = [
        {"id": "p2", "priority": 10, "type": "keyword", "keywords": ["maybe"], "outcome": "PENDING_REVIEW", "description": "medium risk"}
    ]
    pfile = tmp_path / "policy.json"
    pfile.write_text(json.dumps(policy))

    svc.policy_engine.load(policy_file=str(pfile))
    resp = client.post("/content/submit", json={"user_id": "bob", "text": "maybe problematic"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "PENDING_REVIEW"
    assert "p2" in body["reason"]
    q = client.get("/review/queue")
    assert any(item["user_id"] == "bob" for item in q.json()["items"])


def test_policy_high_risk_block_user(tmp_path):
    policy = [
        {"id": "p3", "priority": 5, "type": "user", "users": ["bad_user"], "outcome": "BLOCK", "description": "block bad user"}
    ]
    pfile = tmp_path / "policy.json"
    pfile.write_text(json.dumps(policy))
    svc.policy_engine.load(policy_file=str(pfile))

    resp = client.post("/content/submit", json={"user_id": "bad_user", "text": "anything"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "BLOCKED"
    assert "p3" in body["reason"]


def test_rule_composition_and_operator(tmp_path):
    # composite rule: AND of keyword 'secret' and user prefix 'vip-'
    policy = [
        {
            "id": "p_and",
            "priority": 10,
            "type": "composite",
            "operator": "AND",
            "rules": [
                {"type": "keyword", "keywords": ["secret"]},
                {"type": "user", "user_prefixes": ["vip-"]}
            ],
            "outcome": "REJECT",
            "description": "reject secret from vip users"
        }
    ]
    pfile = tmp_path / "policy.json"
    pfile.write_text(json.dumps(policy))
    svc.policy_engine.load(policy_file=str(pfile))

    # matching case
    resp = client.post("/content/submit", json={"user_id": "vip-joe", "text": "this contains secret"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "REJECTED"

    # non-matching user prefix
    resp2 = client.post("/content/submit", json={"user_id": "joe", "text": "this contains secret"})
    assert resp2.json()["status"] == "PENDING_REVIEW"


def test_policy_vs_blacklist_order(tmp_path):
    # Policy that would approve 'spam' (conflicts with blacklist). Policy takes precedence per design.
    policy = [
        {"id": "p_spam_allow", "priority": 1, "type": "keyword", "keywords": ["spam"], "outcome": "APPROVE", "description": "allow spam via policy"}
    ]
    pfile = tmp_path / "policy.json"
    pfile.write_text(json.dumps(policy))
    svc.policy_engine.load(policy_file=str(pfile))

    resp = client.post("/content/submit", json={"user_id": "u4", "text": "spammy content"})
    assert resp.status_code == 200
    body = resp.json()
    # Expect APPROVED due to policy-first override of blacklist
    assert body["status"] == "APPROVED"
    assert "p_spam_allow" in body["reason"]


def test_reason_for_blacklist_when_no_policy():
    svc.policy_engine.load(policy_file="nonexistent-policy.json")
    resp = client.post("/content/submit", json={"user_id": "u5", "text": "spam here"})
    assert resp.json()["reason"].startswith("Blacklisted keyword hit")
