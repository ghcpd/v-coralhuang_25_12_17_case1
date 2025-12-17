# baseline_moderation_service.py
# Baseline content moderation service:
# - Keyword blacklist
# - Manual review queue
# - Block interception on blacklist hit

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from enum import Enum
from typing import Dict, List, Optional
import uuid
import time

app = FastAPI(title="Baseline Content Moderation Service", version="0.1.0")


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


@app.get("/health")
def health():
    return {"ok": True}


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


@app.post("/content/submit", response_model=SubmitContentResponse)
def submit_content(req: SubmitContentRequest):
    content_id = str(uuid.uuid4())
    ts = _now()

    hit = _hit_blacklist(req.text)
    if hit is not None:
        item = ContentItem(
            content_id=content_id,
            user_id=req.user_id,
            text=req.text,
            status=ContentStatus.BLOCKED,
            created_at=ts,
            updated_at=ts,
            reason=f"Blacklisted keyword hit: {hit}",
        )
        CONTENTS[content_id] = item
        return SubmitContentResponse(
            content_id=content_id,
            status=item.status,
            reason=item.reason,
        )

    # Not blocked -> require manual review in baseline
    item = ContentItem(
        content_id=content_id,
        user_id=req.user_id,
        text=req.text,
        status=ContentStatus.PENDING_REVIEW,
        created_at=ts,
        updated_at=ts,
        reason="Requires manual review",
    )
    CONTENTS[content_id] = item
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
