# n8n Workflow Static Analyzer — MVP architecture

## Purpose

Provide a deterministic first gate before any external n8n workflow can enter the Vorquel n8n Brain.

```text
GitHub / file / corpus
        |
        v
   RAW_UNTRUSTED
        |
        v
 JSON parse only
        |
        v
 Static rule engine
        |
        +--> node inventory
        +--> trigger inventory
        +--> risk findings
        +--> secret-like hardcode detection
        +--> evidence redaction
        |
        v
 STATIC_ANALYZED
        |
        +--> SAFE_FOR_LEARNING
        +--> REVIEW_REQUIRED
        +--> BLOCKED
```

## Risk decisions

- `SAFE_FOR_LEARNING`: no HIGH/CRITICAL finding. This means suitable for study, not proven safe to run.
- `REVIEW_REQUIRED`: at least one HIGH finding.
- `BLOCKED`: at least one CRITICAL finding or parse/size failure.

## Initial rules

- OS command execution
- decrypted n8n credential export
- SSH execution
- filesystem access
- outbound HTTP
- local/private HTTP target
- custom code
- `eval()` / dynamic Function
- child process primitives
- filesystem import from Code nodes
- possible hardcoded secrets
- AI/agent + privileged execution co-occurrence

## Important limitation

This is a static triage layer, not a formal security proof. Later phases should add graph-aware taint analysis, version-aware node schemas, secret scanning with entropy/context, sandbox execution and behavioral evals.
