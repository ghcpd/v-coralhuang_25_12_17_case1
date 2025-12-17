# Content Moderation Service - Policy-Driven Architecture

## Overview

This is an extended version of the baseline content moderation service that adds **policy-driven automated decision-making** while maintaining full backward compatibility.

### What It Does

The service moderates user-submitted content through three stages:

1. **Policy Evaluation** (if enabled): External configuration-driven rules determine if content should be automatically approved, rejected, blocked, or sent to manual review
2. **Blacklist Matching** (fallback): If no policy matches, legacy keyword blacklist is checked
3. **Manual Review** (default): Content that doesn't trigger policies or blacklist goes to a human review queue

## Architecture

### Directory Structure

```
.
├── baseline_moderation_service.py    # Original baseline implementation (reference)
├── moderation_service.py             # Extended service with policy engine
├── policy.json                       # Configuration file for policies
├── requirements.txt                  # Python dependencies
├── Dockerfile                        # Container image definition
├── docker-compose.yml                # Multi-container orchestration
├── run_tests                         # Linux/Mac test runner script
├── run_tests.bat                     # Windows test runner script
├── README.md                         # This file
├── src/
│   ├── __init__.py
│   └── policy_engine.py              # Policy evaluation engine
└── tests/
    ├── __init__.py
    ├── test_policy_engine.py         # Unit tests for engine
    └── test_moderation_service.py    # Integration tests
```

## Baseline Functionality (Unchanged)

The original service is fully preserved:

- **Keyword Blacklist**: `/blacklist` endpoints manage the keyword blacklist
- **Content Submission**: `POST /content/submit` accepts user content
- **Blocking**: Content matching blacklist keywords is immediately blocked
- **Manual Review Queue**: Non-blocked content enters `PENDING_REVIEW` queue
- **Human Review**: `/review/{content_id}` endpoints handle approvals/rejections

**To use only baseline behavior**: Set `ENABLE_POLICY_ENGINE=false` environment variable.

## New Policy-Driven Feature

### What Are Policies?

Policies are **external configuration rules** that automatically decide content moderation actions. They replace the "blacklist or manual review only" flow with intelligent automation.

### Rule Types

#### 1. Keyword Rules
Match against the content text:
- **substring** (default): Match if keyword appears anywhere (case-insensitive)
- **explicit**: Match only if text is exactly the keyword

Example:
```json
{
  "type": "keyword",
  "match_type": "substring",
  "values": ["bomb", "exploit", "crack"]
}
```

#### 2. User ID Rules
Match against the submitting user's ID:
- **explicit**: Match if user ID is in the list
- **prefix**: Match if user ID starts with any prefix

Example:
```json
{
  "type": "user_id",
  "match_type": "prefix",
  "values": ["admin_", "trusted_", "verified_"]
}
```

### Rule Composition

Policies can combine multiple rules with logic operators:

- **OR**: At least one rule must match (used for broad filtering)
- **AND**: All rules must match (used for specific combinations)

Example AND policy:
```json
{
  "id": "combined_spam",
  "name": "Spam from new users",
  "rules": [
    {
      "type": "keyword",
      "match_type": "substring",
      "values": ["discount", "offer", "buy now"]
    },
    {
      "type": "user_id",
      "match_type": "prefix",
      "values": ["guest_"]
    }
  ],
  "composition": "AND"
}
```

This policy matches only if BOTH:
- Content contains spam keywords (discount/offer/buy now)
- AND user ID starts with "guest_"

### Risk Levels and Actions

Each policy specifies a risk level and corresponding action:

| Risk Level | Action | Behavior |
|-----------|--------|----------|
| LOW | APPROVED | Content auto-approved |
| MEDIUM | PENDING_REVIEW | Sent to manual review queue |
| HIGH | REJECTED | Content auto-rejected |
| HIGH | BLOCKED | Content auto-blocked |

## Configuration

### Policy Configuration File

Policies are defined in `policy.json`. The file structure:

```json
{
  "enabled": true,
  "policies": [
    {
      "id": "unique_policy_id",
      "name": "Human-readable policy name",
      "description": "What this policy does",
      "risk_level": "LOW|MEDIUM|HIGH",
      "action": "APPROVED|REJECTED|BLOCKED|PENDING_REVIEW",
      "rules": [
        {
          "type": "keyword|user_id",
          "match_type": "substring|explicit|prefix",
          "values": ["list", "of", "matching", "values"]
        }
      ],
      "composition": "AND|OR"
    }
  ]
}
```

### Environment Variables

```bash
# Enable/disable the policy engine
ENABLE_POLICY_ENGINE=true|false  # default: true

# Path to policy configuration file
POLICY_FILE=policy.json  # default: policy.json
```

### Example Policies

See included `policy.json` for complete examples:

1. **Auto-approve verified users**: Whitelist of trusted user IDs
2. **Auto-reject banned users**: Blacklist of prohibited user IDs
3. **Block dangerous content**: High-risk keywords (bomb, exploit, etc.)
4. **Route suspicious content**: Medium-risk content for review
5. **Trusted domain auto-approval**: Prefix-based user filtering
6. **Combined spam detection**: AND logic for specific user + keyword combinations

