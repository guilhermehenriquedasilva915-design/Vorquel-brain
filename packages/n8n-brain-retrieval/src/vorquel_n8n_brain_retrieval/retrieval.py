"""Unified, scope-enforced retrieval.

One entry point, `retrieve_n8n_context`, combines:

  1. approved semantic knowledge   (vorquel_knowledge)
  2. n8n structural references     (n8n_brain)
  3. measured operational experience
  4. current n8n environment facts
  5. conflicts and gaps

FTS first. No embeddings: nothing has yet measured that they are needed, and
adding a vector store before that evidence exists is infrastructure, not
capability.
"""

from __future__ import annotations

from typing import Any

from .contextpack import Authority, Conflict, ContextItem, ContextPack, Provenance
from .db import DatabaseUnavailable, column_exists, fetch_all, function_exists
from .scope import Scope

TASK_TYPES = ("LEARN", "ASK", "BUILD", "DEBUG", "EVOLVE")

# Per-store caps keep a pack readable. A pack that does not fit in a head is not
# a pack, it is a dump.
DEFAULT_LIMIT = 12


def _authority_for_knowledge(row: dict[str, Any]) -> Authority:
    """Map a stored knowledge row onto an operational authority class.

    Everything in vorquel_knowledge is human-approved, so the question is not
    "is it trusted" but "what kind of evidence is it".
    """
    epistemic = (row.get("epistemic_status") or "").upper()
    ktype = (row.get("knowledge_type") or "").upper()

    if epistemic == "MEDIDO":
        # Measured on our own runs. The strongest thing knowledge can be.
        return Authority.MEASURED_OWN_EXECUTION
    if ktype in ("PATTERN", "CHECKLIST") and epistemic in ("OBSERVADO", "MEDIDO"):
        return Authority.VORQUEL_VALIDATED_PATTERN
    if ktype in ("FIX", "ANTI_PATTERN", "WARNING"):
        return Authority.HUMAN_APPROVED_CORRECTION
    if epistemic == "DECLARADO":
        return Authority.TUTORIAL
    if epistemic in ("INFERIDO", "HIPOTESE", "ESTIMADO"):
        return Authority.MODEL_INFERENCE
    return Authority.COMMUNITY


def _knowledge_row_to_item(row: dict[str, Any], provenance: list[Provenance]) -> ContextItem:
    return ContextItem(
        item_id=row["knowledge_id"],
        store="vorquel_knowledge",
        title=row.get("title") or "(sem titulo)",
        summary=row.get("summary") or "",
        scope_type=row.get("scope_type") or "GLOBAL_VORQUEL",
        scope_id=row.get("scope_id") or "GLOBAL",
        epistemic_status=row.get("epistemic_status") or "DESCONHECIDO",
        authority=_authority_for_knowledge(row),
        relevance=float(row.get("rank") or 0.0),
        data_classification=row.get("data_classification") or "INTERNAL",
        compatibility_status=row.get("compatibility_status") or "UNKNOWN_COMPATIBILITY",
        observed_n8n_version=row.get("observed_n8n_version"),
        node_type=row.get("node_type"),
        node_version=row.get("node_version"),
        last_verified_at=str(row["last_verified_at"]) if row.get("last_verified_at") else None,
        instruction_authority=row.get("instruction_authority") or "NONE",
        provenance=provenance,
    )


def _load_provenance(
    conn: Any, knowledge_ids: list[str], has_locator: bool
) -> dict[str, list[Provenance]]:
    if not knowledge_ids:
        return {}
    if has_locator:
        sql = """
            select knowledge_id, source_id, locator_kind, locator
            from vorquel_knowledge.knowledge_sources
            where knowledge_id = any(%s)
        """
    else:
        sql = """
            select knowledge_id, source_id,
                   'MEDIA_TIME' as locator_kind,
                   jsonb_strip_nulls(jsonb_build_object(
                     'transcript_id', transcript_id,
                     'segment_id', segment_id,
                     'start_ms', start_ms,
                     'end_ms', end_ms)) as locator
            from vorquel_knowledge.knowledge_sources
            where knowledge_id = any(%s)
        """
    out: dict[str, list[Provenance]] = {}
    for row in fetch_all(conn, sql, (knowledge_ids,)):
        out.setdefault(row["knowledge_id"], []).append(
            Provenance(
                source_id=row.get("source_id"),
                locator_kind=row.get("locator_kind") or "GENERIC",
                locator=row.get("locator") or {},
            )
        )
    return out


