"""Video and screen material, by way of Vorquel Watch.

The Brain does not transcribe, does not do OCR and does not download video.
That pipeline exists in Vorquel Watch, it already registers the media source
and it already stores transcripts and screen observations. Rebuilding any of it
here would create a second, diverging copy of the same capability.

What lives here is the contract: given what Watch produced for a source it
already registered, turn it into scoped, cited candidates the same way every
other adapter does. The media source is cited, never re-registered -- Watch
owns that row.

Limitation, stated rather than hidden: the end-to-end path from a real video
file to candidates is exercised against a fixture, because it needs a Watch
runtime with its media dependencies installed. What is proven here is the
contract and the provenance, not that transcription works. That claim belongs
to Watch's own tests.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from ..extract import RawUnit, to_batch
from ..model import LearnBatch, LearnError, SourceRef
from ..scope_util import resolve_scope

# Segments are merged up to this size before becoming a candidate: a single
# three-second line of speech is not a citable claim.
TARGET_WINDOW_MS = 90_000


@dataclass(frozen=True)
class WatchSegment:
    """One transcript segment as Vorquel Watch stores it."""

    segment_id: str
    start_ms: int
    end_ms: int
    text: str

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms < self.start_ms:
            raise LearnError(f"segmento {self.segment_id} tem limites invalidos")


@dataclass(frozen=True)
class WatchTranscript:
    """What Watch hands over for a source it has already registered."""

    source_id: str
    transcript_id: str
    title: str
    segments: Sequence[WatchSegment]
    duration_ms: int | None = None
    screen_observations: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.source_id.startswith("src_"):
            raise LearnError("source_id do Watch invalido")
        if not self.segments:
            raise LearnError("transcricao sem segmentos")


def _windows(segments: Sequence[WatchSegment]) -> list[list[WatchSegment]]:
    grouped: list[list[WatchSegment]] = []
    current: list[WatchSegment] = []
    for segment in segments:
        if current and segment.end_ms - current[0].start_ms > TARGET_WINDOW_MS:
            grouped.append(current)
            current = []
        current.append(segment)
    if current:
        grouped.append(current)
    return grouped


def learn_watch_transcript(
    transcript: WatchTranscript,
    scope: str,
    data_classification: str = "INTERNAL",
) -> LearnBatch:
    """Turn a Watch transcript into candidates cited by MEDIA_TIME."""
    source = SourceRef(
        source_kind="YOUTUBE",
        # The bytes are Watch's business; identity here is the source it
        # registered, which is why existing_source_id is what gets cited.
        content_sha256="0" * 64,
        byte_size=0,
        detected_mime="video/mp4",
        scope=resolve_scope(scope),
        data_classification=data_classification,
        existing_source_id=transcript.source_id,
        external_metadata={
            "transcript_id": transcript.transcript_id,
            "title": transcript.title,
            "segment_count": len(transcript.segments),
            "screen_observation_count": len(transcript.screen_observations),
            "produced_by": "vorquel-watch",
        },
    )

    units: list[RawUnit] = []
    for window in _windows(list(transcript.segments)):
        start = window[0].start_ms
        end = window[-1].end_ms
        if transcript.duration_ms is not None and end > transcript.duration_ms:
            raise LearnError("segmento aponta para alem da duracao da fonte")
        units.append(
            RawUnit(
                title=f"{transcript.title} [{start // 1000}s-{end // 1000}s]",
                text=" ".join(segment.text.strip() for segment in window).strip(),
                locator_kind="MEDIA_TIME",
                locator={
                    "transcript_id": transcript.transcript_id,
                    "segment_id": window[0].segment_id,
                    "start_ms": start,
                    "end_ms": end,
                },
                # Someone said it on camera. That makes it asserted, not measured.
                epistemic_status="DECLARADO",
            )
        )

    return to_batch(source, units, data_classification)
