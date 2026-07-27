# Retail Analytics Agent

Natural-language questions → BigQuery SQL → analyst-quality reports for non-technical retail executives.

Built with LangGraph (explicit state graph, no black-box agents), Gemini 2.5 Flash, and a three-layer safety stack that ensures no LLM output reaches BigQuery unvalidated.

## Architecture

```mermaid
graph TD
    START --> triage
    triage -->|analysis / report_create| context
    triage -->|metadata| metadata
    triage -->|report_delete| resolve_targets
    triage -->|refuse| guardrail_out

    context --> planner
    planner -->|query| sql_generator
    planner -->|compose_from_history| analyst

    sql_generator --> sql_validator
    sql_validator -->|execute| executor
    sql_validator -->|repair| repair

    executor -->|repair| repair
    executor -->|diagnose| diagnose
    executor -->|replan| replan
    executor -->|degrade| degrade

    repair -->|retry| sql_generator
    repair -->|give_up| degrade
    diagnose --> sql_generator

    replan -->|more| sql_generator
    replan -->|done| analyst

    analyst -->|report| compose_report
    analyst -->|chat| guardrail_out
    compose_report --> save_report
    save_report --> guardrail_out

    resolve_targets --> confirm
    confirm -->|delete| delete
    confirm -->|cancel| guardrail_out
    delete --> guardrail_out

    metadata --> guardrail_out
    degrade --> guardrail_out
    guardrail_out --> END
```

**18 nodes, one directed graph, fully explicit state transitions.** Every LLM call, query result, and routing decision is visible in the graph state. See [ARCHITECTURE.md](ARCHITECTURE.md) for design rationale.

## Quick start

### Demo mode (no credentials needed)

```bash
git clone <repo-url> && cd retail-analytics-agent
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make demo
```

Demo mode uses `FakeLLM` (keyword-aware scripted responses) and `FakeBigQuery` (CSV fixture data). No API keys, no GCP project, no network access required.

### Live mode

```bash
cp .env.example .env
# Add at least one LLM key:
#   GEMINI_API_KEY=...       (primary)
#   OPENROUTER_API_KEY=...   (fallback)
# Add GCP credentials for BigQuery:
#   GCP_PROJECT_ID=...
#   GOOGLE_APPLICATION_CREDENTIALS=path/to/key.json
make run
```

The agent auto-detects available credentials. If no LLM keys are set, it falls back to FakeLLM.

## Example session

```
╭──────────────────────────────────────────────────────────────╮
│ Retail Analytics Agent                                       │
│ Thread: 55609784c549  |  Mode: FakeLLM (demo)                │
│ Type exit or quit to end.                                    │
╰──────────────────────────────────────────────────────────────╯

You: What are the top product categories by revenue?

Agent: Based on the data provided, here are the key findings:
The results show the requested metrics across the analysed period.
[Demo mode — connect a real LLM for detailed analysis.]

You: Create a report from that

Agent: # Retail Performance Report
**Period:** 2023
## Findings
  1. Revenue totalled $459.93 across the analysed period
  2. Outerwear and Dresses are the highest-revenue categories
## Action Items
  1. Increase marketing spend on top-performing categories
  2. Investigate low conversion in underperforming segments
*Report saved (id: b39c93bdf0d5)*

You: What tables do you have?

Agent: I have access to the thelook_ecommerce dataset with these tables:
  order_items — Line items with sale prices and fulfillment status
  orders — Order headers (status, timestamps, item count)
  products — Product catalog (name, brand, category, cost, retail price)
  users — Customer demographics (age, gender, state, city, traffic source)
```

## Safety design

Three layers, each deterministic and non-bypassable:

| Layer | What it does | Where |
|-------|-------------|-------|
| **SQL AST validation** | Parses with sqlglot; rejects `SELECT *`, PII columns, disallowed tables, unfiltered `CROSS JOIN` | `safety/ast_rules.py` |
| **PII denylist** | Hard-coded column pairs `(table, column)` — never prompted | `safety/pii.py` |
| **Output scrubbing** | Regex-based email/phone/address/postal redaction on every response | `safety/pii.py:scrub_output` |

The SQL path is: **LLM → AST validate → dry_run → execute**. There is exactly one code path to BigQuery and it goes through both validation stages. `SELECT *` is always rejected because it cannot be column-checked.

### Budgets

Every turn is bounded: max 3 SQL repairs, 8 LLM calls, 15 GB scanned. Enforced in graph state, checked before each call. Exhausting any budget triggers graceful degradation, not a crash.

## How it works

