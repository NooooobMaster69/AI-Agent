from __future__ import annotations

import json
from pathlib import Path

from app_v2.schemas.pause_packet import PausePacket
from app_v2.schemas.resume_decision import ResumeDecision


class CloudArbitrator:
    """Minimal local stand-in for future cloud arbitration."""

    def decide_from_pause_packet(self, pause_packet_path: Path) -> ResumeDecision:
        payload = json.loads(pause_packet_path.read_text(encoding="utf-8"))
        packet = PausePacket(**payload)

        reason = (packet.reason or "").lower()

        # conservative defaults: continue with safe tool limits
        decision = ResumeDecision(
            run_id=packet.run_id,
            decision="continue_with_limits",
            rationale=f"Auto decision derived from pause reason: {packet.reason}",
            updated_allowed_tools=["filesystem_read", "code_inspection", "report_write", "review"],
            updated_allowed_write_paths=["artifacts", "runs"],
        )

        if "payment" in reason or "credential" in reason or "irreversible" in reason:
            decision.decision = "ask_human"
            decision.rationale = f"Manual approval required for high-risk pause reason: {packet.reason}"

        return decision
