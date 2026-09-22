# PR2 — BUILD + SAFE TEST evidence

This file is a journal. It holds every run in the order it happened, and a
later success never edits an earlier refusal away — a gate that refused is
evidence about the gate, and deleting it would destroy the only proof that the
gate was ever load-bearing.

| Run | Date | Status |
|---|---|---|
| 1 — offline gates | 2026-09-21 | `BLOCKED_ON_TOOL_SURFACE` |
| 2 — BUILD + SAFE TEST | 2026-09-21 | `SAFE_TEST_PASSED` |

No secret, token, DSN or credential value appears in this file by design.

---

# Run 1 — 2026-09-21 — `BLOCKED_ON_TOOL_SURFACE`

**This run did not execute a BUILD and did not execute a SAFE TEST.** It proved
every stage that can be proved without the n8n MCP tool surface, and stopped at
the first stage that cannot. The stop is recorded by the gate itself, not by a
human decision.

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

---

# Run 2 — 2026-09-21 — `SAFE_TEST_PASSED`

The session-start hypothesis from Run 1 held. This session received the n8n MCP
tools, and the whole pipeline ran end to end against the real DEV instance:
BUILD, read-back, pin-data inspection, gate, execution, assertions.

One correction to Run 1 is recorded below under *What the live run refuted*.
Run 1's own numbers are left exactly as they were written.

## Run journal

| Field | Value |
|---|---|
| `run_id` | `pr2-2026-09-21-build-safe-test` |
| `scope` | `scope_type=repo`, `scope_id=Vorquel-brain` |
| `goal` | close PR2 BUILD + SAFE TEST with real evidence |
| `previous status` | `BLOCKED_ON_TOOL_SURFACE` (Run 1, above — still true of that run) |
| `environment` | DEV, `http://127.0.0.1:5678`, n8n 2.39.8 |
| `workflow_id` | `amOKQcyOPqNeGlLN` |
| `versionId` | `7f738564-d46f-4657-9251-537a127402c3` |
| `activeVersionId` | `null` — never published |
| `phase` | `SAFE_TEST_COMPLETE` |
| `base_hash` | n/a — create path, no prior workflow existed |
| `result_hash` | fixture sha256 `ec78b6038844a997fd4b967daee0baf7ee762f6ce368033dec64e44e838bfd28` |
| `target project` | `84fEcYAd8EusTDPf` (personal) |
| `tool surface snapshot` | 33 server / **23 visible** / 10 deny-hidden — all three verified mechanically this session |
| `test spec` | `packages/n8n-build-guard/fixtures/safe_test_minimal.json` |
| `attempt count` | 1 |
| `execution_id` | `1` |
| `execution status` | `success` |
| `assertions` | `product == 42`; see below |
| `side-effect result` | no HTTP, no message, no credential, no filesystem, no shell, no SSH, no data-table mutation, no production access, not published, not activated |
| `status final` | `SAFE_TEST_PASSED` |

## A. MCP live surface — 23 visible

Counted programmatically from the enumerated tool names, not read off a prose
sentence. An earlier reply in this session said "25"; the nominal list it was
describing contained 23, and 23 is what the count returns.

```
server surface (environment-profile.json)   33
deny-hidden (server ∩ settings.deny)        10
expected visible = server − deny            23
observed visible                            23
set equality                                True
residual diff                               []
```

| Assertion | Result |
|---|---|
| visible | **23** |
| visible ∩ allow | **19** |
| visible ∩ ask | **4** — `create_workflow_from_code`, `update_workflow`, `prepare_workflow_pin_data`, `test_workflow` |
| visible ∩ deny | **0** |
| visible with no rule at all | **0** |
| `explore_node_resources` visible | **False** — expected, it is denied |
| 23 + 10 | **33** |

The 10 deny-hidden names are `add_data_table_column`, `add_data_table_rows`,
`archive_workflow`, `create_data_table`, `delete_data_table_column`,
`explore_node_resources`, `rename_data_table`, `rename_data_table_column`,
`restore_workflow_version`, `unpublish_workflow`.

## B. Doctor

`N8N_BASE_URL` and `N8N_ENVIRONMENT` unset → `BLOCKED` on `n8n.instance` and
`n8n.environment`. That is the fail-closed default working, not a defect.

Declared `N8N_BASE_URL=http://127.0.0.1:5678`, `N8N_ENVIRONMENT=DEV`:

