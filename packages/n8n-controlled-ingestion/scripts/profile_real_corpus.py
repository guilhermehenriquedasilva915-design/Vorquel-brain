from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from vorquel_n8n_analyzer.analyzer import analyze_file
from vorquel_n8n_knowledge_compiler.compiler import compile_knowledge_item

from vorquel_n8n_controlled_ingestion.common import (
    MAX_WORKFLOW_BYTES,
    read_json_object,
    safe_relative_path,
    sha256_bytes,
    workflow_has_credentials,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aggregate controlled-ingestion eligibility diagnostics without persistence."
    )
    parser.add_argument("corpus_root", type=Path)
    parser.add_argument("--source-repo", required=True)
    parser.add_argument("--source-commit", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    counters = collections.Counter()
    finding_sets = collections.Counter()
    role_counts = collections.Counter()

    for path in sorted(args.corpus_root.rglob("*.json")):
        counters["files_seen"] += 1
        if path.is_symlink():
            counters["symlink"] += 1
            continue

        relative = safe_relative_path(args.corpus_root, path)
        report = analyze_file(path, max_file_bytes=MAX_WORKFLOW_BYTES)
        if report.parse_error is not None:
            counters["parse_error"] += 1
            continue
        if report.risk_decision != "SAFE_FOR_LEARNING":
            counters["not_safe_for_learning"] += 1
            continue

        raw, workflow = read_json_object(
            path,
            max_bytes=MAX_WORKFLOW_BYTES,
            label=f"workflow:{relative}",
        )
        if workflow_has_credentials(workflow):
            counters["has_credentials"] += 1
            continue

        digest = sha256_bytes(raw)
        item = compile_knowledge_item(
            workflow,
            report.to_dict(),
            source_repo=args.source_repo,
            source_commit=args.source_commit,
            source_path=relative,
            source_sha256=digest,
        )
        role_counts[item["admission"]["knowledge_role"]] += 1

        findings = item.get("security_findings", [])
        rules = tuple(sorted({str(f.get("rule_id")) for f in findings if isinstance(f, dict)}))
        finding_sets["+".join(rules) if rules else "<none>"] += 1

        if item.get("untrusted_text"):
            counters["has_untrusted_text"] += 1
        if item.get("executable_snippets_untrusted"):
            counters["has_executable_metadata"] += 1

        nodes = item.get("workflow", {}).get("nodes", [])
        if any(
            isinstance(node, dict) and node.get("credential_types")
            for node in nodes
        ):
            counters["compiler_credential_types"] += 1

        if (
            not item.get("untrusted_text")
            and not item.get("executable_snippets_untrusted")
            and not any(
                isinstance(node, dict) and node.get("credential_types")
                for node in nodes
            )
        ):
            counters["no_text_exec_or_credentials"] += 1

    print(
        json.dumps(
            {
                "counters": dict(sorted(counters.items())),
                "finding_rule_sets_after_no_credentials": dict(
                    finding_sets.most_common(20)
                ),
                "knowledge_roles_after_no_credentials": dict(sorted(role_counts.items())),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
