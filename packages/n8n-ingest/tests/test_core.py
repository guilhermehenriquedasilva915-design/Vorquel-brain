from __future__ import annotations

import copy

import pytest

from vorquel_n8n_ingest.core import (
    ControlledIngestError,
    compile_manifest_items,
    plan_manifest,
)

REPO = "JustInCache/n8n-workflows"
COMMIT = "5a7864987c22930521382b597873b713cc830dac"


def plan(root, count=1):
    return plan_manifest(
        root,
        source_repo=REPO,
        source_commit=COMMIT,
        analyzer_version="0.1.0",
        count=count,
    )


def test_planner_selects_strict_safe_workflow(tmp_path, safe_workflow, write_workflow):
    write_workflow("workflows/safe.json", safe_workflow)

    manifest = plan(tmp_path)

    assert manifest["policy"] == "STRICT_REFERENCE_V01"
    assert len(manifest["items"]) == 1
    assert manifest["items"][0]["source_path"] == "workflows/safe.json"
    assert manifest["items"][0]["risk_decision"] == "SAFE_FOR_LEARNING"
    assert manifest["items"][0]["knowledge_role"] == "REFERENCE_PATTERN"


def test_planner_rejects_sticky_note_text(tmp_path, safe_workflow, write_workflow):
    workflow = copy.deepcopy(safe_workflow)
    workflow["nodes"].append(
        {
            "name": "Note",
            "type": "n8n-nodes-base.stickyNote",
            "typeVersion": 1,
            "parameters": {"content": "untrusted instructions"},
        }
    )
    write_workflow("workflows/note.json", workflow)

    with pytest.raises(ControlledIngestError, match="only 0 workflows"):
        plan(tmp_path)


def test_planner_rejects_credentials(tmp_path, safe_workflow, write_workflow):
    workflow = copy.deepcopy(safe_workflow)
    workflow["nodes"][1]["credentials"] = {
        "httpHeaderAuth": {"id": "not-read-by-compiler", "name": "credential"}
    }
    write_workflow("workflows/credentials.json", workflow)

    with pytest.raises(ControlledIngestError, match="only 0 workflows"):
        plan(tmp_path)


def test_planner_rejects_executable_expression(tmp_path, safe_workflow, write_workflow):
    workflow = copy.deepcopy(safe_workflow)
    workflow["nodes"][1]["parameters"] = {"value": "={{ $json.input }}"}
    write_workflow("workflows/expression.json", workflow)

    with pytest.raises(ControlledIngestError, match="only 0 workflows"):
        plan(tmp_path)


def test_ingest_detects_hash_drift(tmp_path, safe_workflow, write_workflow):
    path = write_workflow("workflows/safe.json", safe_workflow)
    manifest = plan(tmp_path)

    changed = copy.deepcopy(safe_workflow)
    changed["name"] = "Changed"
    path.write_text(__import__("json").dumps(changed), encoding="utf-8")

    with pytest.raises(ControlledIngestError, match="manifest drift"):
        compile_manifest_items(tmp_path, manifest)


def test_ingest_rejects_path_traversal(tmp_path, safe_workflow, write_workflow):
    write_workflow("workflows/safe.json", safe_workflow)
    manifest = plan(tmp_path)
    manifest["items"][0]["source_path"] = "../outside.json"

    with pytest.raises(ControlledIngestError, match="unsafe path traversal"):
        compile_manifest_items(tmp_path, manifest)


def test_ingest_rejects_duplicate_paths(tmp_path, safe_workflow, write_workflow):
    write_workflow("workflows/safe.json", safe_workflow)
    manifest = plan(tmp_path)
    manifest["items"].append(copy.deepcopy(manifest["items"][0]))

    with pytest.raises(ControlledIngestError, match="duplicate source_path"):
        compile_manifest_items(tmp_path, manifest)


def test_manifest_hard_cap_is_four(tmp_path, safe_workflow, write_workflow):
    for index in range(5):
        write_workflow(f"workflows/{index}.json", safe_workflow)

    with pytest.raises(ControlledIngestError, match="between 1 and 4"):
        plan(tmp_path, count=5)


def test_compile_manifest_is_deterministic(tmp_path, safe_workflow, write_workflow):
    write_workflow("workflows/safe.json", safe_workflow)
    manifest = plan(tmp_path)

    first = compile_manifest_items(tmp_path, manifest)
    second = compile_manifest_items(tmp_path, manifest)

    assert first[0].sha256 == second[0].sha256
    assert first[0].records == second[0].records
