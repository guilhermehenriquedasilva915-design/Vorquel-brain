"""Shared fixtures: the synthetic world, and the scopes the evals use."""

from __future__ import annotations

from pathlib import Path

import pytest

from vorquel_brain_retrieval import InMemoryBrainStore, Scope

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "brain_v1_b.json"
REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def store() -> InMemoryBrainStore:
    """The whole synthetic world.

    Session-scoped and immutable. If a test could mutate it, a later test could
    pass because an earlier one changed the world, and the suite would stop
    meaning what it says.
    """
    return InMemoryBrainStore.from_json(FIXTURE)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def chaves() -> Scope:
    return Scope("ENTITY", "chaves-hugo")


@pytest.fixture
def chaves_client() -> Scope:
    return Scope("CLIENT", "chaves")


@pytest.fixture
def jacqueline() -> Scope:
    return Scope("CLIENT", "jacqueline")


@pytest.fixture
def clinica() -> Scope:
    return Scope("CLIENT", "clinica")


@pytest.fixture
def imobiliaria() -> Scope:
    return Scope("VERTICAL", "imobiliaria")


@pytest.fixture
def global_scope() -> Scope:
    return Scope.global_vorquel()
