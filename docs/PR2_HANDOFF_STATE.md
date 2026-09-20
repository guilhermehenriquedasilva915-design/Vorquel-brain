# PR2 handoff — everything is provisioned, BUILD has not started

Written 2026-09-20, at the moment every Phase 12 gate went green. Read this
first in a new session: it says what is already true, so you do not re-derive
or re-prove it.

## Start here

The n8n MCP tools are registered but were added mid-session last time, so they
only load in a **new** session. Confirm they are live before building:

```
ToolSearch  select:mcp__n8n__search_workflows,mcp__n8n__validate_workflow
```

If that returns nothing, the tools are still not loaded and no BUILD step can
be proven. Do not proceed by assuming.

## Branch

`feat/n8n-brain-build-safe-test`, based on `3f10ce7` (PR #21 head, which
contains PR #20's head). Commit `3ca2644` carries the policy, profile, doctor
and this repo's tool matrix. **PR2 is not open yet** — open it only when BUILD
+ SAFE TEST actually works.

## What is already proven — do not redo

| Fact | How it was proven |
|---|---|
| Brain PR #21 CI | 11/11 pass |
| Watch 0024 live | `anon=False authenticated=False service_role=True watch_runtime=True` on all four scoped RPCs |
| Brain 005 live | `touch_build_run: search_path=pg_catalog, n8n_brain` |
| Watch gate test | Ran clean-room on disposable PostgreSQL 17: bootstrap → 0001-0024 → gate test → 0021-0024 re-apply |
| DB retrieval | Connects, read-only session enforced — a write was refused with `ReadOnlySqlTransaction` |
| n8n DEV | 2.39.8, digest `sha256:b73045ab…d23ae`, bound `127.0.0.1:5678` only, healthz 200 |
| MCP | OAuth connected, 33 tools enumerated at runtime |
| DEV is clean | `No credentials found`, `No workflows found` |

`vorquel-brain-doctor` reports **READY_WITH_LIMITS**, no BLOCK. The two
warnings are honest: the structural corpus is empty, and ffmpeg is absent
(video LEARN only).

## A correction that matters

Watch PR #13's gate test never ran. The block asserting that no scoped RPC is
reachable by `anon`/`authenticated` opened with `do $` — a single dollar sign
is not a valid dollar-quote, so psql aborted there. The repository has no
Actions minutes, so nothing caught it. Fixed in `1ec6825` on
`fix/knowledge-rpc-privileges` and proven locally. **That repo's red CI is a
quota blocker, not code** — its jobs report zero steps.

## Local environment (outside both repos, nothing committed)

| Thing | Where |
|---|---|
| n8n encryption key | `%LOCALAPPDATA%\Vorquel\n8n-dev\encryption-key.dpapi` (DPAPI, ACL-locked) |
| Brain DSN | `%LOCALAPPDATA%\Vorquel\brain\database-url.dpapi` (DPAPI, ACL-locked) |
| Environment profile | `%LOCALAPPDATA%\Vorquel\n8n-dev\environment-profile.json` |
| Helper scripts | `%LOCALAPPDATA%\Vorquel\bin\` |

Run anything needing the database through the wrapper, which decrypts into the
child process only:

```powershell
& "$env:LOCALAPPDATA\Vorquel\bin\with-brain-dsn.ps1" vorquel-brain-doctor
```

Start or restart the DEV instance with
`%LOCALAPPDATA%\Vorquel\bin\start-n8n-dev.ps1`. It reads the key from DPAPI and
passes it by env inheritance, so the key never reaches a command line. The
named volume `n8n_dev_data` holds the owner account.

Do not start the `n8nwahalocal-*` containers. That is an old WhatsApp/WAHA
stack on `n8n:latest` bound to `0.0.0.0`, untouched and stopped.

## Policy, in one line each

- 33 tools, 33 rules, none in two buckets. See `N8N_MCP_TOOL_MATRIX.md`.
- `test_workflow` is **not** a sandbox: unpinned nodes run for real, including
  `Execute Command` and file I/O. It is a gate with seven preconditions.
- `explore_node_resources` is denied: it authenticates to third parties.
- `update_workflow`'s `setNodeCredential` makes credential binding an
  argument-level risk, so name-level permission is not sufficient.
- The doctor grades the denylist only against a tool surface that was really
  observed. An unverified rule is not protection.

## Operational note

In a non-interactive run the client prints *"Ignoring N permissions.allow
entries … workspace has not been trusted"*. Only `allow` is dropped; `deny`
still applies (verified by watching a denied command be refused). Accepting the
trust dialog once removes the friction without changing safety.

## What PR2 still has to build

```
request → context pack → environment profile → plan → draft
→ deterministic validation → validate_workflow → Analyzer
→ side-effect guard → snapshot/drift → create/update DEV
→ SAFE TEST → assertions/report
```

None of it exists yet. The credential guard and safe-test gate are specified in
the tool matrix but not implemented.
