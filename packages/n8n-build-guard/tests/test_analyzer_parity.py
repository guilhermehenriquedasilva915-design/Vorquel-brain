"""Guard against drift between this package's node sets and the Analyzer's.

:mod:`vorquel_n8n_build_guard.node_risk` duplicates the dangerous-node sets from
:mod:`vorquel_n8n_analyzer.rules` so that the execution guard does not depend on
the learning-side analyzer. The cost of that choice is drift: someone adds a node
type to one set and the other silently keeps waving it through.

These tests close that gap. They skip when the analyzer is not installed, so the
package stays independently testable — and CI installs both, so in CI they run.
"""

from __future__ import annotations

import pytest

from vorquel_n8n_build_guard import node_risk

rules = pytest.importorskip(
    "vorquel_n8n_analyzer.rules",
    reason="analyzer not installed alongside the build guard",
)


@pytest.mark.parametrize(
    ("guard_set", "analyzer_set"),
    [
        ("COMMAND_TYPES", "DANGEROUS_COMMAND_TYPES"),
        ("SSH_TYPES", "SSH_TYPES"),
        ("FILE_TYPES", "FILE_TYPES"),
        ("CODE_TYPES", "CODE_TYPES"),
    ],
)
def test_dangerous_node_sets_match_the_analyzer(guard_set, analyzer_set):
    assert set(getattr(node_risk, guard_set)) == set(getattr(rules, analyzer_set)), (
        f"{guard_set} has drifted from vorquel_n8n_analyzer.rules.{analyzer_set}; "
        "update both or the two components disagree about what is dangerous"
    )


def test_the_guard_covers_every_http_type_the_analyzer_knows():
    # The guard deliberately treats more types as network-reaching than the
    # analyzer does (it adds webhook), so this is containment, not equality.
    assert set(rules.HTTP_TYPES) <= set(node_risk.HTTP_TYPES)
