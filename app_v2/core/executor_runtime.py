from __future__ import annotations

from app_v2.policies.risk_policy import should_pause
from app_v2.schemas.observation import Observation
from app_v2.schemas.step_result import StepResult
from app_v2.tools.code.test_plugin import run_pytest
from app_v2.tools.files.file_plugin import inspect_workspace
from app_v2.tools.web.web_research_plugin import research_query


STEP_KIND_TO_ACTION = {
    "inspect_codebase": "inspect_workspace",
    "analyze_examples": "inspect_workspace",
    "analyze_media_task": "inspect_workspace",
    "research": "web_research_stub",
    "browser_prep": "browser_stub",
    "final_report": "final_report",
    "report": "final_report",
    "test": "run_tests",
}

TOOL_TO_ACTION = {
    "filesystem_read": "inspect_workspace",
    "code_inspection": "local_summarize",
    "run_tests": "run_tests",
    "web_research": "web_research_stub",
    "browser": "browser_stub",
    "report_write": "final_report",
    "write_files": "production_write",
}


class ExecutorRuntime:
    def _collect_prior_outputs(self, context: dict) -> list[str]:
        outputs: list[str] = []
        for result in context.get("step_results", []):
            if not isinstance(result, dict):
                continue
            if result.get("status") != "completed":
                continue
            text = str(result.get("output_text", "")).strip()
            if text:
                outputs.append(text)
        return outputs

    def _build_report_text(self, *, step_kind: str, goal: str, context: dict) -> str:
        prior_outputs = self._collect_prior_outputs(context)

        if step_kind == "final_report":
            lines = ["# Final Draft", "", f"Goal: {goal}"]
            if prior_outputs:
                lines += ["", "## Supporting Notes"]
                for idx, text in enumerate(prior_outputs[-4:], start=1):
                    lines += ["", f"### Note {idx}", text]
            else:
                lines += ["", "## Supporting Notes", "No prior notes were available."]
            return "\n".join(lines).strip()

        return f"{step_kind.replace('_', ' ').title()} Notes:\n{goal}"

    def _pause_if_needed(self, step: dict, task_spec: dict) -> tuple[bool, str | None]:
        step_kind = step.get("kind", "unknown")
        tool = step.get("tool", "none")

        # no-op steps should not be blocked by tool checks
        if tool == "none":
            return False, None

        action = TOOL_TO_ACTION.get(tool)
        if action is None:
            action = STEP_KIND_TO_ACTION.get(step_kind, step_kind)

        return should_pause(action=action, confidence=1.0, context={"task_spec": task_spec})

    def execute_step(self, step: dict, task_spec: dict, context: dict | None = None) -> StepResult:
        context = context or {}

        step_id = str(step.get("id"))
        step_kind = step.get("kind", "unknown")
        tool = step.get("tool", "none")
        goal = step.get("goal", "")

        should_block, pause_reason = self._pause_if_needed(step, task_spec)
        if should_block:
            return StepResult(
                step_id=step_id,
                step_kind=step_kind,
                status="paused",
                summary=f"Step paused by policy: {pause_reason}",
                output_text="",
                pause_reason=pause_reason,
                confidence=0.4,
                raw_data={"tool": tool, "goal": goal},
            )

        try:
            if tool == "none":
                obs = Observation(
                    source_type="model",
                    source_ref=step_kind,
                    summary=f"Step analyzed without tools: {goal}",
                    content_excerpt=goal,
                    confidence=0.9,
                )
                return StepResult(
                    step_id=step_id,
                    step_kind=step_kind,
                    status="completed",
                    summary=f"No tool required. Goal understood: {goal}",
                    output_text=goal,
                    findings=[f"Analyzed step '{step_kind}'"],
                    confidence=0.9,
                    raw_data={"tool": tool, "observation": obs.model_dump(), "context": context},
                )

            if tool == "report_write":
                report_text = self._build_report_text(step_kind=step_kind, goal=goal, context=context)
                obs = Observation(
                    source_type="model",
                    source_ref=step_kind,
                    summary="Report content drafted",
                    content_excerpt=report_text,
                    confidence=0.9,
                )
                return StepResult(
                    step_id=step_id,
                    step_kind=step_kind,
                    status="completed",
                    summary=f"Prepared report step: {goal}",
                    output_text=report_text,
                    findings=[f"Drafted report section for '{step_kind}'"],
                    confidence=0.9,
                    raw_data={"tool": tool, "observation": obs.model_dump(), "context": context},
                )

            if tool == "filesystem_read":
                workspace_excerpt = inspect_workspace()
                obs = Observation(
                    source_type="file",
                    source_ref="workspace",
                    summary="Workspace inspected",
                    content_excerpt=workspace_excerpt[:1000],
                    confidence=0.8,
                )
                return StepResult(
                    step_id=step_id,
                    step_kind=step_kind,
                    status="completed",
                    summary="Workspace inspection completed",
                    output_text=workspace_excerpt[:3000],
                    findings=["Workspace contents inspected"],
                    confidence=0.8,
                    raw_data={"tool": tool, "observation": obs.model_dump(), "context": context},
                )

            if tool == "run_tests":
                test_output = run_pytest()
                obs = Observation(
                    source_type="code",
                    source_ref="pytest",
                    summary="Pytest execution finished",
                    content_excerpt=test_output[:1000],
                    confidence=0.75,
                )
                return StepResult(
                    step_id=step_id,
                    step_kind=step_kind,
                    status="completed",
                    summary="Test execution finished",
                    output_text=test_output,
                    findings=["Pytest was executed"],
                    confidence=0.75,
                    raw_data={"tool": tool, "observation": obs.model_dump(), "context": context},
                )

            if tool == "web_research":
                research_data = research_query(goal)
                serialized = str(research_data)
                obs = Observation(
                    source_type="web",
                    source_ref=goal,
                    summary="Web research query completed",
                    content_excerpt=serialized[:1000],
                    confidence=0.8,
                )
                return StepResult(
                    step_id=step_id,
                    step_kind=step_kind,
                    status="completed",
                    summary="Web research completed",
                    output_text=serialized[:3000],
                    findings=[f"Researched query: {goal}"],
                    confidence=0.8,
                    raw_data={"tool": tool, "research": research_data, "observation": obs.model_dump(), "context": context},
                )

            return StepResult(
                step_id=step_id,
                step_kind=step_kind,
                status="failed",
                summary=f"Tool not implemented yet: {tool}",
                output_text="",
                confidence=0.2,
                raw_data={"tool": tool, "goal": goal, "context": context},
            )
        except Exception as exc:
            return StepResult(
                step_id=step_id,
                step_kind=step_kind,
                status="failed",
                summary=f"Tool execution failed: {tool}",
                output_text="",
                confidence=0.1,
                raw_data={"tool": tool, "goal": goal, "error": str(exc), "context": context},
            )
