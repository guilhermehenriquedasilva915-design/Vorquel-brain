"""Git repository.

A third-party repository is the most hostile source this package accepts, so
the guards are structural rather than advisory:

  * the URL is supplied explicitly by the operator and pinned to one commit.
    A branch name is not accepted: "main" means something different tomorrow;
  * nothing is installed, built or run. No npm install, no setup script, no
    "just to see if it works";
  * hooks are disabled at fetch time, because a hook is code the repository
    chose and the fetch would run it;
  * submodules are not fetched, since a submodule is a second URL the
    repository picked rather than the operator;
  * symlinks are skipped and every path is verified to resolve inside the
    checkout, so a crafted entry cannot address the host filesystem;
  * binaries are skipped and files above a size cap are skipped, by extension
    and by content sniff, not by trusting the name;
  * README.md, CLAUDE.md, AGENTS.md and their neighbours are read as ordinary
    files with no special standing. A repository does not get to configure the
    agent reading it.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..extract import RawUnit, to_batch
from ..model import LearnBatch, LearnError, SourceRef, sha256_text
from ..scope_util import resolve_scope

_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_HTTPS_URL_RE = re.compile(r"^https://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+$")

MAX_FILE_BYTES = 512 * 1024
MAX_FILES = 400
MAX_TOTAL_BYTES = 16 * 1024 * 1024

TEXT_SUFFIXES = frozenset(
    {
        ".md",
        ".markdown",
        ".txt",
        ".rst",
        ".adoc",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".py",
        ".js",
        ".ts",
        ".sql",
        ".sh",
    }
)

# Files whose content is convention-loaded instruction to an agent. They are
# still readable as evidence; the point is that they carry no authority.
AGENT_CONFIG_NAMES = frozenset(
    {"claude.md", "agents.md", "agent.md", ".cursorrules", "copilot-instructions.md"}
)


@dataclass(frozen=True)
class SkippedFile:
    path: str
    reason: str


def _run_git(args: list[str], cwd: Path | None = None) -> None:
    """Run a git plumbing command with every repository-controlled hook off."""
    completed = subprocess.run(  # noqa: S603 - fixed argv, never a shell string
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "protocol.version=2",
            # A repository must not be able to nominate the credential helper
            # or an external filter program that the fetch would then execute.
            "-c",
            "core.askPass=",
            "-c",
            "credential.helper=",
            *args,
        ],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
        env={"GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1", "PATH": _safe_path()},
    )
    if completed.returncode != 0:
        # git's stderr can echo the URL but never a repository's file content.
        raise LearnError(f"git {args[0]} falhou: {completed.stderr.strip()[:300]}")


def _safe_path() -> str:
    import os

    return os.environ.get("PATH", "")


def checkout_pinned(url: str, commit: str, destination: Path) -> None:
    """Fetch exactly one commit into an empty directory, running nothing."""
    if not _HTTPS_URL_RE.match(url):
        raise LearnError("a URL do repositorio deve ser https explicita")
    if not _COMMIT_RE.match(commit):
        raise LearnError("o repositorio deve ser fixado por commit completo de 40 caracteres")

    destination.mkdir(parents=True, exist_ok=True)
    _run_git(["init", "--quiet", str(destination)])
    _run_git(["remote", "add", "origin", url], cwd=destination)
    _run_git(
        ["fetch", "--depth=1", "--no-tags", "--no-recurse-submodules", "origin", commit],
        cwd=destination,
    )
    _run_git(["checkout", "--detach", "FETCH_HEAD"], cwd=destination)

    # Trust the fetch only after confirming it produced the commit we asked for.
    completed = subprocess.run(  # noqa: S603 - fixed argv
        ["git", "rev-parse", "HEAD"],
        cwd=str(destination),
        capture_output=True,
        text=True,
        check=False,
    )
    actual = completed.stdout.strip()
    if actual != commit:
        raise LearnError(f"commit obtido ({actual[:12]}) difere do pedido ({commit[:12]})")


def _is_probably_binary(payload: bytes) -> bool:
    if b"\x00" in payload[:4096]:
        return True
    # A file that does not decode as UTF-8 is not text we can cite honestly.
    try:
        payload[:4096].decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def iter_repo_files(root: Path) -> tuple[list[Path], list[SkippedFile]]:
    """Enumerate readable text files, refusing anything that leaves the tree."""
    resolved_root = root.resolve()
    kept: list[Path] = []
    skipped: list[SkippedFile] = []
    total = 0

    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if ".git/" in f"{relative}/" or relative.startswith(".git"):
            continue

        # Checked before is_file(), which follows the link and would report on
        # the target instead of the entry.
        if path.is_symlink():
            skipped.append(SkippedFile(relative, "symlink"))
            continue
        if not path.is_file():
            continue

        try:
            real = path.resolve(strict=True)
        except OSError:
            skipped.append(SkippedFile(relative, "unresolvable"))
            continue
        if not real.is_relative_to(resolved_root):
            skipped.append(SkippedFile(relative, "path_escapes_checkout"))
            continue

        if path.suffix.lower() not in TEXT_SUFFIXES:
            skipped.append(SkippedFile(relative, "not_a_text_suffix"))
            continue

        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            skipped.append(SkippedFile(relative, "too_large"))
            continue
        if total + size > MAX_TOTAL_BYTES:
            skipped.append(SkippedFile(relative, "total_budget_exhausted"))
            continue
        if len(kept) >= MAX_FILES:
            skipped.append(SkippedFile(relative, "file_count_budget_exhausted"))
            continue

        if _is_probably_binary(path.read_bytes()[:4096]):
            skipped.append(SkippedFile(relative, "binary"))
            continue

        total += size
        kept.append(path)

    return kept, skipped


def learn_git_repo(
    url: str,
    commit: str,
    checkout: str | Path,
    scope: str,
    data_classification: str = "INTERNAL",
) -> LearnBatch:
    """Learn from a repository already fetched at `checkout`, pinned to `commit`.

    Fetching is a separate step (`checkout_pinned`) so a caller can inspect what
    landed before anything is read, and so tests can exercise the guards against
    a local tree without any network.
    """
    if not _COMMIT_RE.match(commit):
        raise LearnError("o repositorio deve ser fixado por commit completo de 40 caracteres")

    root = Path(checkout)
    if not root.is_dir():
        raise LearnError(f"checkout inexistente: {root}")

    files, skipped = iter_repo_files(root)
    if not files:
        raise LearnError("nenhum arquivo de texto elegivel no checkout")

    # The identity of a repo source is the commit, not the bytes of any file.
    source = SourceRef(
        source_kind="GIT_REPO",
        content_sha256=sha256_text(f"{url}@{commit}"),
        byte_size=sum(path.stat().st_size for path in files),
        detected_mime="application/x-git",
        scope=resolve_scope(scope),
        data_classification=data_classification,
        # Same repository, later commit: version 2 rather than a new source.
        logical_key=f"git:{url}",
        external_metadata={
            "url": url,
            "commit": commit,
            "files_read": len(files),
            "files_skipped": [
                {"path": item.path, "reason": item.reason} for item in skipped[:100]
            ],
        },
    )

    units: list[RawUnit] = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        is_agent_config = path.name.lower() in AGENT_CONFIG_NAMES
        units.append(
            RawUnit(
                title=relative,
                text=text,
                locator_kind="REPO_FILE",
                locator={"path": relative[:200], "commit": commit},
                # What a repository file says about itself is a claim. Nothing
                # was run, so nothing here was observed.
                epistemic_status="DECLARADO",
                knowledge_type="WARNING" if is_agent_config else "CONCEPT",
            )
        )

    return to_batch(source, units, data_classification)
