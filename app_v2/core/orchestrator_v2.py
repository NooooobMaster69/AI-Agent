from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app_v2.core.cloud_arbitrator import CloudArbitrator
from app_v2.core.executor_runtime import ExecutorRuntime
from app_v2.core.task_understanding import infer_task_spec
from app_v2.core.workflow_router import select_workflow
from app_v2.policies.permission_broker import approve_tools
from app_v2.policies.risk_policy import should_pause_for_goal
from app_v2.schemas.pause_packet import PausePacket
from app_v2.schemas.resume_decision import ResumeDecision
from app_v2.state.run_state import RunState
from app_v2.workflows.coding_project import CodingProjectWorkflow
from app_v2.workflows.multimedia_project import MultimediaProjectWorkflow
from app_v2.workflows.operations_execution import OperationsExecutionWorkflow
from app_v2.workflows.research_writing import ResearchWritingWorkflow


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
        self.executor = ExecutorRuntime()
        self.arbitrator = CloudArbitrator()

    def _run_json_path(self, run_id: str) -> Path:
        return RUNS_DIR / f"run_{run_id}.json"

    def _pause_packet_path(self, run_id: str) -> Path:
        return ARTIFACTS_DIR / f"pause_packet_v2_{run_id}.json"

    def _resume_decision_path(self, run_id: str) -> Path:
        return ARTIFACTS_DIR / f"resume_decision_v2_{run_id}.json"

    def _save_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _write_report(self, run_id: str, lines: list[str], prefix: str = "final_report_v2") -> Path:
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = ARTIFACTS_DIR / f"{prefix}_{run_id}.md"
        report_path.write_text("\n".join(lines), encoding="utf-8")
        return report_path

    def _build_pause_packet(self, state: RunState) -> PausePacket:
        packet = PausePacket(
            run_id=state.run_id,
            reason=state.pause_reason or "unknown",
            current_step_id=state.current_step_id or "",
            current_step_kind=state.current_step_kind or "",
            task=state.task,
            recent_findings=state.findings[-8:],
            recent_artifacts=state.artifacts[-8:],
            recent_step_results=state.step_results[-8:],
            question_for_cloud="Should execution continue? If yes, what limits should be applied?",
            decision_path=str(self._resume_decision_path(state.run_id)),
        )
        return packet

    def _save_pause_packet(self, state: RunState) -> Path:
        packet = self._build_pause_packet(state)
        path = self._pause_packet_path(state.run_id)
        self._save_json(path, packet.model_dump())
        state.approval_context["pause_packet_path"] = str(path)
        return path

    def _load_resume_decision(self, run_id: str) -> ResumeDecision | None:
        path = self._resume_decision_path(run_id)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ResumeDecision(**payload)

    def _apply_resume_decision(self, decision: ResumeDecision, task_spec: dict, state: RunState) -> None:
        state.approval_context["resume_decision"] = decision.model_dump()

        if decision.updated_allowed_tools:
            task_spec["allowed_tools"] = list(dict.fromkeys(decision.updated_allowed_tools))
            task_spec["approved_tools"] = list(dict.fromkeys(decision.updated_allowed_tools))

        if decision.updated_allowed_write_paths:
            task_spec["allowed_write_paths"] = list(dict.fromkeys(decision.updated_allowed_write_paths))

        if decision.decision == "ask_human":
            state.paused = True
            state.approval_required = True
            state.pause_reason = "resume_decision_requires_human"
            state.final_status = "paused"

        if decision.decision == "stop":
            state.final_status = "stopped_by_resume_decision"

    def generate_resume_decision(self, run_id: str, mode: str = "auto") -> Path:
        pause_path = self._pause_packet_path(run_id)
        if not pause_path.exists():
            raise FileNotFoundError(f"Pause packet not found: {pause_path}")

        decision = self.arbitrator.decide_from_pause_packet(pause_path, mode=mode)
        decision_path = self._resume_decision_path(run_id)
        self._save_json(decision_path, decision.model_dump())
        return decision_path

    def set_resume_decision(
        self,
        run_id: str,
        decision: str,
        rationale: str = "",
        allowed_tools: list[str] | None = None,
        allowed_write_paths: list[str] | None = None,
    ) -> Path:
        decision_obj = ResumeDecision(
            run_id=run_id,
            decision=decision,  # type: ignore[arg-type]
            rationale=rationale,
            updated_allowed_tools=allowed_tools or [],
            updated_allowed_write_paths=allowed_write_paths or [],
        )
        decision_path = self._resume_decision_path(run_id)
        self._save_json(decision_path, decision_obj.model_dump())
        return decision_path

    def _derive_result_text(self, state: RunState) -> str:
        for result in reversed(state.step_results):
            if not isinstance(result, dict):
                continue
            if result.get("status") != "completed":
                continue
            output_text = str(result.get("output_text", "")).strip()
            if output_text:
                return output_text
        return ""

    def _append_result_section(self, report_lines: list[str], state: RunState) -> None:
        result_text = self._derive_result_text(state)
        if not result_text:
            return
        report_lines += ["", "## Result", result_text]

    def _execute_plan_steps(
        self,
        *,
        plan: list[dict],
        task_spec: dict,
        state: RunState,
        report_lines: list[str],
        start_index: int = 0,
        max_failures: int = 2,
    ) -> None:
        if start_index >= len(plan):
            report_lines += ["", "## Execution", "No remaining steps to execute."]
            state.final_status = "completed"
            return

        report_lines += ["", "## Execution"]

        for step in plan[start_index:]:
            step_kind = step.get("kind", "unknown")
            step_id = str(step.get("id", ""))
            state.current_step_id = step_id
            state.current_step_kind = step_kind

            step_result = self.executor.execute_step(
                step=step,
                task_spec=task_spec,
                context={
                    "run_id": state.run_id,
                    "task": state.task,
                    "step_results": list(state.step_results),
                },
            )

            state.step_results.append(step_result.model_dump())
            state.last_action = step_kind
            state.last_action_result = step_result.summary
            state.last_confidence = step_result.confidence

            observation = step_result.raw_data.get("observation") if isinstance(step_result.raw_data, dict) else None
            if isinstance(observation, dict):
                state.observations.append(observation)

            report_lines.append(
                f"- [{step_id}] {step_kind}: {step_result.status} — {step_result.summary}"
            )

            if step_result.status == "completed":
                if step_kind not in state.completed_steps:
                    state.completed_steps.append(step_kind)
                if step_id not in state.completed_step_ids:
                    state.completed_step_ids.append(step_id)
                if step_kind in state.pending_steps:
                    state.pending_steps.remove(step_kind)
                if step_id in state.pending_step_ids:
                    state.pending_step_ids.remove(step_id)
                state.findings.extend(step_result.findings)
                state.artifacts.extend(step_result.artifacts)
                continue

            if step_result.status == "paused":
                state.paused = True
                state.approval_required = True
                state.pause_reason = step_result.pause_reason
                state.final_status = "paused"

                pause_packet_path = self._save_pause_packet(state)
                state.artifacts.append(str(pause_packet_path))
                report_lines.append(f"- Pause packet saved: {pause_packet_path}")
                return

            state.failure_count += 1
            if state.failure_count >= max_failures:
                state.final_status = "execution_failed"
                report_lines.append(f"- Execution stopped after {state.failure_count} failures.")
                return

        state.final_status = "completed"
        state.paused = False
        state.approval_required = False
        state.pause_reason = None

    def run(self, task: str) -> Path:
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        task_spec_model = infer_task_spec(task)
        approved_tools = approve_tools(task_spec_model.model_dump())
        task_spec_model.approved_tools = approved_tools
        task_spec_model.allowed_tools = list(approved_tools)
        task_spec = task_spec_model.model_dump()

        should_block, pause_reason = should_pause_for_goal(task_spec)

        workflow_name = select_workflow(task_spec_model)
        workflow = self.workflow_map[workflow_name]

        plan = workflow.build_plan(task_spec_model, {})

        state = RunState(
            run_id=run_id,
            task=task,
            current_phase="planning",
            spec=task_spec,
            pending_steps=[step["kind"] for step in plan],
            pending_step_ids=[str(step["id"]) for step in plan],
            paused=should_block,
            pause_reason=pause_reason,
            approval_required=should_block,
            final_status="paused" if should_block else "running",
        )

        report_lines = [
            "# V2 Run Report",
            "",
            f"- Run ID: {run_id}",
            f"- Task: {task}",
            f"- Task family: {task_spec_model.task_family}",
            f"- Workflow: {workflow_name}",
            f"- Risk level: {task_spec_model.risk_level}",
            f"- Approved tools: {task_spec_model.approved_tools}",
            "",
            "## Plan",
        ]

        for step in plan:
            report_lines.append(f"- [{step['id']}] {step['kind']} -> {step['goal']}")

        if should_block:
            report_lines += ["", "## Status", f"Run paused at goal gate: `{pause_reason}`"]
            pause_packet_path = self._save_pause_packet(state)
            state.artifacts.append(str(pause_packet_path))
            report_lines.append(f"- Pause packet saved: {pause_packet_path}")
        else:
            self._execute_plan_steps(
                plan=plan,
                task_spec=task_spec,
                state=state,
                report_lines=report_lines,
                start_index=0,
            )

        self._append_result_section(report_lines, state)
        report_path = self._write_report(run_id, report_lines)
        state.artifacts.append(str(report_path))

        payload = {
            "task": task,
            "task_spec": task_spec,
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
        plan = payload.get("plan", [])
        task_spec = payload.get("task_spec", {})

        state = RunState(**(payload.get("state", {})))
        state.paused = False
        state.approval_required = False
        state.pause_reason = None
        state.final_status = "running"

        decision = self._load_resume_decision(run_id)

        report_lines = [
            "# V2 Resume Report",
            "",
            f"- Run ID: {run_id}",
            f"- Task: {state.task}",
            f"- Workflow: {payload.get('workflow', 'unknown')}",
        ]

        if decision:
            report_lines.append(f"- Resume decision: {decision.decision}")
            report_lines.append(f"- Rationale: {decision.rationale}")
            self._apply_resume_decision(decision, task_spec, state)

            if state.final_status in {"paused", "stopped_by_resume_decision"}:
                report_path = self._write_report(f"resume_{run_id}", report_lines, prefix="final_report_v2")
                state.artifacts.append(str(report_path))
                payload["task_spec"] = task_spec
                payload["state"] = state.model_dump()
                self._save_json(path, payload)
                return report_path

        completed_step_ids = set(state.completed_step_ids)
        start_index = 0
        for idx, step in enumerate(plan):
            if str(step.get("id")) in completed_step_ids:
                start_index = idx + 1
            else:
                break

        report_lines.append(f"- Resume start index: {start_index}")

        self._execute_plan_steps(
            plan=plan,
            task_spec=task_spec,
            state=state,
            report_lines=report_lines,
            start_index=start_index,
        )

        self._append_result_section(report_lines, state)
        report_path = self._write_report(f"resume_{run_id}", report_lines, prefix="final_report_v2")
        state.artifacts.append(str(report_path))

        payload["task_spec"] = task_spec
        payload["state"] = state.model_dump()
        self._save_json(path, payload)
        return report_path
