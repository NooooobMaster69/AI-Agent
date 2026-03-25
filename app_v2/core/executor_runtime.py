from __future__ import annotations

import os
import re
import importlib.util

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
    def __init__(self) -> None:
        self.local_worker = None
        if importlib.util.find_spec("ollama") is not None:
            from app_v2.models.local_client_v2 import LocalWorker

            self.local_worker = LocalWorker()
        self.enable_local_drafter = os.getenv("V2_USE_LOCAL_DRAFTER", "1").strip() == "1"

    def _build_model_final_report(self, *, task: str, sources: list[dict], prior_outputs: list[str]) -> str | None:
        if not self.enable_local_drafter:
            return None
        if self.local_worker is None:
            return None

        compact_sources = [
            {"title": src.get("title", ""), "url": src.get("url", "")}
            for src in sources[:8]
        ]
        prompt = (
            "Write a practical shopping recommendation in markdown.\n"
            "Requirements:\n"
            "1) Start with a direct recommendation summary.\n"
            "2) Include at least 3 concrete option directions (budget/performance/quietness).\n"
            "3) Include exact buying criteria and red flags.\n"
            "4) Do not claim payment or checkout was performed.\n"
            "5) If sources are missing, still provide useful guidance based on common product-evaluation best practices.\n\n"
            f"Task: {task}\n"
            f"Sources: {compact_sources}\n"
            f"Prior notes: {prior_outputs[-4:]}"
        )

        try:
            drafted = self.local_worker.summarize(prompt, fast=False).strip()
            if drafted:
                return drafted
        except Exception:
            return None
        return None

    def _extract_research_sources(self, prior_outputs: list[str]) -> list[dict]:
        sources: list[dict] = []
        current: dict | None = None

        for text in prior_outputs:
            for line in text.splitlines():
                row = line.strip()
                if not row:
                    continue

                match = re.match(r"^\d+\.\s+(.+)$", row)
                if match:
                    title = match.group(1).strip()
                    current = {"title": title, "url": ""}
                    sources.append(current)
                    continue

                if row.startswith("- URL:") and current is not None:
                    current["url"] = row.replace("- URL:", "", 1).strip()

        return sources

    def _format_research_output(self, research_data: dict) -> str:
        query = str(research_data.get("query", "")).strip()
        engine = str(research_data.get("engine", "")).strip()
        results = research_data.get("results", [])

        lines = ["## Research Notes"]
        if query:
            lines.append(f"- Query: {query}")
        if engine:
            lines.append(f"- Engine: {engine}")

        if isinstance(results, list) and results:
            lines += ["", "### Candidate Sources"]
            for idx, item in enumerate(results[:5], start=1):
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title", "Untitled")).strip()
                url = str(item.get("url", "")).strip()
                snippet = str(item.get("snippet", "")).strip()
                lines.append(f"{idx}. {title}")
                if url:
                    lines.append(f"   - URL: {url}")
                if snippet:
                    lines.append(f"   - Note: {snippet[:280]}")
        else:
            lines += [
                "",
                "### Candidate Sources",
                "No web results were returned.",
                "- Try broader keywords (brand/product/category).",
                "- Try a different network/proxy and rerun.",
            ]

        return "\n".join(lines).strip()

    def _run_research_with_retry(self, goal: str, context: dict) -> dict:
        candidate_queries = [goal]

        task_text = str(context.get("task", "")).strip()
        if task_text and task_text not in candidate_queries:
            candidate_queries.append(task_text)

        for query in candidate_queries:
            payload = research_query(query)
            results = payload.get("results", [])
            if isinstance(results, list) and results:
                return payload

        return payload

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
            task = str(context.get("task", "")).strip()
            sources = self._extract_research_sources(prior_outputs)
            drafted = self._build_model_final_report(task=task or goal, sources=sources, prior_outputs=prior_outputs)
            if drafted:
                return drafted

            lines = [
                "# Final Recommendation",
                "",
                f"Task: {task or goal}",
                "",
                "## Safety Boundaries",
                "- Recommendation only. No payment, checkout, or account operations were executed.",
                "",
                "## Suggested Options",
            ]

            if sources:
                for idx, source in enumerate(sources[:5], start=1):
                    title = source.get("title", "").strip() or "Candidate option"
                    url = source.get("url", "").strip()
                    lines.append(f"{idx}. {title}")
                    if url:
                        lines.append(f"   - Link: {url}")
            else:
                lines += [
                    "- No reliable product sources were returned by the search provider in this run.",
                    "- Please rerun with stable network or narrower query (brand + model + budget).",
                ]

            lines += [
                "",
                "## Quick Buying Checklist",
                "- Confirm room size coverage (CADR / square footage).",
                "- Compare filter type and replacement cost.",
                "- Check seller credibility, warranty, and return policy.",
            ]

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
                try:
                    research_data = self._run_research_with_retry(goal, context)
                    serialized = self._format_research_output(research_data)
                    result_count = len(research_data.get("results", []) or [])
                    if result_count:
                        summary = f"Web research completed ({result_count} sources)"
                    else:
                        summary = "Web research completed but returned no sources"
                    confidence = 0.8
                    findings = [f"Researched query: {goal}"]
                except Exception as exc:
                    research_data = {
                        "query": goal,
                        "fallback": [
                            "Web search unavailable in this environment.",
                            "Provide recommendations only; do not execute payment or checkout.",
                            "Present candidate options with price range, ratings, and seller/shipping caveats.",
                        ],
                        "error": str(exc),
                    }
                    serialized = self._format_research_output(research_data)
                    summary = "Web research unavailable; returned fallback guidance"
                    confidence = 0.45
                    findings = [f"Research fallback used for query: {goal}"]
                obs = Observation(
                    source_type="web",
                    source_ref=goal,
                    summary=summary,
                    content_excerpt=serialized[:1000],
                    confidence=confidence,
                )
                return StepResult(
                    step_id=step_id,
                    step_kind=step_kind,
                    status="completed",
                    summary=summary,
                    output_text=serialized[:3000],
                    findings=findings,
                    confidence=confidence,
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
