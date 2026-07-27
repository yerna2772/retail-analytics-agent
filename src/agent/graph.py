from langgraph.graph import END, START, StateGraph

from agent.nodes import (
    analyst,
    context,
    degrade,
    diagnose,
    executor,
    guardrail_out,
    metadata,
    planner,
    repair,
    replan,
    sql_generator,
    sql_validator,
    triage,
)
from agent.nodes.reports import compose, confirm, delete, resolve, save
from agent.state import AgentState


def build_graph(checkpointer):
    g = StateGraph(AgentState)

    g.add_node("triage", triage.run)  # classify + route + contextualise: ONE call
    g.add_node("context", context.run)
    g.add_node("planner", planner.run)
    g.add_node("sql_generator", sql_generator.run)
    g.add_node("sql_validator", sql_validator.run)
    g.add_node("executor", executor.run)  # dry_run + execute
    g.add_node("repair", repair.run)
    g.add_node("diagnose", diagnose.run)
    g.add_node("replan", replan.run)
    g.add_node("analyst", analyst.run)  # interpret + format: ONE call
    g.add_node("compose_report", compose.run)
    g.add_node("save_report", save.run)
    g.add_node("guardrail_out", guardrail_out.run)
    g.add_node("metadata", metadata.run)
    g.add_node("degrade", degrade.run)

    g.add_node("resolve_targets", resolve.run)
    g.add_node("confirm", confirm.run)  # interrupt()
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