def _fetch_knowledge(
    conn: Any, query: str, scope: Scope, limit: int, pack: ContextPack
) -> list[ContextItem]:
    scoped = column_exists(conn, "vorquel_knowledge", "knowledge_items", "scope_type")

    if not scoped:
        # Migration 0021 has not been applied. Every stored row is effectively
        # unscoped, so we cannot prove a row belongs to the caller's client.
        # Global reads stay correct; anything narrower fails closed.
        if not scope.is_global():
            pack.degraded.append(
                "colunas de scope ausentes (migration 0021 nao aplicada): "
                f"retrieval para {scope} bloqueado para evitar vazamento entre clientes"
            )
            return []
        pack.degraded.append(
            "colunas de scope ausentes (migration 0021 nao aplicada): "
            "tratando todo o store como GLOBAL_VORQUEL"
        )

    has_locator = column_exists(conn, "vorquel_knowledge", "knowledge_sources", "locator_kind")

    if scoped and function_exists(conn, "public", "search_knowledge_items_scoped"):
        rows = fetch_all(
            conn,
            "select * from public.search_knowledge_items_scoped(%s, %s, %s, null, %s)",
            (query, scope.scope_type, scope.scope_id, limit),
        )
    else:
        # Direct scoped read. Same isolation predicate as the RPC, used when the
        # RPC is not deployed yet.
        scope_predicate = (
            "and (ki.scope_type = 'GLOBAL_VORQUEL' "
            "or (ki.scope_type = %(stype)s and ki.scope_id = %(sid)s))"
            if scoped
            else ""
        )
        extra_cols = (
            "ki.scope_type, ki.scope_id, ki.data_classification, ki.compatibility_status, "
            "ki.observed_n8n_version, ki.node_type, ki.node_version, ki.last_verified_at,"
            if scoped
            else (
                "'GLOBAL_VORQUEL'::text as scope_type, 'GLOBAL'::text as scope_id, "
                "'INTERNAL'::text as data_classification, "
                "'UNKNOWN_COMPATIBILITY'::text as compatibility_status, "
                "null::text as observed_n8n_version, null::text as node_type, "
                "null::text as node_version, null::timestamptz as last_verified_at,"
            )
        )
        sql = f"""
            select ki.knowledge_id, ki.knowledge_type, ki.domain, ki.title, ki.summary,
                   ki.epistemic_status, {extra_cols}
                   ki.approved_at, ki.instruction_authority,
                   case when %(q)s is null or btrim(%(q)s) = '' then 0::real
                        else ts_rank(ki.search_vector, websearch_to_tsquery('simple', %(q)s))
                   end as rank
            from vorquel_knowledge.knowledge_items ki
            where ki.lifecycle_state = 'ACTIVE'
              and (ki.valid_until is null or ki.valid_until > now())
              {scope_predicate}
              and (%(q)s is null or btrim(%(q)s) = ''
                   or ki.search_vector @@ websearch_to_tsquery('simple', %(q)s))
            order by rank desc, ki.approved_at desc nulls last, ki.knowledge_id
            limit %(lim)s
        """
        with conn.cursor() as cur:
            cur.execute(
                sql,
                {"q": query, "stype": scope.scope_type, "sid": scope.scope_id, "lim": limit},
            )
            if cur.description is None:
                rows = []
            else:
                cols = [d[0] for d in cur.description]
                rows = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]

    # Belt and braces: re-check isolation on every row we are about to return,
    # whatever produced it.
    safe_rows = [
        r
        for r in rows
        if scope.admits(r.get("scope_type") or "GLOBAL_VORQUEL", r.get("scope_id") or "GLOBAL")
    ]
    dropped = len(rows) - len(safe_rows)
    if dropped:
        pack.degraded.append(
            f"{dropped} linha(s) descartada(s) por falharem a checagem de escopo pos-query"
        )

    provenance = _load_provenance(conn, [r["knowledge_id"] for r in safe_rows], has_locator)
    return [_knowledge_row_to_item(r, provenance.get(r["knowledge_id"], [])) for r in safe_rows]


