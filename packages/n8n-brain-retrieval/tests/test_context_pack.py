"""Authority ordering, conflict surfacing and citation shape."""

from __future__ import annotations

from conftest import FakeConn
from test_scope_isolation import SCOPED_COLUMNS, _knowledge_row

from vorquel_n8n_brain_retrieval.contextpack import (
    Authority,
    ContextItem,
    ContextPack,
    Provenance,
)
from vorquel_n8n_brain_retrieval.retrieval import _authority_for_knowledge, retrieve_n8n_context
from vorquel_n8n_brain_retrieval.scope import Scope


def _item(item_id: str, authority: Authority, **over) -> ContextItem:
    base = {
        "item_id": item_id,
        "store": "vorquel_knowledge",
        "title": item_id,
        "summary": "s",
        "scope_type": "GLOBAL_VORQUEL",
        "scope_id": "GLOBAL",
        "epistemic_status": "OBSERVADO",
        "authority": authority,
        "relevance": 0.5,
    }
    base.update(over)
    return ContextItem(**base)


class TestAuthorityMapping:
    def test_measured_beats_everything_a_stored_item_can_be(self):
        assert (
            _authority_for_knowledge({"epistemic_status": "MEDIDO", "knowledge_type": "CLAIM"})
            is Authority.MEASURED_OWN_EXECUTION
        )

    def test_observed_pattern_is_a_validated_pattern(self):
        assert (
            _authority_for_knowledge(
                {"epistemic_status": "OBSERVADO", "knowledge_type": "PATTERN"}
            )
            is Authority.VORQUEL_VALIDATED_PATTERN
        )

    def test_fix_is_a_human_approved_correction(self):
        assert (
            _authority_for_knowledge({"epistemic_status": "OBSERVADO", "knowledge_type": "FIX"})
            is Authority.HUMAN_APPROVED_CORRECTION
        )

    def test_inference_ranks_last(self):
        assert (
            _authority_for_knowledge({"epistemic_status": "HIPOTESE", "knowledge_type": "CLAIM"})
            is Authority.MODEL_INFERENCE
        )

    def test_environment_fact_outranks_official_docs(self):
        assert Authority.N8N_ENVIRONMENT_FACT < Authority.OFFICIAL_DOCS


class TestOrdering:
    def test_pack_orders_by_authority_then_relevance(self):
        pack = ContextPack(
            query="q", task_type="ASK", scope_str="GLOBAL_VORQUEL", environment="DEV"
        )
        pack.items = [
            _item("low", Authority.COMMUNITY, relevance=0.9),
            _item("high", Authority.MEASURED_OWN_EXECUTION, relevance=0.1),
            _item("mid", Authority.OFFICIAL_DOCS, relevance=0.5),
        ]
        assert [i.item_id for i in pack.ordered()] == ["high", "mid", "low"]


class TestConflicts:
    def test_conflicting_item_is_surfaced_not_hidden(self):
        conn = FakeConn(
            columns=SCOPED_COLUMNS,
            knowledge_rows=[_knowledge_row(knowledge_id="knw_c", epistemic_status="CONFLITANTE")],
        )
        pack = retrieve_n8n_context(conn, "q", task_type="ASK")
        assert any("CONFLITANTE" in c.reason for c in pack.conflicts)

    def test_same_node_on_two_n8n_versions_is_a_conflict(self):
        conn = FakeConn(
            columns=SCOPED_COLUMNS,
            knowledge_rows=[
                _knowledge_row(
                    knowledge_id="knw_a", node_type="n8n-nodes-base.httpRequest",
                    observed_n8n_version="1.40.0",
                ),
                _knowledge_row(
                    knowledge_id="knw_b", node_type="n8n-nodes-base.httpRequest",
                    observed_n8n_version="1.62.0",
                ),
            ],
        )
        pack = retrieve_n8n_context(conn, "q", task_type="ASK")
        reasons = [c.reason for c in pack.conflicts]
        assert any("versoes n8n diferentes" in r for r in reasons)

    def test_deprecated_beside_current_is_a_conflict(self):
        conn = FakeConn(
            columns=SCOPED_COLUMNS,
            knowledge_rows=[
                _knowledge_row(
                    knowledge_id="knw_old", node_type="x",
                    observed_n8n_version="1.0.0", compatibility_status="DEPRECATED",
                ),
                _knowledge_row(
                    knowledge_id="knw_new", node_type="x",
                    observed_n8n_version="1.0.0", compatibility_status="CURRENT",
                ),
            ],
        )
        pack = retrieve_n8n_context(conn, "q", task_type="ASK")
        assert any("DEPRECATED" in c.reason for c in pack.conflicts)


class TestGapsAndAuthorityBoundary:
    def test_build_states_the_missing_environment_instead_of_omitting_it(self):
        conn = FakeConn(columns=SCOPED_COLUMNS, knowledge_rows=[_knowledge_row()])
        pack = retrieve_n8n_context(conn, "q", task_type="BUILD")
        assert any("N8N_ENVIRONMENT_PROFILE" in g for g in pack.gaps)

    def test_empty_result_is_reported_as_a_gap(self):
        conn = FakeConn(columns=SCOPED_COLUMNS, knowledge_rows=[])
        pack = retrieve_n8n_context(conn, "nada", task_type="ASK")
        assert any("nenhum item recuperado" in g for g in pack.gaps)

    def test_pack_never_claims_instruction_authority(self):
        conn = FakeConn(columns=SCOPED_COLUMNS, knowledge_rows=[_knowledge_row()])
        pack = retrieve_n8n_context(conn, "q", task_type="ASK")
        assert pack.instruction_authority == "NONE"
        assert all(i.instruction_authority == "NONE" for i in pack.items)
        assert "instruction_authority: NONE" in pack.render()


class TestCitations:
    def test_locator_is_rendered_as_an_address(self):
        item = _item(
            "knw_1",
            Authority.OFFICIAL_DOCS,
            provenance=[Provenance("src_pdf_1", "PDF_PAGE", {"page": 12})],
        )
        assert item.citations() == "src_pdf_1 [PDF_PAGE page=12]"

    def test_item_without_provenance_says_so(self):
        assert _item("knw_2", Authority.COMMUNITY).citations() == "(sem provenance)"

    def test_provenance_reaches_retrieved_items(self):
        conn = FakeConn(
            columns=SCOPED_COLUMNS,
            knowledge_rows=[_knowledge_row(knowledge_id="knw_p")],
            provenance_rows=[
                {
                    "knowledge_id": "knw_p",
                    "source_id": "src_repo_1",
                    "locator_kind": "REPO_FILE",
                    "locator": {"path": "workflows/a.json"},
                }
            ],
        )
        pack = retrieve_n8n_context(conn, "q", task_type="ASK", scope=Scope.global_vorquel())
        assert pack.items[0].citations() == "src_repo_1 [REPO_FILE path=workflows/a.json]"