## Decision Flow (Execution Order)

When content is submitted, the system makes a decision in this order:

```
1. Is policy engine enabled?
   → YES: Evaluate all policies in order
      - First matching policy determines action
      - Return (action, reason with policy details)
   → NO: Continue to step 2

2. Does content hit blacklist?
   → YES: Return (BLOCKED, keyword details)
   → NO: Continue to step 3

3. Default: Route to manual review
   → Return (PENDING_REVIEW, "Requires manual review")
```

### Why This Order?

- **Policies first**: Highly tuned automated decisions take priority
- **Blacklist second**: Legacy safety mechanism remains active
- **Manual review default**: Anything ambiguous gets human attention

### Key Design Decision

**Policies override blacklist**: If a policy matches before checking the blacklist, the policy action is used. This allows policies like "auto-approve verified users" to override generic blacklist rules.

Example:
- Policy: "Auto-approve user_verified_1"
- Blacklist: Contains "spam"
- Content: "user_verified_1" submits "spam"
- Result: **APPROVED** (policy wins)

This ensures policies can implement nuanced business rules (e.g., verified users can post anything).

## Running the Service

### Option 1: Local Python (Recommended for Development)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate          # Linux/Mac
# or
venv\Scripts\activate.bat          # Windows

# Install dependencies
pip install -r requirements.txt

# Run service
python -m uvicorn moderation_service:app --reload --host 0.0.0.0 --port 8000

# Service will be at http://localhost:8000
```

### Option 2: Docker (Recommended for Production)

```bash
# Build and run
docker-compose up --build

# Service will be at http://localhost:8000

# Run tests in container
docker-compose run moderation-service python -m pytest tests/ -v
```

### Option 3: Docker Standalone

```bash
docker build -t moderation-service .
docker run -p 8000:8000 \
  -e ENABLE_POLICY_ENGINE=true \
  -e POLICY_FILE=policy.json \
  -v $(pwd)/policy.json:/app/policy.json \
  moderation-service
```

## Running Tests

### One-Click Test Execution

**Windows:**
```cmd
run_tests.bat
```

**Linux/Mac:**
```bash
chmod +x run_tests
./run_tests
```

Both scripts:
1. Create a Python virtual environment (if needed)
2. Install dependencies from `requirements.txt`
3. Run full test suite with pytest
4. Show summary of results

### Manual Test Execution

```bash
# Activate virtual environment first
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_policy_engine.py -v

# Run specific test
python -m pytest tests/test_moderation_service.py::TestLowRiskPolicy::test_verified_user_auto_approval -v
```

## Test Coverage

The test suite covers:

### Unit Tests (`test_policy_engine.py`)
- ✅ Keyword rule matching (substring, explicit)
- ✅ User ID rule matching (explicit, prefix)
- ✅ Policy evaluation with OR composition
- ✅ Policy evaluation with AND composition
- ✅ Policy engine decision flow
- ✅ Loading policies from file

### Integration Tests (`test_moderation_service.py`)
- ✅ **Baseline behavior regression**
  - Blacklist blocking still works
  - Non-blacklisted content goes to manual review
  - Blacklist management endpoints work

- ✅ **Low-risk policy (auto-approval)**
  - Verified users auto-approved
  - Trusted prefixes auto-approved

- ✅ **Medium-risk policy (manual review)**
  - Suspicious keywords route to review
  - AND logic correctly combines rules

- ✅ **High-risk policy (rejection/blocking)**
  - Dangerous keywords blocked
  - Banned users rejected

- ✅ **Policy execution order**
  - Policies checked before blacklist
  - Fallback to blacklist when no policy matches
  - Manual review as default

- ✅ **Manual review operations**
  - Pending items in queue
  - Review decisions update status
  - Reviewed items removed from queue

- ✅ **Reason field correctness**
  - Traceable explanations for all decisions
  - Identifies which policy or rule matched

- ✅ **Error handling**
  - 404 for non-existent content
  - 409 when trying to review already decided content
  - 422 for invalid decisions

## API Endpoints

### Content Submission

```
POST /content/submit
{
  "user_id": "string",
  "text": "string"
}

Response:
{
  "content_id": "uuid",
  "status": "APPROVED|REJECTED|BLOCKED|PENDING_REVIEW",
  "reason": "string (explanation of decision)"
}
```

### Get Content

```
GET /content/{content_id}

Response:
{
  "content_id": "uuid",
  "user_id": "string",
  "text": "string",
  "status": "status",
  "created_at": "timestamp",
  "updated_at": "timestamp",
  "reason": "string",
  "reviewer_id": "string|null",
  "review_note": "string|null"
}
```

### Review Queue

```
GET /review/queue?limit=20

