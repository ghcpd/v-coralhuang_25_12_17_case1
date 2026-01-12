# policy_engine.py
"""Simple configuration-driven policy engine.

Policy file format (JSON):
{
  "enabled": true,
  "policies": [
    {
      "id": "rule1",
      "match": {"any": [{"type": "keyword", "value": "spam"}]},
      "risk": "low"  # low|medium|high
      # optional action: "reject" or "block" for high risk; default is reject
    },
    ...
  ]
}

Where a match can be "any" (OR) or "all" (AND) of conditions. Each condition is
{ "type": "keyword", "value": "word" } or { "type": "user", "value": "user1" } or { "type": "user", "prefix": "prefix_" }.

The engine is intentionally simple and extensible: to add new rule types, add a
handler in _match_condition.
"""

import json
import os
from enum import Enum
from typing import Dict, List, Optional

from baseline_moderation_service import ContentStatus, SubmitContentRequest


class PolicyAction(Enum):
    APPROVE = "APPROVE"
    REVIEW = "REVIEW"
    REJECT = "REJECT"
    BLOCK = "BLOCK"


def _load_policy_file(path: str) -> Optional[Dict]:
    if not os.path.exists(path):
        print(f"policy_engine: path not found: {path}")
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(f"policy_engine: loaded policy: {data}")
            return data
    except Exception as e:
        print(f"policy_engine: error loading policy file {path}: {e}")
        return None


def _match_condition(condition: Dict, req: SubmitContentRequest) -> bool:
    typ = condition.get("type")
    if typ == "keyword":
        val = condition.get("value", "").lower()
        return val in req.text.lower()
    if typ == "user":
        if "value" in condition:
            return req.user_id == condition["value"]
        if "prefix" in condition:
            return req.user_id.startswith(condition["prefix"])
    # Unknown condition type -> default non-matching
    return False


def _evaluate_policy(req: SubmitContentRequest, policy: Dict) -> Optional[Dict]:
    # policy is the loaded JSON object
    if not policy.get("enabled", False):
        return None

    for rule in policy.get("policies", []):
        match = rule.get("match", {})
        if "any" in match:
            matched = any(_match_condition(c, req) for c in match["any"])
        elif "all" in match:
            matched = all(_match_condition(c, req) for c in match["all"])
        else:
            matched = False

        if matched:
            # Determine action based on risk and optional action override
            risk = rule.get("risk", "medium").lower()
            action = rule.get("action")
            if risk == "low":
                final_action = PolicyAction.APPROVE
            elif risk == "medium":
                final_action = PolicyAction.REVIEW
            else:  # high
                if action == "block":
                    final_action = PolicyAction.BLOCK
                else:
                    final_action = PolicyAction.REJECT

            return {
                "rule_id": rule.get("id", "<unnamed>"),
                "risk": risk,
                "action": final_action,
                "reason": rule.get("reason", f"Rule matched: {rule.get('id')}")
            }
    return None


def evaluate_request(req: SubmitContentRequest) -> Optional[Dict]:
    # Load policy from env or default
    path = os.environ.get("MODERATION_POLICY_FILE")
    # If the env var is not set, do not use any policy (keeps baseline behavior)
    if not path:
        return None

    print(f"policy_engine: evaluating with policy file: {path}")

    policy = _load_policy_file(path)

    if not policy:
        return None

    return _evaluate_policy(req, policy)


def decision_from_evaluation(eval_result: Dict) -> (ContentStatus, str):
    action = eval_result["action"]
    rule_id = eval_result.get("rule_id", "<unnamed>")
    reason = eval_result.get("reason", f"Policy rule '{rule_id}' matched")
    if action == PolicyAction.APPROVE:
        return ContentStatus.APPROVED, f"Policy '{rule_id}' -> APPROVED (low risk)"
    if action == PolicyAction.REVIEW:
        return ContentStatus.PENDING_REVIEW, f"Policy '{rule_id}' -> PENDING_REVIEW (medium risk)"
    if action == PolicyAction.REJECT:
        return ContentStatus.REJECTED, f"Policy '{rule_id}' -> REJECTED (high risk)"
    if action == PolicyAction.BLOCK:
        return ContentStatus.BLOCKED, f"Policy '{rule_id}' -> BLOCKED (high risk)"
    # fallback
    return ContentStatus.PENDING_REVIEW, reason
