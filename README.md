# Baseline Content Moderation Service (with Policy-driven Multi-stage Moderation)

Overview
--------
This repository contains a simple baseline content moderation service implemented with FastAPI. It supports a keyword blacklist and a manual review queue.

New Feature: Policy-driven Multi-stage Moderation
------------------------------------------------
Policies provide configurable automated decisions before manual review. Policies are read from an external `policy.json` (or path defined by the `POLICY_FILE` env var). Policies are configuration-driven (not hard-coded) and support:

- Keyword-based rules
- User-based rules (exact user IDs and user ID prefixes)
- Rule composition using `AND` / `OR` (composite rules)

Decision mapping
----------------
Policy outcomes map to final statuses:
- `APPROVE` => `APPROVED`
- `PENDING_REVIEW` => `PENDING_REVIEW`
- `REJECT` => `REJECTED`
- `BLOCK` => `BLOCKED`

Execution order and backward compatibility
-----------------------------------------
- If no policy file is present or policies are disabled, the service behaves exactly like the baseline (blacklist + manual review).
- If policies are present, the service evaluates policies first; if a policy matches it decides the final state. If no policy matches, the service falls back to the original blacklist behavior.

This design ensures policies can override blacklist behavior when explicitly configured.

Files
-----
- `baseline_moderation_service.py` - main FastAPI service (modified to integrate policy engine)
- `policy/engine.py` - policy engine implementation (loading, rule types, evaluation)
- `policy.json` - example policy configuration
- `tests/` - pytest test suite validating baseline and policy-driven behavior
- `requirements.txt` - dependencies
- `run_tests` / `run_tests.sh` - convenience scripts to run tests

Policy file format (example)
----------------------------
policy.json is a JSON array of rule objects. Example rule:

{
  "id": "rule_approve_safe_keyword",
  "priority": 10,
  "type": "keyword",
  "keywords": ["safe"],
  "outcome": "APPROVE",
  "description": "Auto-approve safe content"
}

Composite rule example (AND):

{
  "id": "p_and",
  "type": "composite",
  "operator": "AND",
  "rules": [
    {"type": "keyword", "keywords": ["secret"]},
    {"type": "user", "user_prefixes": ["vip-"]}
  ],
  "outcome": "REJECT",
  "description": "reject secret from vip users"
}

Running the service
-------------------
Install dependencies:

    python -m pip install -r requirements.txt

Run the FastAPI app:

    uvicorn baseline_moderation_service:app --reload

Running tests
-------------
Run the tests with the provided helper:

    ./run_tests

or

    ./run_tests.sh

Design decisions
----------------
- Policies are configuration-driven and loaded at startup. The engine sorts rules by `priority` and picks the first matching rule.
- Execution order is: policies first, blacklist second (fallback). This lets administrators explicitly craft exceptions via policy files.
- The policy engine is extensible: adding a new rule type requires implementing a Rule subclass and adding it to the instantiation logic in `policy/engine.py`.