Response:
{
  "count": "int",
  "items": [ContentItem...]
}
```

### Make Review Decision

```
POST /review/{content_id}
{
  "reviewer_id": "string",
  "decision": "APPROVED|REJECTED",
  "note": "string (optional)"
}
```

### Blacklist Management

```
GET /blacklist
POST /blacklist?keyword=string
DELETE /blacklist?keyword=string
```

### Policy Status

```
GET /policy/status

Response:
{
  "enabled": bool,
  "policy_file": "string|null"
}
```

### Health Check

```
GET /health

Response:
{
  "ok": true,
  "policies_enabled": bool
}
```

## Design Decisions

### 1. Configuration Format: JSON vs JSONL

**Decision: JSON** (single file object with array)

**Rationale:**
- Simpler to understand and maintain
- Better IDE support and validation
- Easier to reason about policy order (array order is preserved)
- Works well for typical policy sets (100-1000 policies)

For even larger deployments, could extend to support JSONL (one policy per line) for streaming.

### 2. Rule Matching Strategy

**Decision: Case-insensitive substring matching for keywords**

**Rationale:**
- Matches user expectation (people don't think about case when flagging spam)
- Reduces false negatives ("SPAM", "spam", "Spam" all caught)
- Case sensitivity available via "explicit" match type if needed

### 3. Policies Execute Before Blacklist

**Decision: Policy evaluation happens first**

**Rationale:**
- Policies represent business rules and should take priority
- Allows nuanced decisions (e.g., verified users bypass keyword checks)
- Blacklist acts as safety net for uncovered cases
- Faster execution: policies can short-circuit without checking blacklist

### 4. First Matching Policy Wins

**Decision: Return first matching policy action, don't combine**

**Rationale:**
- Simpler logic and easier to reason about
- Policy order in config file determines priority
- Prevents conflicting actions (what if two policies match?)
- Can group related policies together

### 5. AND/OR at Policy Level, Not Cross-Policy

**Decision: Composition operator applies within single policy only**

**Rationale:**
- Clear, scoped logic
- Easier to test and debug
- Can order policies to implement cross-policy logic if needed
- Prevents exponential complexity

### 6. In-Memory Storage for Baseline

**Decision: Keep in-memory dict storage as in baseline**

**Rationale:**
- Maintains full backward compatibility
- Acceptable for demo/testing (as in baseline)
- Easy to replace with DB without changing API
- Focus on policy engine, not persistence

For production, would replace with database (PostgreSQL, MongoDB, etc.).

## Extensibility

The design is extensible in several ways:

### Add New Rule Type

1. Add new enum value to `RuleType` in `src/policy_engine.py`
2. Add matching logic in `Rule._match_*` method
3. Update `Rule.matches()` to handle new type
4. Add tests in `tests/test_policy_engine.py`

Example: Add "email_domain" rule type:
```python
class RuleType(str, Enum):
    KEYWORD = "keyword"
    USER_ID = "user_id"
    EMAIL_DOMAIN = "email_domain"  # NEW

def _match_email_domain(self, email: str) -> bool:
    domain = email.split("@")[1] if "@" in email else ""
    return domain in self.values
```

### Add New Match Type

1. Add to `MatchType` enum
2. Implement logic in rule matching methods
3. Add tests

### Change Decision Logic

Core decision logic is in `moderation_service._make_moderation_decision()`:
- Modify to change policy/blacklist execution order
- Add new decision stages
- Implement different composition logic

## Backward Compatibility Testing

To verify baseline behavior is unchanged:

```bash
# Run with policy engine disabled
ENABLE_POLICY_ENGINE=false python -m pytest tests/test_moderation_service.py::TestBaselineBehavior -v
```

All baseline tests should pass regardless of policy engine state.

## Troubleshooting

### Service won't start

```bash
# Check Python version
python --version  # Should be 3.8+

# Check dependencies installed
pip list | grep fastapi

# Verify policy file exists
ls -la policy.json
```

### Tests fail

```bash
# Run with full output
python -m pytest tests/ -v -s

# Check imports
python -c "from moderation_service import app"

# Validate policy.json format
python -c "import json; json.load(open('policy.json'))"
```

### Policy not matching

1. Check policy is enabled: `GET /policy/status`
2. Verify policy.json syntax is valid JSON
3. Check policy "enabled" field is true
4. Review rule matching logic in test cases
5. Add print statements to debug (or use pytest -s)

## Future Enhancements

1. **Persistent Storage**: Replace in-memory with database
2. **Async Policy Loading**: Load policies in background without restart
3. **Policy Analytics**: Track which policies match most often
4. **Machine Learning**: Add ML-based rule suggestions
5. **Audit Trail**: Log all moderation decisions with policy info
6. **Dynamic Reloading**: Update policies without restarting service
7. **Policy Versioning**: Multiple versions of policies, gradual rollout
8. **A/B Testing**: Compare policy effectiveness

## License

Part of Bug Bash evaluation - December 2025

## Support

For issues, questions, or feedback:
1. Check this README first
2. Review test cases for usage examples
3. Check policy.json for configuration examples
4. Enable verbose logging for debugging
