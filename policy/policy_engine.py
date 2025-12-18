import json
import os
from typing import Any, Dict, List, Optional, Tuple

from enum import Enum


class PolicyAction(Enum):
    APPROVE = "APPROVE"
    REVIEW = "REVIEW"
    REJECT = "REJECT"
    BLOCK = "BLOCK"


ACTION_MAP = {
    "LOW": PolicyAction.APPROVE,
    "MEDIUM": PolicyAction.REVIEW,
    "HIGH": PolicyAction.REJECT,
}


class PolicyEngine:
    """Simple, extensible policy engine.

    - Loads policies from a JSON file (path passed or from POLICY_CONFIG_PATH env var).
    - Policies are evaluated in order; the first matching policy is applied.

    Policy JSON (example):
    {
      "policies": [
        {
          "id": "auto_approve_trusted",
          "description": "auto approve trusted users",
          "operator": "OR",
          "rules": [
            {"type": "user", "user_prefixes": ["trusted_"]}
          ],
          "risk": "LOW",            # optional
          "action": "APPROVE"      # optional, overrides risk
        }
      ]
    }
    """

    def __init__(self, path: Optional[str] = None):
        self.path = path or os.getenv("POLICY_CONFIG_PATH", "policy.json")
        self.policies: List[Dict[str, Any]] = []
        self.loaded: bool = False
        self.load()

    def load(self):
        if not self.path:
            self.policies = []
            self.loaded = False
            return
        if not os.path.exists(self.path):
            self.policies = []
            self.loaded = False
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                conf = json.load(f)
            self.policies = conf.get("policies", []) or []
            self.loaded = bool(self.policies)
        except Exception:
            self.policies = []
            self.loaded = False

    def reload(self, path: Optional[str] = None):
        if path is not None:
            self.path = path
        self.load()

    def decide(self, user_id: str, text: str) -> Optional[Tuple[PolicyAction, str, str]]:
        """
        Evaluate policies. Returns a tuple (PolicyAction, reason, policy_id) when a policy matches, otherwise None.
        """
        if not self.loaded:
            return None
        lower_text = text.lower()
        for policy in self.policies:
            pid = policy.get("id", "<unnamed>")
            operator = (policy.get("operator") or "OR").upper()
            rules = policy.get("rules", [])
            rule_matches = []
            # Evaluate each rule
            for r in rules:
                rtype = r.get("type")
                matched = False
                match_detail = None
                if rtype == "keyword":
                    keywords = r.get("keywords", [])
                    matched_keywords = [kw for kw in keywords if kw.lower() in lower_text]
                    if matched_keywords:
                        matched = True
                        match_detail = f"keywords={matched_keywords}"
                elif rtype == "user":
                    user_ids = r.get("user_ids", [])
                    prefixes = r.get("user_prefixes", [])
                    if user_id in user_ids:
                        matched = True
                        match_detail = f"user_id={user_id}"
                    else:
                        matched_prefixes = [p for p in prefixes if user_id.startswith(p)]
                        if matched_prefixes:
                            matched = True
                            match_detail = f"user_prefixes={matched_prefixes}"
                else:
                    # Unknown rule types are not matched but can be extended
                    matched = False
                rule_matches.append((matched, match_detail or "no-detail", r))

            # Combine rule results
            booleans = [m for m, _, _ in rule_matches]
            if not booleans:
                continue
            if operator == "AND":
                overall = all(booleans)
            else:
                overall = any(booleans)

            if overall:
                # Determine action
                action_str = (policy.get("action") or "").upper()
                if action_str in (a.name for a in PolicyAction):
                    action = PolicyAction[action_str]
                else:
                    # fallback to risk
                    risk = (policy.get("risk") or "").upper()
                    action = ACTION_MAP.get(risk, PolicyAction.REVIEW)

                matched_details = [d for m, d, _ in rule_matches if m]
                reason = f"policy:{pid}; matched: {matched_details}; action: {action.name}"
                return action, reason, pid
        return None
