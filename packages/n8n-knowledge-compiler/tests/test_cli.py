from __future__ import annotations

import json

import pytest

from vorquel_n8n_knowledge_compiler.cli import _read_untrusted_json


def test_cli_rejects_symlink_input(tmp_path):
    target = tmp_path / "target.json"
    target.write_text('{"name":"x"}', encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)

    with pytest.raises(ValueError, match="symlink input is not allowed"):
        _read_untrusted_json(link, max_bytes=1024, label="workflow")


def test_cli_rejects_oversized_input_before_parse(tmp_path):
    path = tmp_path / "large.json"
    path.write_bytes(b"x" * 64)

    with pytest.raises(ValueError, match="exceeds configured size limit"):
        _read_untrusted_json(path, max_bytes=16, label="workflow")


def test_cli_reads_small_json_object(tmp_path):
    path = tmp_path / "workflow.json"
    payload = {"name": "Example", "nodes": []}
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert _read_untrusted_json(path, max_bytes=1024, label="workflow") == payload
