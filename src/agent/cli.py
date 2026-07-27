from __future__ import annotations

import asyncio
import uuid

import typer
from rich.console import Console
from rich.panel import Panel
from rich.theme import Theme

theme = Theme({"info": "dim cyan", "warning": "magenta", "error": "bold red"})
console = Console(theme=theme)
app = typer.Typer(pretty_exceptions_enable=False)


async def _chat_loop(fake: bool) -> None:
    from langchain_core.messages import HumanMessage
    from langgraph.checkpoint.memory import MemorySaver

    from agent.graph import build_graph

    checkpointer = MemorySaver()
    graph = build_graph(checkpointer)
    thread_id = uuid.uuid4().hex[:12]
    mode = "FakeLLM (demo)" if fake else "Live"

    console.print(
        Panel(
            "[bold]Retail Analytics Agent[/bold]\n"
            f"Thread: {thread_id}  |  Mode: {mode}\n"
            "Type [bold]exit[/bold] or [bold]quit[/bold] to end.",
            border_style="blue",
        )
    )

    config = {"configurable": {"thread_id": thread_id}}

    while True:
        try:
            user_input = console.input("[bold green]You:[/bold green] ")
        except (EOFError, KeyboardInterrupt):
            break

        text = user_input.strip()
        if not text:
            continue
        if text.lower() in ("exit", "quit"):
            break

        try:
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content=text)]},
                config=config,
            )
            answer = result.get("final_answer", "No answer generated.")
            console.print(f"\n[bold blue]Agent:[/bold blue] {answer}\n")
        except Exception as exc:
            trace_id = uuid.uuid4().hex[:12]
            console.print(f"\n[error]Error: {exc} (trace: {trace_id})[/error]\n")


@app.command()
def chat(fake: bool = typer.Option(False, "--fake", help="Use FakeLLM (no network)")) -> None:
    """Start an interactive chat session."""
    asyncio.run(_chat_loop(fake))


@app.command()
def demo() -> None:
    """Start in demo mode — FakeLLM, no network, no credentials needed."""
    asyncio.run(_chat_loop(fake=True))


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        _detect_and_run()


def _detect_and_run() -> None:
    from agent.config import settings

    fake = not (settings.gemini_api_key or settings.openrouter_api_key)
    asyncio.run(_chat_loop(fake))


if __name__ == "__main__":
    app()
