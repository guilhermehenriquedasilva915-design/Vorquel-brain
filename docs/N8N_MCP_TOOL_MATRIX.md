# N8N MCP — real tool surface and policy

Observed on the Vorquel DEV instance, n8n **2.39.8**, instance-level MCP over
`/mcp-server/http`. Every name below was enumerated at runtime from the
connected client. Nothing here is inferred from documentation.

The previous policy in `.claude/settings.json` denied eleven `mcp__n8n__*`
names. **None of them exists on this server.** The tools that can actually
change production state, destroy a workflow or call a third party had no rule
at all. That is the gap this document closes.

## Why the names matter more than the categories

Claude Code matches permissions by exact tool name. A denylist entry that names
a tool the server does not expose blocks nothing. It is still worth keeping a
small set of forward-looking guards, but they must never be counted as
protection that is currently doing something — `vorquel-brain-doctor` reports
them separately as *guarda futura*.

## Matrix

`SIDE EFFECT` is the worst thing a call can do, not the typical case.

| Tool (`mcp__n8n__…`) | Capability | R/W/X | Side effect | DEV safe | Policy |
|---|---|---|---|---|---|
| `search_workflows` | list workflows | R | none | yes | **allow** |
| `get_workflow_details` | workflow definition | R | none | yes | **allow** |
| `get_workflow_history` | version list | R | none | yes | **allow** |
| `get_workflow_version` | one version's content | R | none | yes | **allow** |
| `get_workflow_versions_diff` | version delta | R | none | yes | **allow** |
| `get_workflow_sdk_reference` | SDK docs | R | none | yes | **allow** |
| `get_workflow_best_practices` | planning docs | R | none | yes | **allow** |
| `search_nodes` | node catalog | R | none | yes | **allow** |
| `get_node_types` | node type defs | R | none | yes | **allow** |
| `validate_workflow` | static validation of SDK code | R | none | yes | **allow** |
| `validate_node_config` | static validation of a node | R | none | yes | **allow** |
| `list_credentials` | credential **metadata** | R | none — no payload, and the OAuth surface has no `credential:write` | yes | **allow** |
| `search_projects` | project list | R | none | yes | **allow** |
| `list_workflow_tags` | tag list | R | none | yes | **allow** |
| `list_n8n_gateway_services` | managed-credential coverage | R | none | yes | **allow** |
| `get_workflow_execution` | execution detail | R | none | yes | **allow** |
| `search_workflow_executions` | execution list | R | none | yes | **allow** |
| `search_data_tables` | data table list | R | none | yes | **allow** |
| `get_data_table_rows` | data table contents | R | none | yes (instance is empty) | **allow** |
| `prepare_workflow_pin_data` | generate pin data | R→ | unverified whether it touches anything to sample data | unproven | **ask** |
| `create_workflow_from_code` | create workflow | W | creates a workflow; may auto-assign credentials | yes, with guard | **ask** |
| `update_workflow` | mutate workflow | W | `setNodeCredential` can bind a credential by argument | yes, with guard | **ask** |
| `test_workflow` | run with pin data | **X** | **executes unpinned nodes for real** | no — see below | **ask** |
| `unpublish_workflow` | deactivate | W | changes production availability | no | **deny** |
| `archive_workflow` | archive | W | destructive | no | **deny** |
| `restore_workflow_version` | roll a workflow back | W | overwrites current definition | no | **deny** |
| `explore_node_resources` | resolve dropdown values | R→**net** | **real outbound call to a third party with a real credential** | no | **deny** |
| `create_data_table` | create table | W | schema change | no | **deny** |
| `rename_data_table` | rename table | W | schema change | no | **deny** |
| `add_data_table_column` | add column | W | schema change | no | **deny** |
| `rename_data_table_column` | rename column | W | schema change | no | **deny** |
| `delete_data_table_column` | drop column | W | **data loss** | no | **deny** |
| `add_data_table_rows` | insert rows | W | data mutation | no | **deny** |

33 tools, 33 rules, no tool in two buckets. `vorquel-brain-doctor` fails the
`n8n.deny_rules` check if that ever stops being true.

## Two findings that changed the policy

