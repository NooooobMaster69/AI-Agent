import json
from pathlib import Path

from app_v2.core.cloud_arbitrator import CloudArbitrator
from app_v2.core.executor_runtime import ExecutorRuntime
from app_v2.core.orchestrator_v2 import OrchestratorV2


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