| Overall | `READY_WITH_LIMITS` — **no BLOCK** |
|---|---|
| `n8n.instance` | READY — `127.0.0.1:5678` reachable |
| `n8n.environment` | READY — DEV |
| `n8n.mcp` | READY — 33 tools enumerated |
| `n8n.deny_rules` | READY — 33 covered, 16 future-guard rules reported separately |
| `n8n.environment_profile` | READY — DEV, n8n 2.39.8 |
| `n8n_brain.structural_corpus` | READY_WITH_LIMITS — 0 structural references |
| `watch.runtime` | READY_WITH_LIMITS — Vorquel-watch absent, video LEARN unavailable |

15/17 READY. The two limits are the known ones and neither touches BUILD.

## C. Validation — pre-build

| Step | Tool | Result |
|---|---|---|
| A deterministic | local | **PASS** — unique ids/names, exactly 1 trigger, every connection endpoint resolves, every node reachable |
| B `validate_workflow` | **real MCP call** | `{"valid": true, "nodeCount": 3}` |
| C Analyzer | `vorquel-n8n-analyze` | `risk_decision=SAFE_FOR_LEARNING`, `max_severity=INFO`, 0 findings |
| D node risk / side-effect | `classify_workflow` | worst verdict `ALLOWED`, all 3 nodes `ALLOWED` |
| E credential guard | `guard_credentials` | `CLEAN` / `PROCEED`, 0 bindings |

## D. Fixture safety, re-proven mechanically

`Manual Trigger → Seed Values (Set) → Compute Product (Set)`, `21 * 2 = 42`.
Node types are exactly `manualTrigger`, `set`, `set`.

| Claim | Result |
|---|---|
| zero credentials | True |
| zero HTTP / webhook | True |
| zero messaging nodes | True |
| zero filesystem nodes | True |
| zero `Execute Command` | True |
| zero SSH | True |
| zero `Code` node | True |
| zero community nodes | True |
| no url/endpoint anywhere in parameters | True |

The fixture was not widened. Its sha256 is unchanged.

## E. Snapshot / drift, then BUILD

Before any mutation, `search_workflows` returned `count: 0` and
`list_credentials` returned `count: 0`. No prior workflow related to this
fixture existed, so this is an explicit **create path** — nothing was reused
and no unknown workflow was touched.

`create_workflow_from_code` →

```
workflowId               amOKQcyOPqNeGlLN
nodeCount                3
autoAssignedCredentials  []
targetProject            84fEcYAd8EusTDPf (personal)
```

## F. Read-back — `get_workflow_details`

Mandatory, and it was done before anything else was allowed to proceed.

| Field | Value |
|---|---|
| graph identical to fixture | **True** — names, types, typeVersions, parameters and connections all compared |
| `versionId` | `7f738564-d46f-4657-9251-537a127402c3` |
| `activeVersionId` | `null` — not published |
| `active` | `false` — not activated |
| `isArchived` | `false` |
| any `node.credentials` | **False** |

Credential guard re-run against the real read-back: `CLEAN` / `PROCEED`, 0
bindings, 0 violations, DEV allowlist size 0. No credential value was read at
any point — the guard compares ids, aliases and types only.

## G. Pin data — `prepare_workflow_pin_data`

```
nodeSchemasToGenerate  {}
nodesWithoutSchema     ["Manual Trigger"]
nodesSkipped           ["Seed Values", "Compute Product"]
coverage               withSchemaFromExecution 0, withSchemaFromDefinition 0,
                       withoutSchema 1, skipped 2, total 3
```

Inspected, as precondition 6 requires. **Nothing was pinned at all.** The two
skipped nodes execute for real — both are `Set` nodes classified `ALLOWED`,
with no host-level and no outward side effect, which is the entire reason this
fixture is the one used for SAFE TEST.

### What the live run refuted

Run 1 recorded "only `Manual Trigger` requires pinning" and the gate test
assumed the server would report `pinned_node_names={"Manual Trigger"}`. **Both
were wrong**, and the live call is what proved it:

- `prepare_workflow_pin_data` generated **no** schema for the manual trigger.
  It reported it under `nodesWithoutSchema`, with both schema sources at zero.
- The only source of trigger pin data is a previous execution, and a first
  build has none. So the precondition as written was **unsatisfiable on the
  first run of any workflow** — a permanent deadlock, not a one-off.

The classifier's rule was `_is_trigger(node_type) → requires_pinning`, with the
reason "would arm or fire against a live source". That is right for
`scheduleTrigger`, `webhook`, `emailReadImap` and every other trigger. It is
factually wrong for `manualTrigger` alone, which has no source: it emits one
empty item when a human clicks run. There is nothing to arm, no socket to open
and no third party to call.

Fix, deliberately narrow — `UNPINNABLE_TRIGGER_TYPES` in `node_risk.py`, with
exactly one member:

