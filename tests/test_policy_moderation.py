import json
import os
import tempfile

import importlib.util
import pathlib
import sys
import pytest

try:
    import baseline_moderation_service as svc
    from baseline_moderation_service import ContentStatus
except ModuleNotFoundError:
    # Fallback: load by path (works when running in isolated pytest environments)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))
    spec = importlib.util.spec_from_file_location("baseline_moderation_service", str(repo_root / "baseline_moderation_service.py"))
    svc = importlib.util.module_from_spec(spec)
    sys.modules["baseline_moderation_service"] = svc
    spec.loader.exec_module(svc)
    from baseline_moderation_service import ContentStatus
    # cleanup sys.path insert
    try:
        sys.path.pop(0)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def clean_state():
    # ensure clean environment for each test
    svc.reset_state()
    svc.clear_policies()
    # ensure default blacklist
    svc.BLACKLIST[:] = ["spam", "scam", "illegal"]
    yield


def write_policy_file(tmp_path, content: dict):
    p = tmp_path / "policy.json"
    p.write_text(json.dumps(content))
    return str(p)


def test_baseline_behavior_no_policy_blocked_by_blacklist():
    # No policy loaded -> follow baseline blacklist behavior
    svc.clear_policies()
    body = svc.submit_content_internal("user1", "This is spam content")
    assert body["status"] == ContentStatus.BLOCKED.value
    assert "Blacklisted keyword hit" in body["reason"]


def test_low_risk_auto_approve(tmp_path):
    policy = {
        "policies": [
            {
                "id": "auto_approve_test",
                "rules": [{"type": "keyword", "keywords": ["hello"]}],
                "action": "APPROVE",
            }
        ]
    }
    path = write_policy_file(tmp_path, policy)
    svc.load_policies(path)

    body = svc.submit_content_internal("u1", "Hello there")
    assert body["status"] == ContentStatus.APPROVED.value
    assert "policy:auto_approve_test" in body["reason"]


def test_medium_risk_routes_to_review(tmp_path):
    policy = {
        "policies": [
            {
                "id": "to_review",
                "rules": [{"type": "keyword", "keywords": ["maybe"]}],
                "risk": "MEDIUM",
            }
        ]
    }
    path = write_policy_file(tmp_path, policy)
    svc.load_policies(path)

    body = svc.submit_content_internal("u1", "This is maybe suspicious")
    assert body["status"] == ContentStatus.PENDING_REVIEW.value
    # ensure in queue
    q = svc.get_review_queue_internal()
    items = q["items"]
    assert any(i["content_id"] == body["content_id"] for i in items)


def test_high_risk_auto_block_or_reject(tmp_path):
    policy = {
        "policies": [
            {
                "id": "block_policy",
                "rules": [{"type": "keyword", "keywords": ["fraud"]}],
                "action": "BLOCK",
            },
            {
                "id": "reject_policy",
                "rules": [{"type": "keyword", "keywords": ["hate"]}],
                "action": "REJECT",
            },
        ]
    }
    path = write_policy_file(tmp_path, policy)
    svc.load_policies(path)

    body = svc.submit_content_internal("u1", "This is fraud")
    assert body["status"] == ContentStatus.BLOCKED.value

    body2 = svc.submit_content_internal("u1", "This is hate speech")
    assert body2["status"] == ContentStatus.REJECTED.value


def test_rule_composition_and_or(tmp_path):
    # AND operator: must match both user_prefix and keyword
    policy = {
        "policies": [
            {
                "id": "and_policy",
                "operator": "AND",
                "rules": [
                    {"type": "user", "user_prefixes": ["vip_"]},
                    {"type": "keyword", "keywords": ["welcome"]},
                ],
                "action": "APPROVE",
            }
        ]
    }
    path = write_policy_file(tmp_path, policy)
    svc.load_policies(path)

    r = svc.submit_content_internal("vip_123", "welcome to our site")
    assert r["status"] == ContentStatus.APPROVED.value

    # Not matching both -> no policy -> fallback to baseline (no blacklist word -> pending review)
    r2 = svc.submit_content_internal("other_1", "welcome to our site")
    assert r2["status"] == ContentStatus.PENDING_REVIEW.value


def test_policy_precedence_over_blacklist(tmp_path):
    # Policy that approves trusted_ prefix even if text contains blacklisted keyword
    policy = {
        "policies": [
            {
                "id": "trusted_override",
                "rules": [{"type": "user", "user_prefixes": ["trusted_"]}],
                "action": "APPROVE",
            }
        ]
    }
    path = write_policy_file(tmp_path, policy)
    svc.load_policies(path)

    # Text contains blacklist 'spam' but policy should take precedence
    r = svc.submit_content_internal("trusted_jane", "this is spam")
    assert r["status"] == ContentStatus.APPROVED.value
    assert "trusted_override" in r["reason"]

