# tests/test_policy_engine.py
"""
Unit tests for the policy engine.
Tests rule matching, policy evaluation, and decision logic.
"""

import pytest
from src.policy_engine import (
    Rule, Policy, PolicyEngine, PolicyConfiguration, 
    RuleType, MatchType, RiskLevel, Composition
)


class TestRule:
    """Test individual rule matching."""
    
    def test_keyword_substring_match(self):
        rule = Rule("keyword", "substring", ["spam", "scam"])
        assert rule.matches("any_user", "This is spam content") is True
        assert rule.matches("any_user", "clean content") is False
        assert rule.matches("any_user", "SPAM") is True  # case insensitive
    
    def test_keyword_explicit_match(self):
        rule = Rule("keyword", "explicit", ["spam"])
        assert rule.matches("any_user", "spam") is True
        assert rule.matches("any_user", "this is spam") is False
        assert rule.matches("any_user", "SPAM") is True  # case insensitive
    
    def test_user_id_explicit_match(self):
        rule = Rule("user_id", "explicit", ["user1", "user2"])
        assert rule.matches("user1", "any content") is True
        assert rule.matches("user3", "any content") is False
    
    def test_user_id_prefix_match(self):
        rule = Rule("user_id", "prefix", ["admin_", "trusted_"])
        assert rule.matches("admin_user1", "any content") is True
        assert rule.matches("trusted_reviewer", "any content") is True
        assert rule.matches("guest_user", "any content") is False


class TestPolicy:
    """Test policy evaluation."""
    
    def test_policy_or_composition_keyword(self):
        policy = Policy(
            policy_id="test_1",
            name="Test Policy",
            description="Test",
            risk_level="HIGH",
            action="BLOCKED",
            rules=[
                {"type": "keyword", "match_type": "substring", "values": ["bomb", "exploit"]}
            ],
            composition="OR"
        )
        matches, reason = policy.evaluate("user1", "content with bomb keyword")
        assert matches is True
        assert "Policy" in reason
    
    def test_policy_or_composition_no_match(self):
        policy = Policy(
            policy_id="test_1",
            name="Test Policy",
            description="Test",
            risk_level="HIGH",
            action="BLOCKED",
            rules=[
                {"type": "keyword", "match_type": "substring", "values": ["bomb", "exploit"]}
            ],
            composition="OR"
        )
        matches, reason = policy.evaluate("user1", "clean content")
        assert matches is False
    
    def test_policy_and_composition_both_match(self):
        policy = Policy(
            policy_id="test_2",
            name="Combined Check",
            description="Test",
            risk_level="MEDIUM",
            action="PENDING_REVIEW",
            rules=[
                {"type": "keyword", "match_type": "substring", "values": ["discount"]},
                {"type": "user_id", "match_type": "prefix", "values": ["guest_"]}
            ],
            composition="AND"
        )
        matches, reason = policy.evaluate("guest_user1", "discount offer")
        assert matches is True
    
    def test_policy_and_composition_partial_match(self):
        policy = Policy(
            policy_id="test_2",
            name="Combined Check",
            description="Test",
            risk_level="MEDIUM",
            action="PENDING_REVIEW",
            rules=[
                {"type": "keyword", "match_type": "substring", "values": ["discount"]},
                {"type": "user_id", "match_type": "prefix", "values": ["guest_"]}
            ],
            composition="AND"
        )
        # Only keyword matches, user ID doesn't
        matches, reason = policy.evaluate("admin_user", "discount offer")
        assert matches is False


class TestPolicyEngine:
    """Test the main policy engine."""
    
    def test_engine_with_no_policies(self):
        engine = PolicyEngine([])
        action, reason = engine.decide("user1", "any content")
        assert action is None
        assert reason is None
    
    def test_engine_returns_first_matching_policy(self):
        policy1 = Policy(
            policy_id="policy_1",
            name="Policy 1",
            description="Test",
            risk_level="HIGH",
            action="BLOCKED",
            rules=[{"type": "keyword", "match_type": "substring", "values": ["bomb"]}],
            composition="OR"
        )
        policy2 = Policy(
            policy_id="policy_2",
            name="Policy 2",
            description="Test",
            risk_level="LOW",
            action="APPROVED",
            rules=[{"type": "keyword", "match_type": "substring", "values": ["safe"]}],
            composition="OR"
        )
        engine = PolicyEngine([policy1, policy2])
        
        # Should match policy1
        action, reason = engine.decide("user1", "content with bomb")
        assert action == "BLOCKED"
        
        # Should match policy2 (policy1 doesn't match)
        action, reason = engine.decide("user1", "safe content")
        assert action == "APPROVED"
    
    def test_engine_load_from_file(self):
        engine = PolicyEngine.load_from_file("policy.json")
        assert engine is not None
        assert len(engine.policies) > 0
        
        # Test a real decision
        action, reason = engine.decide("user_verified_1", "some content")
        assert action == "APPROVED"
        assert "low" in reason.lower() or "verify" in reason.lower() or "auto-approve" in reason.lower()


class TestPolicyConfiguration:
    """Test policy configuration management."""
    
    def test_configuration_disabled_with_no_file(self):
        config = PolicyConfiguration(None)
        assert config.is_enabled() is False
        action, reason = config.decide("user1", "any content")
        assert action is None
        assert reason is None
    
    def test_configuration_enabled_with_file(self):
        config = PolicyConfiguration("policy.json")
        assert config.is_enabled() is True
        
        # Should have decisions
        action, reason = config.decide("user_verified_1", "some content")
        assert action is not None
    
    def test_configuration_reload(self):
        config = PolicyConfiguration("policy.json")
        assert config.is_enabled() is True
        
        # Reload should work
        config.reload("policy.json")
        assert config.is_enabled() is True
