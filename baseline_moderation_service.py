# baseline_moderation_service.py
# Baseline content moderation service:
# - Keyword blacklist
# - Manual review queue
# - Block interception on blacklist hit

# FastAPI import is optional for test environments where FastAPI/pydantic have incompatibilities
try:
    from fastapi import FastAPI, HTTPException
    FASTAPI_AVAILABLE = True
except Exception:
    FastAPI = None  # type: ignore
    HTTPException = Exception  # fallback for raising errors in pure functions
    FASTAPI_AVAILABLE = False

from pydantic import BaseModel, Field
from enum import Enum
from typing import Dict, List, Optional
import uuid
import time
import os

from policy.policy_engine import PolicyEngine, PolicyAction

app = FastAPI(title="Baseline Content Moderation Service", version="0.1.0") if FASTAPI_AVAILABLE else None

# Initialize policy engine (will silently disable if no valid config found)
POLICY_ENGINE = PolicyEngine()  # loads policy.json by default if present



class ContentStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"


if FASTAPI_AVAILABLE:
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
else:
    # Lightweight fallback classes for non-FastAPI test environments (avoid Pydantic model construction)
    class SubmitContentRequest:
        def __init__(self, user_id: str, text: str):
            self.user_id = user_id
            self.text = text


    class SubmitContentResponse:
        def __init__(self, content_id: str, status: str, reason: Optional[str] = None):
            self.content_id = content_id
            self.status = status
            self.reason = reason


    class ReviewDecisionRequest:
        def __init__(self, reviewer_id: str, decision: str, note: Optional[str] = None):
            self.reviewer_id = reviewer_id
            self.decision = decision
            self.note = note


    class ContentItem:
        def __init__(
            self,
            content_id: str,
            user_id: str,
            text: str,
            status: ContentStatus,
            created_at: float,
            updated_at: float,
            reason: Optional[str] = None,
            reviewer_id: Optional[str] = None,
            review_note: Optional[str] = None,
        ):
            self.content_id = content_id
            self.user_id = user_id
            self.text = text
            self.status = status
            self.created_at = created_at
            self.updated_at = updated_at
            self.reason = reason
            self.reviewer_id = reviewer_id
            self.review_note = review_note

        def dict(self):
            return {
                "content_id": self.content_id,
                "user_id": self.user_id,
                "text": self.text,
                "status": self.status.value if isinstance(self.status, ContentStatus) else self.status,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "reason": self.reason,
                "reviewer_id": self.reviewer_id,
                "review_note": self.review_note,
            }


# --- In-memory stores (baseline) ---
BLACKLIST: List[str] = ["spam", "scam", "illegal"]  # baseline static list
CONTENTS: Dict[str, ContentItem] = {}
REVIEW_QUEUE: List[str] = []  # store content_id in FIFO order


def _now() -> float:
    return time.time()


def _hit_blacklist(text: str) -> Optional[str]:
    # Simple substring match (baseline)
    lower = text.lower()
    for kw in BLACKLIST:
        if kw.lower() in lower:
            return kw
    return None


def load_policies(path: Optional[str] = None):
    """Load policies from a file path. If path is None, policies are disabled."""
    global POLICY_ENGINE
    if path is None:
        POLICY_ENGINE = PolicyEngine(path=None)
    else:
        POLICY_ENGINE = PolicyEngine(path=path)


def clear_policies():
    """Disable policies."""
    load_policies(path=None)


def reset_state():
    """Clear in-memory stores (useful for tests)."""
    global CONTENTS, REVIEW_QUEUE
    CONTENTS.clear()
    REVIEW_QUEUE.clear()
    # Do not clear blacklist by default



def health():
    return {"ok": True}


def list_blacklist():
    return {"keywords": BLACKLIST}


def add_blacklist_keyword(keyword: str):
    keyword = keyword.strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="keyword cannot be empty")
    if keyword in BLACKLIST:
        return {"added": False, "keywords": BLACKLIST}
    BLACKLIST.append(keyword)
    return {"added": True, "keywords": BLACKLIST}


def remove_blacklist_keyword(keyword: str):
    keyword = keyword.strip()
    if keyword in BLACKLIST:
        BLACKLIST.remove(keyword)
        return {"removed": True, "keywords": BLACKLIST}
    return {"removed": False, "keywords": BLACKLIST}

