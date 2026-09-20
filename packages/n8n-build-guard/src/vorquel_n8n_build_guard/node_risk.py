"""Side-effect classification of n8n nodes, for the SAFE TEST gate.

``test_workflow`` is not a sandbox. Verbatim from its own schema, pin data
suppresses trigger nodes, nodes with credentials and HTTP Request nodes, while
*"other nodes (Set, If, Code, etc.) execute normally — including credential-free
I/O nodes like Execute Command or file read/write nodes."*

Two different questions follow from that sentence, and conflating them produces a
gate that looks strict and checks nothing:

**What is the worst thing this node can do to the host?** That is
:attr:`NodeRisk.verdict`, and it is decided without reference to pin data,
because pin data does not cover these nodes at all:

``BLOCKED``
    Arbitrary command execution, remote shell, or filesystem I/O. Refused.
``REVIEW_REQUIRED``
    Runs code we did not classify, or ships from outside the first-party node
    set, so its side effects are unknown. Unknown is not the same as safe.
``ALLOWED``
    A first-party node whose worst case is data shuffling inside the execution.

**Would executing this node for real reach outside the execution?** That is
:attr:`NodeRisk.requires_pinning`, and it is a *separate* axis. An HTTP Request
node is ``ALLOWED`` — it cannot touch the host — yet running it unpinned calls a
third party for real. Pin data normally covers it; the gate's job is to confirm
that it actually did, rather than to assume the category held.

Keeping the axes apart is what makes precondition 7 do real work. If
``requires_pinning`` only ever marked nodes that were already ``BLOCKED`` or
``REVIEW_REQUIRED``, precondition 4 would reject them first and precondition 7
would be unreachable.

The node-type sets below are deliberately *duplicated* from
:mod:`vorquel_n8n_analyzer.rules` rather than imported: this package guards an
execution and must not gain a dependency on the learning-side analyzer to do it.
Duplication invites drift, so ``test_analyzer_parity.py`` asserts the two stay
identical whenever the analyzer is installed alongside this package, and CI
installs both so that assertion actually runs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

BLOCKED = "BLOCKED"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
ALLOWED = "ALLOWED"

#: Least dangerous first. Used to fold a workflow's nodes into one decision.
VERDICT_ORDER = {ALLOWED: 0, REVIEW_REQUIRED: 1, BLOCKED: 2}

#: Arbitrary command execution on the n8n host.
COMMAND_TYPES = frozenset({"n8n-nodes-base.executeCommand"})

#: Remote shell. Reaches a machine we are not even testing.
SSH_TYPES = frozenset({"n8n-nodes-base.ssh"})

#: Filesystem read or write on the n8n host. Blocked by default: a SAFE TEST
#: that writes to disk has already stopped being a test.
FILE_TYPES = frozenset(
    {
        "n8n-nodes-base.readWriteFile",
        "n8n-nodes-base.readBinaryFile",
        "n8n-nodes-base.writeBinaryFile",
        "n8n-nodes-base.localFileTrigger",
    }
)

#: Runs user JavaScript/Python in-process. Not blocked outright — a Code node is
#: the normal way to shape data — but never waved through either.
CODE_TYPES = frozenset(
    {
        "n8n-nodes-base.code",
        "n8n-nodes-base.function",
        "n8n-nodes-base.functionItem",
    }
)

#: Reaches the network. Harmless to the host, never harmless to a third party.
HTTP_TYPES = frozenset({"n8n-nodes-base.httpRequest", "n8n-nodes-base.webhook"})

#: Prefixes that ship with n8n itself. Anything else is community or custom
#: code whose side effects were never reviewed here.
FIRST_PARTY_PREFIXES = ("n8n-nodes-base.", "@n8n/n8n-nodes-langchain.", "n8n-nodes-langchain.")


@dataclass(frozen=True)
class NodeRisk:
    """One node on two independent axes: host danger, and reach outside.

    ``verdict`` is judged at precondition 4 and concerns the host.
    ``requires_pinning`` is judged at precondition 7 and concerns everything
    beyond this execution.
    """

    node_name: str
    node_type: str
    verdict: str
    reason: str

    #: True when executing this node for real would reach outside the execution
    #: — the network, a third party, or a live trigger — so the gate has to prove
    #: pin data actually covered it.
    requires_pinning: bool
    pinning_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _is_trigger(node_type: str) -> bool:
    """True for a node that fires on its own rather than when called.

    ``webhook`` is a trigger too, but it is already caught by
    :data:`HTTP_TYPES` before this is reached, so it is not repeated here.
    """
    return node_type.endswith(("Trigger", "trigger"))


def _pinning_requirement(node_type: str, node: dict[str, Any]) -> str | None:
    """Why this node must be pinned, or ``None`` if it need not be.

    Mirrors the three categories the schema says pin data covers, so that the
    gate checks the same set the server claims to handle.
    """
    if node_type in HTTP_TYPES:
        return "reaches the network — would call a third party for real"
    credentials = node.get("credentials")
    if isinstance(credentials, dict) and credentials:
        return "carries a credential — would authenticate to a third party for real"
    if _is_trigger(node_type):
        return "is a trigger — would arm or fire against a live source"
    return None


def classify_node(node: dict[str, Any]) -> NodeRisk:
    """Classify one node dict as it appears in a workflow definition."""
    name = str(node.get("name") or "<unnamed>")
    node_type = str(node.get("type") or "<untyped>")
    pinning_reason = _pinning_requirement(node_type, node)

    def risk(verdict: str, reason: str) -> NodeRisk:
        return NodeRisk(
            node_name=name,
            node_type=node_type,
            verdict=verdict,
            reason=reason,
            requires_pinning=pinning_reason is not None,
            pinning_reason=pinning_reason,
        )

    if node_type in COMMAND_TYPES:
        return risk(BLOCKED, "executes arbitrary commands on the n8n host")
    if node_type in SSH_TYPES:
        return risk(BLOCKED, "opens a remote shell")
    if node_type in FILE_TYPES:
        return risk(BLOCKED, "reads or writes the host filesystem")
    if node_type in CODE_TYPES:
        return risk(REVIEW_REQUIRED, "runs user-supplied code in the execution")
    if not node_type.startswith(FIRST_PARTY_PREFIXES):
        return risk(
            REVIEW_REQUIRED, "community or custom node — side effects were never classified"
        )
    return risk(ALLOWED, "first-party node with no host-level side effect")


def classify_workflow(workflow: dict[str, Any]) -> list[NodeRisk]:
    """Classify every node in a workflow definition, in document order."""
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        return []
    return [classify_node(node) for node in nodes if isinstance(node, dict)]


def worst_verdict(risks: list[NodeRisk]) -> str:
    """Fold per-node verdicts into the workflow's verdict.

    An empty list folds to ``ALLOWED``; the gate rejects an empty classification
    separately, because "nothing to classify" must not be able to masquerade as
    "classified and clean".
    """
    if not risks:
        return ALLOWED
    return max((risk.verdict for risk in risks), key=lambda verdict: VERDICT_ORDER[verdict])


def nodes_requiring_pinning(risks: list[NodeRisk]) -> list[NodeRisk]:
    """The nodes that must be proven pinned before any execution."""
    return [risk for risk in risks if risk.requires_pinning]
