# Policy-driven Multi-stage Moderation Service

This repository contains a small **content moderation service** implemented with **FastAPI**.  The baseline service implements a blacklist + manual-review queue.  The new feature adds a **configurable, policy-driven decision engine** that can automatically approve, send to review, or reject/block content before the manual review step.

---

## ✅ Baseline behavior (unchanged)
- **Keyword blacklist** (configured in memory in the app) immediately blocks content and returns `BLOCKED`.
- If not blocked, content is placed in a **manual review queue** and returned as `PENDING_REVIEW`.
- Reviewers can `APPROVE` or `REJECT` items in the queue.

## 🔧 Policy-driven multi-stage moderation
- A policy file (**`policy.json`** by default) can be loaded via the environment variable `MODERATION_POLICY_FILE`.
- When enabled, **policy evaluation happens before the blacklist** so policies can override the blacklist if matched (this is documented and covered by tests).
- Policies are **configuration driven** (no hard coded rules) and are extensible via rule types.
- Policy rules support:
  - **Keyword rules**: `{"type": "keyword", "value": "spam"}`
  - **User rules**: `{"type": "user", "value": "user1"}` or `{"type": "user", "prefix": "prefix_"}`
  - **Composition**: `any` (OR) or `all` (AND) of conditions
- **Risk levels** determine the automated action:
  - **low** → `APPROVED`
  - **medium** → `PENDING_REVIEW` (manual)
  - **high** → `REJECTED` by default or `BLOCKED` if `action: "block"` is supplied on the rule

## 📁 Project structure
```
.
├── baseline_moderation_service.py   # FastAPI app + baseline endpoints
├── policy_engine.py                  # Policy engine (configuration-driven)
├── policy.json                       # Example policy config
├── requirements.txt                  # runtime + test deps
├── run_tests                         # Bash one-click runner
├── run_tests.bat                     # Windows one-click runner
├── tests/
│   └── test_moderation.py           # pytest coverage
└── README.md                         # this file
```

## ⚙️ How to run the service
```bash
# Install dependencies (or use the provided run_tests scripts)
python -m pip install -r requirements.txt

# Start the API (Uvicorn)
uvicorn baseline_moderation_service:app --reload
```

If you want the policy engine to take effect, set `MODERATION_POLICY_FILE` to the path of your policy JSON **before starting the service**:
```bash
export MODERATION_POLICY_FILE=/path/to/policy.json  # linux/mac
set MODERATION_POLICY_FILE=C:\path\to\policy.json  # windows cmd / PowerShell
uvicorn baseline_moderation_service:app --reload
```

## ✅ Running tests (one-click)
- On Linux/macOS: `./run_tests` (bash)
- On Windows (cmd/PowerShell): `run_tests.bat`

Both scripts will install the `requirements.txt` and run the full pytest suite.

## 📌 Key design decisions
- **Policy-first**: when policies are enabled, we evaluate them before the blacklist so policy-driven actions can override the default blacklist behavior (documented and tested).
- **External config**: policy file is external and not hard-coded; adding new rule types can be done by extending `_match_condition` in `policy_engine.py`.
- **Backward compatibility**: if `MODERATION_POLICY_FILE` is not set or the file cannot be loaded, we fall back to the exact baseline behavior (blacklist + manual review).

---

If you want to add new rule types, modify `policy_engine._match_condition` to add handlers and add appropriate rule schema. The engine and `baseline_moderation_service.py` do not require changes to add new rules.