def submit_content_internal(user_id: str, text: str) -> dict:
    """Core logic for submitting content. Returns dict suitable for response.

    This is separated from the FastAPI route to allow testing without importing FastAPI.
    """
    content_id = str(uuid.uuid4())
    ts = _now()

    # 1) Policy-driven decision (if policies loaded)
    if POLICY_ENGINE and POLICY_ENGINE.loaded:
        decision = POLICY_ENGINE.decide(user_id, text)
        if decision is not None:
            action, reason, pid = decision
            if action == PolicyAction.APPROVE:
                item_status = ContentStatus.APPROVED
            elif action == PolicyAction.REVIEW:
                item_status = ContentStatus.PENDING_REVIEW
            elif action == PolicyAction.REJECT:
                item_status = ContentStatus.REJECTED
            elif action == PolicyAction.BLOCK:
                item_status = ContentStatus.BLOCKED
            else:
                item_status = ContentStatus.PENDING_REVIEW

            item = ContentItem(
                content_id=content_id,
                user_id=user_id,
                text=text,
                status=item_status,
                created_at=ts,
                updated_at=ts,
                reason=reason,
            )
            CONTENTS[content_id] = item
            if item_status == ContentStatus.PENDING_REVIEW:
                REVIEW_QUEUE.append(content_id)

            return {"content_id": content_id, "status": item.status.value, "reason": item.reason}

    # 2) No policy decision -> fallback to original blacklist behavior
    hit = _hit_blacklist(text)
    if hit is not None:
        item = ContentItem(
            content_id=content_id,
            user_id=user_id,
            text=text,
            status=ContentStatus.BLOCKED,
            created_at=ts,
            updated_at=ts,
            reason=f"Blacklisted keyword hit: {hit}",
        )
        CONTENTS[content_id] = item
        return {"content_id": content_id, "status": item.status.value, "reason": item.reason}

    # Not blocked => manual review (baseline default)
    item = ContentItem(
        content_id=content_id,
        user_id=user_id,
        text=text,
        status=ContentStatus.PENDING_REVIEW,
        created_at=ts,
        updated_at=ts,
        reason="Requires manual review",
    )
    CONTENTS[content_id] = item
    REVIEW_QUEUE.append(content_id)

    return {"content_id": content_id, "status": item.status.value, "reason": item.reason}


def submit_content(req: SubmitContentRequest):
    return SubmitContentResponse(**submit_content_internal(req.user_id, req.text))


def get_content(content_id: str):
    item = CONTENTS.get(content_id)
    if item is None:
        raise HTTPException(status_code=404, detail="content not found")
    return item


def get_review_queue_internal(limit: int = 20) -> dict:
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be > 0")
    ids = REVIEW_QUEUE[:limit]
    items = [CONTENTS[i].dict() if hasattr(CONTENTS[i], "dict") else {
        "content_id": CONTENTS[i].content_id,
        "user_id": CONTENTS[i].user_id,
        "text": CONTENTS[i].text,
        "status": CONTENTS[i].status.value if isinstance(CONTENTS[i].status, ContentStatus) else CONTENTS[i].status,
        "created_at": CONTENTS[i].created_at,
        "updated_at": CONTENTS[i].updated_at,
        "reason": CONTENTS[i].reason,
        "reviewer_id": CONTENTS[i].reviewer_id,
        "review_note": CONTENTS[i].review_note,
    } for i in ids if i in CONTENTS]
    return {"count": len(items), "items": items}

def get_review_queue(limit: int = 20):
    return get_review_queue_internal(limit)


def review_content(content_id: str, req: ReviewDecisionRequest):
    return review_content_internal(content_id, req.reviewer_id, req.decision.value if isinstance(req.decision, ContentStatus) else req.decision, req.note)


# Register routes only if FastAPI is available
if FASTAPI_AVAILABLE:
    app.get("/health")(health)
    app.get("/blacklist")(list_blacklist)
    app.post("/blacklist")(add_blacklist_keyword)
    app.delete("/blacklist")(remove_blacklist_keyword)
    app.post("/content/submit", response_model=SubmitContentResponse)(submit_content)
    app.get("/content/{content_id}", response_model=ContentItem)(get_content)
    app.get("/review/queue")(get_review_queue)
    app.post("/review/{content_id}")(review_content)


def review_content_internal(content_id: str, reviewer_id: str, decision: str, note: Optional[str]):
    item = CONTENTS.get(content_id)
    if item is None:
        raise HTTPException(status_code=404, detail="content not found")

    if item.status != ContentStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=409,
            detail=f"content status is {item.status}, cannot review",
        )

    # decision may be a string value
    try:
        dec_enum = ContentStatus(decision)
    except Exception:
        raise HTTPException(status_code=400, detail="decision must be APPROVED or REJECTED")

    if dec_enum not in (ContentStatus.APPROVED, ContentStatus.REJECTED):
        raise HTTPException(status_code=400, detail="decision must be APPROVED or REJECTED")

    item.status = dec_enum
    item.updated_at = _now()
    item.reviewer_id = reviewer_id
    item.review_note = note

    # Remove from queue if present
    try:
        REVIEW_QUEUE.remove(content_id)
    except ValueError:
        pass

    CONTENTS[content_id] = item
    return {"content_id": content_id, "status": item.status.value, "reviewer_id": item.reviewer_id}

