from datetime import datetime
from pathlib import Path
import json


from app.tools.web_tools import research_query, save_web_results
from app.tools.browser_tools import browse_url, extract_first_url
from app.schemas.run_state import RunState
from app.schemas.task_spec import TaskSpec
from app.models.openai_client import OpenAIPlanner
from app.models.local_client import LocalWorker
from app.tools.file_tools import inspect_workspace, save_artifact
from app.tools.pytest_runner import run_pytest
from app.tools.code_tools import (
    build_code_index,
    find_relevant_files,
    read_workspace_file,
    backup_and_write_file,
)
from app.config import RUNS_DIR, ARTIFACTS_DIR, MAX_FIX_ROUNDS
from app.policies.risk_policy import should_pause, should_pause_for_goal
from app.policies.permission_broker import approve_tools

class Orchestrator:
    def __init__(self) -> None:
        self.planner = OpenAIPlanner()
        self.local_worker = LocalWorker()
    def _run_json_path(self, run_id: str) -> Path:
        return RUNS_DIR / f"run_{run_id}.json"

    def _save_run_payload(self, run_id: str, payload: dict, state: RunState) -> None:
        run_json = self._run_json_path(run_id)
        payload["state"] = state.model_dump()

        run_json.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        final_state_json = RUNS_DIR / f"run_{run_id}_final_state.json"
        final_state_json.write_text(
            json.dumps(state.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    def _update_runtime_context(
        self,
        payload: dict,
        workspace_summary: str,
        local_summary: str,
        web_payload: dict | None,
        browser_payload: dict | None,
        test_output: str,
    ) -> None:
        payload["runtime_context"] = {
            "workspace_summary": workspace_summary,
            "local_summary": local_summary,
            "web_payload": web_payload,
            "browser_payload": browser_payload,
            "test_output": test_output,
        }

    def _step_confidence(
        self,
        action: str,
        task: str,
        workspace_summary: str,
        web_payload: dict | None = None,
    ) -> float:
        if action == "inspect_workspace":
            return 0.95 if workspace_summary and workspace_summary.strip() else 0.60

        if action == "local_summarize":
            if web_payload and web_payload.get("results"):
                return 0.85
            if workspace_summary and workspace_summary.strip():
                return 0.80
            return 0.40

        if action == "run_tests":
            return 0.95

        if action == "web_research_stub":
            return 0.80 if len(task.strip()) >= 12 else 0.55

        if action == "browser_stub":
            explicit_url = extract_first_url(task)
            if explicit_url:
                return 0.90
            if web_payload and web_payload.get("results"):
                return 0.65
            return 0.35

        if action == "pause_for_review":
            return 0.95

        if action == "final_report":
            return 0.90

        return 0.60


    def _write_confidence(
        self,
        target_file: str,
        returned_path: str,
        relevant_files: list[str],
        new_content: str,
        test_output: str,
        fix_goal: str,
    ) -> float:
        normalized_target = target_file.replace("\\", "/")
        normalized_returned = returned_path.replace("\\", "/")
        normalized_relevant = [f.replace("\\", "/") for f in relevant_files]

        score = 0.0

        if normalized_returned == normalized_target:
            score += 0.45
        elif normalized_returned in normalized_relevant:
            score += 0.25

        if new_content.strip():
            score += 0.20

        if test_output and "Return code:" in test_output:
            score += 0.15

        if fix_goal and fix_goal.strip():
            score += 0.10

        if normalized_returned.endswith((".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml")):
            score += 0.05

        return min(score, 0.95)


    def run(self, task: str) -> Path:
        RUNS_DIR.mkdir(parents=True, exist_ok=True)

        workspace_summary = inspect_workspace()

        task_spec = self.planner.make_task_spec(task=task, workspace_summary=workspace_summary)
        task_spec = TaskSpec(**task_spec).model_dump()
        approved_tools = approve_tools(task_spec)
        task_spec["approved_tools"] = approved_tools

        # 暂时保留旧字段，但把它收紧到“已批准工具”，
        # 避免旧流程继续拿 requested_tools 或 plan 自动扩权。
        task_spec["allowed_tools"] = list(approved_tools)

        goal_pause, goal_reason = should_pause_for_goal(task_spec)

        if goal_pause:
            plan = {
                "goal": task_spec.get("user_goal", task),
                "steps": [],
                "done_when": task_spec.get("done_when", []),
            }
        else:
            plan = self.planner.make_plan(
                task=task,
                workspace_summary=workspace_summary,
                task_spec=task_spec,
            )


        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        task_spec_artifact = ARTIFACTS_DIR / f"task_spec_{run_id}.json"
        task_spec_artifact.write_text(
            json.dumps(task_spec, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        
        state = RunState(
            run_id=run_id,
            task=task,
            current_phase="planning",
            spec=task_spec,
        )
        state.artifacts.append(str(task_spec_artifact))
        state.pending_steps = [step.get("action", "") for step in plan.get("steps", [])]
        if goal_pause:
            state.paused = True
            state.pause_reason = goal_reason or "Paused at goal review."
            state.final_status = "paused"
            state.approval_required = True
            state.approval_context = {
                "phase": "goal_gate",
                "reason": state.pause_reason,
                "risk_level": task_spec.get("risk_level"),
                "ambiguity_level": task_spec.get("ambiguity_level"),
                "requested_tools": task_spec.get("requested_tools", []),
                "approved_tools": task_spec.get("approved_tools", []),
            }
            state.last_action = "goal_gate"
            state.last_action_result = "paused"
            state.last_confidence = 1.0
            state.findings.append(f"Goal gate blocked execution: {state.pause_reason}")      
        
        
        run_json = RUNS_DIR / f"run_{run_id}.json"
        run_payload = {
             "task": task,
             "task_spec": task_spec,
             "plan": plan,
             "state": state.model_dump(),
             "runtime_context": {
                 "workspace_summary": workspace_summary,
                 "local_summary": "",
                 "web_payload": None,
                 "browser_payload": None,
                 "test_output": "",
             },
        }    
        run_json.write_text(
            json.dumps(run_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


        local_summary = ""
        web_payload: dict | None = None
        browser_payload: dict | None = None
        test_output = ""
        change_lines: list[str] = []

        self._update_runtime_context(
            run_payload,
            workspace_summary,
            local_summary,
            web_payload,
            browser_payload,
            test_output,
        )

        for step in plan.get("steps", []):
            action = step.get("action", "")
            state.current_phase = action
            state.last_action = action
            state.last_action_result = "running"


            step_confidence = self._step_confidence(
                action=action,
                task=task,
                workspace_summary=workspace_summary,
                web_payload=web_payload,
            )
            state.last_confidence = step_confidence

            pause, reason = should_pause(
                action=action,
                confidence=step_confidence,
                context={
                    "task_spec": task_spec,
                    "state": state.model_dump(),
                },
            )
            if pause:
                state.paused = True
                state.pause_reason = reason or f"Paused before action: {action}"
                state.final_status = "paused"
                state.approval_required = True
                state.approval_context = {
                    "phase": "plan_step",
                    "action": action,
                    "confidence": step_confidence,
                    "reason": state.pause_reason,
                }
                state.last_action_result = "paused"
                self._update_runtime_context(
                    run_payload,
                    workspace_summary,
                    local_summary,
                    web_payload,
                    browser_payload,
                    test_output,
                )
                self._save_run_payload(run_id, run_payload, state)
                break
            if action == "inspect_workspace":
                workspace_summary = inspect_workspace()

            elif action == "local_summarize":
                summary_input = workspace_summary

                if web_payload and web_payload.get("results"):
                    parts = [f"Research query: {web_payload.get('query', '')}"]
                    for item in web_payload.get("results", [])[:3]:
                        parts.append(
                            "\n".join(
                                [
                                    f"Title: {item.get('title', '')}",
                                    f"URL: {item.get('url', '')}",
                                    f"Snippet: {item.get('snippet', '')}",
                                    f"Page title: {item.get('page_title', '')}",
                                    f"Page text excerpt: {item.get('page_text_excerpt', '')}",
                                ]
                            )
                        )
                    summary_input = "\n\n---\n\n".join(parts)

                local_summary = self.local_worker.summarize(summary_input, fast=False)
                state.findings.append("Generated local summary.")

            elif action == "run_tests":
                test_output = run_pytest()
                self._update_runtime_context(
                    run_payload,
                    workspace_summary,
                    local_summary,
                    web_payload,
                    browser_payload,
                    test_output,
                )
                self._save_run_payload(run_id, run_payload, state)
                state.findings.append("Executed pytest.")
            elif action == "final_report":
                state.completed_steps.append(action)
                if action in state.pending_steps:
                    state.pending_steps.remove(action)
                break
            elif action == "pause_for_review":
                state.paused = True
                state.pause_reason = "manual_review_requested_by_plan"
                state.final_status = "paused"
                state.approval_required = True
                state.approval_context = {
                    "phase": "plan_step",
                    "action": action,
                    "reason": state.pause_reason,
                }
                state.last_action = action
                state.last_action_result = "paused"
                state.completed_steps.append(action)
                if action in state.pending_steps:
                    state.pending_steps.remove(action)
                break

            elif action == "web_research_stub":
                web_payload = research_query(task, max_results=5, fetch_top_n=3)
                web_artifact = save_web_results(web_payload)
                state.artifacts.append(str(web_artifact))
                state.findings.append(
                    f"Collected {len(web_payload.get('results', []))} web results."
                )

            elif action == "browser_stub":
                target_url = extract_first_url(task)

                if not target_url and web_payload and web_payload.get("results"):
                    target_url = web_payload["results"][0].get("url")

                if not target_url:
                    state.findings.append("Browser step skipped: no URL available.")
                else:
                    browser_payload = browse_url(target_url, headless=True)
                    state.artifacts.append(browser_payload["screenshot_path"])
                    state.artifacts.append(browser_payload["text_path"])
                    state.findings.append(f"Browsed URL: {target_url}")
            
            if state.last_action_result == "running":
                state.last_action_result = "completed"            
            state.completed_steps.append(action)
            if action in state.pending_steps:
                state.pending_steps.remove(action)

            self._update_runtime_context(
                run_payload,
                workspace_summary,
                local_summary,
                web_payload,
                browser_payload,
                test_output,
            )
            self._save_run_payload(run_id, run_payload, state)

        should_allow_code_changes = (
            not state.paused
            and any(
                word in task.lower()
                for word in ["fix", "debug", "test", "pytest", "code", "bug", "rewrite"]
            )
        )

        if should_allow_code_changes and "Return code: 0" not in test_output:
            for round_num in range(1, MAX_FIX_ROUNDS + 1):
                code_index = build_code_index()
                fix_plan = self.planner.make_fix_plan(
                    task=task,
                    test_output=test_output,
                    code_index=code_index,
                )

                likely_files = fix_plan.get("likely_files", [])
                search_terms = fix_plan.get("search_terms", [])
                fix_goal = fix_plan.get("fix_goal", "Fix the failing tests.")

                relevant_files = find_relevant_files(likely_files, search_terms)

                if not relevant_files:
                    change_lines.append(f"Round {round_num}: no relevant files found.")
                    break
                non_test_files = [
                    f for f in relevant_files
                    if not (
                        f.replace("\\", "/").startswith("tests/")
                        or "/tests/" in f.replace("\\", "/")
                        or f.endswith("_test.py")
                        or f.replace("\\", "/").split("/")[-1].startswith("test_")
                    )
                ]

                target_file = non_test_files[0] if non_test_files else relevant_files[0]
                current_content = read_workspace_file(target_file)
                related_context_parts = []
                for rel in relevant_files[1:3]:
                    try:
                        related_context_parts.append(f"\n### {rel}\n{read_workspace_file(rel)}")
                    except Exception:
                        pass

                rewrite = self.local_worker.rewrite_file(
                    task=task,
                    test_output=test_output,
                    relative_path=target_file,
                    current_content=current_content,
                    fix_goal=fix_goal,
                    related_context="\n".join(related_context_parts),
                )

                returned_path = rewrite.get("relative_path", target_file)
                reason = rewrite.get("reason", "No reason provided.")
                new_content = rewrite.get("new_content", "")

                normalized_returned = returned_path.replace("\\", "/")
                is_test_file = (
                    normalized_returned.startswith("tests/")
                    or "/tests/" in normalized_returned
                    or normalized_returned.endswith("_test.py")
                    or normalized_returned.split("/")[-1].startswith("test_")
                )

                if is_test_file:
                    state.failure_count += 1
                    state.last_action = "production_write"
                    state.last_action_result = "failed"
                    state.findings.append(f"Refused test-file rewrite: {returned_path}")
                    change_lines.append(
                        f"Round {round_num}: refused to modify test file `{returned_path}`."
                    )
                    break

                if not new_content.strip():
                    state.failure_count += 1
                    state.last_action = "production_write"
                    state.last_action_result = "failed"
                    state.findings.append(f"Empty rewrite content for: {returned_path}")
                    change_lines.append(f"Round {round_num}: model returned empty content for {returned_path}.")
                    break
                state.current_phase = f"fix_round_{round_num}"
                state.last_action = "production_write"
                state.last_action_result = "running"

                write_confidence = self._write_confidence(
                    target_file=target_file,
                    returned_path=returned_path,
                    relevant_files=relevant_files,
                    new_content=new_content,
                    test_output=test_output,
                    fix_goal=fix_goal,
                )
                state.last_confidence = write_confidence

                pause, pause_reason = should_pause(
                    action="production_write",
                    confidence=write_confidence,
                    context={
                        "task_spec": task_spec,
                        "state": state.model_dump(),
                        "intended_write_path": returned_path,
                    },
                )
                if pause:
                    state.paused = True
                    state.pause_reason = pause_reason or f"Write blocked for path: {returned_path}"
                    state.final_status = "paused"
                    state.approval_required = True
                    state.approval_context = {
                        "phase": "fix_round",
                        "round": round_num,
                        "action": "production_write",
                        "target_file": target_file,
                        "returned_path": returned_path,
                        "confidence": write_confidence,
                        "reason": state.pause_reason,
                    }
                    state.last_action_result = "paused"
                    change_lines.append(f"Write blocked before modifying `{returned_path}`: {state.pause_reason}")
                    break

                backup_path = backup_and_write_file(returned_path, new_content)
                state.last_action_result = "completed"
                state.findings.append(f"Rewrote file: {returned_path}")
                change_lines.append(
                    f"Round {round_num}: rewrote `{returned_path}`. Reason: {reason}. Backup: `{backup_path}`"
                )

                test_output = run_pytest()
                self._update_runtime_context(
                    run_payload,
                    workspace_summary,
                    local_summary,
                    web_payload,
                    browser_payload,
                    test_output,
                )
                self._save_run_payload(run_id, run_payload, state)
                if "Return code: 0" in test_output:
                    state.failure_count = 0
                    state.findings.append("Pytest passed after rewrite.")
                else:
                    state.failure_count += 1
                    state.findings.append(f"Pytest still failing after rewrite. failure_count={state.failure_count}")

                    if state.failure_count >= 2:
                        state.paused = True
                        state.pause_reason = "too_many_failures"
                        state.final_status = "paused"
                        state.approval_required = True
                        state.approval_context = {
                            "phase": "fix_round",
                            "round": round_num,
                            "action": "production_write",
                            "reason": state.pause_reason,
                            "failure_count": state.failure_count,
                            "target_file": returned_path,
                        }
                        break                
                if "Return code: 0" in test_output:
                    change_lines.append(f"Round {round_num}: tests passed after rewrite.")
                    break
            else:
                change_lines.append("Reached maximum fix rounds.")

        change_log = "\n".join(change_lines) if change_lines else "No code changes were made."
        if state.paused and state.pause_reason:
            change_log += f"\nExecution paused: {state.pause_reason}"

        if not state.paused:
            state.current_phase = "review"

        if state.paused:
            state.final_status = "paused"
        else:
            state.final_status = (
                "completed" if "Return code: 0" in test_output or not test_output
                else "finished_with_issues"
            )

        self._update_runtime_context(
            run_payload,
            workspace_summary,
            local_summary,
            web_payload,
            browser_payload,
            test_output,
        )

        final_report = self.planner.review(
            task=task,
            workspace_summary=workspace_summary,
            local_summary=local_summary,
            test_output=test_output,
            change_log=change_log,
        )

        artifact = save_artifact(f"final_report_{run_id}.md", final_report)
        state.artifacts.append(str(artifact))
        state.last_action = "final_report"
        state.last_action_result = "completed"

        self._save_run_payload(run_id, run_payload, state)
        return artifact
    
    def resume_run(self, run_id: str) -> Path:
        run_json = self._run_json_path(run_id)
        if not run_json.exists():
            raise FileNotFoundError(f"Run file not found: {run_json}")

        payload = json.loads(run_json.read_text(encoding="utf-8"))

        task = payload.get("task", "")
        task_spec = payload.get("task_spec", {}) or {}
        plan = payload.get("plan", {}) or {}
        state_dict = payload.get("state", {}) or {}

        task_spec.setdefault("requested_tools", task_spec.get("allowed_tools", []))
        task_spec["approved_tools"] = approve_tools(task_spec)
        task_spec["allowed_tools"] = list(task_spec["approved_tools"])
        payload["task_spec"] = task_spec

        state = RunState(**state_dict)

        decision = (state.approval_context or {}).get("decision")
        if state.final_status != "approved_waiting_resume" and decision != "approved":
            raise ValueError(
                "Run is not approved for resume. Approve it first with `py -m app.main approve <run_id>`."
            )

        if not state.pending_steps:
            raise ValueError("Run has no pending steps to resume.")

        state.paused = False
        state.pause_reason = None
        state.approval_required = False
        state.current_phase = "resume"
        state.last_action = "resume_run"
        state.last_action_result = "running"
        state.final_status = "running"

        self._save_run_payload(run_id, payload, state)

        runtime_context = payload.get("runtime_context", {}) or {}

        workspace_summary = runtime_context.get("workspace_summary") or inspect_workspace()
        local_summary = runtime_context.get("local_summary", "")
        web_payload = runtime_context.get("web_payload")
        browser_payload = runtime_context.get("browser_payload")
        test_output = runtime_context.get("test_output", "")
        change_lines: list[str] = ["Resumed from approved paused run."]

        pending_now = list(state.pending_steps)

        for step in plan.get("steps", []):
            action = step.get("action", "")
            if action not in pending_now:
                continue

            state.current_phase = action
            state.last_action = action
            state.last_action_result = "running"

            step_confidence = self._step_confidence(
                action=action,
                task=task,
                workspace_summary=workspace_summary,
                web_payload=web_payload,
            )
            state.last_confidence = step_confidence

            pause, reason = should_pause(
                action=action,
                confidence=step_confidence,
                context={
                    "task_spec": task_spec,
                    "state": state.model_dump(),
                },
            )
            if pause:
                state.paused = True
                state.pause_reason = reason or f"Paused before action: {action}"
                state.final_status = "paused"
                state.approval_required = True
                state.approval_context = {
                    "phase": "plan_step_resume",
                    "action": action,
                    "confidence": step_confidence,
                    "reason": state.pause_reason,
                }
                state.last_action_result = "paused"
                self._update_runtime_context(
                    payload,
                    workspace_summary,
                    local_summary,
                    web_payload,
                    browser_payload,
                    test_output,
                )
                self._save_run_payload(run_id, payload, state)
                break

            if action == "inspect_workspace":
                workspace_summary = inspect_workspace()

            elif action == "local_summarize":
                summary_input = workspace_summary

                if web_payload and web_payload.get("results"):
                    parts = [f"Research query: {web_payload.get('query', '')}"]
                    for item in web_payload.get("results", [])[:3]:
                        parts.append(
                            "\n".join(
                                [
                                    f"Title: {item.get('title', '')}",
                                    f"URL: {item.get('url', '')}",
                                    f"Snippet: {item.get('snippet', '')}",
                                    f"Page title: {item.get('page_title', '')}",
                                    f"Page text excerpt: {item.get('page_text_excerpt', '')}",
                                ]
                            )
                        )
                    summary_input = "\n\n---\n\n".join(parts)

                local_summary = self.local_worker.summarize(summary_input, fast=False)
                state.findings.append("Generated local summary during resume.")

            elif action == "run_tests":
                test_output = run_pytest()
                state.findings.append("Executed pytest during resume.")

            elif action == "web_research_stub":
                web_payload = research_query(task, max_results=5, fetch_top_n=3)
                web_artifact = save_web_results(web_payload)
                state.artifacts.append(str(web_artifact))
                state.findings.append(
                    f"Collected {len(web_payload.get('results', []))} web results during resume."
                )

            elif action == "browser_stub":
                target_url = extract_first_url(task)

                if not target_url and web_payload and web_payload.get("results"):
                    target_url = web_payload["results"][0].get("url")

                if not target_url:
                    state.findings.append("Browser step skipped during resume: no URL available.")
                else:
                    browser_payload = browse_url(target_url, headless=True)
                    state.artifacts.append(browser_payload["screenshot_path"])
                    state.artifacts.append(browser_payload["text_path"])
                    state.findings.append(f"Browsed URL during resume: {target_url}")

            elif action == "pause_for_review":
                state.paused = True
                state.pause_reason = "manual_review_requested_by_plan"
                state.final_status = "paused"
                state.approval_required = True
                state.approval_context = {
                    "phase": "plan_step_resume",
                    "action": action,
                    "reason": state.pause_reason,
                }
                state.last_action_result = "paused"
                break

            elif action == "final_report":
                state.last_action_result = "completed"
                state.completed_steps.append(action)
                if action in state.pending_steps:
                    state.pending_steps.remove(action)
                break

            if state.last_action_result == "running":
                state.last_action_result = "completed"

            state.completed_steps.append(action)
            if action in state.pending_steps:
                state.pending_steps.remove(action)

            self._update_runtime_context(
                payload,
                workspace_summary,
                local_summary,
                web_payload,
                browser_payload,
                test_output,
            )
            self._save_run_payload(run_id, payload, state)

        if not state.paused:
            state.current_phase = "review"

        if state.paused:
            state.final_status = "paused"
        else:
            state.final_status = (
                "completed" if "Return code: 0" in test_output or not test_output
                else "finished_with_issues"
            )

        change_log = "\n".join(change_lines) if change_lines else "Resumed execution with no code changes."
        if state.paused and state.pause_reason:
            change_log += f"\nExecution paused: {state.pause_reason}"

        self._update_runtime_context(
            payload,
            workspace_summary,
            local_summary,
            web_payload,
            browser_payload,
            test_output,
        )

        final_report = self.planner.review(
            task=task,
            workspace_summary=workspace_summary,
            local_summary=local_summary,
            test_output=test_output,
            change_log=change_log,
        )

        artifact = save_artifact(f"final_report_resume_{run_id}.md", final_report)
        state.artifacts.append(str(artifact))
        state.last_action_result = "completed" if not state.paused else "paused"

        self._save_run_payload(run_id, payload, state)
        return artifact    