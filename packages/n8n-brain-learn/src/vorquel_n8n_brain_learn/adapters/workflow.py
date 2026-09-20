"""n8n workflow JSON.

A workflow is never read as raw JSON here. It goes through the static Analyzer
and then the Knowledge Compiler, and what the Compiler's admission decision
says is what this adapter is allowed to learn:

  security_only        -> only the security lesson. No structure, ever.
  review_only          -> quarantined: the fact that it needs review, nothing
                          about how it is built.
  structure_only       -> shape and integrations, explicitly restricted.
  structure_and_metadata -> shape and integrations as a reference pattern.

There is no path that widens this, and no path that skips the Analyzer. The
Compiler is the component that marks embedded code as untrusted and refuses to
persist it; reading the JSON directly would throw that away.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vorquel_n8n_analyzer import analyze_file
from vorquel_n8n_knowledge_compiler import compile_knowledge_item

from ..extract import RawUnit, to_batch
from ..model import LearnBatch, LearnError, SourceRef
from ..scope_util import resolve_scope

# Roles that may contribute anything about how the workflow is built.
_STRUCTURAL_SCOPES = frozenset({"structure_only", "structure_and_metadata"})


def _structure_units(compiled: dict[str, Any], role: str) -> list[RawUnit]:
    workflow = compiled["workflow"]
    integrations = ", ".join(workflow["integrations"]) or "(nenhuma)"
    triggers = ", ".join(workflow["trigger_types"]) or "(nenhum)"

    units = [
        RawUnit(
            title=f"Estrutura: {workflow['node_count']} nos, disparo por {triggers}",
            text=(
                f"O workflow tem {workflow['node_count']} nos. "
                f"Disparos: {triggers}. Integracoes: {integrations}. "
                f"Papel de admissao: {role}. "
                "Estrutura observada estaticamente; nada foi executado."
            ),
            locator_kind="WORKFLOW_NODE",
            locator={"scope": "workflow"},
            knowledge_type="PATTERN" if role == "REFERENCE_PATTERN" else "EXAMPLE",
            # Read from the file, not run. We saw the shape; we measured nothing.
            epistemic_status="OBSERVADO",
        )
    ]

    for node in workflow["nodes"]:
        node_type = node["type"]
        units.append(
            RawUnit(
                title=f"No {node_type}",
                text=(
                    f"O workflow usa o no {node_type}. "
                    f"Rotulo declarado pela fonte (nao confiavel): "
                    f"{node.get('name_untrusted', '')!r}. "
                    "Parametros nao sao reproduzidos: podem conter conteudo executavel."
                ),
                locator_kind="WORKFLOW_NODE",
                locator={"node": str(node.get("name_untrusted", ""))[:120], "type": node_type},
                knowledge_type="EXAMPLE",
                epistemic_status="OBSERVADO",
            )
        )
    return units


def _security_units(compiled: dict[str, Any]) -> list[RawUnit]:
    units: list[RawUnit] = []
    admission = compiled["admission"]
    for finding in compiled.get("security_findings", []):
        rule = finding.get("rule", "desconhecida")
        units.append(
            RawUnit(
                title=f"Risco em workflow n8n: {rule}",
                text=(
                    f"A analise estatica encontrou {rule} "
                    f"(severidade {finding.get('severity', 'DESCONHECIDA')}). "
                    f"Decisao de risco: {admission['risk_decision']}. "
                    "Este workflow serve como exemplo do que evitar, nunca como "
                    "referencia de implementacao."
                ),
                locator_kind="WORKFLOW_NODE",
                locator={"rule": str(rule)[:120]},
                knowledge_type="ANTI_PATTERN",
                epistemic_status="OBSERVADO",
            )
        )

    if not units:
        units.append(
            RawUnit(
                title="Workflow n8n bloqueado pela politica de admissao",
                text=(
                    f"Decisao de risco {admission['risk_decision']} com severidade "
                    f"{admission['max_severity']}. O conteudo nao pode ser usado como "
                    "referencia de estrutura nem de implementacao."
                ),
                locator_kind="WORKFLOW_NODE",
                locator={"scope": "admission"},
                knowledge_type="WARNING",
                epistemic_status="OBSERVADO",
            )
        )
    return units


def learn_n8n_workflow(
    path: str | Path,
    scope: str,
    data_classification: str = "INTERNAL",
    source_repo: str = "operator-supplied",
    source_commit: str = "0" * 40,
) -> LearnBatch:
    file_path = Path(path)
    report = analyze_file(file_path)
    analysis = report.to_dict()

    if report.parse_error:
        raise LearnError(f"workflow ilegivel: {report.parse_error}")

    workflow = json.loads(file_path.read_text(encoding="utf-8"))
    compiled = compile_knowledge_item(
        workflow,
        analysis,
        source_repo=source_repo,
        source_commit=source_commit,
        source_path=file_path.name,
        source_sha256=report.sha256,
    )

    admission = compiled["admission"]
    learning_scope = admission["learning_scope"]

    source = SourceRef(
        source_kind="N8N_WORKFLOW",
        content_sha256=report.sha256,
        byte_size=file_path.stat().st_size,
        detected_mime="application/json",
        scope=resolve_scope(scope),
        data_classification=data_classification,
        logical_key=f"n8n-workflow:{file_path.name}",
        external_metadata={
            "admission": admission,
            "analyzer_risk_decision": report.risk_decision,
            "analyzer_max_severity": report.max_severity,
        },
    )

    if learning_scope in _STRUCTURAL_SCOPES:
        units = _structure_units(compiled, admission["knowledge_role"])
    else:
        # security_only and review_only: the lesson is the risk, not the shape.
        units = _security_units(compiled)

    return to_batch(source, units, data_classification)