def _fetch_n8n_structure(conn: Any, query: str, limit: int, pack: ContextPack) -> list[ContextItem]:
    """Structural references compiled from analyzed external workflows.

    These are topology, node types and risk findings — never a recommendation.
    """
    rows = fetch_all(
        conn,
        """
        select ki.id::text as id,
               ki.knowledge_role,
               ki.learning_scope,
               ki.structure,
               ki.implementation_reference_allowed,
               ki.vorquel_validated,
               wa.risk_decision,
               wa.max_severity,
               ss.source_repo, ss.source_commit, ss.source_path
        from n8n_brain.knowledge_items ki
        join n8n_brain.workflow_analyses wa on wa.id = ki.analysis_id
        join n8n_brain.source_snapshots ss on ss.id = wa.source_id
        where ki.implementation_reference_allowed
        order by ki.compiled_at desc
        limit %s
        """,
        (limit,),
    )
    if not rows:
        pack.gaps.append(
            "n8n_brain nao tem referencia estrutural utilizavel "
            "(nenhuma ingestao controlada persistida neste banco)"
        )
        return []

    items: list[ContextItem] = []
    for row in rows:
        structure = row.get("structure") or {}
        node_types = structure.get("node_types") or []
        title = f"Referencia estrutural: {row.get('source_path') or row['id']}"
        summary = (
            f"role={row.get('knowledge_role')} scope={row.get('learning_scope')} "
            f"risk={row.get('risk_decision')}/{row.get('max_severity')} "
            f"nodes={', '.join(map(str, node_types[:8]))}"
        )
        items.append(
            ContextItem(
                item_id=row["id"],
                store="n8n_brain",
                title=title,
                summary=summary,
                scope_type="GLOBAL_VORQUEL",
                scope_id="GLOBAL",
                epistemic_status="OBSERVADO",
                authority=Authority.EXTERNAL_WORKFLOW_ANALYZED,
                relevance=0.0,
                instruction_authority="NONE",
                provenance=[
                    Provenance(
                        source_id=row.get("source_repo"),
                        locator_kind="REPO_FILE",
                        locator={
                            k: v
                            for k, v in {
                                "path": row.get("source_path"),
                                "commit": row.get("source_commit"),
                            }.items()
                            if v
                        },
                    )
                ],
            )
        )
    return items


def _fetch_experiences(
    conn: Any, query: str, scope: Scope, environment: str, limit: int, pack: ContextPack
) -> list[ContextItem]:
    """Our own measured runs. Highest-authority knowledge after the live
    environment itself."""
    if not column_exists(conn, "n8n_brain", "operational_experiences", "experience_id"):
        pack.gaps.append(
            "n8n_brain.operational_experiences ausente: nenhuma experiencia medida "
            "para reutilizar (aplique a migration 20260920_004)"
        )
        return []

    rows = fetch_all(
        conn,
        """
        select experience_id, scope_type, scope_id, environment, node, category,
               observed_error, hypothesis, change_summary, result_before, result_after,
               n8n_version, epistemic_status, workflow_id, created_at
        from n8n_brain.operational_experiences
        where (scope_type = 'GLOBAL_VORQUEL'
               or (scope_type = %s and scope_id = %s))
          and (%s is null or btrim(%s) = ''
               or search_vector @@ websearch_to_tsquery('simple', %s))
        order by (environment = %s) desc, created_at desc
        limit %s
        """,
        (scope.scope_type, scope.scope_id, query, query, query, environment, limit),
    )

    items: list[ContextItem] = []
    for row in rows:
        if not scope.admits(row["scope_type"], row["scope_id"]):
            continue
        measured = (row.get("epistemic_status") or "").upper() == "MEDIDO"
        items.append(
            ContextItem(
                item_id=row["experience_id"],
                store="experience",
                title=f"[{row.get('category')}] {(row.get('observed_error') or '')[:120]}",
                summary=(
                    f"hipotese: {row.get('hypothesis') or '-'} | "
                    f"mudanca: {row.get('change_summary') or '-'} | "
                    f"antes: {row.get('result_before') or '-'} -> "
                    f"depois: {row.get('result_after') or '-'}"
                ),
                scope_type=row["scope_type"],
                scope_id=row["scope_id"],
                epistemic_status=row.get("epistemic_status") or "OBSERVADO",
                authority=(
                    Authority.MEASURED_OWN_EXECUTION if measured else Authority.MODEL_INFERENCE
                ),
                relevance=1.0 if row.get("environment") == environment else 0.5,
                observed_n8n_version=row.get("n8n_version"),
                node_type=row.get("node"),
                instruction_authority="NONE",
                provenance=[
                    Provenance(
                        source_id=row.get("workflow_id"),
                        locator_kind="N8N_EXECUTION",
                        locator={"experience_id": row["experience_id"]},
                    )
                ],
            )
        )
    return items


