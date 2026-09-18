# n8n Knowledge Compiler

Transforms an n8n workflow plus a static-analysis report into a deterministic, provenance-aware knowledge item.

## Trust boundary

The compiler does **not** execute workflows, code, expressions, shell, SSH, or requests.

External material remains `RAW_UNTRUSTED`. The compiler only restructures it.

Important safety rules:

- credential values, IDs, and names are never copied;
- executable snippets are represented by metadata + SHA-256 only;
- BLOCKED workflows become `SECURITY_EXAMPLE`, never implementation recipes;
- HIGH-risk workflows remain quarantined;
- even low-risk knowledge is **not** `VORQUEL_VALIDATED`;
- natural-language material stays explicitly tagged `UNTRUSTED_TEXT`.

## CLI

```bash
cd packages/n8n-knowledge-compiler
python -m pip install -e '.[dev]'

vorquel-n8n-compile workflow.json \
  --analysis analyzer-report.json \
  --source-repo JustInCache/n8n-workflows \
  --source-commit 5a7864987c22930521382b597873b713cc830dac \
  --source-path workflows/Foo/example.json \
  --pretty
```

The analyzer report may be either one report object or an aggregate payload containing a `reports` array.
