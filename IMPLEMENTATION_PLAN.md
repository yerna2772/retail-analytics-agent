# Implementation Plan

Build order for the retail analytics agent. Steps are sequential; each ends in a working, committable state. Obligation IDs in brackets refer to `TZ_TRACEABILITY.md`.

## Scope

**Built:** Safety & PII Masking, High-Stakes Oversight, Resilience. Observability partially (telemetry is captured by `llm/gateway.py` and `data/bigquery.py` already).

**Designed only:** Hybrid Intelligence, Learning Loop, Persona Management.

This split comes from the assignment, not from effort estimation. Deliverable 3 lists five requirements to choose at least two from; Hybrid Intelligence, Learning Loop and Persona Management are not among them. The Golden Bucket is additionally marked "(Theoretical)" in the source document — there is no data to build it against.

A minimal Golden Bucket ships anyway (seed trios in JSON, metadata-filtered selection) because Requirement 1 is the intellectual core of the assignment and its total absence from the code would read as avoidance.

---

## Pinned contract

Implement against these. Do not redesign them mid-build.

### `src/agent/state.py`

```python
from typing import Annotated, Literal, TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage
from pydantic import BaseModel


class PlanStep(BaseModel):
    index: int
    question: str
    depends_on: list[int] = []


class SQLAttempt(BaseModel):
    step_index: int
    attempt: int
    sql: str
    validator_verdict: str
    dry_run_error: str | None = None
    estimated_bytes: int | None = None


class QueryResult(BaseModel):
    step_index: int
    question: str
    sql: str
    columns: list[str]
    rows: list[dict]
    row_count: int
    bytes_scanned: int


class Trio(BaseModel):
    id: str
    question_variants: list[str]        # not a single question -- see note below
    sql: str
    report: str
    tables_used: list[str]
    metrics_used: list[str]
    quality_score: float
    provenance: Literal["authored", "backfilled", "captured"]
    supersedes: str | None = None
    retrieval_score: float | None = None


class ReportRef(BaseModel):
    id: str
    title: str
    created_at: str
    thread_id: str


class GuardrailVerdict(BaseModel):
    layer: Literal["intent", "ast", "output"]
    passed: bool
    reason: str | None = None


class AgentState(TypedDict, total=False):
    # identity
    messages: Annotated[list[AnyMessage], add_messages]
    thread_id: str
    user_id: str
    turn_id: str
    trace_id: str

    # routing -- produced by one structured call (Invariant 10)
    intent: Literal["analysis", "report_create", "report_delete", "metadata", "refuse"]
    standalone_question: str            # follow-up resolved against history [3.4]
    guardrail_verdicts: list[GuardrailVerdict]

    # context
    retrieved_trios: list[Trio]
    schema_slice: str
    metric_defs: str
    user_prefs: dict
    persona: str
    prompt_versions: dict[str, str]

    # plan & execution
    plan: list[PlanStep]
    current_step: int
    replan_count: int                   # [6.5]
    sql_attempts: list[SQLAttempt]
    query_results: list[QueryResult]

    # budgets (Invariant 7)
    repair_count: int
    llm_call_count: int
    bytes_scanned: int

    # reports
    draft_report: str                   # [5.8]
    action_items: list[str]             # [5.8]
    saved_report_id: str | None
    delete_targets: list[ReportRef]
    delete_risk_tier: Literal["low", "medium", "high"]
    delete_confirmed: bool | None

    # output
    final_answer: str
    degradation_level: int
    error: str | None
```

> **Note on `question_variants`.** One analysis gets asked twenty ways. A trio keyed on a single question string, combined with dedup at cosine similarity > 0.95, would reject paraphrases as duplicates instead of attaching them. Paraphrases attach to an existing trio; they do not create new ones.

### `src/agent/graph.py`

