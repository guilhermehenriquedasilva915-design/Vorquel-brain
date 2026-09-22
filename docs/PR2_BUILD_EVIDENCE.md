# PR2 — BUILD + SAFE TEST evidence

Run recorded 2026-09-21. **This run did not execute a BUILD and did not execute
a SAFE TEST.** It proved every stage that can be proved without the n8n MCP
tool surface, and stopped at the first stage that cannot. The stop is recorded
by the gate itself, not by a human decision.

No secret, token, DSN or credential value appears in this file by design.

## Run journal

| Field | Value |
|---|---|
| `run_id` | `pr2-2026-09-21-offline-gates` |
| `scope` | `scope_type=repo`, `scope_id=Vorquel-brain` |
| `goal` | close PR2 BUILD + SAFE TEST with real evidence |
| `workflow_id` | **none — no workflow was created on DEV** |
| `phase` | `PRE_BUILD_GATES` |
| `base_hash` | n/a — nothing was mutated |
| `result_hash` | n/a — nothing was mutated |
| `tool surface snapshot` | 33 observed / 23 visible-by-policy / 10 deny-hidden; **0 actually visible in this session** |
| `test spec` | `packages/n8n-build-guard/fixtures/safe_test_minimal.json` |
| `attempt count` | 1 |
| `execution id` | **none — `test_workflow` was never called** |
| `assertions` | offline guard assertions only; see below |
| `side-effect result` | **no side effect of any kind**: no create, no update, no publish, no activate, no execution, no credential use, no file written outside the repo, no production access |
| `status final` | `BLOCKED_ON_TOOL_SURFACE` |

## What was proven

| Stage | Result |
|---|---|
| Repo state | branch `feat/n8n-brain-build-safe-test`, tree clean, remote `bae5a59` |
| n8n DEV health | `vorquel-n8n-dev` Up, `n8nio/n8n:2.39.8`, listening on `127.0.0.1:5678` only |
| Tool surface reconciliation | 12/12 programmatic checks pass (see `N8N_MCP_TOOL_MATRIX.md`) |
| Doctor, environment undeclared | `BLOCKED` — fail-closed, correct |
| Doctor, environment declared DEV | `READY_WITH_LIMITS`, **no BLOCK** |
| Fixture classification | worst verdict `ALLOWED`; only `Manual Trigger` requires pinning |
| Credential guard | `CLEAN` / `PROCEED` — fixture binds nothing, DEV allowlist empty |
| SAFE TEST gate, today's evidence | **`REFUSE` at precondition 2, `validate_workflow`** |
| SAFE TEST gate, with server evidence | `PROCEED`, 7/7 — the fixture is eligible once the server can speak |
| Tests | 147 pass, 0 skip |
| `ruff check` | clean |

The gate refusing at precondition 2 is the central piece of evidence here. The
first precondition requiring the server is exactly where the run stops, which
is what the design intends: absence of evidence is failure, not success.

## The fixture, and why it is SAFE_TEST eligible

`Manual Trigger → Seed Values (Set) → Compute Product (Set)`, `21 * 2 = 42`.

| Requirement | How the fixture satisfies it |
|---|---|
| deterministic | two `Set` nodes and one arithmetic expression; no clock, no randomness, no input |
| no credentials | no `credentials` key on any node; credential guard returns `CLEAN` |
| no external HTTP | no `httpRequest`, no `webhook` |
| no email / WhatsApp / Slack | no messaging node of any kind |
| no filesystem | no read/write node |
| no `Execute Command` / SSH | absent — either would classify `BLOCKED` |
| no arbitrary `Code` node | absent — would classify `REVIEW_REQUIRED` |
| no community nodes | only `n8n-nodes-base.*` first-party types |
| no publish / activate | not part of the plan, and both are deny-listed |

`test_safe_test_fixture.py` pins every one of these claims, so an edit that
makes the fixture interesting fails CI rather than silently widening what SAFE
TEST proves.

## Why BUILD and SAFE TEST did not run

The session has **zero** `mcp__n8n__*` tools. Without them there is no
`validate_workflow`, no `create_workflow_from_code`, no
`prepare_workflow_pin_data` and no `test_workflow`, so preconditions 2, 5, 6
and 7 cannot be satisfied by evidence and the gate refuses.

### The previous diagnosis is now refuted

`N8N_MCP_TOOL_MATRIX.md` recorded the leading explanation as "an untrusted
workspace skips loading the project-local MCP registration". That is no longer
consistent with what is observed:

| Fact | Value today |
|---|---|
| `hasTrustDialogAccepted` for `C:/VORQUEL/VORQUEL N8N/Vorquel-brain` | **`true`** |
| `projects[...].mcpServers` | `['n8n']` — registered |
| Duplicate drive-letter project key | none — only one key matches |
| DEV instance | up, healthy, correct port binding |
| `mcp__n8n__*` tools in session | **0** |

Trust is accepted, the registration is present and the server is up, and the
tools are still absent. The remaining explanation consistent with all of it is
that **MCP servers are resolved when a session starts**, and this session was
started before trust was accepted. That predicts a *newly started* session will
have the tools — which is the next thing to test, and it is cheap.

The absence is also total, not selective. If deny-hiding were the only effect
in play the session would still see the 23 allow+ask tools; it sees none. So
the 10 missing deny-hidden tools are expected and are **not** evidence of a
problem, exactly as the policy says — but 0 of 23 visible is.

## Next session, in order

1. Start a **fresh** session in this workspace (trust is already accepted).
2. `ToolSearch select:mcp__n8n__search_workflows,mcp__n8n__validate_workflow`.
   If still empty, the session-start hypothesis is refuted too and the next
   suspect is the client's MCP resolution for project-local HTTP servers.
3. Confirm 23 visible tools; the 10 denied must be absent.
4. Declare `N8N_BASE_URL=http://127.0.0.1:5678` and `N8N_ENVIRONMENT=DEV`, then
   run the doctor and require `READY`/`READY_WITH_LIMITS` with no `BLOCK`.
5. Run the pipeline over the fixture and record the real `workflow_id`,
   `base_hash`, `result_hash`, `execution id` and assertions in this file.

Do not mark PR #24 ready for review before step 5 produces those values.
