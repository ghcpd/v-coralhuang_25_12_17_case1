# Baseline Content Moderation Service (extended)

Overview
--------
This project provides a small FastAPI-based Content Moderation Service (baseline + extension).

Baseline features (preserved):
- Keyword blacklist blocking: submissions containing a blacklisted keyword are immediately BLOCKED.
- Manual review queue: content that isn't blocked is placed into PENDING_REVIEW and queued for human review.
- Human reviewers can APPROVE or REJECT queued items.

New feature (policy-driven, configurable)
----------------------------------------
A policy-driven, multi-stage moderation engine has been added and is configurable via an external `policy.json` file (no hard-coded rules). When policies are present and enabled, submissions are evaluated by the policy engine before the blacklist. Execution order: POLICY -> BLACKLIST -> DEFAULT (manual review). This means policies take precedence when enabled.

Policy configuration (policy.json)
----------------------------------
- File: `policy.json` (placed in the project root by default)
- Environment controls:
  - `POLICY_FILE` - path to policy file (default: `policy.json`)
  - `POLICY_ENABLED` - set to `0` or `false` (case-insensitive) to disable policies and retain baseline behavior

Supported rule features (required by the assignment):
- Keyword-based rules (keyword lists, substring match)
- User-based rules (explicit `ids` and `prefixes`)
- Rule composition with `match` using `op`: `any` (OR) or `all` (AND)
- Risk levels: `LOW`, `MEDIUM`, `HIGH`.
  - LOW -> auto-APPROVE
  - MEDIUM -> PENDING_REVIEW (manual review)
  - HIGH -> REJECT or BLOCK (controlled by rule's `action`, default REJECT)

Example rule (see provided `policy.json`):
- `low_keywords_auto_approve` (LOW) — auto-approves content with words like `benign` or `announcement`.
- `medium_keyword_or_user` (MEDIUM) — composite OR rule: certain keywords OR users with specific prefixes go to manual review.
- `high_bad_actor` (HIGH, action=REJECT) — known bad user ids are auto-REJECTED.
- `high_blocked_words` (HIGH, action=BLOCK) — certain dangerous words are auto-BLOCKED.

Backward compatibility
----------------------
- If policies are disabled or the policy file is missing/invalid, the app behaves exactly like the original baseline (blacklist first behavior is preserved in that case).
- When both policies and blacklist exist, policy evaluation happens first (documented and tested).

Running the service
-------------------
Install dependencies (recommended inside a venv):

    python -m pip install -r requirements.txt

Run with uvicorn (example):

    uvicorn baseline_moderation_service:app --reload

API endpoints
-------------
- `GET /health` - health check
- `GET /blacklist` - list blacklist keywords
- `POST /blacklist?keyword=...` - add keyword
- `DELETE /blacklist?keyword=...` - remove keyword
- `POST /content/submit` - submit content (JSON: `{user_id, text}`)
- `GET /content/{content_id}` - get content item
- `GET /review/queue` - fetch pending review items
- `POST /review/{content_id}` - reviewer decision

Testing
-------
A test suite using pytest is included in `tests/` and covers:
- Baseline regression (policies disabled)
- Low-risk auto-approval
- Medium-risk routing to manual review
- High-risk reject and block behaviors
- Rule composition (OR) and user prefix matching
- Execution order between policy and blacklist (policy-first)

One-click test scripts:
- POSIX: `./run_tests` (make executable)
- Windows: `run_tests.bat`

Design notes
------------
- The policy engine is intentionally simple and extensible: adding a new condition type only requires writing a small matching helper and the rule evaluation will pick it up without rewiring the core flow.
- Reasons returned in `POST /content/submit` include the matched policy id and risk level (e.g. `policy:low_keywords_auto_approve (LOW) match=keyword:benign`) so decisions are traceable.

Files added/modified
--------------------
- `baseline_moderation_service.py` (modified, policy engine + policy-first behavior)
- `policy.json` (example policy configuration)
- `tests/test_moderation.py` (pytest suite)
- `requirements.txt`, `run_tests`, `run_tests.bat`, `README.md`

Contact
-------
This is an exercise submission. For questions about the design or behavior, inspect `policy.json` and `tests/test_moderation.py` which demonstrate usage patterns and expectations.
