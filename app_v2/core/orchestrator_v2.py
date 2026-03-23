from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app_v2.core.task_understanding import infer_task_spec
from app_v2.core.workflow_router import select_workflow

from app_v2.workflows.operations_execution import OperationsExecutionWorkflow
from app_v2.workflows.research_writing import ResearchWritingWorkflow
from app_v2.workflows.coding_project import CodingProjectWorkflow
from app_v2.workflows.multimedia_project import MultimediaProjectWorkflow

from app_v2.state.run_state import RunState
from app_v2.policies.permission_broker import approve_tools
from app_v2.policies.risk_policy import should_pause_for_goal


RUNS_DIR = Path("runs")
ARTIFACTS_DIR = Path("artifacts")


class OrchestratorV2:
    def __init__(self) -> None:
        self.workflow_map = {
            "operations_execution": OperationsExecutionWorkflow(),
            "research_writing": ResearchWritingWorkflow(),
            "coding_project": CodingProjectWorkflow(),
            "multimedia_project": MultimediaProjectWorkflow(),
        }

    def _run_json_path(self, run_id: str) -> Path:
        return RUNS_DIR / f"run_{run_id}.json"

    def _save_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _write_report(self, run_id: str, lines: list[str]) -> Path:
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = ARTIFACTS_DIR / f"final_report_v2_{run_id}.md"
        report_path.write_text("\n".join(lines), encoding="utf-8")
        return report_path

    def run(self, task: str) -> Path:
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        task_spec = infer_task_spec(task)
        approved_tools = approve_tools(task_spec.model_dump())
        task_spec.approved_tools = approved_tools
        task_spec.allowed_tools = list(approved_tools)

        should_block, pause_reason = should_pause_for_goal(task_spec.model_dump())

        workflow_name = select_workflow(task_spec)
        workflow = self.workflow_map[workflow_name]

        context = {}
        plan = workflow.build_plan(task_spec, context)

        state = RunState(
            run_id=run_id,
            task=task,
            current_phase="planning",
            spec=task_spec.model_dump(),
            pending_steps=[step["kind"] for step in plan],
            paused=should_block,
            pause_reason=pause_reason,
            approval_required=should_block,
            final_status="paused" if should_block else "running",
        )

        report_lines = [
            f"# V2 Run Report",
            f"",
            f"- Run ID: {run_id}",
            f"- Task: {task}",
            f"- Task family: {task_spec.task_family}",
            f"- Workflow: {workflow_name}",
            f"- Risk level: {task_spec.risk_level}",
            f"- Approved tools: {task_spec.approved_tools}",
            f"",
            f"## Plan",
        ]

        for step in plan:
            report_lines.append(f"- [{step['id']}] {step['kind']} -> {step['goal']}")

        if should_block:
            report_lines += [
                "",
                "## Status",
                f"Run paused at goal gate: `{pause_reason}`",
            ]
        else:
            report_lines += [
                "",
                "## Status",
                "Initial planning completed.",
            ]
            state.final_status = "planned"

        report_path = self._write_report(run_id, report_lines)
        state.artifacts.append(str(report_path))

        payload = {
            "task": task,
            "task_spec": task_spec.model_dump(),
            "workflow": workflow_name,
            "plan": plan,
            "state": state.model_dump(),
        }

        self._save_json(self._run_json_path(run_id), payload)
        return report_path

    def resume_run(self, run_id: str) -> Path:
        path = self._run_json_path(run_id)
        if not path.exists():
            raise FileNotFoundError(f"Run file not found: {path}")

        payload = json.loads(path.read_text(encoding="utf-8"))
        state = payload.get("state", {})
        task = payload.get("task", "")
        workflow_name = payload.get("workflow", "unknown")

        report_lines = [
            "# V2 Resume Report",
            "",
            f"- Run ID: {run_id}",
            f"- Task: {task}",
            f"- Workflow: {workflow_name}",
            "",
            "Resume behavior is not fully implemented yet.",
            "This confirms the v2 pipeline is wired correctly.",
        ]

        report_path = self._write_report(f"resume_{run_id}", report_lines)

        state["paused"] = False
        state["approval_required"] = False
        state["pause_reason"] = None
        state["final_status"] = "resumed_stub"
        state.setdefault("artifacts", []).append(str(report_path))

        payload["state"] = state
        self._save_json(path, payload)
        return report_path