### `test_workflow` is not a sandbox

Verbatim from its schema:

> Trigger nodes, nodes with credentials, and HTTP Request nodes are pinned (use
> simulated data). **Other nodes (Set, If, Code, etc.) execute normally —
> including credential-free I/O nodes like Execute Command or file read/write
> nodes.**

Pin data suppresses *some* nodes. Everything else runs, including shell
execution and filesystem writes. So `test_workflow` is a gate with
preconditions, not a safe playground:

1. deterministic validation
2. `validate_workflow`
3. Static Analyzer
4. side-effect classification
5. `prepare_workflow_pin_data`
6. inspect which nodes were skipped
7. refuse privileged nodes

`Execute Command` — BLOCKED. SSH — BLOCKED. Filesystem — BLOCKED by default.
`Code` — REVIEW_REQUIRED. Community/custom nodes — REVIEW_REQUIRED.

### `explore_node_resources` reaches outside

It reads like a catalog lookup and is not one. Verbatim:

> Requires a credential ID from `list_credentials` — the call runs as the
> current user with that credential.

It authenticates to Slack, Google, OpenAI and so on to list real channels,
tabs or models. Denied in V1.

## Credential auto-assignment guard

`create_workflow_from_code` and `update_workflow` can bind credentials, and
`update_workflow`'s `operations[].type` enum includes `setNodeCredential`. The
danger is argument-level, so name-level permission is not enough.

After every create or update:

- read back `autoAssignedCredentials`;
- compare **ids, aliases and types only** against the DEV allowlist;
- never read a credential value;
- if anything is outside the allowlist: STOP, do not test, revert or restore
  the snapshot.

This DEV instance was provisioned empty (`No credentials found with specified
filters`), so the allowlist starts at zero and any binding is an anomaly.

## What the OAuth scopes do and do not give

Granted: `workflow:read`, `workflow:write`, `workflow:execute`,
`execution:read`, `credential:read`, `dataTable:read`, `dataTable:write`,
`project:read`, `project:write`, `tag:read`.

There is no `credential:write` scope on this server, so creating or altering a
credential is impossible at the protocol layer, not merely denied by policy.
`dataTable:write` and `workflow:execute` *are* granted, which is precisely why
the data-table writers are denied by name and `test_workflow` is gated.

## Operational note: workspace trust

A non-interactive run in an untrusted workspace prints:

> Ignoring N permissions.allow entries … this workspace has not been trusted.

Only `allow` is dropped. `deny` still applies — verified by running a denied
command and watching it be refused. That part still holds, and the safety
posture is unchanged either way.

**But "the failure mode is extra prompts" understated it.** On 2026-09-20 a new
non-interactive session in this untrusted workspace got *no* `mcp__n8n__*` tools
at all. Not denied, not prompted — absent, and absent silently: the session's
own list of connected and unauthenticated MCP servers never mentioned `n8n`.

What was observed, and what was not:

| Observed | How |
|---|---|
| The server and token are fine | `claude mcp list` → `n8n: http://127.0.0.1:5678/mcp-server/http (HTTP) - ✔ Connected` |
| DEV is up and correct | `vorquel-n8n-dev` Up, `n8nio/n8n:2.39.8`, `127.0.0.1:5678->5678/tcp` |
| The endpoint rejects anonymous callers | unauthenticated `initialize` → `401 Unauthorized: Authorization header not sent` |
| The registration exists | `~/.claude.json` → `projects["C:/VORQUEL/VORQUEL N8N/Vorquel-brain"].mcpServers.n8n` |
| The workspace is untrusted | same entry: `hasTrustDialogAccepted: false` |

The registration is **project-local**, so the leading explanation is that an
untrusted workspace skips loading it. That is a hypothesis, not a proven
mechanism — it was not confirmed against client internals, and a second
candidate (the drive-letter case of the project key, which this session was seen
to flip between `c:` and `C:`) was not ruled out.

The consequence is what matters, and it is not a prompt: **no BUILD step can be
proven in a session that has no n8n tools.** Accept the trust dialog once, in an
interactive session, and confirm the tools are present before building — the
check at the top of `PR2_HANDOFF_STATE.md` exists for exactly this.
