import importlib
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
def decide(run_id: str = typer.Argument(..., help="Run id, e.g. 20260323_014811")):
    agent = OrchestratorV2()
    decision = agent.generate_resume_decision(run_id)
    print(f"[green]Decision generated.[/green] Resume decision saved to: {decision}")


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