1. **Triage** classifies intent (analysis, report_create, report_delete, metadata, refuse) and resolves follow-up references into standalone questions.

2. **Context** loads the safe schema (PII columns stripped), metric definitions, and retrieves relevant golden trios via TF-IDF similarity.

3. **Planner** decomposes complex questions into 1–3 SQL steps with dependency tracking. Causal questions ("why does X differ from Y?") get parallel queries followed by a dependent comparison step.

4. **SQL Generator → Validator → Executor** generates SQL grounded in schema + metrics + golden examples, validates the AST, dry-runs against BigQuery, then executes. Failed queries route to repair (up to 3 attempts) or degrade.

5. **Replan** checks whether intermediate results are sufficient or more queries are needed. Up to 2 replan rounds.

6. **Analyst** interprets results in business language. For report-create intents, routes to **Compose → Save** which produces structured findings + action items.

7. **Guardrail Out** scrubs PII from every response before it reaches the user.

### Report lifecycle

- **Create**: analysis results → LLM composition → structured report with findings and action items → persisted to ReportStore
- **Delete**: intent detected → targets resolved by ownership filter **in code** (`WHERE owner_id = :current_user`) → risk-tiered confirmation → soft delete with `deleted_at` tombstone + audit row in one transaction
- Target IDs are resolved **before** confirmation and deleted by those IDs **after** — the filter is never re-run post-confirmation

### Resilience

Five-level degradation ladder:

1. **Repair** — feed the error back to the LLM, retry SQL generation (up to 3 times)
2. **Diagnose** — distinguish empty-result causes (filter too narrow vs. no data)
3. **Replan** — discard failed step, ask whether remaining data suffices
4. **Degrade** — return a partial answer with an explanation of what failed
5. **Error state** — return a user-facing error message with a trace ID

The CLI never crashes. Every node is wrapped; unhandled exceptions become an error state with a user-facing message and a trace ID.

## Project structure

```
src/agent/
├── cli.py                  # Typer + Rich CLI with auto-detection
├── config.py               # pydantic-settings from .env
├── state.py                # AgentState TypedDict + Pydantic models
├── graph.py                # StateGraph wiring (18 nodes)
├── data/
│   ├── bigquery.py         # BigQueryClient Protocol + FakeBigQuery
│   ├── semantic_layer.py   # Safe schema + metric definitions
│   └── golden_bucket.py    # TF-IDF retrieval over seed trios
├── llm/
│   ├── gateway.py          # LLMGateway Protocol + Gemini/OpenRouter/FakeLLM
│   └── circuit.py          # Circuit breaker for LLM calls
├── nodes/                  # One file per graph node
│   ├── triage.py           # Intent classification
│   ├── context.py          # Schema + metrics + trio retrieval
│   ├── planner.py          # Multi-step plan decomposition
│   ├── sql_generator.py    # SQL generation with repair context
│   ├── sql_validator.py    # AST validation gate
│   ├── executor.py         # Dry-run + execute + budget check
│   ├── repair.py           # Retry counter with bounded attempts
│   ├── replan.py           # Intermediate result evaluation
│   ├── analyst.py          # Result interpretation
│   ├── diagnose.py         # Empty result diagnosis
│   ├── degrade.py          # Five-level degradation
│   ├── metadata.py         # Schema/capability questions
│   ├── guardrail_out.py    # Output PII scrubbing
│   └── reports/
│       ├── compose.py      # LLM-driven report composition
│       ├── save.py         # Persist to ReportStore
│       ├── resolve.py      # Pre-confirmation target resolution
│       ├── confirm.py      # Risk-tiered confirmation gate
│       └── delete.py       # Soft delete + audit
├── safety/
│   ├── ast_rules.py        # sqlglot AST validation
│   └── pii.py              # PII denylist + output scrubbing
├── store/
│   ├── reports.py          # ReportStore Protocol + FakeReportStore
│   └── audit.py            # AuditEntry model + FakeAuditStore
├── prompts/
│   └── registry.py         # YAML loader with 60s TTL hot-reload
└── observability/
    └── tracing.py          # Trace ID generation

prompts/                    # Prompt templates (YAML, hot-reloadable)
├── triage.yaml
├── planner.yaml
├── sql_generator.yaml
├── analyst.yaml
├── replan.yaml
├── repair.yaml
├── compose_report.yaml
├── persona.yaml            # owner: business (editable without code change)
└── system.yaml

golden/trios/               # 12 seed question→SQL→result trios
semantic/metrics.yaml       # Metric definitions (revenue, AOV, etc.)
fixtures/                   # CSV data for FakeBigQuery
evals/safety_suite.yaml     # 45 adversarial safety eval cases
```

