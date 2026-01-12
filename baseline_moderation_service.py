# baseline_moderation_service.py
# Baseline content moderation service:
# - Keyword blacklist
# - Manual review queue
# - Block interception on blacklist hit

# fastapi import is optional for running unit tests in constrained envs (pydantic on Py3.14 can fail)
try:
    from fastapi import FastAPI, HTTPException  # type: ignore
    FASTAPI_AVAILABLE = True
except Exception:
    # provide minimal stand-ins so module can be imported in test runners
    class HTTPException(Exception):
        def __init__(self, status_code: int = 500, detail: str = ""):
            super().__init__(f"HTTP {status_code}: {detail}")

    class _DummyApp:
        def __init__(self, *args, **kwargs):
            pass
        # provide minimal decorator methods used in this module
        def get(self, path, **kwargs):
            def _dec(fn):
                return fn
            return _dec
        def post(self, path, **kwargs):
            def _dec(fn):
                return fn
            return _dec
        def delete(self, path, **kwargs):
            def _dec(fn):
                return fn
            return _dec

        def put(self, path, **kwargs):
            def _dec(fn):
                return fn
            return _dec

    FastAPI = lambda *a, **k: _DummyApp()  # type: ignore
    FASTAPI_AVAILABLE = False

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


# Pydantic models are preferred, but can fail to import/initialize on some Python/pydantic
# version combinations. Fall back to plain Python dataclasses-like objects to keep runtime/test
# behavior stable for the exercise environment.
try:
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
except Exception:
    # simple fallbacks
    class SubmitContentRequest:
        def __init__(self, user_id: str, text: str):
            self.user_id = user_id
            self.text = text

    class SubmitContentResponse:
        def __init__(self, content_id: str, status: ContentStatus, reason: Optional[str] = None):
            self.content_id = content_id
            self.status = status
            self.reason = reason

    class ReviewDecisionRequest:
        def __init__(self, reviewer_id: str, decision: ContentStatus, note: Optional[str] = None):
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


# --- In-memory stores (baseline) ---
BLACKLIST: List[str] = ["spam", "scam", "illegal"]  # baseline static list
CONTENTS: Dict[str, ContentItem] = {}
REVIEW_QUEUE: List[str] = []  # store content_id in FIFO order


# --- Policy engine (config-driven, extensible) ---
# Policies are loaded from an external JSON file (policy.json by default).
# Control via environment variables:
# - POLICY_FILE: path to the policy file (default: ./policy.json)
# - POLICY_ENABLED: if set to "0", "false" (case-insensitive) policies are disabled

import os
import json

POLICY_FILE = os.environ.get("POLICY_FILE", "policy.json")
POLICY_ENABLED = os.environ.get("POLICY_ENABLED", "1").lower() not in ("0", "false")
_POLICIES: List[dict] = []


def _load_policies() -> List[dict]:
    global _POLICIES
    if not POLICY_ENABLED:
        return []
    try:
        with open(POLICY_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, list):
                _POLICIES = data
            else:
                _POLICIES = []
    except FileNotFoundError:
        _POLICIES = []
    except Exception:
        # On any parse error, disable policies to maintain baseline behavior
        _POLICIES = []
    return _POLICIES


# load once at import
_load_policies()


def _match_keyword_condition(text: str, cond: dict) -> Optional[str]:
    """Return matched keyword or None"""
    kws = cond.get("keywords", [])
    lower = text.lower()
    for kw in kws:
        if kw.lower() in lower:
            return kw
    return None


def _match_user_condition(user_id: str, cond: dict) -> Optional[str]:
    # exact ids
    ids = cond.get("ids", [])
    if user_id in ids:
        return user_id
    # prefixes
    for p in cond.get("prefixes", []):
        if user_id.startswith(p):
            return p
    return None


def _evaluate_rule(rule: dict, text: str, user_id: str) -> Optional[dict]:
    """Return a dict with match info if rule matches, otherwise None"""
    # composite match
    match = rule.get("match")
    if match:
        op = match.get("op", "any").lower()
        conds = match.get("conditions", [])
        results = []
        for c in conds:
            t = c.get("type")
            if t == "keyword":
                m = _match_keyword_condition(text, c)
                results.append(bool(m))
            elif t == "user":
                m = _match_user_condition(user_id, c)
                results.append(bool(m))
            else:
                results.append(False)
        ok = any(results) if op == "any" else all(results)
        if ok:
            # for reason, try to pick first positive condition match
            for c in conds:
                if c.get("type") == "keyword":
                    m = _match_keyword_condition(text, c)
                    if m:
                        return {"rule": rule, "match": f"keyword:{m}"}
                if c.get("type") == "user":
                    m = _match_user_condition(user_id, c)
                    if m:
                        return {"rule": rule, "match": f"user:{m}"}
            return {"rule": rule, "match": "composite"}

    # simple keyword rule
    if rule.get("type") == "keyword":
        m = _match_keyword_condition(text, rule)
        if m:
            return {"rule": rule, "match": f"keyword:{m}"}

    # simple user rule
    if rule.get("type") == "user":
        m = _match_user_condition(user_id, rule)
        if m:
            return {"rule": rule, "match": f"user:{m}"}

    return None


def evaluate_policies(text: str, user_id: str) -> Optional[dict]:
    """Evaluate loaded policies and return decision dict or None if no policy matched."""
    for rule in _POLICIES:
        res = _evaluate_rule(rule, text, user_id)
        if res:
            rule = res["rule"]
            risk = (rule.get("risk") or "MEDIUM").upper()
            action = rule.get("action")
            if risk == "LOW":
                status = ContentStatus.APPROVED
            elif risk == "MEDIUM":
                status = ContentStatus.PENDING_REVIEW
            else:  # HIGH
                if action == "BLOCK":
                    status = ContentStatus.BLOCKED
                else:
                    # default for HIGH is REJECT
                    status = ContentStatus.REJECTED
            reason = f"policy:{rule.get('id')} ({risk}) match={res['match']}"
            return {"status": status, "reason": reason, "rule": rule}
    return None


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

    # Policy-driven decision (policy engine is optional)
    policy_decision = None
    try:
        policy_decision = evaluate_policies(req.text, req.user_id) if _POLICIES else None
    except Exception:
        policy_decision = None

    if policy_decision is not None:
        status = policy_decision["status"]
        reason = policy_decision.get("reason")
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
        if status == ContentStatus.PENDING_REVIEW:
            REVIEW_QUEUE.append(content_id)
        return SubmitContentResponse(
            content_id=content_id,
            status=item.status,
            reason=item.reason,
        )

    # No policy matched (or policies disabled) -> fallback to blacklist (baseline behavior)
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
