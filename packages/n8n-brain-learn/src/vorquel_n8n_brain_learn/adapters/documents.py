"""PDF and DOCX.

Both formats can carry executable content -- an embedded JavaScript action in a
PDF, a macro in a Word document. Neither is opened here in a way that could run
it: the readers used extract text and nothing else, and a macro-enabled
document is refused outright rather than silently read as if it were inert.

Native text is preferred and OCR is not attempted. A scanned page with no text
layer is reported as such, because an empty extraction that looks like a
successful one is the worst possible outcome for a memory.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from ..extract import RawUnit, to_batch
from ..model import LearnBatch, LearnError, SourceRef, sha256_bytes
from ..scope_util import resolve_scope

# Word's macro-enabled formats. A macro is code; this package reads documents.
_MACRO_SUFFIXES = {".docm", ".dotm", ".xlsm", ".pptm"}

_HEADING_STYLE = re.compile(r"^Heading\s*(\d+)$", re.IGNORECASE)


def _guard_suffix(path: Path) -> None:
    if path.suffix.lower() in _MACRO_SUFFIXES:
        raise LearnError(
            f"{path.suffix} carrega macros; converta para um formato sem codigo antes de aprender"
        )


def learn_pdf(
    path: str | Path,
    scope: str,
    data_classification: str = "INTERNAL",
    logical_key: str | None = None,
) -> LearnBatch:
    """One unit per page, addressed by PDF_PAGE."""
    from pypdf import PdfReader

    file_path = Path(path)
    _guard_suffix(file_path)
    payload = file_path.read_bytes()

    source = SourceRef(
        source_kind="PDF",
        content_sha256=sha256_bytes(payload),
        byte_size=len(payload),
        detected_mime="application/pdf",
        scope=resolve_scope(scope),
        data_classification=data_classification,
        logical_key=logical_key or file_path.name,
        external_metadata={"filename": file_path.name},
    )

    reader = PdfReader(str(file_path))
    if reader.is_encrypted:
        # Supplying a password would mean handling a credential here.
        raise LearnError("PDF encriptado; descriptografe fora do Brain antes de aprender")

    units: list[RawUnit] = []
    empty_pages: list[int] = []
    for index, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if not text:
            empty_pages.append(index)
            continue
        units.append(
            RawUnit(
                title=f"{file_path.name} p.{index}",
                text=text,
                locator_kind="PDF_PAGE",
                locator={"page": index},
            )
        )

    if not units:
        raise LearnError(
            f"nenhuma pagina do PDF tem camada de texto ({len(reader.pages)} paginas). "
            "Provavelmente e digitalizado; OCR nao e feito aqui."
        )

    batch = to_batch(source, units, data_classification)
    if empty_pages:
        # Recorded on the source so the reviewer knows the extraction is partial.
        batch.source.external_metadata["pages_without_text"] = empty_pages
    return batch


def learn_docx(
    path: str | Path,
    scope: str,
    data_classification: str = "INTERNAL",
    logical_key: str | None = None,
) -> LearnBatch:
    """One unit per heading section, addressed by DOC_SECTION."""
    import docx

    file_path = Path(path)
    _guard_suffix(file_path)
    payload = file_path.read_bytes()

    # A .docx is a zip. A macro project inside one is still a macro, whatever
    # the extension claims.
    with zipfile.ZipFile(file_path) as archive:
        if any(name.endswith("vbaProject.bin") for name in archive.namelist()):
            raise LearnError("o documento contem um projeto VBA; recusado")

    source = SourceRef(
        source_kind="DOCX",
        content_sha256=sha256_bytes(payload),
        byte_size=len(payload),
        detected_mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        scope=resolve_scope(scope),
        data_classification=data_classification,
        logical_key=logical_key or file_path.name,
        external_metadata={"filename": file_path.name},
    )

    document = docx.Document(str(file_path))
    sections: list[tuple[str, list[str]]] = []
    current_title = "(preambulo)"
    current_body: list[str] = []

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style = (paragraph.style.name if paragraph.style is not None else "") or ""
        if _HEADING_STYLE.match(style) or style.lower() == "title":
            if current_body:
                sections.append((current_title, current_body))
            current_title = text
            current_body = []
        else:
            current_body.append(text)

    if current_body:
        sections.append((current_title, current_body))

    if not sections:
        raise LearnError("o documento nao tem texto extraivel")

    units = [
        RawUnit(
            title=title,
            text="\n\n".join(body),
            locator_kind="DOC_SECTION",
            locator={"section": title[:200], "ordinal": ordinal},
        )
        for ordinal, (title, body) in enumerate(sections, start=1)
    ]
    return to_batch(source, units, data_classification)
