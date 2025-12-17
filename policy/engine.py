import json
import os
from typing import Any, Dict, List, Optional


class Rule:
    def __init__(self, rule_id: str, outcome: str, description: Optional[str] = None, priority: int = 100):
        self.id = rule_id
        self.outcome = outcome  # "APPROVE", "PENDING_REVIEW", "REJECT", "BLOCK"
        self.description = description
        self.priority = priority

    def matches(self, text: str, user_id: str) -> bool:
        raise NotImplementedError


class KeywordRule(Rule):
    def __init__(self, rule_id: str, keywords: List[str], **kwargs):
        super().__init__(rule_id, **kwargs)
        self.keywords = [k.lower() for k in keywords]

    def matches(self, text: str, user_id: str) -> bool:
        if not text:
            return False
        lower = text.lower()
        for k in self.keywords:
            if k in lower:
                return True
        return False


class UserRule(Rule):
    def __init__(self, rule_id: str, users: Optional[List[str]] = None, user_prefixes: Optional[List[str]] = None, **kwargs):
        super().__init__(rule_id, **kwargs)
        self.users = set(users or [])
        self.user_prefixes = user_prefixes or []

    def matches(self, text: str, user_id: str) -> bool:
        if not user_id:
            return False
        if user_id in self.users:
            return True
        for p in self.user_prefixes:
            if user_id.startswith(p):
                return True
        return False


class CompositeRule(Rule):
    def __init__(self, rule_id: str, operator: str, rules: List[Rule], **kwargs):
        super().__init__(rule_id, **kwargs)
        self.operator = operator.upper()
        self.rules = rules

    def matches(self, text: str, user_id: str) -> bool:
        if self.operator == "AND":
            return all(r.matches(text, user_id) for r in self.rules)
        else:
            # default OR
            return any(r.matches(text, user_id) for r in self.rules)


_RULE_FACTORY = {
    "keyword": KeywordRule,
    "user": UserRule,
    "composite": CompositeRule,
}


def _instantiate_rule(defn: Dict[str, Any]) -> Rule:
    rtype = defn.get("type")
    rule_id = defn.get("id", defn.get("name", "unnamed_rule"))
    outcome = defn.get("outcome") or defn.get("effect") or "PENDING_REVIEW"
    description = defn.get("description")
    priority = int(defn.get("priority", 100))

    if rtype == "keyword":
        return KeywordRule(rule_id=rule_id, keywords=defn.get("keywords", []), outcome=outcome, description=description, priority=priority)
    elif rtype == "user":
        return UserRule(rule_id=rule_id, users=defn.get("users"), user_prefixes=defn.get("user_prefixes"), outcome=outcome, description=description, priority=priority)
    elif rtype == "composite":
        operator = defn.get("operator", "OR")
        sub_defs = defn.get("rules", [])
        sub_rules = [_instantiate_rule(sub) for sub in sub_defs]
        return CompositeRule(rule_id=rule_id, operator=operator, rules=sub_rules, outcome=outcome, description=description, priority=priority)
    else:
        raise ValueError(f"unknown rule type: {rtype}")


class PolicyEngine:
    def __init__(self, policy_file: Optional[str] = None):
        self.policy_file = policy_file or os.getenv("POLICY_FILE", "policy.json")
        self.enabled = False
        self.rules: List[Rule] = []
        self.load(self.policy_file)

    def load(self, policy_file: Optional[str] = None):
        self.rules = []
        if policy_file:
            self.policy_file = policy_file
        if not os.path.exists(self.policy_file):
            self.enabled = False
            return
        try:
            with open(self.policy_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            instantiated = []
            for defn in data:
                r = _instantiate_rule(defn)
                instantiated.append(r)
            # sort by priority asc (lower value = higher priority)
            self.rules = sorted(instantiated, key=lambda r: r.priority)
            self.enabled = True
        except Exception:
            self.enabled = False

    def evaluate(self, text: str, user_id: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        for rule in self.rules:
            if rule.matches(text, user_id):
                explanation = f"rule {rule.id} matched (priority={rule.priority})"
                return {"rule": rule, "outcome": rule.outcome, "explanation": explanation}
        return None
