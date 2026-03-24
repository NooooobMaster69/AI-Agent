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
from app_v2.core.executor_runtime import ExecutorRuntime

RUNS_DIR = Path("runs")
ARTIFACTS_DIR = Path("artifacts")


class OrchestratorV2:
    def __init__(self) -> None:
        self.executor = ExecutorRuntime()
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
        first_step_result = None

        if not should_block and plan:
            for step in plan:
                state.current_step_id = str(step["id"])
                state.current_step_kind = step["kind"]

                result = self.executor.execute_step(
                    step=step,
                    task_spec=task_spec.model_dump(),
                    context={},
                )

                state.step_results.append(result.model_dump())
                state.last_action = step["kind"]
                state.last_action_result = result.summary
                state.last_confidence = result.confidence

                if result.status == "completed":
                    state.completed_steps.append(step["kind"])
                    if step["kind"] in state.pending_steps:
                        state.pending_steps.remove(step["kind"])
                    state.findings.extend(result.findings)
                    state.artifacts.extend(result.artifacts)

                elif result.status == "paused":
                    state.paused = True
                    state.approval_required = True
                    state.pause_reason = result.pause_reason
                    state.final_status = "paused"
                    break

                else:
                    state.failure_count += 1
                    if state.failure_count >= 2:
                        state.final_status = "failed"
                        break
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
        completed = set(state.get("completed_steps", []))
        plan = payload.get("plan", [])

        remaining_steps = [step for step in plan if step["kind"] not in completed]

        for step in remaining_steps:
            result = self.executor.execute_step(
                step=step,
                task_spec=payload.get("task_spec", {}),
                context={},
            )

            state.setdefault("step_results", []).append(result.model_dump())
            state["last_action"] = step["kind"]
            state["last_action_result"] = result.summary
            state["last_confidence"] = result.confidence

            if result.status == "completed":
                state.setdefault("completed_steps", []).append(step["kind"])
                if step["kind"] in state.get("pending_steps", []):
                    state["pending_steps"].remove(step["kind"])
            elif result.status == "paused":
                state["paused"] = True
                state["approval_required"] = True
                state["pause_reason"] = result.pause_reason
                state["final_status"] = "paused"
                break
            else:
                state["failure_count"] = state.get("failure_count", 0) + 1
                break