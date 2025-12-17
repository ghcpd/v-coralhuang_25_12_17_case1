# Content Moderation Service

This is an extended content moderation service built on FastAPI, featuring policy-driven multi-stage moderation.

## Baseline Functionality

The baseline system supports:

- **Keyword Blacklist Blocking**: Content containing blacklisted keywords is immediately blocked.
- **Manual Review Queue**: Non-blocked content is queued for human review.
- **Human Review Decisions**: Reviewers can approve or reject queued content.

## New Feature: Policy-Driven Moderation

The service now includes a configurable, policy-driven moderation engine that automates decision-making before manual review.

### Policy Configuration

Policies are loaded from `policy.json` (JSON array of policy objects).

Each policy has:
- `name`: Policy identifier
- `action`: Decision (`APPROVED`, `PENDING_REVIEW`, `REJECTED`, `BLOCKED`)
- `rules`: Rule definition (keyword, user, or composite with AND/OR)

#### Rule Types

- **Keyword Rule**: Matches text content
  ```json
  {
    "type": "keyword",
    "keywords": ["bad", "spam"],
    "match": "any"  // or "all"
  }
  ```

- **User Rule**: Matches user ID
  ```json
  {
    "type": "user",
    "users": ["bad_user"]
  }
  ```

- **Composite Rules**: AND/OR combinations
  ```json
  {
    "and": [
      {"type": "keyword", "keywords": ["bad"]},
      {"type": "user", "users": ["user1"]}
    ]
  }
  ```

### Decision Flow

1. If policies are enabled and loaded, evaluate policies in order.
2. First matching policy determines the status and reason.
3. If no policy matches, fall back to baseline behavior (blacklist check then manual review).
4. If policies disabled, use baseline only.

### Configuration

Set `ENABLE_POLICIES` environment variable to `true` to enable policies (default: true).

## Running the Service

1. Install dependencies: `pip install -r requirements.txt`
2. Run: `uvicorn baseline_moderation_service:app --reload`

## Running Tests

Execute `./run_tests.sh` to install dependencies and run the full test suite.

Tests cover:
- Baseline behavior regression
- Policy-driven approvals, rejections, blocks
- Rule composition
- Reason field accuracy

## Key Design Decisions

- **Execution Order**: Policies are evaluated first; if no match, baseline logic applies. This ensures backward compatibility while allowing automation.
- **Extensibility**: New rule types can be added by extending the `Rule` class and updating `_build_rule`.
- **Configuration**: Policies loaded from external JSON file, not hard-coded.
- **Fallback**: When policies enabled but no match, uses baseline to maintain functionality.