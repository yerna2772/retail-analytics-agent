# Architecture

## Design rationale

### Why LangGraph over LangChain agents

LangChain's `AgentExecutor` is a black box: the model decides which tool to call, in what order, with no visibility into the decision graph. For a system where safety invariants must be provably enforced, that opacity is disqualifying.

LangGraph gives us an explicit `StateGraph` — every node, edge, and conditional branch is visible in code. The safety path (AST validate → dry_run → execute) is enforced by the graph topology, not by hoping the model follows instructions. A reviewer can trace the graph and confirm that no code path bypasses validation.

### Why not a single-step text-to-SQL

Single-step text-to-SQL fails on causal and comparative questions ("Why does Texas have higher AOV than California?"). These require multiple dependent queries: compute each metric independently, then compare. The planner decomposes these into a DAG of steps with `depends_on` edges, and the replan loop evaluates whether intermediate results are sufficient before generating the next query.

### Why deterministic PII enforcement

Prompting an LLM not to show PII is a suggestion, not a guarantee. The denylist in `safety/pii.py` is a hard-coded set of `(table, column)` pairs. The AST validator in `ast_rules.py` walks the parsed SQL tree and rejects any query that references a denied column. This is deterministic — it cannot be jailbroken, prompt-injected, or forgotten.

The output scrubber (`scrub_output`) is a safety net, not a primary defense. If it fires, something upstream failed and the event is logged at CRITICAL level.

## Graph topology

```
START → triage → [intent routing]

  analysis/report_create:
    context → planner → [plan routing]
      query:    sql_generator → sql_validator → [validation routing]
                  execute: executor → [execution routing]
                    repair:   repair → [repair routing: retry|give_up]
                    diagnose: diagnose → sql_generator
                    replan:   replan → [replan routing: more|done]
                    degrade:  degrade → guardrail_out
                  repair: repair → ...
      compose_from_history: analyst → ...

    analyst → [intent routing: report|chat]
      report: compose_report → save_report → guardrail_out
      chat:   guardrail_out

  metadata:     metadata → guardrail_out
  report_delete: resolve_targets → confirm → [delete|cancel]
  refuse:       guardrail_out

guardrail_out → END
```

### Report creation flow

```
User: "Create a report from that analysis"
  → triage (intent: report_create)
  → context (load schema + metrics + trios)
  → planner (empty plan → route to compose_from_history)
  → analyst (route: report)
  → compose_report (LLM produces title/period/findings/action_items)
  → save_report (persist to ReportStore)
  → guardrail_out (scrub PII)
  → END
```

When the user asks for a report about data already discussed in the thread, the planner returns an empty plan and routes directly to `compose_from_history`, skipping the SQL generation loop entirely.

### Report deletion flow

```
User: "Delete the Q1 report"
  → triage (intent: report_delete)
  → resolve_targets (query ReportStore with ownership filter in code)
  → confirm (risk-tiered: auto-confirm low-tier single target)
  → delete (soft delete by pre-resolved IDs + audit entry)
  → guardrail_out
  → END
```

Critical safety property: target IDs are resolved **before** the confirmation pause and deleted by those exact IDs **after**. The ownership filter (`WHERE owner_id = :current_user`) is applied in code, never delegated to the LLM.

## State design

```python
class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    intent: str
    standalone_question: str
    guardrail_verdicts: list[GuardrailVerdict]

    schema_slice: str
    metric_defs: str
    retrieved_trios: list[Trio]

    plan: list[PlanStep]
    current_step: int

    sql_attempts: list[SQLAttempt]
    query_results: list[QueryResult]
    repair_count: int
    replan_count: int

    final_answer: str
    report_ref: ReportRef | None
    error: str | None

    llm_call_count: int
    bytes_scanned: int

    delete_targets: list[str]
    delete_confirmed: bool
```

Nodes return partial state updates (a dict with only the keys they modify). LangGraph merges them into the full state. Messages use `add_messages` for append semantics; all other keys use last-write-wins.

## Adapter design

Every external dependency is behind a Protocol:

```python
class LLMGateway(Protocol):
    async def generate(self, prompt: str, *, system: str = "") -> str: ...

class BigQueryClient(Protocol):
    async def dry_run(self, sql: str) -> DryRunResult: ...
    async def execute(self, sql: str) -> QueryResult: ...

class ReportStore(Protocol):
    async def save(self, report: Report) -> str: ...
    async def get(self, report_id: str) -> Report | None: ...
    async def list_by_owner(self, owner_id: str) -> list[Report]: ...
    async def soft_delete(self, report_id: str) -> None: ...

class AuditStore(Protocol):
    async def append(self, entry: AuditEntry) -> None: ...
```

Each has a real implementation (Gemini, BigQuery, Postgres) and a fake (FakeLLM, FakeBigQuery, FakeReportStore, FakeAuditStore). Fakes are injected via LangGraph's `config["configurable"]` dict at graph invocation time. Tests use fakes; the CLI auto-detects available credentials.

