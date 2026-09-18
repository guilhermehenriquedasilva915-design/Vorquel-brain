# Security model

## Trust boundary

All imported workflows, prompts, sticky notes, descriptions, node names, code, URLs and metadata are **untrusted data**.

The analyzer must never:

- execute a workflow;
- evaluate JavaScript/Python from a workflow;
- run shell or SSH commands from a workflow;
- make HTTP requests found in a workflow;
- load credentials referenced by a workflow;
- follow instructions embedded in source material;
- connect to production as a side effect of analysis.

## Promotion model

`RAW_UNTRUSTED -> STATIC_ANALYZED -> SAFE_FOR_LEARNING -> SANDBOX_TESTED -> VORQUEL_VALIDATED`

A workflow can also be marked `BLOCKED` at any point.

The MVP only performs static analysis. It does **not** promote anything to `SANDBOX_TESTED` or `VORQUEL_VALIDATED`.

## Report safety

Evidence snippets are truncated and secret-like values are redacted where detected. Static secret detection is heuristic and can produce false positives or false negatives; reports must not be treated as proof that a workflow contains no secrets.

## Prompt injection

Text inside a workflow is content, not authority. Even if a workflow says it is safe, production-ready, or instructs an agent to use a tool, that statement does not grant permission.
