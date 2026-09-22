# vorquel-n8n-brain-learn

Turns an external source into **reviewable, scoped, cited candidates**. It is
the LEARN half of the pair whose other half is `n8n-brain-retrieval`.

```
SOURCE -> guard -> extracao -> policy -> provenance -> candidates (PENDING)
       -> revisao humana -> approved knowledge -> retrieval
```

Nothing in this package produces knowledge. It stops at PENDING, by
construction: there is no parameter, flag or code path here that approves a
candidate.

## Source kinds

| Kind | Adapter | `locator_kind` | Addressed by |
|---|---|---|---|
| mensagem / texto colado | `learn_message` | `MESSAGE` | paragrafo |
| `.txt` | `learn_text_file` | `DOC_SECTION` | paragrafo |
| `.md` | `learn_text_file` | `DOC_SECTION` | heading |
| `.json` | `learn_json` | `GENERIC` | caminho JSON |
| `.pdf` | `learn_pdf` | `PDF_PAGE` | pagina |
| `.docx` | `learn_docx` | `DOC_SECTION` | secao |
| repositorio Git | `learn_git_repo` | `REPO_FILE` | caminho + commit |
| workflow n8n | `learn_n8n_workflow` | `WORKFLOW_NODE` | no |
| video / YouTube | `learn_watch_transcript` | `MEDIA_TIME` | intervalo |

## What is enforced, and where

**Data policy** (`policy.py`) runs on every unit of every source kind:

- a **secret** is refused, never minimised. The unit is dropped, the rule that
  fired is reported, and the value never appears in the message, the log or the
  database.
- **PII** is minimised in place and widens the batch's classification to `PII`.
  A classification is only ever widened by what is found, never narrowed.

**The untrusted boundary** (`untrusted.py`): every unit is
`UNTRUSTED_DERIVED` with `instruction_authority = NONE`. Text that tries to
instruct the system is *flagged and shown to the reviewer*, not silently
dropped -- an article about prompt injection is legitimate material.

**Delegation**, not reimplementation:

- an n8n workflow goes through `vorquel-n8n-analyze` and the Knowledge
  Compiler, and only learns what the admission decision allows. The generic
  JSON adapter refuses a workflow rather than letting it in through the side
  door;
- video goes through Vorquel Watch. This package never transcribes, never does
  OCR and never downloads. It consumes what Watch produced and cites the media
  source Watch already registered.

**Repository guards** (`repo.py`): explicit https URL, pinned to a full commit
(a branch name is refused), hooks disabled, no submodules, no install and no
execution, symlinks skipped, paths verified to resolve inside the checkout,
binaries and oversized files skipped, and `README.md` / `CLAUDE.md` read as
ordinary evidence with no authority.

## Usage

```bash
# Dry run: shows the batch, touches nothing.
vorquel-brain-learn --scope CLIENT:acme \
  --classification CLIENT_CONFIDENTIAL --file runbook.pdf

# Creates PENDING candidates. Still approves nothing.
export VORQUEL_BRAIN_DATABASE_URL=...   # set it in your shell, never in the repo
vorquel-brain-learn --scope CLIENT:acme --file runbook.pdf --persist
```

## Limits worth knowing

- **No OCR.** A scanned PDF with no text layer raises rather than returning an
  empty batch that looks like a success.
- **No embeddings.** Retrieval is FTS-first until something measures that it is
  not enough.
- **The Watch path is proven at the contract, not end to end.** Turning a real
  video into candidates needs a Watch runtime with its media dependencies;
  what is tested here is the contract and the provenance. The claim that
  transcription works belongs to Watch's own tests.
- **Persistence is tested against a real schema only when one is offered.**
  The `vorquel_knowledge` schema lives in the Vorquel Watch repository, so the
  SQL-level proof of scope isolation and the review gate runs in that
  repository's `knowledge-migrations` job.
