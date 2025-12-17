# tests/test_moderation_service.py
"""
Integration tests for the moderation service.
Tests the full content submission flow with policies and blacklist.
"""

import pytest
import os
from fastapi.testclient import TestClient
from unittest.mock import patch

# Set environment to enable policies
os.environ["ENABLE_POLICY_ENGINE"] = "true"
os.environ["POLICY_FILE"] = "policy.json"

from moderation_service import app, BLACKLIST, CONTENTS, REVIEW_QUEUE, ContentStatus


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state before each test."""
    BLACKLIST.clear()
    BLACKLIST.extend(["spam", "scam", "illegal"])
    CONTENTS.clear()
    REVIEW_QUEUE.clear()
    yield


class TestBaselineBehavior:
    """Test backward compatibility - baseline behavior without policies."""
    
    def test_blacklist_blocking(self, client):
        """Test that blacklist still blocks content."""
        response = client.post("/content/submit", json={
            "user_id": "user1",
            "text": "This content contains spam"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "BLOCKED"
        assert "spam" in data["reason"].lower()
    
    def test_manual_review_default(self, client):
        """Test that non-blacklisted content goes to manual review."""
        response = client.post("/content/submit", json={
            "user_id": "user1",
            "text": "This is clean content"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "PENDING_REVIEW"
        assert data["reason"] is not None
    
    def test_blacklist_management(self, client):
        """Test adding and removing blacklist keywords."""
        # Add keyword
        response = client.post("/blacklist?keyword=malware")
        assert response.status_code == 200
        data = response.json()
        assert data["added"] is True
        assert "malware" in data["keywords"]
        
        # Block with new keyword
        response = client.post("/content/submit", json={
            "user_id": "user1",
            "text": "This has malware"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "BLOCKED"
        
        # Remove keyword
        response = client.delete("/blacklist?keyword=malware")
        assert response.status_code == 200
        data = response.json()
        assert data["removed"] is True


class TestLowRiskPolicy:
    """Test low-risk policies that auto-approve."""
    
    def test_verified_user_auto_approval(self, client):
        """Test that verified users are auto-approved."""
        response = client.post("/content/submit", json={
            "user_id": "user_verified_1",
            "text": "Some content from verified user"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "APPROVED"
        assert data["reason"] is not None
        assert "policy" in data["reason"].lower() or "approve" in data["reason"].lower()
    
    def test_trusted_prefix_auto_approval(self, client):
        """Test that users with trusted prefix are auto-approved."""
        response = client.post("/content/submit", json={
            "user_id": "admin_user1",
            "text": "Content from admin"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "APPROVED"
    
    def test_regular_user_not_auto_approved(self, client):
        """Test that regular users are not auto-approved."""
        response = client.post("/content/submit", json={
            "user_id": "regular_user",
            "text": "Clean content"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "PENDING_REVIEW"


class TestMediumRiskPolicy:
    """Test medium-risk policies that route to manual review."""
    
    def test_suspicious_keywords_require_review(self, client):
        """Test that suspicious content requires manual review."""
        response = client.post("/content/submit", json={
            "user_id": "user1",
            "text": "Check this urgent offer"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "PENDING_REVIEW"
        assert data["reason"] is not None
    
    def test_combined_and_logic_both_match(self, client):
        """Test AND logic requires all rules to match."""
        # Both keyword and user prefix match
        response = client.post("/content/submit", json={
            "user_id": "guest_user1",
            "text": "Limited time discount offer"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "PENDING_REVIEW"
        assert data["reason"] is not None
    
    def test_combined_and_logic_partial_match(self, client):
        """Test AND logic with partial match."""
        # Only keyword matches, user prefix doesn't (admin_ prefix doesn't trigger suspicious policy)
        # But "admin_user1" should match the trusted_prefix policy
        response = client.post("/content/submit", json={
            "user_id": "regular_user1",
            "text": "Limited time discount offer"
        })
        assert response.status_code == 200
        data = response.json()
        # AND policy requires both to match - only keyword matches
        # Falls through to blacklist (no match), then to manual review
        assert data["status"] == "PENDING_REVIEW"


class TestHighRiskPolicy:
    """Test high-risk policies that auto-reject or block."""
    
    def test_dangerous_keywords_blocked(self, client):
        """Test that dangerous keywords trigger blocking."""
        response = client.post("/content/submit", json={
            "user_id": "user1",
            "text": "How to build a bomb"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "BLOCKED"
        # Reason includes policy name which mentions "dangerous keywords"
        assert "dangerous" in data["reason"].lower() or "blocked" in data["reason"].lower()
    
    def test_banned_user_auto_rejection(self, client):
        """Test that banned users are auto-rejected."""
        response = client.post("/content/submit", json={
            "user_id": "user_banned_1",
            "text": "Any content from banned user"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "REJECTED"
        assert data["reason"] is not None
    
    def test_multiple_dangerous_keywords(self, client):
        """Test detection of multiple dangerous keywords."""
        for keyword in ["exploit", "vulnerability", "crack"]:
            response = client.post("/content/submit", json={
                "user_id": "user1",
                "text": f"Information about {keyword}"
            })
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "BLOCKED"


class TestPolicyExecution:
    """Test policy execution order and decision flow."""
    
    def test_policy_executed_before_blacklist(self, client):
        """
        Test that policies are checked before blacklist.
        Verified user with spam content should be auto-approved by policy.
        """
        response = client.post("/content/submit", json={
            "user_id": "user_verified_1",
            "text": "This is spam"
        })
        assert response.status_code == 200
        data = response.json()
        # Policy should approve first
        assert data["status"] == "APPROVED"
    
    def test_blacklist_used_when_no_policy_match(self, client):
        """Test that blacklist is used when no policy matches."""
        response = client.post("/content/submit", json={
            "user_id": "regular_user",
            "text": "This content has illegal stuff"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "BLOCKED"
        assert "illegal" in data["reason"].lower()
    
    def test_manual_review_default_fallback(self, client):
        """Test that manual review is default when nothing matches."""
        response = client.post("/content/submit", json={
            "user_id": "regular_user",
            "text": "Completely normal content here"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "PENDING_REVIEW"


class TestReviewQueue:
    """Test review queue operations."""
    
    def test_pending_items_in_queue(self, client):
        """Test that pending items appear in review queue."""
        # Submit content that requires review
        client.post("/content/submit", json={
            "user_id": "user1",
            "text": "Normal content"
        })
        
        # Check queue
        response = client.get("/review/queue")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert len(data["items"]) == 1
    
    def test_blocked_items_not_in_queue(self, client):
        """Test that blocked items don't appear in review queue."""
        client.post("/content/submit", json={
            "user_id": "user1",
            "text": "Content with spam"
        })
        
        response = client.get("/review/queue")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
    
    def test_approved_items_not_in_queue(self, client):
        """Test that approved items don't appear in review queue."""
        client.post("/content/submit", json={
            "user_id": "user_verified_1",
            "text": "Content from verified user"
        })
        
        response = client.get("/review/queue")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
    
    def test_review_decision(self, client):
        """Test making a review decision."""
        # Submit for review
        submit_response = client.post("/content/submit", json={
            "user_id": "user1",
            "text": "Normal content"
        })
        content_id = submit_response.json()["content_id"]
        
        # Make decision
        review_response = client.post(f"/review/{content_id}", json={
            "reviewer_id": "reviewer1",
            "decision": "APPROVED",
            "note": "Looks good"
        })
        assert review_response.status_code == 200
        
        # Check removed from queue
        queue_response = client.get("/review/queue")
        assert queue_response.json()["count"] == 0
        
        # Check content updated
        content_response = client.get(f"/content/{content_id}")
        content = content_response.json()
        assert content["status"] == "APPROVED"
        assert content["reviewer_id"] == "reviewer1"


