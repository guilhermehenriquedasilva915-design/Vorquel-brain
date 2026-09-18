"""Manifest-gated controlled ingestion for Vorquel n8n knowledge."""

from .ingest import ingest_manifest, load_manifest
from .planner import build_manifest

__all__ = ["build_manifest", "ingest_manifest", "load_manifest"]
