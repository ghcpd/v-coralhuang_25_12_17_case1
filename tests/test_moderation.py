import importlib
import os


def reload_app_with_env(env: dict):
    # set env vars then import/reload module so policy loading runs at import time
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    # ensure project root is importable
    import sys
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    import baseline_moderation_service as mod
    importlib.reload(mod)
    return mod


def test_baseline_behavior_with_policies_disabled():
    mod = reload_app_with_env({"POLICY_ENABLED": "false", "POLICY_FILE": None})

    resp = mod.submit_content(mod.SubmitContentRequest(user_id="alice", text="this contains scam content"))
    assert resp.status == mod.ContentStatus.BLOCKED
    assert "Blacklisted keyword hit" in (resp.reason or "")


def test_low_risk_auto_approve():
    mod = reload_app_with_env({"POLICY_ENABLED": "1", "POLICY_FILE": "policy.json"})

    resp = mod.submit_content(mod.SubmitContentRequest(user_id="bob", text="a benign announcement for users"))
    assert resp.status == mod.ContentStatus.APPROVED
    assert "policy:low_keywords_auto_approve" in (resp.reason or "")


def test_medium_routed_to_manual_review():
    mod = reload_app_with_env({"POLICY_ENABLED": "1", "POLICY_FILE": "policy.json"})

    resp = mod.submit_content(mod.SubmitContentRequest(user_id="charlie", text="I need help with my account"))
    assert resp.status == mod.ContentStatus.PENDING_REVIEW
    # check queue contains it (most recent)
    assert len(mod.REVIEW_QUEUE) >= 1
    cid = mod.REVIEW_QUEUE[-1]
    assert cid in mod.CONTENTS


def test_high_risk_reject_and_block():
    mod = reload_app_with_env({"POLICY_ENABLED": "1", "POLICY_FILE": "policy.json"})

    # user-based high risk -> REJECT
    r = mod.submit_content(mod.SubmitContentRequest(user_id="bad_user_1", text="normal text"))
    assert r.status == mod.ContentStatus.REJECTED
    assert "policy:high_bad_actor" in (r.reason or "")

    # keyword-based high risk -> BLOCK
    r2 = mod.submit_content(mod.SubmitContentRequest(user_id="eve", text="this mentions exploit techniques"))
    assert r2.status == mod.ContentStatus.BLOCKED
    assert "policy:high_blocked_words" in (r2.reason or "")


def test_rule_composition_or_prefix_match():
    mod = reload_app_with_env({"POLICY_ENABLED": "1", "POLICY_FILE": "policy.json"})

    r = mod.submit_content(mod.SubmitContentRequest(user_id="trial_account_7", text="just saying hi"))
    assert r.status == mod.ContentStatus.PENDING_REVIEW
    assert "policy:medium_keyword_or_user" in (r.reason or "")


def test_policy_vs_blacklist_order_policy_first():
    # text contains both a low-risk policy keyword and a blacklist word; policy should win (policy-first)
    mod = reload_app_with_env({"POLICY_ENABLED": "1", "POLICY_FILE": "policy.json"})

    text = "benign but also contains spam"
    r = mod.submit_content(mod.SubmitContentRequest(user_id="sam", text=text))
    # policy low-risk auto-approve should take precedence over blacklist when policies are enabled
    assert r.status == mod.ContentStatus.APPROVED
    assert "policy:low_keywords_auto_approve" in (r.reason or "")
