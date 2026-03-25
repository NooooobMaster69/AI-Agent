import json
from pathlib import Path

from app_v2.core.cloud_arbitrator import CloudArbitrator
from app_v2.core.executor_runtime import ExecutorRuntime
from app_v2.core.orchestrator_v2 import OrchestratorV2
from app_v2.core.task_understanding import infer_task_spec
from app_v2.policies.permission_broker import approve_tools


def test_noop_step_should_not_pause_on_tool_allowlist():
    runtime = ExecutorRuntime()

    should_block, reason = runtime._pause_if_needed(
        step={"id": 4, "kind": "research", "tool": "none", "goal": "Collect facts"},
        task_spec={"approved_tools": ["report_write"], "allowed_tools": ["report_write"]},
    )

    assert should_block is False
    assert reason is None


def test_cloud_arbitrator_escalates_payment_reason(tmp_path: Path):
    packet_path = tmp_path / "pause_packet.json"
    packet_path.write_text(
        json.dumps(
            {
                "run_id": "20260323_192948",
                "reason": "goal_involves_payment",
                "current_step_id": "4",
                "current_step_kind": "research",
                "task": "buy tea",
                "recent_findings": [],
                "recent_artifacts": [],
                "recent_step_results": [],
                "question_for_cloud": "continue?",
                "decision_path": None,
            }
        ),
        encoding="utf-8",
    )

    arbitrator = CloudArbitrator()
    decision = arbitrator.decide_from_pause_packet(packet_path)

    assert decision.decision == "ask_human"
    assert "Manual approval required" in decision.rationale


def test_set_resume_decision_writes_expected_file(tmp_path: Path, monkeypatch):
    import app_v2.core.orchestrator_v2 as orch_mod

    monkeypatch.setattr(orch_mod, "ARTIFACTS_DIR", tmp_path)

    orchestrator = OrchestratorV2()
    target = orchestrator.set_resume_decision(
        run_id="20260324_000001",
        decision="continue_with_limits",
        rationale="human approved",
        allowed_tools=["filesystem_read", "report_write"],
        allowed_write_paths=["artifacts"],
    )

    assert target.exists()

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["run_id"] == "20260324_000001"
    assert payload["decision"] == "continue_with_limits"
    assert payload["updated_allowed_tools"] == ["filesystem_read", "report_write"]
    assert payload["updated_allowed_write_paths"] == ["artifacts"]


def test_cloud_arbitrator_escalates_purchase_intent_task(tmp_path: Path):
    packet_path = tmp_path / "pause_packet_purchase.json"
    packet_path.write_text(
        json.dumps(
            {
                "run_id": "20260324_120000",
                "reason": "tool_not_allowed",
                "current_step_id": "4",
                "current_step_kind": "research",
                "task": "Search on Amazon and buy green tea",
                "recent_findings": [],
                "recent_artifacts": [],
                "recent_step_results": [],
                "question_for_cloud": "continue?",
                "decision_path": None,
            }
        ),
        encoding="utf-8",
    )

    arbitrator = CloudArbitrator()
    decision = arbitrator.decide_from_pause_packet(packet_path)

    assert decision.decision == "ask_human"
    assert "purchase intent" in decision.rationale.lower()


def test_cloud_arbitrator_force_local_mode(tmp_path: Path):
    packet_path = tmp_path / "pause_packet_force_local.json"
    packet_path.write_text(
        json.dumps(
            {
                "run_id": "20260324_120001",
                "reason": "tool_not_allowed",
                "current_step_id": "4",
                "current_step_kind": "research",
                "task": "Please buy tea on Amazon",
                "recent_findings": [],
                "recent_artifacts": [],
                "recent_step_results": [],
                "question_for_cloud": "continue?",
                "decision_path": None,
            }
        ),
        encoding="utf-8",
    )

    arbitrator = CloudArbitrator()
    decision = arbitrator.decide_from_pause_packet(packet_path, mode="force_local")

    assert decision.decision == "ask_human"


def test_cloud_arbitrator_force_cloud_without_key_falls_back(tmp_path: Path):
    packet_path = tmp_path / "pause_packet_force_cloud.json"
    packet_path.write_text(
        json.dumps(
            {
                "run_id": "20260324_120002",
                "reason": "tool_not_allowed",
                "current_step_id": "4",
                "current_step_kind": "research",
                "task": "collect references",
                "recent_findings": [],
                "recent_artifacts": [],
                "recent_step_results": [],
                "question_for_cloud": "continue?",
                "decision_path": None,
            }
        ),
        encoding="utf-8",
    )

    arbitrator = CloudArbitrator()
    decision = arbitrator.decide_from_pause_packet(packet_path, mode="force_cloud")

    assert decision.rationale.startswith("[forced_cloud_unavailable_fallback]")


