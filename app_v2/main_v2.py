import json
from pathlib import Path

import typer
from rich import print

from app_v2.core.orchestrator_v2 import OrchestratorV2

app = typer.Typer(help="Local AI agent V2")


RUNS_DIR = Path("runs")


def _run_json_path(run_id: str) -> Path:
    return RUNS_DIR / f"run_{run_id}.json"


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise typer.BadParameter(f"File not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


@app.command()
def run(task: str = typer.Argument(..., help="The project task for the agent")):
    agent = OrchestratorV2()
    artifact = agent.run(task)
    print(f"[green]Done.[/green] V2 report saved to: {artifact}")


@app.command()
def resume(run_id: str = typer.Argument(..., help="Run id, e.g. 20260323_014811")):
    agent = OrchestratorV2()
    artifact = agent.resume_run(run_id)
    print(f"[green]Resumed.[/green] V2 report saved to: {artifact}")


@app.command()
def show(run_id: str = typer.Argument(..., help="Run id, e.g. 20260323_014811")):
    payload = _load_json(_run_json_path(run_id))
    state = payload.get("state", {})

    print(f"[bold]Run:[/bold] {run_id}")
    print(f"[bold]Task:[/bold] {payload.get('task', '')}")
    print(f"[bold]Workflow:[/bold] {payload.get('workflow', '')}")
    print(f"[bold]Final status:[/bold] {state.get('final_status')}")
    print(f"[bold]Paused:[/bold] {state.get('paused')}")
    print(f"[bold]Pause reason:[/bold] {state.get('pause_reason')}")
    print(f"[bold]Approval required:[/bold] {state.get('approval_required')}")
    print(f"[bold]Pending steps:[/bold] {state.get('pending_steps', [])}")


if __name__ == "__main__":
    app()