```python
from langgraph.graph import StateGraph, START, END

from agent.state import AgentState
from agent.nodes import (
    triage, context, planner, sql_generator, sql_validator, executor,
    repair, diagnose, replan, analyst, guardrail_out, metadata, degrade,
)
from agent.nodes.reports import compose, save, resolve, confirm, delete


def build_graph(checkpointer):
    g = StateGraph(AgentState)

    g.add_node("triage", triage.run)          # classify + route + contextualise: ONE call
    g.add_node("context", context.run)
    g.add_node("planner", planner.run)
    g.add_node("sql_generator", sql_generator.run)
    g.add_node("sql_validator", sql_validator.run)
    g.add_node("executor", executor.run)      # dry_run + execute
    g.add_node("repair", repair.run)
    g.add_node("diagnose", diagnose.run)
    g.add_node("replan", replan.run)
    g.add_node("analyst", analyst.run)        # interpret + format: ONE call
    g.add_node("compose_report", compose.run)
    g.add_node("save_report", save.run)
    g.add_node("guardrail_out", guardrail_out.run)
    g.add_node("metadata", metadata.run)
    g.add_node("degrade", degrade.run)

    g.add_node("resolve_targets", resolve.run)
    g.add_node("confirm", confirm.run)        # interrupt()
    g.add_node("delete", delete.run)

    g.add_edge(START, "triage")

    g.add_conditional_edges(
        "triage",
        lambda s: s["intent"],
        {
            "analysis": "context",
            "report_create": "context",
            "metadata": "metadata",
            "report_delete": "resolve_targets",
            "refuse": "guardrail_out",
        },
    )

    g.add_edge("context", "planner")

    # An empty plan means the question is answerable from prior results in this
    # thread -- "turn what we just discussed into a report" needs no new SQL.
    g.add_conditional_edges(
        "planner",
        planner.route,
        {"query": "sql_generator", "compose_from_history": "analyst"},
    )

    g.add_edge("sql_generator", "sql_validator")
    g.add_conditional_edges(
        "sql_validator",
        sql_validator.route,
        {"execute": "executor", "repair": "repair"},
    )

    g.add_conditional_edges(
        "executor",
        executor.route,
        {
            "repair": "repair",
            "diagnose": "diagnose",
            "replan": "replan",
            "degrade": "degrade",
        },
    )

    g.add_conditional_edges(
        "repair",
        repair.route,
        {"retry": "sql_generator", "give_up": "degrade"},
    )
    g.add_edge("diagnose", "sql_generator")

    # Replanning is what makes causal questions work: step 3 cannot be written
    # before steps 1 and 2 have returned. [6.5]
    g.add_conditional_edges(
        "replan",
        replan.route,
        {"more": "sql_generator", "done": "analyst"},
    )

    g.add_conditional_edges(
        "analyst",
        analyst.route,
        {"report": "compose_report", "chat": "guardrail_out"},
    )
    g.add_edge("compose_report", "save_report")
    g.add_edge("save_report", "guardrail_out")

    g.add_edge("resolve_targets", "confirm")
    g.add_conditional_edges(
        "confirm",
        lambda s: "delete" if s.get("delete_confirmed") else "cancel",
        {"delete": "delete", "cancel": "guardrail_out"},
    )
    g.add_edge("delete", "guardrail_out")

    g.add_edge("metadata", "guardrail_out")
    g.add_edge("degrade", "guardrail_out")
    g.add_edge("guardrail_out", END)

    return g.compile(checkpointer=checkpointer)
```

### `executor.route`

| Condition | Route |
|---|---|
| dry_run failed | `repair` |
| estimate over remaining budget | `degrade` |
| rows returned | `replan` |
| zero rows, not yet diagnosed | `diagnose` |
| zero rows, already diagnosed | `replan` (analyst will explain the absence) |

### `replan.route`

| Condition | Route |
|---|---|
| plan steps remain and no new information changes them | `more` |
| results suggest a follow-up query the original plan missed, and `replan_count < 2` | `more` (append step) |
| plan complete, or budget exhausted | `done` |

---

## Step 0 — Scaffolding

Layout, `pyproject.toml`, `.env.example`, `config.py` (pydantic-settings), `Makefile` (`install / run / demo / test / check / eval`), optional `docker-compose.yml` for Postgres.

`llm/gateway.py` and `data/bigquery.py` are already written — wire them in, add `FakeLLM` fixtures and a CSV-backed fake BigQuery.

