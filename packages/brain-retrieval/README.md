# vorquel-brain-retrieval

The Brain V1 **read path**: entity resolution, state, delta, evidence search and
the deterministic ContextPack.

This package consumes `vorquel-brain-contract` and defines no vocabulary of its
own. It is universal — nothing here knows about Claude, Codex, n8n, GBrain or any
other runtime, and nothing here should learn.

## What it implements

Six of the eight contract tools (DIV-1), as Python functions. Not as MCP tools:
the MCP surface is Brain-V1-C.

| Function | Answers |
|---|---|
| `resolve_entity(store, query, scope)` | which entity is this string |
| `get_entity(store, entity_id, scope)` | the canonical record, plus relations |
| `get_state(store, scope)` | the derived current picture |
| `get_delta(store, scope, since=…)` | what changed, and what it cannot see |
| `search_evidence(store, query, scope)` | evidence, relational before lexical |
| `get_context_pack(store, objective, scope, …)` | the read model for one objective |

The two controlled writes — `record_candidate` and `record_event` — are **not**
here, and a CI step asserts they are not. The storage port has no write method,
so a read path cannot grow one by accident.

## Where the data lives

It does not, yet. This is the one thing to understand before using the package.

An audit of this repository found no home for the twelve V1 objects:

- **`n8n_brain`** is owned here, but holds n8n *operational* memory — experiences,
  build runs, compiled workflow knowledge. None of it is an Entity, Claim,
  Evidence, Decision, Hypothesis, Unknown or Event in the contract's sense.
- **`vorquel_knowledge`** holds human-reviewed semantic knowledge, but its
  migrations live in the **Vorquel-watch** repository. This repo cannot migrate it.

Creating a third knowledge store here was out of bounds without a prior
proposal, so retrieval is written against the `BrainStore` port instead. Every
read depends on that port and on nothing else, so the decision about where the
Brain's own objects finally live stays open and costs exactly one adapter when
it is made.

`InMemoryBrainStore` is the adapter Brain-V1-B ships. It is not a stub — it is
what the negative evals run against — and it validates everything against the
published schemas at load time, so a fixture cannot prove a rule by being
malformed in a convenient way.

```python
from vorquel_brain_retrieval import InMemoryBrainStore, Scope, get_context_pack

store = InMemoryBrainStore.from_json("fixtures/brain_v1_b.json")
result = get_context_pack(
    store,
    objective="reduzir tempo de resposta ao lead",
    scope=Scope("ENTITY", "chaves-hugo"),
    mode="OPERATIONAL",
    token_budget=8000,
    entity_ids=("ent_chaves_hugo",),
)
result.pack               # schema-valid ContextPack, pointer-based
result.state_projection   # the StateProjection it points at
result.delta              # what changed, with coverage stated
```

## The rules it enforces

**Scope is closed.** A request sees exactly its own scope plus
`GLOBAL_VORQUEL`. There is **no inheritance**: a CLIENT does not see its
VERTICAL, and a VERTICAL does not see its clients. That is a deliberate,
costly choice — inheritance is the feature that would make the clinic pack
quietly pull real-estate material — and it cannot be switched on by a caller
passing a flag.

**SECRET is excluded, not redacted.** It never reaches a pack, at any budget, in
any mode. That something was withheld is recorded as a gap, because a silent
omission and an empty record look identical to a reader.

**PII is orthogonal.** Carrying `PII` neither raises nor lowers a tier. PUBLIC
material containing personal data stays PUBLIC and stays retrievable, marked
rather than dropped.

**A budget cuts content, never traceability.** Trimming is monotone — a step
that costs more tokens than it saves is rolled back — and nothing in
`NON_DROPPABLE` is ever removed. No item stays without its provenance, and no
provenance outlives its item. When even the smallest permitted pack will not
fit, the answer is `BUDGET_TOO_SMALL` and **no pack is generated**: there is no
safe mutilated ContextPack, so none is offered.

**Absence is not falsehood.** `NO_EVIDENCE_FOUND` is an `Absence` object. It is
falsy for control flow and is never the boolean `False`.

**Nothing is corrected silently.** A forbidden epistemic promotion produces a
finding and a candidate conflict. The proposal is not rewritten and canonical
state is not touched.

## Determinism

For the same store, the same inputs and the same generator version, a pack comes
out byte-identical.

- every list is sorted, with an id-based tie-break, so the order is total;
- nothing reads the clock — `generated_at` defaults to the newest timestamp in
  the store;
- `context_pack_id` excludes `generated_at`, so two packs built from the same
  facts at different moments are the same pack and say so;
- `context_pack_id` includes a fingerprint of the store, so the same question
  asked of a different world is a different pack.

## Development

```bash
python -m pip install -e ../brain-contract
python -m pip install -e '.[dev]'
pytest
ruff check .
python fixtures/build_fixture.py   # regenerating must be a no-op
```

The fixture is generated, never hand-edited: `fixtures/build_fixture.py` keeps
ids and cross-references consistent and states next to each object what it is
there to prove. It is entirely synthetic — the names echo the real Vorquel cases
only so the evals read the way the contract states them.

CI runs this as `brain-retrieval-quality`, which additionally proves the fixture
is reproducible, that the closed vocabularies agree across Python, the schemas
and the migration SQL, that the pack is byte-reproducible, and that no MCP
server, vector database or graph database was introduced.
