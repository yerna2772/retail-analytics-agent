from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
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
    question_variants: list[str]
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
    standalone_question: str
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
    replan_count: int
    sql_attempts: list[SQLAttempt]
    query_results: list[QueryResult]

    # budgets (Invariant 7)
    repair_count: int
    llm_call_count: int
    bytes_scanned: int

    # reports
    draft_report: str
    action_items: list[str]
    saved_report_id: str | None
    delete_targets: list[ReportRef]
    delete_risk_tier: Literal["low", "medium", "high"]
    delete_confirmed: bool | None

    # output
    final_answer: str
    degradation_level: int
    error: str | None