def test_final_report_uses_prior_outputs():
    runtime = ExecutorRuntime()

    result = runtime.execute_step(
        step={
            "id": 6,
            "kind": "final_report",
            "tool": "report_write",
            "goal": "Assemble a coherent final draft.",
        },
        task_spec={"approved_tools": ["report_write"], "allowed_tools": ["report_write"]},
        context={
            "run_id": "20260324_104413",
            "task": "Search on Amazon and buy tea for me",
            "step_results": [
                {"status": "completed", "output_text": "Outline: compare tea options by price and rating."},
                {
                    "status": "completed",
                    "step_kind": "research_benchmarks",
                    "output_text": "## Research Notes\n1. Tea Option A\n   - URL: https://example.com/a",
                    "raw_data": {"research_assessment": {"is_valid": True}},
                },
            ],
        },
    )

    assert result.status == "completed"
    assert "Final Recommendation" in result.output_text
    assert "Suggested Options" in result.output_text
    assert "Tea Option A" in result.output_text


def test_general_task_enables_external_research():
    spec = infer_task_spec("Find tea options on Amazon and suggest what to buy")
    assert spec.workflow_hint == "research_writing"
    assert spec.needs_external_research is True


def test_high_risk_tool_approval_keeps_web_research():
    spec = infer_task_spec("Search on Amazon and buy tea for me")
    approved = approve_tools(spec.model_dump())
    assert "web_research" in approved


def test_web_research_fallback_when_provider_errors(monkeypatch):
    runtime = ExecutorRuntime()

    import app_v2.core.executor_runtime as runtime_mod

    def _boom(_: str):
        raise RuntimeError("network blocked")

    monkeypatch.setattr(runtime_mod, "research_query", _boom)

    result = runtime.execute_step(
        step={"id": 4, "kind": "research", "tool": "web_research", "goal": "best tea on amazon"},
        task_spec={"approved_tools": ["web_research"], "allowed_tools": ["web_research"]},
        context={},
    )

    assert result.status == "completed"
    assert "fallback guidance" in result.summary.lower()
    assert "No web results were returned." in result.output_text


def test_web_research_retries_with_task_context(monkeypatch):
    runtime = ExecutorRuntime()

    import app_v2.core.executor_runtime as runtime_mod

    calls: list[str] = []

    def _research(query: str):
        calls.append(query)
        if len(calls) == 1:
            return {"query": query, "engine": "mock", "results": []}
        return {
            "query": query,
            "engine": "mock",
            "results": [{"title": "Top Air Purifier", "url": "https://example.com/ap", "snippet": "good CADR"}],
        }

    monkeypatch.setattr(runtime_mod, "research_query", _research)

    result = runtime.execute_step(
        step={"id": 4, "kind": "research", "tool": "web_research", "goal": "too generic query"},
        task_spec={"approved_tools": ["web_research"], "allowed_tools": ["web_research"]},
        context={"task": "Search on Amazon give me recommendation on air purifier"},
    )

    assert result.status == "completed"
    assert "1 sources" in result.summary
    assert "Top Air Purifier" in result.output_text


def test_web_research_returns_low_confidence_on_irrelevant_results(monkeypatch):
    runtime = ExecutorRuntime()
    import app_v2.core.executor_runtime as runtime_mod

    def _research(query: str):
        return {
            "query": query,
            "engine": "mock",
            "results": [{"title": "Collect by WeTransfer", "url": "https://wetransfer.com", "snippet": "save ideas"}],
        }

    monkeypatch.setattr(runtime_mod, "research_query", _research)

    result = runtime.execute_step(
        step={"id": 4, "kind": "research_benchmarks", "tool": "web_research", "goal": "collect supporting facts for gpu"},
        task_spec={"approved_tools": ["web_research"], "allowed_tools": ["web_research"]},
        context={"task": "what is the best gaming graphic card now"},
    )

    assert result.status == "completed"
    assert "low confidence" in result.summary.lower()
    assert "sources_not_relevant_to_task" in result.risk_signals
    assert result.raw_data["research_assessment"]["is_valid"] is False


def test_resume_decision_tool_aliases_are_normalized():
    orchestrator = OrchestratorV2()
    task_spec = {"allowed_tools": ["report_write"], "approved_tools": ["report_write"]}
    from app_v2.schemas.resume_decision import ResumeDecision

    decision = ResumeDecision(
        run_id="20260325_000001",
        decision="continue_with_limits",
        rationale="ok",
        updated_allowed_tools=["web_search", "web_fetch", "calculator"],
        updated_allowed_write_paths=[],
    )

    state = {
        "run_id": "20260325_000001",
        "task": "test",
    }

    from app_v2.state.run_state import RunState
    run_state = RunState(**state)
    orchestrator._apply_resume_decision(decision, task_spec, run_state)

    assert task_spec["allowed_tools"] == ["web_research", "report_write"]


def test_final_report_refuses_specific_recommendation_without_valid_research():
    runtime = ExecutorRuntime()

    result = runtime.execute_step(
        step={
            "id": 7,
            "kind": "final_report",
            "tool": "report_write",
            "goal": "Assemble final report.",
        },
        task_spec={"approved_tools": ["report_write"], "allowed_tools": ["report_write"]},
        context={
            "task": "What's the best gaming graphic card now",
            "step_results": [
                {
                    "status": "completed",
                    "step_kind": "research_benchmarks",
                    "raw_data": {"research_assessment": {"is_valid": False}},
                }
            ],
        },
    )

    assert result.status == "completed"
    assert "Insufficient reliable external evidence" in result.output_text
    assert "no specific gpu model is asserted" in result.output_text.lower()
