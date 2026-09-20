"""Message, plain text and Markdown.

The operator pasting a paragraph into the conversation is a first-class source.
It is registered, hashed, versioned and cited exactly like a PDF, because the
alternative -- treating "things the user said" as automatically true and
uncited -- is how a memory stops being auditable.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..extract import RawUnit, to_batch
from ..model import LearnBatch, SourceRef, sha256_text
from ..scope_util import resolve_scope

# A heading is the natural unit of a document: it is what a reader would cite.
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$", re.MULTILINE)
# Two or more blank lines separate topics in plain text that has no headings.
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


def _markdown_sections(text: str) -> list[tuple[str, str]]:
    matches = list(_MD_HEADING.finditer(text))
    if not matches:
        return []

    sections: list[tuple[str, str]] = []
    preamble = text[: matches[0].start()].strip()
    if preamble:
        sections.append(("(preambulo)", preamble))

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        if body:
            sections.append((match.group(2), body))
    return sections


def learn_message(
    text: str,
    scope: str,
    data_classification: str = "INTERNAL",
    conversation_ref: str | None = None,
) -> LearnBatch:
    """Learn from text the operator supplied directly."""
    payload = text.encode("utf-8")
    source = SourceRef(
        source_kind="MESSAGE",
        content_sha256=sha256_text(text),
        byte_size=len(payload),
        detected_mime="text/plain",
        scope=resolve_scope(scope),
        data_classification=data_classification,
        # A message has no stable identity beyond its bytes: there is no file to
        # re-export. Leaving logical_key unset keeps it out of the version chain.
        logical_key=None,
        external_metadata=(
            {"conversation_ref": conversation_ref} if conversation_ref else {}
        ),
    )

    paragraphs = [block.strip() for block in _PARAGRAPH_BREAK.split(text) if block.strip()]
    units = [
        RawUnit(
            title=paragraph.splitlines()[0][:120],
            text=paragraph,
            locator_kind="MESSAGE",
            locator={"paragraph": index + 1},
            # The operator is asserting this, not demonstrating it. OBSERVADO
            # and MEDIDO have to be earned by seeing or measuring a run.
            epistemic_status="DECLARADO",
        )
        for index, paragraph in enumerate(paragraphs)
    ]
    return to_batch(source, units, data_classification)


def learn_text_file(
    path: str | Path,
    scope: str,
    data_classification: str = "INTERNAL",
    logical_key: str | None = None,
) -> LearnBatch:
    """Learn from a .txt or .md file, segmented by heading where there is one."""
    file_path = Path(path)
    payload = file_path.read_bytes()
    text = payload.decode("utf-8", errors="replace")

    is_markdown = file_path.suffix.lower() in {".md", ".markdown"}
    source = SourceRef(
        source_kind="MARKDOWN" if is_markdown else "TEXT",
        content_sha256=sha256_text(text),
        byte_size=len(payload),
        detected_mime="text/markdown" if is_markdown else "text/plain",
        scope=resolve_scope(scope),
        data_classification=data_classification,
        logical_key=logical_key or file_path.name,
        external_metadata={"filename": file_path.name},
    )

    sections = _markdown_sections(text) if is_markdown else []
    if sections:
        units = [
            RawUnit(
                title=heading,
                text=body,
                locator_kind="DOC_SECTION",
                locator={"section": heading[:200]},
            )
            for heading, body in sections
        ]
    else:
        units = [
            RawUnit(
                title=block.splitlines()[0][:120],
                text=block,
                locator_kind="DOC_SECTION",
                locator={"paragraph": index + 1},
            )
            for index, block in enumerate(
                block.strip() for block in _PARAGRAPH_BREAK.split(text) if block.strip()
            )
        ]

    return to_batch(source, units, data_classification)
