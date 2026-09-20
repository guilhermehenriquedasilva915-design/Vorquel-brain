"""Client isolation. The rule the rest of the Brain is not allowed to break."""

from __future__ import annotations

import pytest
from conftest import FakeConn

from vorquel_n8n_brain_retrieval.retrieval import retrieve_n8n_context
from vorquel_n8n_brain_retrieval.scope import Scope, ScopeError

SCOPED_COLUMNS = {
    ("vorquel_knowledge", "knowledge_items", "scope_type"),
    ("vorquel_knowledge", "knowledge_sources", "locator_kind"),
}


def _knowledge_row(**over):
    row = {
        "knowledge_id": "knw_x",
        "knowledge_type": "PROCEDURE",
        "domain": "n8n",
        "title": "titulo",
        "summary": "resumo",
        "epistemic_status": "OBSERVADO",
        "scope_type": "GLOBAL_VORQUEL",
        "scope_id": "GLOBAL",
        "data_classification": "INTERNAL",
        "compatibility_status": "UNKNOWN_COMPATIBILITY",
        "observed_n8n_version": None,
        "node_type": None,
        "node_version": None,
        "last_verified_at": None,
        "approved_at": None,
        "instruction_authority": "NONE",
        "rank": 0.5,
    }
    row.update(over)
    return row


class TestScopeValue:
    def test_global_requires_reserved_id(self):
        with pytest.raises(ScopeError):
            Scope("GLOBAL_VORQUEL", "acme")

    def test_reserved_id_cannot_be_borrowed_by_a_client(self):
        with pytest.raises(ScopeError):
            Scope("CLIENT", "GLOBAL")

    def test_unknown_scope_type_rejected(self):
        with pytest.raises(ScopeError):
            Scope("EVERYONE", "x")

    @pytest.mark.parametrize("bad", ["", "-acme", "a" * 65, "acme/../other", "acme;drop"])
    def test_malformed_scope_id_rejected(self, bad):
        with pytest.raises(ScopeError):
            Scope("CLIENT", bad)

    def test_parse_roundtrip(self):
        assert str(Scope.parse("CLIENT:acme")) == "CLIENT:acme"
        assert str(Scope.parse("GLOBAL_VORQUEL")) == "GLOBAL_VORQUEL"


class TestAdmits:
    def test_client_sees_own_and_global(self):
        scope = Scope("CLIENT", "acme")
        assert scope.admits("CLIENT", "acme")
        assert scope.admits("GLOBAL_VORQUEL", "GLOBAL")

    def test_client_a_never_sees_client_b(self):
        assert not Scope("CLIENT", "acme").admits("CLIENT", "globex")

    def test_client_never_sees_project_or_private_test(self):
        scope = Scope("CLIENT", "acme")
        assert not scope.admits("PROJECT", "acme")
        assert not scope.admits("PRIVATE_TEST", "acme")

    def test_global_caller_sees_only_global(self):
        scope = Scope.global_vorquel()
        assert scope.admits("GLOBAL_VORQUEL", "GLOBAL")
        assert not scope.admits("CLIENT", "acme")


class TestRetrievalIsolation:
    def test_foreign_client_row_is_dropped_even_if_the_query_returns_it(self):
        """The post-query check is the one that survives a bad query."""
        conn = FakeConn(
            columns=SCOPED_COLUMNS,
            knowledge_rows=[
                _knowledge_row(knowledge_id="knw_leak", scope_type="CLIENT", scope_id="globex"),
                _knowledge_row(knowledge_id="knw_mine", scope_type="CLIENT", scope_id="acme"),
            ],
        )
        pack = retrieve_n8n_context(
            conn, "qualquer", task_type="ASK", scope=Scope("CLIENT", "acme")
        )
        ids = {i.item_id for i in pack.items}
        assert ids == {"knw_mine"}
        assert any("escopo" in d for d in pack.degraded)

    def test_unscoped_store_blocks_client_retrieval(self):
        """Without migration 0021 nothing proves a row belongs to this client,
        so a client-scoped read must return nothing rather than guess."""
        conn = FakeConn(columns=set(), knowledge_rows=[_knowledge_row()])
        pack = retrieve_n8n_context(
            conn, "qualquer", task_type="ASK", scope=Scope("CLIENT", "acme")
        )
        assert pack.items == []
        assert any("0021" in d for d in pack.degraded)

    def test_unscoped_store_still_serves_global(self):
        conn = FakeConn(columns=set(), knowledge_rows=[_knowledge_row()])
        pack = retrieve_n8n_context(conn, "qualquer", task_type="ASK")
        assert [i.item_id for i in pack.items] == ["knw_x"]
        assert any("GLOBAL_VORQUEL" in d for d in pack.degraded)
