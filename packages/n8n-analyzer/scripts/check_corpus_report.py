from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_RULES = {
    "EXECUTE_COMMAND",
    "SSH_EXECUTION",
    "DECRYPTED_CREDENTIAL_EXPORT",
}

REQUIRED_DECISIONS = {
    "BLOCKED",
    "REVIEW_REQUIRED",
}


def _risk_index(payload: dict) -> list[dict]:
    risky: list[dict] = []
    for report in payload.get("reports", []):
        if report.get("risk_decision") == "SAFE_FOR_LEARNING":
            continue
        risky.append(
            {
                "source_path": report.get("source_path"),
                "risk_decision": report.get("risk_decision"),
                "max_severity": report.get("max_severity"),
                "rules": sorted(
                    {
                        finding.get("rule_id")
                        for finding in report.get("findings", [])
                        if finding.get("rule_id")
                    }
                ),
            }
        )
    return sorted(
        risky,
        key=lambda item: (
            0 if item["risk_decision"] == "BLOCKED" else 1,
            str(item["source_path"]),
        ),
    )


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_corpus_report.py REPORT.json")

    report_path = Path(sys.argv[1])
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    summary = payload.get("summary", {})

    files_analyzed = int(summary.get("files_analyzed", 0))
    finding_rules = summary.get("finding_rules", {})
    risk_decisions = summary.get("risk_decisions", {})

    if files_analyzed <= 0:
        raise SystemExit("corpus gate failed: no JSON files were analyzed")

    missing_rules = sorted(
        rule for rule in REQUIRED_RULES if int(finding_rules.get(rule, 0)) <= 0
    )
    if missing_rules:
        raise SystemExit(
            "corpus gate failed: expected known high-risk rules were not detected: "
            + ", ".join(missing_rules)
        )

    missing_decisions = sorted(
        decision
        for decision in REQUIRED_DECISIONS
        if int(risk_decisions.get(decision, 0)) <= 0
    )
    if missing_decisions:
        raise SystemExit(
            "corpus gate failed: expected risk decisions were absent: "
            + ", ".join(missing_decisions)
        )

    print("CORPUS_SUMMARY")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("RISK_INDEX_NO_EVIDENCE")
    print(json.dumps(_risk_index(payload), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