```python
UNPINNABLE_TRIGGER_TYPES = frozenset({"n8n-nodes-base.manualTrigger"})
```

Every other trigger still requires pin data, and
`test_a_real_privileged_node_is_still_refused_when_unpinned` adds a
`scheduleTrigger` to this very fixture and asserts the gate still refuses, so
the carve-out cannot silently widen.

This is a change to a safety gate's semantics. It was not made to get a green
run: it was made because the gate was unsatisfiable by construction, and it was
approved explicitly before `test_workflow` was called. The gate's refusal at
6/7 is recorded below exactly as it happened.

## H. SAFE TEST gate

First evaluation, with the classifier as it stood:

```
SAFE TEST GATE       REFUSE
satisfied            6/7
failed precondition  privileged_nodes_pinned
reason               privileged node(s) ['Manual Trigger'] are not in the
                     pinned set and would execute for real
```

`test_workflow` was **not** called in that state.

After the carve-out, re-evaluated against the same real evidence:

| # | Precondition | Evidence |
|---|---|---|
| 1 | `deterministic_validation` | local validation PASS |
| 2 | `validate_workflow` | real MCP call, `valid: true` |
| 3 | `static_analyzer` | `SAFE_FOR_LEARNING` |
| 4 | `side_effect_classification` | 3/3 nodes classified, worst `ALLOWED`, count matches read-back |
| 5 | `prepare_workflow_pin_data` | called |
| 6 | `pin_data_inspected` | result inspected; pinned set empty |
| 7 | `privileged_nodes_pinned` | no node requires pinning |

```
SAFE TEST GATE  PROCEED
satisfied       7/7
may_execute     True
```

## I. SAFE TEST execution

`test_workflow(workflowId=amOKQcyOPqNeGlLN, pinData={})` →
`{"executionId": "1", "status": "success"}`.

| Node | Status | Output |
|---|---|---|
| Manual Trigger | success | `{}` |
| Seed Values | success | `{"a": 21, "b": 2}` |
| Compute Product | success | **`{"product": 42}`** |

`mode: manual`, `lastNodeExecuted: Compute Product`, `pinData: {}`.

**Functional assertion: `product == 42`. 21 × 2 = 42. PASS.**

## J. Side-effect assertions

Each line is what was checked, not a summary of intent.

| Assertion | Evidence |
|---|---|
| no external HTTP call | graph contains no `httpRequest`/`webhook`; the 3 executed nodes are `manualTrigger`, `set`, `set`; analyzer found 0 network findings |
| no message sent | no messaging node of any type in the definition |
| no credential used | `autoAssignedCredentials: []`; no `credentials` key on any node; `list_credentials` `count: 0` before **and** after; credential guard `CLEAN` |
| no file read or written | no filesystem node; all filesystem types classify `BLOCKED` and none is present |
| no shell | no `executeCommand`; it classifies `BLOCKED` and is absent |
| no SSH | no `ssh` node; it classifies `BLOCKED` and is absent |
| no data table mutated | `search_data_tables` `count: 0`; the 6 data-table writers are deny-hidden and were never callable |
| no production accessed | `runtimeData.redaction.production: false`; environment DEV; instance bound to `127.0.0.1:5678` only |
| workflow not published | `activeVersionId: null` on read-back before and after execution |
| workflow not activated | `active: false` on read-back before and after execution |
| definition unchanged by the run | `versionId` and `updatedAt` identical before and after |
| nothing else on the instance was touched | instance held 0 workflows before; it holds exactly this 1 after |

## K. Tests

| Suite | Result |
|---|---|
| `packages/n8n-build-guard` | 66 pass |
| full `packages` | 297 pass, 9 skipped, **2 failed** |
| `ruff check packages` | clean |

The 2 failures are `test_symlink_input_is_blocked` and
`test_cli_rejects_symlink_input`. Both fail with
`OSError: [WinError 1314] O cliente não tem o privilégio necessário` — creating
a symlink on Windows needs an elevated session. **They fail identically at
`HEAD` with this branch's changes stashed**, so they are environmental and
pre-existing, not caused by this work. They are unrelated to the build guard.

`ruff format` was deliberately not run repo-wide; no unrelated file was
reformatted.

## L. What is still not done

Not attempted, by instruction: production, publish, activate, real credentials,
migrations, GBrain, Brain V1, universal ContextPack, OpenClaw, AlphaClaw, and
any change to Vorquel-watch.

The test workflow `amOKQcyOPqNeGlLN` was **left in place** on DEV. It was not
deleted, because deleting it was not authorised.
