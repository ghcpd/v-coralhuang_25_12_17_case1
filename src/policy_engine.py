# src/policy_engine.py
"""
Policy-driven moderation decision engine.
Supports keyword-based, user-based, and composite rule evaluation.
"""

from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
import json
from pathlib import Path


class RuleType(str, Enum):
    KEYWORD = "keyword"
    USER_ID = "user_id"


class MatchType(str, Enum):
    EXPLICIT = "explicit"
    PREFIX = "prefix"
    SUBSTRING = "substring"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Composition(str, Enum):
    AND = "AND"
    OR = "OR"


class Rule:
    """Single rule that can match against content."""
    
    def __init__(self, rule_type: str, match_type: str, values: List[str]):
        self.rule_type = RuleType(rule_type)
        self.match_type = MatchType(match_type)
        self.values = values
    
    def matches(self, user_id: str, text: str) -> bool:
        """Check if this rule matches the given content."""
        if self.rule_type == RuleType.KEYWORD:
            return self._match_keyword(text)
        elif self.rule_type == RuleType.USER_ID:
            return self._match_user_id(user_id)
        return False
    
    def _match_keyword(self, text: str) -> bool:
        """Match against text content."""
        lower_text = text.lower()
        if self.match_type == MatchType.SUBSTRING:
            return any(kw.lower() in lower_text for kw in self.values)
        elif self.match_type == MatchType.EXPLICIT:
            return lower_text in [v.lower() for v in self.values]
        return False
    
    def _match_user_id(self, user_id: str) -> bool:
        """Match against user ID."""
        if self.match_type == MatchType.EXPLICIT:
            return user_id in self.values
        elif self.match_type == MatchType.PREFIX:
            return any(user_id.startswith(prefix) for prefix in self.values)
        return False


class Policy:
    """Policy containing multiple rules and decision logic."""
    
    def __init__(self, policy_id: str, name: str, description: str, 
                 risk_level: str, action: str, rules: List[Dict[str, Any]], 
                 composition: str):
        self.policy_id = policy_id
        self.name = name
        self.description = description
        self.risk_level = RiskLevel(risk_level)
        self.action = action
        self.composition = Composition(composition)
        self.rules = [Rule(r["type"], r["match_type"], r["values"]) for r in rules]
    
    def evaluate(self, user_id: str, text: str) -> Tuple[bool, str]:
        """
        Evaluate if this policy matches the content.
        Returns (matches: bool, reason: str)
        """
        if not self.rules:
            return False, ""
        
        if self.composition == Composition.AND:
            # All rules must match
            matches = all(rule.matches(user_id, text) for rule in self.rules)
            if matches:
                return True, f"Policy '{self.name}' matched (AND logic)"
        elif self.composition == Composition.OR:
            # At least one rule must match
            matches = any(rule.matches(user_id, text) for rule in self.rules)
            if matches:
                return True, f"Policy '{self.name}' matched (OR logic)"
        
        return False, ""


class PolicyEngine:
    """Main policy evaluation engine."""
    
    def __init__(self, policies: List[Policy]):
        self.policies = policies
    
    @staticmethod
    def load_from_file(file_path: str) -> "PolicyEngine":
        """Load policies from JSON file."""
        with open(file_path, 'r') as f:
            config = json.load(f)
        
        enabled = config.get("enabled", False)
        if not enabled:
            return PolicyEngine([])
        
        policies_data = config.get("policies", [])
        policies = [
            Policy(
                policy_id=p["id"],
                name=p["name"],
                description=p["description"],
                risk_level=p["risk_level"],
                action=p["action"],
                rules=p["rules"],
                composition=p["composition"]
            )
            for p in policies_data
        ]
        return PolicyEngine(policies)
    
    def decide(self, user_id: str, text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Evaluate all policies and return (action, reason) for first matching policy.
        Returns (None, None) if no policies match.
        """
        for policy in self.policies:
            matches, reason = policy.evaluate(user_id, text)
            if matches:
                return policy.action, f"{reason} → Action: {policy.action}"
        
        return None, None


class PolicyConfiguration:
    """Manages policy configuration and lifecycle."""
    
    def __init__(self, policy_file: Optional[str] = None):
        self.engine: Optional[PolicyEngine] = None
        if policy_file and Path(policy_file).exists():
            self.engine = PolicyEngine.load_from_file(policy_file)
    
    def is_enabled(self) -> bool:
        """Check if policies are enabled."""
        return self.engine is not None and len(self.engine.policies) > 0
    
    def decide(self, user_id: str, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Get moderation decision from policies."""
        if not self.is_enabled():
            return None, None
        return self.engine.decide(user_id, text)
    
    def reload(self, policy_file: str):
        """Reload policies from file."""
        self.engine = PolicyEngine.load_from_file(policy_file)
