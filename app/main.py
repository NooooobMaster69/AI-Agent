import json
from pathlib import Path

import typer
from rich import print

from app.config import RUNS_DIR
from app.orchestrator import Orchestrator
from app.policies.risk_policy import ACTION_TO_TOOL
from app.policies.permission_broker import approve_tools

app = typer.Typer(help="Local AI agent MVP")


def _run_json_path(run_id: str) -> Path:
    return RUNS_DIR / f"run_{run_id}.json"


def _final_state_path(run_id: str) -> Path:
    return RUNS_DIR / f"run_{run_id}_final_state.json"


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise typer.BadParameter(f"File not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_run_payload(run_id: str) -> tuple[Path, dict]:
    path = _run_json_path(run_id)
    payload = _load_json(path)
    return path, payload


def _sync_final_state_if_exists(run_id: str, state: dict) -> None:
    final_state = _final_state_path(run_id)
    if final_state.exists():
        _save_json(final_state, state)


def _normalized_state(state: dict | None) -> dict:
    state = state or {}
    return {
        "final_status": state.get("final_status", "unknown"),
        "paused": bool(state.get("paused", False)),
        "pause_reason": state.get("pause_reason"),
        "approval_required": bool(state.get("approval_required", False)),
        "last_action": state.get("last_action"),
        "last_action_result": state.get("last_action_result"),
        "last_confidence": state.get("last_confidence"),
        "pending_steps": state.get("pending_steps", []),
        "current_phase": state.get("current_phase"),
    }


@app.command()
def run(task: str = typer.Argument(..., help="The project task for the agent")):
    agent = Orchestrator()
    artifact = agent.run(task)
    print(f"[green]Done.[/green] Final report saved to: {artifact}")


@app.command("list")
def list_runs(limit: int = typer.Option(10, help="How many recent runs to show")):
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    files = [
        p for p in RUNS_DIR.glob("run_*.json")
        if not p.name.endswith("_final_state.json")
    ]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    if not files:
        print("[yellow]No runs found.[/yellow]")
        return

    for path in files[:limit]:
        payload = _load_json(path)
        run_id = path.stem.replace("run_", "", 1)
        state = _normalized_state(payload.get("state", {}))
        task = payload.get("task", "")

        print(f"[bold]Run:[/bold] {run_id}")
        print(f"  [bold]Status:[/bold] {state['final_status']}")
        print(f"  [bold]Paused:[/bold] {state['paused']}")
        print(f"  [bold]Approval required:[/bold] {state['approval_required']}")
        print(f"  [bold]Last action:[/bold] {state['last_action']}")
        print(f"  [bold]Task:[/bold] {task}")
        print("")


@app.command()
def show(run_id: str = typer.Argument(..., help="Run id, e.g. 20260323_014811")):
    _, payload = _load_run_payload(run_id)
    state = _normalized_state(payload.get("state", {}))

    print(f"[bold]Run:[/bold] {run_id}")
    print(f"[bold]Task:[/bold] {payload.get('task', '')}")
    print(f"[bold]Final status:[/bold] {state['final_status']}")
    print(f"[bold]Paused:[/bold] {state['paused']}")
    print(f"[bold]Pause reason:[/bold] {state['pause_reason']}")
    print(f"[bold]Approval required:[/bold] {state['approval_required']}")
    print(f"[bold]Current phase:[/bold] {state['current_phase']}")
    print(f"[bold]Last action:[/bold] {state['last_action']}")
    print(f"[bold]Last action result:[/bold] {state['last_action_result']}")
    print(f"[bold]Last confidence:[/bold] {state['last_confidence']}")
    print(f"[bold]Pending steps:[/bold] {state['pending_steps']}")


@app.command()
def approve(run_id: str = typer.Argument(..., help="Run id, e.g. 20260323_014811")):
    path, payload = _load_run_payload(run_id)

    original_state = payload.get("state", {}) or {}
    state = dict(original_state)  # 保留完整 state

    task_spec = payload.get("task_spec", {}) or {}

    # 如果这次暂停是因为工具权限不够，
    # 那就在“人工批准”时，把当前 pending steps 对应的工具申请补进去，
    # 再重新走一次 broker 批准。
    if state.get("pause_reason") == "tool_not_allowed":
        requested_tools = list(task_spec.get("requested_tools", []))
        pending_steps = state.get("pending_steps", []) or []

        for action in pending_steps:
            required_tool = ACTION_TO_TOOL.get(action)
            if required_tool and required_tool not in requested_tools:
                requested_tools.append(required_tool)

        task_spec["requested_tools"] = requested_tools
        task_spec["approved_tools"] = approve_tools(task_spec)
        task_spec["allowed_tools"] = list(task_spec["approved_tools"])

        payload["task_spec"] = task_spec
        state["spec"] = task_spec

    state["approval_required"] = False
    state["paused"] = False
    state["pause_reason"] = None
    state["final_status"] = "approved_waiting_resume"
    state["last_action_result"] = "approved"
    state["approval_context"] = {
        **state.get("approval_context", {}),
        "decision": "approved",
    }

    payload["state"] = state
    _save_json(path, payload)
    _sync_final_state_if_exists(run_id, state)

    print(f"[green]Approved.[/green] Updated run: {path}")

    
@app.command()
def deny(run_id: str = typer.Argument(..., help="Run id, e.g. 20260323_014811")):
    path, payload = _load_run_payload(run_id)

    original_state = payload.get("state", {}) or {}
    state = dict(original_state)  # 保留完整 state，不要用 _normalized_state

    state["approval_required"] = False
    state["paused"] = True
    state["pause_reason"] = state.get("pause_reason") or "denied_by_user"
    state["final_status"] = "denied"
    state["last_action_result"] = "denied"
    state["approval_context"] = {
        **state.get("approval_context", {}),
        "decision": "denied",
    }

    payload["state"] = state
    _save_json(path, payload)
    _sync_final_state_if_exists(run_id, state)

    print(f"[yellow]Denied.[/yellow] Updated run: {path}")

@app.command()
def resume(run_id: str = typer.Argument(..., help="Run id, e.g. 20260323_014811")):
    agent = Orchestrator()
    artifact = agent.resume_run(run_id)
    print(f"[green]Resumed.[/green] Final report saved to: {artifact}")

if __name__ == "__main__":
    app()