"""One adapter per source kind. All of them end at the same policy gate.

Imports are deliberately lazy at module level only for the heavy document
readers, so a caller learning from a pasted message does not pay for pypdf.
"""

from .repo import checkout_pinned, iter_repo_files, learn_git_repo
from .structured import learn_json, looks_like_n8n_workflow
from .text import learn_message, learn_text_file
from .watch import WatchSegment, WatchTranscript, learn_watch_transcript
from .workflow import learn_n8n_workflow

__all__ = [
    "WatchSegment",
    "WatchTranscript",
    "checkout_pinned",
    "iter_repo_files",
    "learn_git_repo",
    "learn_json",
    "learn_message",
    "learn_n8n_workflow",
    "learn_text_file",
    "learn_watch_transcript",
    "looks_like_n8n_workflow",
]


def learn_document(path: str, scope: str, data_classification: str = "INTERNAL"):
    """Dispatch a file to its adapter by extension."""
    from pathlib import Path

    from ..model import LearnError

    suffix = Path(path).suffix.lower()
    # Named before the "unsupported extension" fallback so the operator is told
    # why the format is refused rather than that it was merely unrecognised.
    if suffix in {".docm", ".dotm", ".xlsm", ".pptm"}:
        raise LearnError(
            f"{suffix} carrega macros; converta para um formato sem codigo antes de aprender"
        )
    if suffix == ".pdf":
        from .documents import learn_pdf

        return learn_pdf(path, scope, data_classification)
    if suffix in {".docx", ".dotx"}:
        from .documents import learn_docx

        return learn_docx(path, scope, data_classification)
    if suffix == ".json":
        return learn_json(path, scope, data_classification)
    if suffix in {".txt", ".md", ".markdown", ".rst"}:
        return learn_text_file(path, scope, data_classification)
    raise LearnError(f"extensao nao suportada no PR1: {suffix!r}")
