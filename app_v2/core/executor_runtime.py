from __future__ import annotations

from app_v2.schemas.step_result import StepResult
from app_v2.tools.web.web_research_plugin import research_query
from app_v2.tools.files.file_plugin import inspect_workspace
from app_v2.tools.code.test_plugin import run_pytest
from app_v2.policies.risk_policy import should_pause


class ExecutorRuntime:
    def execute_step(self, step: dict, task_spec: dict, context: dict | None = None) -> StepResult:
        context = context or {}

        step_id = str(step.get("id"))
        step_kind = step.get("kind", "unknown")
        tool = step.get("tool", "none")
        goal = step.get("goal", "")

        if tool == "none":
            return StepResult(
                step_id=step_id,
                step_kind=step_kind,
                status="completed",
                summary=f"No tool required. Goal understood: {goal}",
                output_text=goal,
                confidence=0.9,
            )

        if tool == "report_write":
            return StepResult(
                step_id=step_id,
                step_kind=step_kind,
                status="completed",
                summary=f"Prepared report step: {goal}",
                output_text=f"REPORT STEP: {goal}",
                confidence=0.9,
            )
        if tool == "web_research":
            try:
                data = research_query(goal)
                return StepResult(
                    step_id=step_id,
                    step_kind=step_kind,
                    status="completed",
                    summary="Web research completed",
                    output_text=str(data),
                    findings=[f"Research completed for: {goal}"],
                    raw_data=data,
                    confidence=0.8,
                )
            except Exception as e:
                return StepResult(
                    step_id=step_id,
                    step_kind=step_kind,
                    status="failed",
                    summary=f"Web research failed: {e}",
                    confidence=0.2,
                ) 

        if tool == "browser":
            return StepResult(
                step_id=step_id,
                step_kind=step_kind,
                status="completed",
                summary="Browser step placeholder completed",
                output_text=goal,
                confidence=0.7,
            )   
        if tool == "filesystem_read":
            try:
                text = inspect_workspace()
                return StepResult(
                    step_id=step_id,
                    step_kind=step_kind,
                    status="completed",
                    summary="Workspace inspection completed",
                    output_text=text[:3000],
                    findings=["Workspace inspected"],
                    confidence=0.8,
                )
            except Exception as e:
                return StepResult(
                    step_id=step_id,
                    step_kind=step_kind,
                    status="failed",
                    summary=f"Filesystem read failed: {e}",
                    confidence=0.2,
                )      

        if tool == "run_tests":
            try:
                output = run_pytest()
                return StepResult(
                    step_id=step_id,
                    step_kind=step_kind,
                    status="completed",
                    summary="Tests executed",
                    output_text=output,
                    findings=["Tests executed"],
                    confidence=0.8,
                )
            except Exception as e:
                return StepResult(
                    step_id=step_id,
                    step_kind=step_kind,
                    status="failed",
                    summary=f"Test execution failed: {e}",
                    confidence=0.2,
                )

        pause, reason = should_pause(
            action=step_kind,
            confidence=1.0,
            context={"task_spec": task_spec},
        )

        if pause:
            return StepResult(
                step_id=step_id,
                step_kind=step_kind,
                status="paused",
                summary=f"Step paused by risk policy: {reason}",
                pause_reason=reason,
                confidence=0.3,
            )