class TestReasonField:
    """Test that reason field is clear and traceable."""
    
    def test_reason_for_policy_decision(self, client):
        """Test that reason explains which policy matched."""
        response = client.post("/content/submit", json={
            "user_id": "user_verified_1",
            "text": "Test"
        })
        data = response.json()
        reason = data["reason"]
        assert reason is not None
        assert len(reason) > 0
        assert "policy" in reason.lower() or "approved" in reason.lower()
    
    def test_reason_for_blacklist_decision(self, client):
        """Test that reason explains blacklist hit."""
        response = client.post("/content/submit", json={
            "user_id": "user1",
            "text": "This has spam"
        })
        data = response.json()
        reason = data["reason"]
        assert "spam" in reason.lower()
        assert "blacklist" in reason.lower() or "hit" in reason.lower()
    
    def test_reason_for_manual_review(self, client):
        """Test that reason explains why manual review is needed."""
        response = client.post("/content/submit", json={
            "user_id": "user1",
            "text": "Normal content"
        })
        data = response.json()
        reason = data["reason"]
        assert reason is not None
        assert "review" in reason.lower()


class TestHealthAndStatus:
    """Test health and status endpoints."""
    
    def test_health_endpoint(self, client):
        """Test health check."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "policies_enabled" in data
    
    def test_policy_status_endpoint(self, client):
        """Test policy status endpoint."""
        response = client.get("/policy/status")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "policy_file" in data


class TestErrorHandling:
    """Test error handling."""
    
    def test_content_not_found(self, client):
        """Test 404 for non-existent content."""
        response = client.get("/content/nonexistent")
        assert response.status_code == 404
    
    def test_invalid_review_decision(self, client):
        """Test validation of review decision."""
        submit_response = client.post("/content/submit", json={
            "user_id": "user1",
            "text": "Normal content"
        })
        content_id = submit_response.json()["content_id"]
        
        # Invalid decision
        response = client.post(f"/review/{content_id}", json={
            "reviewer_id": "reviewer1",
            "decision": "INVALID"
        })
        assert response.status_code == 422
    
    def test_review_already_decided_content(self, client):
        """Test cannot review already decided content."""
        # Create blocked content
        submit_response = client.post("/content/submit", json={
            "user_id": "user1",
            "text": "Content with spam"
        })
        content_id = submit_response.json()["content_id"]
        
        # Try to review
        response = client.post(f"/review/{content_id}", json={
            "reviewer_id": "reviewer1",
            "decision": "APPROVED"
        })
        assert response.status_code == 409