## Safety layers

### Layer 1: SQL AST validation (`safety/ast_rules.py`)

The sqlglot parser converts the SQL string to an AST. The validator walks the tree and checks:

1. **Single SELECT statement** — no multi-statement injection, no DDL/DML
2. **No `SELECT *`** — cannot be column-checked, returns the full PII set on `users`
3. **Table allowlist** — only `users`, `orders`, `order_items`, `products`
4. **PII column denylist** — `first_name`, `last_name`, `email`, `street_address`, `postal_code`, `latitude`, `longitude`, `user_geom` on `users`
5. **No unfiltered `CROSS JOIN`** — prevents cartesian explosions
6. **LIMIT injection** — adds `LIMIT 1000` if absent

CTE and subquery aliases are tracked to avoid false positives on virtual table names.

### Layer 2: Output scrubbing (`safety/pii.py:scrub_output`)

Regex-based detection and redaction of email addresses, phone numbers, street addresses, and postal codes. This is a safety net — if it fires, the AST layer should have caught the query. Events are logged at CRITICAL level to surface upstream failures.

### Layer 3: k-anonymity (`safety/pii.py:enforce_k_anonymity`)

Suppresses result rows where a user-count column falls below k=5. Prevents re-identification through small-group aggregation.

## Budget enforcement

| Budget | Limit | Enforced in |
|--------|-------|-------------|
| SQL repairs | 3 per turn | `nodes/repair.py` |
| LLM calls | 8 per turn | All LLM-calling nodes check before calling |
| Bytes scanned | 15 GB per turn | `nodes/executor.py` (from dry_run estimate) |

Exceeding any budget triggers the degradation ladder, never a crash.

## Prompt management

All prompts live in `prompts/*.yaml` and are loaded through `prompts/registry.py`. The registry caches loaded prompts with a 60-second TTL (using `time.monotonic()`). On TTL expiry, the file is re-read from disk. If the file has a YAML parse error, the last-known-good version is served and the error is logged.

Each prompt declares:
- `owner: business` — safe for non-developers to edit (persona, tone)
- `owner: dev` — requires developer review (SQL generation, planning)

## Golden Bucket

The golden bucket is a retrieval-augmented generation (RAG) component that provides the SQL generator with relevant examples of question → SQL → expected result trios.

**Current implementation**: 12 hand-authored seed trios in `golden/trios/*.json`. Retrieval uses TF-IDF cosine similarity over tokenized questions — appropriate for this corpus size, no embedding model or pgvector required.

**Production path**: at scale (1000+ trios), replace TF-IDF with pgvector embeddings. The retrieval interface (`retrieve(question, top_k) → list[Trio]`) stays the same.

**Cold-start problem**: the current trios are hand-authored. A production system should backfill from existing dashboard SQL, dbt models, and analyst write-ups — these are proto-trios that pair natural-language intent with validated SQL.

**Blind-spot problem**: the capture loop (learning from successful queries) only learns where the agent already succeeds. Repeated failures with no matching trio create self-reinforcing blind spots. The mitigation is a human-in-the-loop authoring flow: cluster repeated failures, surface them to an analyst to author a reference trio.

## Extensibility

### New capabilities (charts, email, web search)

The graph architecture supports adding nodes without modifying existing ones:

- **Charts**: add a `chart` node after `analyst` with a conditional edge. The node receives `query_results` from graph state and produces a rendered chart. Route based on whether the question implies a visual answer.
- **Email delivery**: add a `send_email` node after `save_report`. The report model already has structured fields (title, period, findings, action_items) that map directly to an email template.
- **Web search**: add a `web_search` node as an alternative to `sql_generator`. The planner can route questions outside the dataset scope (market benchmarks, competitor data) to web search instead of SQL generation.

### New data sources

Implement the `BigQueryClient` Protocol for the new source. The SQL validator and executor work through the same interface. Registration requires:

1. Add tables to `ALLOWED_TABLES` and `TABLE_SCHEMA` in `ast_rules.py`
2. Add PII columns (if any) to `PII_COLUMNS` in `pii.py`
3. Add metric definitions to `semantic/metrics.yaml`
4. Author seed trios for common questions about the new data

The adapter Protocol ensures the new source is testable with the same fake infrastructure.

## Acknowledged limitations

- **`dry_run` does not catch semantically wrong SQL.** A query that returns the wrong metric but scans the right tables passes all validation. This is the dominant text-to-SQL failure mode. Golden trios mitigate it by providing examples, but cannot eliminate it.
- **Hybrid retrieval is over-engineered for this corpus.** 12 trios do not need TF-IDF; a keyword match would suffice. The abstraction exists because the production path requires embedding-based retrieval, and the interface should be stable from the start.
- **PII Layer 2 cannot be demonstrated.** The `thelook_ecommerce` dataset is synthetic — there is no real PII to protect. The k-anonymity filter is implemented and tested but its value is only realized on real user data.
