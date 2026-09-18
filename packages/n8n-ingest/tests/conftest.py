from __future__ import annotations

import json

import pytest


@pytest.fixture
def safe_workflow():
    return {
        "name": "Safe fixture",
        "nodes": [
            {
                "name": "Manual",
                "type": "n8n-nodes-base.manualTrigger",
                "typeVersion": 1,
                "parameters": {},
            },
            {
                "name": "Set",
                "type": "n8n-nodes-base.set",
                "typeVersion": 3.4,
                "parameters": {"values": {}},
            },
        ],
        "connections": {
            "Manual": {
                "main": [[{"node": "Set", "type": "main", "index": 0}]]
            }
        },
    }


@pytest.fixture
def write_workflow(tmp_path):
    def writer(relative_path, payload):
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    return writer