`observability/tracing.py`: Langfuse init plus a `@traced_node` decorator recording node name, model, tokens, latency, retries. **Must no-op cleanly with no Langfuse keys** so the project runs on a reviewer's machine.

**Acceptance:** `make demo` starts the CLI, round-trips through `FakeLLM`, exits cleanly. Zero network.

---

## Step 1 — Safety core `[4.4, 4.5, 4.6]` — tests first

`safety/pii.py` — denylist for `thelook_ecommerce`:
```
users.first_name, users.last_name, users.email, users.street_address,
users.postal_code, users.latitude, users.longitude, users.user_geom
```
Output scrubber: emails, phones, postal codes, street-address patterns. **Every redaction logs at high severity** — this layer should never fire.

`safety/ast_rules.py` — sqlglot validation. Reject unless:
- root is `SELECT` or `WITH`; any DML/DDL/scripting rejected
- every table ∈ {orders, order_items, products, users}
- every column resolves and is not denylisted (through aliases, subqueries, CTEs)
- no `SELECT *`
- `LIMIT` present or injected
- no cross join without predicate

k-anonymity: suppress demographic groups with fewer than 5 underlying users.

> **`[6.1]` vs `[4.6]`.** "Top customers" is row-level data about people. Resolution: answer with `user_id` plus non-identifying attributes (state, age bracket, traffic source, lifetime value). k-anonymity applies to demographic aggregates, **not** to rankings over pseudonymous IDs — otherwise the rule suppresses a capability the assignment explicitly requires.

**Acceptance:** `evals/safety_suite.yaml` passes 100%; `make check` fails the build otherwise.

---

## Step 2 — Read path `[3.3, 3.4, 6.1–6.4, 6.6]`

`data/semantic_layer.py` — columns and types come from `BigQueryRunner.get_table_schema`; only metric definitions are hand-written in `semantic/metrics.yaml`:

```yaml
revenue:
  sql: SUM(order_items.sale_price)
  filter: order_items.status NOT IN ('Cancelled', 'Returned')
  note: |
    The single most consequential definition here. Omitting the filter inflates
    every revenue figure the agent reports, and dry_run cannot catch it.
```
Plus `aov`, `return_rate`, `active_user`, `churn`.

Nodes: `triage` (classify + route + contextualise in one structured call), `context`, `planner`, `sql_generator`, `executor`, `analyst` (interpret + format in one call), `guardrail_out`, `metadata`.

The analyst sees **only returned rows** and is prompted to ground every number in a specific row.

**Acceptance:** "What was revenue by month in 2023?" answers correctly end-to-end. Follow-up "and in Texas?" resolves against history without re-stating the metric `[3.4]`.

---

## Step 3 — Replanning `[6.5, 1.1, 1.2, 6.2]`

`replan.py`. Bounded at 2 replans per turn.

This is what makes the assignment's own examples work. "Why are Texas users underspending vs California?" cannot be planned upfront — the third query depends on whether the first two show a basket-size gap or a frequency gap.

**Acceptance:** the two causal examples from the assignment intro produce multi-query answers with a stated driver, not a single aggregate.

---

## Step 4 — Report creation `[5.8, 1.3]`

`nodes/reports/compose.py` — structured output: title, period, findings, **action items**. Action items are a required field, not an optional flourish; the assignment names them twice.

`nodes/reports/save.py` — Postgres row with `owner_id`, `thread_id`, `title`, `body`, `action_items`, `created_at`, `deleted_at`.

Two entry paths: from fresh analysis, and from prior results in the thread ("turn that into a report") via `planner.route → compose_from_history`.

**Acceptance:** "Create a Q1 report with insights and action items for Q2" produces a saved, listable report. `/reports` shows the library.

---

## Step 5 — Destructive ops `[4.7–4.11]`

Depends on Step 4. Do not start earlier — deletion against an empty library demonstrates nothing.

`store/audit.py` — append-only: actor, resolved IDs, filter text, tier, timestamp, trace ID. Deletion and audit write in **one transaction**.

`nodes/reports/resolve.py` — ownership filter in code `[4.11]`, then risk tiering:

