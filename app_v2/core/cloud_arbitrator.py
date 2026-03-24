from __future__ import annotations

import json
from pathlib import Path

import requests

from app.config import OPENAI_API_KEY, OPENAI_MODEL
from app_v2.schemas.pause_packet import PausePacket
from app_v2.schemas.resume_decision import ResumeDecision


HIGH_RISK_REASON_KEYWORDS = {"payment", "credential", "irreversible"}
PURCHASE_INTENT_KEYWORDS = {
    "amazon",
    "buy",
    "purchase",
    "checkout",
    "order",
    "cart",
    "pay",
    "付款",
    "购买",
    "下单",
}

SAFE_TOOLS = ["filesystem_read", "code_inspection", "report_write", "review"]
SAFE_PATHS = ["artifacts", "runs"]


class CloudArbitrator:
    """Hybrid arbitrator: cloud LLM when configured, local rules as fallback."""

    def _contains_any(self, text: str, keywords: set[str]) -> bool:
        text_l = (text or "").lower()
        return any(keyword in text_l for keyword in keywords)

    def _local_rule_decision(self, packet: PausePacket) -> ResumeDecision:
        reason = (packet.reason or "").lower()
        task = (packet.task or "").lower()

        decision = ResumeDecision(
            run_id=packet.run_id,
            decision="continue_with_limits",
            rationale=f"Auto decision derived from pause reason: {packet.reason}",
            updated_allowed_tools=SAFE_TOOLS,
            updated_allowed_write_paths=SAFE_PATHS,
        )

        reason_is_high_risk = self._contains_any(reason, HIGH_RISK_REASON_KEYWORDS)
        task_looks_like_purchase = self._contains_any(task, PURCHASE_INTENT_KEYWORDS)

        if reason_is_high_risk or task_looks_like_purchase:
            decision.decision = "ask_human"
            if reason_is_high_risk:
                decision.rationale = f"Manual approval required for high-risk pause reason: {packet.reason}"
            else:
                decision.rationale = "Manual approval required for purchase intent task."

        return decision

    def _cloud_llm_decision(self, packet: PausePacket) -> ResumeDecision:
        endpoint = "https://api.openai.com/v1/chat/completions"

        system_prompt = (
            "You are a safety arbitrator for an autonomous agent. "
            "Return ONLY valid JSON with this schema: "
            "{\"decision\":\"continue|continue_with_limits|ask_human|stop\","
            "\"rationale\":\"string\","
            "\"updated_allowed_tools\":[\"string\"],"
            "\"updated_allowed_write_paths\":[\"string\"]}. "
            "Prefer conservative decisions. If payment, credentials, checkout, purchase, or irreversible actions are implied, return ask_human."
        )

        user_payload = {
            "run_id": packet.run_id,
            "reason": packet.reason,
            "task": packet.task,
            "current_step_kind": packet.current_step_kind,
            "question_for_cloud": packet.question_for_cloud,
            "recent_findings": packet.recent_findings,
        }

        body = {
            "model": OPENAI_MODEL,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "temperature": 0,
        }

        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }

        response = requests.post(endpoint, headers=headers, json=body, timeout=30)
        response.raise_for_status()

        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        parsed = json.loads(content)

        decision = ResumeDecision(
            run_id=packet.run_id,
            decision=parsed.get("decision", "continue_with_limits"),
            rationale=parsed.get("rationale", "Cloud arbitrator decision."),
            updated_allowed_tools=parsed.get("updated_allowed_tools", SAFE_TOOLS),
            updated_allowed_write_paths=parsed.get("updated_allowed_write_paths", SAFE_PATHS),
        )
        return decision

    def decide_from_pause_packet(self, pause_packet_path: Path, mode: str = "auto") -> ResumeDecision:
        payload = json.loads(pause_packet_path.read_text(encoding="utf-8"))
        packet = PausePacket(**payload)

        normalized_mode = (mode or "auto").strip().lower()

        if normalized_mode == "force_local":
            return self._local_rule_decision(packet)

        if normalized_mode == "force_cloud" and not OPENAI_API_KEY.strip():
            fallback = self._local_rule_decision(packet)
            fallback.rationale = "[forced_cloud_unavailable_fallback] OPENAI_API_KEY missing; using local rules"
            return fallback

        if OPENAI_API_KEY.strip() and normalized_mode in {"auto", "force_cloud"}:
            try:
                decision = self._cloud_llm_decision(packet)
                decision.rationale = f"[cloud] {decision.rationale}"
                return decision
            except Exception as exc:
                fallback = self._local_rule_decision(packet)
                fallback.rationale = f"[local_fallback_after_cloud_error] {fallback.rationale}; error={exc}"
                return fallback

        return self._local_rule_decision(packet)
