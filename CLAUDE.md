# CLAUDE.md

Project context for Claude Code. Read `ARCHITECTURE.md` for the full design rationale and `IMPLEMENTATION_PLAN.md` for the phased build order.

## What this is

A data-analysis chat agent for non-technical retail executives. Natural-language questions → BigQuery SQL → analyst-quality reports. Take-home assignment; graded on **system design, technical explanation, and an elegant prototype** — not on feature count.

Stack: Python 3.11+, LangGraph, Gemini 2.5 Flash (OpenRouter fallback), BigQuery (`bigquery-public-data.thelook_ecommerce`), Postgres + pgvector, Redis, Langfuse, Typer + Rich CLI.

## Non-negotiable invariants

These are graded. Violating any of them is a failed submission, not a bug.

1. **No LLM output reaches BigQuery unvalidated.** Every generated query passes `safety/ast_rules.py` (sqlglot AST) before `dry_run`, and `dry_run` before execution. There is exactly one code path to BigQuery and it goes through both. Never add a second one.

2. **PII enforcement is deterministic, never prompted.** The denylist lives in `safety/pii.py`. Do not "ask the model not to show emails" anywhere. If you find yourself writing that instruction into a prompt, the design is wrong.

3. **`SELECT *` is always rejected.** It cannot be column-checked, and on `users` it returns the entire PII set.

4. **Destructive ops resolve target IDs *before* the confirmation pause, and delete by those IDs after.** Never re-run the filter post-confirmation.

5. **Deletion is soft.** `deleted_at` tombstone + audit row, in one transaction. No hard DELETE anywhere in the codebase.

6. **Every ownership filter is applied in code**, never requested of the model: `WHERE owner_id = :current_user`.

7. **Bounded budgets per turn.** Max 3 SQL repairs, 8 LLM calls, 15 GB scanned. Enforced in graph state, checked in `nodes/repair.py` and `data/bigquery.py`.

8. **The CLI never crashes.** Every node is wrapped; unhandled exceptions become an error state with a user-facing message and a trace ID.

9. **Report creation ships before report deletion.** The assignment requires the agent to "create a report with action items when asked to" as a base capability, and the deletion flow is meaningless against an empty library. Never build step 6 before step 5.

10. **Four LLM calls per typical turn.** The Gemini free tier is rate-limited and one manager question must not exhaust it. Intent classification and routing are one structured call; analysis and formatting are one call; the groundedness judge samples at 10% for chat and 100% only for saved reports. Nodes stay separate in code — the consolidation is in how many of them reach the model.

## Conventions

- **Type everything.** Pydantic models for all cross-boundary data, `TypedDict` for graph state. `mypy --strict` on `src/agent/safety/` at minimum.
- **Nodes are pure-ish functions** `(state) -> dict`. They return partial state updates, never mutate in place. No I/O in the graph assembly file.
- **Adapters behind protocols.** `BigQueryClient`, `LLMGateway`, `TrioStore`, `ReportStore` are Protocols with a real and a fake implementation. Tests use the fakes; no network in unit tests.
- **Prompts are never string literals in Python.** They live in `prompts/*.yaml` and load through `prompts/registry.py`. This is Requirement 8 — inline prompts break it.
- **Config via pydantic-settings** from `.env`. No `os.getenv` scattered around.
- **Async where it touches network**, sync elsewhere. Don't make the whole codebase async for no reason.

## Testing

- `safety/` gets tests **first**, before implementation. It is the graded core.
- The adversarial suite in `evals/safety_suite.yaml` must pass 100%. This is a hard gate — wire it into `make check`.
- Unit tests never hit BigQuery or an LLM. Integration tests are marked `@pytest.mark.integration` and skipped by default.

## Style

- Prefer boring, readable code over clever code. A reviewer reads this in 20 minutes.
- Docstrings on every node explaining *why* it exists, not what the code does.
- No commented-out code, no TODOs left in the final commit.
- Commit messages: imperative mood, one logical change per commit. The commit history is part of what gets reviewed.

## Things not to do

- Don't add LangChain agents/AgentExecutor. LangGraph only — explicit graph, explicit state.
- Don't add features outside the assignment scope. Charts, email, web search are *extensibility points* to describe in the README, not to build.
- Don't use `langchain_community` unless there is no alternative; prefer direct SDKs.
- Don't write the README until the code works. It should describe reality.
- Don't skip the fake adapters "for now". They are what makes the tests fast and the demo reliable when someone else runs it on their machine.
