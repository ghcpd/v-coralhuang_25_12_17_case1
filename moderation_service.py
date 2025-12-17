# moderation_service.py
"""
Extended content moderation service with policy-driven decision engine.
Maintains backward compatibility with baseline blacklist-based moderation.

Execution Order:
1. If policies are enabled, evaluate policies first
2. If no policy matches, fall back to blacklist
3. If neither policy nor blacklist match, route to manual review

This order prioritizes automated decisions (policies) while maintaining
legacy blacklist functionality and ensuring all content is handled.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from enum import Enum
from typing import Dict, List, Optional
import uuid
import time
import os
from src.policy_engine import PolicyConfiguration

app = FastAPI(title="Content Moderation Service", version="1.0.0")


class ContentStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"


class SubmitContentRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1, max_length=5000)


class SubmitContentResponse(BaseModel):
    content_id: str
    status: ContentStatus
    reason: Optional[str] = None


class ReviewDecisionRequest(BaseModel):
    reviewer_id: str = Field(..., min_length=1)
    decision: ContentStatus  # APPROVED or REJECTED
    note: Optional[str] = Field(default=None, max_length=1000)


class ContentItem(BaseModel):
    content_id: str
    user_id: str
    text: str
    status: ContentStatus
    created_at: float
    updated_at: float
    reason: Optional[str] = None
    reviewer_id: Optional[str] = None
    review_note: Optional[str] = None


# --- Configuration ---
POLICY_FILE = os.environ.get("POLICY_FILE", "policy.json")
ENABLE_POLICY_ENGINE = os.environ.get("ENABLE_POLICY_ENGINE", "true").lower() == "true"

# --- In-memory stores ---
BLACKLIST: List[str] = ["spam", "scam", "illegal"]  # baseline static list
CONTENTS: Dict[str, ContentItem] = {}
REVIEW_QUEUE: List[str] = []  # store content_id in FIFO order

# --- Policy engine initialization ---
policy_config = PolicyConfiguration(POLICY_FILE if ENABLE_POLICY_ENGINE else None)


def _now() -> float:
    return time.time()


def _hit_blacklist(text: str) -> Optional[str]:
    """Check if text matches any keyword in the blacklist."""
    lower = text.lower()
    for kw in BLACKLIST:
        if kw.lower() in lower:
            return kw
    return None


def _make_moderation_decision(user_id: str, text: str) -> tuple[ContentStatus, str]:
    """
    Make a moderation decision based on policies and blacklist.
    
    Returns (status, reason)
    
    Execution order:
    1. Check policies first (if enabled)
    2. Fall back to blacklist
    3. Default to manual review
    """
    reason = ""
    
    # Step 1: Check policies
    if ENABLE_POLICY_ENGINE and policy_config.is_enabled():
        action, policy_reason = policy_config.decide(user_id, text)
        if action:
            reason = policy_reason or f"Policy triggered: {action}"
            return ContentStatus(action), reason
    
    # Step 2: Check blacklist
    blacklist_hit = _hit_blacklist(text)
    if blacklist_hit is not None:
        reason = f"Blacklisted keyword hit: {blacklist_hit}"
        return ContentStatus.BLOCKED, reason
    
    # Step 3: Default to manual review
    reason = "Requires manual review"
    return ContentStatus.PENDING_REVIEW, reason


@app.get("/health")
def health():
    return {
        "ok": True,
        "policies_enabled": ENABLE_POLICY_ENGINE and policy_config.is_enabled()
    }


@app.get("/blacklist")
def list_blacklist():
    return {"keywords": BLACKLIST}


@app.post("/blacklist")
def add_blacklist_keyword(keyword: str):
    keyword = keyword.strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="keyword cannot be empty")
    if keyword in BLACKLIST:
        return {"added": False, "keywords": BLACKLIST}
    BLACKLIST.append(keyword)
    return {"added": True, "keywords": BLACKLIST}


@app.delete("/blacklist")
def remove_blacklist_keyword(keyword: str):
    keyword = keyword.strip()
    if keyword in BLACKLIST:
        BLACKLIST.remove(keyword)
        return {"removed": True, "keywords": BLACKLIST}
    return {"removed": False, "keywords": BLACKLIST}


@app.get("/policy/status")
def policy_status():
    """Get policy engine status."""
    return {
        "enabled": ENABLE_POLICY_ENGINE and policy_config.is_enabled(),
        "policy_file": POLICY_FILE if ENABLE_POLICY_ENGINE else None
    }


@app.post("/content/submit", response_model=SubmitContentResponse)
def submit_content(req: SubmitContentRequest):
    content_id = str(uuid.uuid4())
    ts = _now()

    # Make moderation decision
    status, reason = _make_moderation_decision(req.user_id, req.text)

    item = ContentItem(
        content_id=content_id,
        user_id=req.user_id,
        text=req.text,
        status=status,
        created_at=ts,
        updated_at=ts,
        reason=reason,
    )
    CONTENTS[content_id] = item

    # Add to review queue if needed
    if status == ContentStatus.PENDING_REVIEW:
        REVIEW_QUEUE.append(content_id)

    return SubmitContentResponse(
        content_id=content_id,
        status=item.status,
        reason=item.reason,
    )


@app.get("/content/{content_id}", response_model=ContentItem)
def get_content(content_id: str):
    item = CONTENTS.get(content_id)
    if item is None:
        raise HTTPException(status_code=404, detail="content not found")
    return item


@app.get("/review/queue")
def get_review_queue(limit: int = 20):
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be > 0")
    ids = REVIEW_QUEUE[:limit]
    items = [CONTENTS[i] for i in ids if i in CONTENTS]
    return {"count": len(items), "items": items}


@app.post("/review/{content_id}")
def review_content(content_id: str, req: ReviewDecisionRequest):
    item = CONTENTS.get(content_id)
    if item is None:
        raise HTTPException(status_code=404, detail="content not found")

    if item.status != ContentStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=409,
            detail=f"content status is {item.status}, cannot review",
        )

    if req.decision not in (ContentStatus.APPROVED, ContentStatus.REJECTED):
        raise HTTPException(status_code=400, detail="decision must be APPROVED or REJECTED")

    item.status = req.decision
    item.updated_at = _now()
    item.reviewer_id = req.reviewer_id
    item.review_note = req.note

    # Remove from queue if present
    try:
        REVIEW_QUEUE.remove(content_id)
    except ValueError:
        pass

    CONTENTS[content_id] = item
    return {"content_id": content_id, "status": item.status, "reviewer_id": item.reviewer_id}


# Keep baseline functionality for backward compatibility
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