| Tier | Match | Confirmation |
|---|---|---|
| low | exact, single, thread-scoped | inline y/n |
| medium | exact set, thread-scoped `[4.8]` | preview list + y/n |
| high | fuzzy match `[4.7]`, or >10 matches, or any report >30 days old | preview + count + typed confirmation |

> **Fuzzy matching stays deterministic.** The LLM extracts only the search string ("Client X") from the utterance; the matching itself is Postgres full-text/ILIKE. Letting the model decide which reports match would put non-determinism back into the deletion path that the whole safety design exists to keep out.

`nodes/reports/delete.py` — soft delete **by IDs resolved before the pause**. `/undo` restores the last deletion in the thread.

**Acceptance:** all three tiers demo cleanly; the pause survives Ctrl-C and resume `[4.9, 4.10]`.

---

## Step 6 — Resilience `[4.15–4.20]`

`repair.py` — feeds the exact dry_run error plus the schema slice back to the generator. Max 3 attempts.

`diagnose.py` — on empty results, probe with progressively relaxed filters to distinguish "filter too narrow" from "no such data". Never emit a bare "no results found".

`degrade.py` — five-level ladder, sets `degradation_level` into the trace.

Wire budget enforcement and the circuit breaker into live calls.

**Acceptance:** four injected failures (syntax error, persistent failure, primary LLM down, over-budget query) each produce a sane CLI response and a complete trace. CLI survives all four `[4.18]`.

---

## Step 7 — Golden Bucket, minimal `[4.1]`

`golden/trios/*.json` — 12–15 seed trios covering the metric vocabulary and the assignment's example question shapes. Hand-written; they are the system's expert knowledge.

`data/golden_bucket.py` — load, embed once at startup, cosine similarity + metadata filter, top 3. No pgvector, no reranking, no curation job: at this corpus size they are unjustifiable, and the HLD says so explicitly.

Candidate capture: on report save, write a `candidate` trio JSON. Half an hour of work, and it makes the learning loop visible in code rather than only on a diagram.

**Acceptance:** a question matching a seed trio produces demonstrably better SQL than the same question with retrieval disabled. Log the comparison in the README.

---

## Step 8 — Persona hot-reload `[4.27, 4.28]`

`prompts/registry.py` — loads `prompts/*.yaml`, watches for changes with a 60s TTL, falls back to last-known-good on parse error. Ownership split visible in the layout: `persona.yaml` editable, `sql_generator.yaml` marked dev-owned.

One hour of work for a demo that closes Requirement 8 more convincingly than any paragraph: edit the file while the CLI runs, next turn changes tone, no restart.

---

## Step 9 — Documentation `[5.6, 5.11, 7.2, 7.4]`

`README.md`: what it is; architecture summary with Mermaid; setup (venv, `.env`, GCP auth); **example run with a real transcript** `[5.6]`; requirements traceability table in English; which prototype requirements are implemented and where; extensibility notes `[3.5, 3.6]`; known limitations.

**Demo mode with no credentials** — fake BigQuery over CSV fixtures plus `FakeLLM`, so a reviewer runs it in 60 seconds without a GCP project.

**Acceptance:** a clean clone on another machine runs following only the README `[5.11]`.

---

## Also required in ARCHITECTURE.md

Not code, but currently missing:

- **Extensibility section** `[3.5, 3.6]` — charts, email, web search as new nodes and tools; new data sources behind the same adapter protocols.
- **Report creation flow** `[5.8]` — absent from the current diagrams.
- **Acknowledged limits** — dry_run does not catch semantically valid but wrong SQL, and that is the dominant text-to-SQL failure mode; `[6.1]` vs `[4.6]` and how it is resolved; hybrid retrieval is over-engineered for this corpus size; PII Layer 2 cannot be demonstrated on a public dataset.
- **Golden Bucket authoring from failures** — the capture loop learns only where the agent already succeeds, so a repeated-failure cluster with no golden trio is routed to an analyst to *author* a reference. Without this the blind spots are self-reinforcing.
- **Backfill for cold start** — existing dashboard SQL, dbt models and analyst write-ups are proto-trios; pairing them beats hand-authoring for the first population.