## Testing

```bash
make check    # lint + typecheck + 129 unit tests + 45 safety evals
make test     # unit tests only
make eval     # adversarial safety suite only
```

All tests run with `FakeLLM` and `FakeBigQuery` — no network, no credentials. The safety eval suite (`evals/safety_suite.yaml`) is a hard gate: 100% pass rate required.

Tests cover: SQL AST validation (PII, `SELECT *`, table allowlist, injection attempts), PII scrubbing (email, phone, address patterns), full graph traversal (read path, causal replanning, report lifecycle, delete flow, resilience/degradation), golden bucket retrieval, and persona hot-reload.

## Adapters and testing

Every external dependency is behind a Protocol with a real and a fake implementation:

| Protocol | Real | Fake |
|----------|------|------|
| `LLMGateway` | `GeminiGateway`, `OpenRouterGateway` | `FakeLLM` |
| `BigQueryClient` | (production impl) | `FakeBigQuery` (CSV-backed) |
| `ReportStore` | (Postgres impl) | `FakeReportStore` (in-memory) |
| `AuditStore` | (Postgres impl) | `FakeAuditStore` (in-memory) |

Injected via LangGraph's `config["configurable"]` dict — no global singletons, no monkey-patching.

## Prompt management

All prompts live in `prompts/*.yaml`, loaded through a registry with 60-second TTL hot-reload. Edit a prompt file while the agent is running; the next turn picks up the change without a restart.

Each prompt declares an `owner` field:
- `business` — persona, tone, and style prompts that non-developers can safely edit
- `dev` — SQL generation, planning, and system prompts that require developer review

## Extensibility

The graph-based architecture makes the agent extensible without modifying existing nodes:

- **Charts/visualisation**: add a `chart` node after `analyst` with a conditional edge based on response type. The node receives `query_results` from state and produces a chart artifact.
- **Email delivery**: add a `send_email` node after `save_report`. The report is already structured (title, period, findings, action items).
- **Web search**: add a `web_search` node as an alternative to `sql_generator` for questions outside the dataset scope. Route from `planner` based on question type.
- **New data sources**: implement the `BigQueryClient` Protocol for the new source. The SQL validator and executor work through the same interface. Add tables to `ALLOWED_TABLES` and `TABLE_SCHEMA` in `ast_rules.py`.

## Known limitations

- **Semantic correctness**: `dry_run` validates SQL syntax and permissions but not whether the query answers the question correctly. A syntactically valid but semantically wrong query passes validation. This is the dominant text-to-SQL failure mode and is mitigated but not solved by golden trios.
- **PII Layer 2 (k-anonymity)**: implemented but cannot be demonstrated on the public `thelook_ecommerce` dataset, which has no real PII.
- **Golden Bucket scale**: TF-IDF cosine similarity is appropriate for the current 12-trio corpus. At scale (1000+ trios), this should be replaced with pgvector embeddings.
- **Cold start**: the golden bucket only contains hand-authored seed trios. A production system would backfill from existing dashboard SQL, dbt models, and analyst write-ups.
- **Circuit breaker**: implemented for LLM calls but not configurable per-model. The fallback from Gemini → OpenRouter is at the gateway factory level.

## Requirements traceability

| Requirement | Implementation | Files |
|-------------|----------------|-------|
| Natural language → SQL | Triage → Plan → Generate → Validate → Execute | `nodes/triage.py` → `nodes/sql_generator.py` → `nodes/executor.py` |
| PII protection (deterministic) | Column denylist + AST check + output scrubbing | `safety/pii.py`, `safety/ast_rules.py`, `nodes/guardrail_out.py` |
| No `SELECT *` | AST rule, always enforced | `safety/ast_rules.py:99` |
| Bounded budgets | 3 repairs / 8 LLM calls / 15 GB scanned | `config.py`, `nodes/repair.py`, `nodes/executor.py` |
| Report creation | Compose → Save with structured output | `nodes/reports/compose.py`, `nodes/reports/save.py` |
| Safe deletion | Resolve → Confirm → Soft delete + audit | `nodes/reports/resolve.py` → `delete.py` |
| Graceful degradation | Five-level ladder | `nodes/degrade.py`, `nodes/repair.py`, `nodes/diagnose.py` |
| Prompt management | YAML files with TTL hot-reload | `prompts/`, `prompts/registry.py` |
| Golden bucket | TF-IDF retrieval over seed trios | `data/golden_bucket.py`, `golden/trios/` |
| Semantic layer | Metric definitions + safe schema | `data/semantic_layer.py`, `semantic/metrics.yaml` |
