# Baseline Content Moderation Service (with Policy-driven Engine)

✅ **Overview**

This project provides a baseline content moderation service implemented with FastAPI and a policy-driven decision engine that can automatically approve, route to review, reject, or block submitted content according to external policy configuration.

---

## Features

- Baseline functionality:
  - Keyword blacklist blocking
  - Manual review queue
  - Human reviewer decisions

- New: Policy-driven multi-stage moderation (configurable)
  - Policies are loaded from `policy.json` by default
  - Supports keyword-based and user-based rules
  - Supports simple composition using `AND` / `OR`
  - Policies are evaluated in order; the first matching policy is applied
  - Policy `action` or `risk` determines final decision

---

## Design decision (Policy vs Blacklist execution order) ⚖️

- **Policies are evaluated first.** If a policy matches, its `action` is applied (APPROVE / REVIEW / REJECT / BLOCK) and the blacklist is not consulted for that submission.
- If no policy applies (or policies are disabled), the **legacy blacklist** behavior is used (substring match → `BLOCKED`; otherwise `PENDING_REVIEW`).

This choice aligns with the roadmap to reduce manual effort by allowing explicit automation via policy configuration.

---

## Configuration: `policy.json` 💡

Example `policy.json` (already included):

```
{
  "policies": [
    {
      "id": "auto_approve_trusted",
      "description": "Auto-approve trusted users",
      "operator": "OR",
      "rules": [
        { "type": "user", "user_prefixes": ["trusted_"] }
      ],
      "risk": "LOW",
      "action": "APPROVE"
    }
  ]
}
```

- Rule types supported:
  - `keyword` — match text substrings (case-insensitive)
  - `user` — match exact `user_ids` or `user_prefixes`
- `operator` controls composition (`AND` / `OR`, default `OR`)
- `action` may be `APPROVE`, `REVIEW`, `REJECT`, or `BLOCK`. If omitted, `risk` (`LOW`/`MEDIUM`/`HIGH`) is used to determine action.

To change the path of the policy config, set the environment variable `POLICY_CONFIG_PATH` or call `load_policies(path)` from the service.

---

## How to run the service

1. Install requirements / create venv:

    - Linux/macOS:
      - ./run_tests.sh will create a venv and run the tests
    - Windows:
      - run `run_tests.bat` (uses the same venv approach)

2. Run the app locally (for manual testing):

```
uvicorn baseline_moderation_service:app --reload
```

---

## Tests

- Tests are implemented using `pytest` in the `tests/` directory.
- One-click: run `./run_tests.sh` (or `run_tests.bat` on Windows). The script sets up a virtualenv, installs dependencies, and runs tests.

---

## Files changed / added

- `baseline_moderation_service.py` — integrated with policy engine
- `policy/policy_engine.py` — simple, extensible policy engine
- `policy.json` — sample policy configuration
- `tests/test_policy_moderation.py` — pytest test suite
- `requirements.txt`, `run_tests.sh`, `run_tests.bat`, `README.md`

---

## Notes

- The design is intentionally simple and easily extensible: adding a new rule type only requires implementing the matching logic in `policy_engine.py`.
- The reason field in responses includes the matching `policy:id` and matched details for traceability.

---

If you want, I can help extend policies (e.g., add regex support, model-based risk scoring, or a management endpoint).