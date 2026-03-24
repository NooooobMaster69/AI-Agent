import importlib
import json
from pathlib import Path
from typing import Optional

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




@app.command(name="check-env")
def check_env():
    checks = [
        ("pydantic", "pydantic"),
        ("dotenv", "python-dotenv"),
        ("typer", "typer"),
        ("rich", "rich"),
        ("requests", "requests"),
        ("bs4", "beautifulsoup4"),
        ("playwright.sync_api", "playwright"),
    ]

    missing: list[str] = []
    for module_name, package_name in checks:
        ok = importlib.util.find_spec(module_name) is not None
        if ok:
            print(f"[green]OK[/green] {module_name}")
        else:
            print(f"[red]MISSING[/red] {module_name} (install package: {package_name})")
            missing.append(package_name)

    if missing:
        print("\n[bold red]Environment not ready.[/bold red]")
        print("Install missing packages:")
        print(f"python -m pip install {' '.join(dict.fromkeys(missing))}")
    else:
        print("\n[bold green]Environment ready for V2 runtime tests.[/bold green]")


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
def decide(
    run_id: str = typer.Argument(..., help="Run id, e.g. 20260323_014811"),
    force_local: bool = typer.Option(False, help="Force local rule-based arbitration"),
    force_cloud: bool = typer.Option(False, help="Force cloud arbitration when API key is configured"),
):
    mode = "auto"
    if force_local and force_cloud:
        raise typer.BadParameter("Choose only one of --force-local or --force-cloud")
    if force_local:
        mode = "force_local"
    elif force_cloud:
        mode = "force_cloud"

    agent = OrchestratorV2()
    decision = agent.generate_resume_decision(run_id, mode=mode)
    print(f"[green]Decision generated.[/green] Resume decision saved to: {decision} (mode={mode})")




def _csv_to_list(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(',') if item.strip()]


@app.command()
def approve(
    run_id: str = typer.Argument(..., help="Run id, e.g. 20260323_014811"),
    decision: str = typer.Option("continue_with_limits", help="continue | continue_with_limits | ask_human | stop"),
    rationale: str = typer.Option("", help="Human rationale for approval decision"),
    tools: Optional[str] = typer.Option(None, help="Comma-separated allowed tools"),
    write_paths: Optional[str] = typer.Option(None, help="Comma-separated allowed write paths"),
):
    agent = OrchestratorV2()
    decision_path = agent.set_resume_decision(
        run_id=run_id,
        decision=decision,
        rationale=rationale,
        allowed_tools=_csv_to_list(tools),
        allowed_write_paths=_csv_to_list(write_paths),
    )
    print(f"[green]Human decision saved.[/green] Resume decision saved to: {decision_path}")


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