def _detect_conflicts(items: list[ContextItem]) -> list[Conflict]:
    conflicts: list[Conflict] = []

    for item in items:
        if item.epistemic_status.upper() == "CONFLITANTE":
            conflicts.append(
                Conflict(
                    reason="item marcado CONFLITANTE na revisao humana",
                    item_ids=[item.item_id],
                )
            )

    # Same node discussed against different n8n versions: not necessarily wrong,
    # but the reader must not treat them as one fact.
    by_node: dict[str, list[ContextItem]] = {}
    for item in items:
        if item.node_type and item.observed_n8n_version:
            by_node.setdefault(item.node_type, []).append(item)
    for node, group in by_node.items():
        versions = {i.observed_n8n_version for i in group}
        if len(versions) > 1:
            conflicts.append(
                Conflict(
                    reason="mesmo node observado em versoes n8n diferentes",
                    item_ids=[i.item_id for i in group],
                    detail=f"node={node} versoes={sorted(v for v in versions if v)}",
                )
            )

    # A deprecated item sitting beside a current one on the same node.
    for node, group in by_node.items():
        statuses = {i.compatibility_status for i in group}
        if "DEPRECATED" in statuses and statuses - {"DEPRECATED"}:
            conflicts.append(
                Conflict(
                    reason="node com conhecimento DEPRECATED e nao-DEPRECATED simultaneos",
                    item_ids=[i.item_id for i in group],
                    detail=f"node={node}",
                )
            )
    return conflicts


def retrieve_n8n_context(
    conn: Any,
    query: str,
    task_type: str = "ASK",
    scope: Scope | None = None,
    environment: str = "DEV",
    limit: int = DEFAULT_LIMIT,
) -> ContextPack:
    """Build a CONTEXT PACK for one task.

    `conn` is a read-only connection. The caller owns it so a single request can
    reuse one session across stores.
    """
    scope = scope or Scope.global_vorquel()
    task_type = task_type.upper()
    if task_type not in TASK_TYPES:
        raise ValueError(f"task_type desconhecido: {task_type!r}")

    pack = ContextPack(
        query=query,
        task_type=task_type,
        scope_str=str(scope),
        environment=environment,
    )

    pack.items.extend(_fetch_knowledge(conn, query, scope, limit, pack))

    if task_type in ("BUILD", "DEBUG", "ASK"):
        try:
            pack.items.extend(_fetch_n8n_structure(conn, query, limit, pack))
        except Exception as exc:  # store may not exist in every deployment
            pack.degraded.append(f"n8n_brain indisponivel: {type(exc).__name__}")
        try:
            pack.items.extend(
                _fetch_experiences(conn, query, scope, environment, limit, pack)
            )
        except Exception as exc:
            pack.degraded.append(f"operational_experiences indisponivel: {type(exc).__name__}")

    # The live environment outranks everything, so its absence is a gap worth
    # stating rather than a silent omission.
    if task_type in ("BUILD", "DEBUG"):
        pack.gaps.append(
            "N8N_ENVIRONMENT_PROFILE ausente: nenhuma instancia n8n registrada. "
            "Autoridade 1 (fato do ambiente) nao pode ser consultada."
        )

    if not pack.items:
        pack.gaps.append(f"nenhum item recuperado para {query!r} em {scope}")

    pack.conflicts.extend(_detect_conflicts(pack.items))
    return pack


__all__ = [
    "Authority",
    "ContextPack",
    "DatabaseUnavailable",
    "Scope",
    "retrieve_n8n_context",
]
