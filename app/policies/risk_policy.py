HIGH_RISK_ACTIONS = {
    "send_email",
    "submit_form",
    "delete_file",
    "payment",
    "credential_entry",
}

PAUSE_REASONS = {
    "high_risk_action",
    "low_confidence",
    "tool_not_allowed",
    "write_path_not_allowed",
    "conflicting_sources",
    "too_many_failures",
    "goal_requires_human_approval",
    "goal_involves_credentials",
    "goal_involves_payment",
    "goal_irreversible",
    "goal_too_ambiguous",
}

ACTION_TO_TOOL = {
    "inspect_workspace": "filesystem_read",
    "local_summarize": "code_inspection",
    "run_tests": "run_tests",
    "web_research_stub": "web_research",
    "browser_stub": "browser",
    "pause_for_review": "review",
    "final_report": "report_write",
    "production_write": "write_files",
}


def _is_path_allowed(target_path: str, allowed_paths: list[str]) -> bool:
    normalized_target = target_path.replace("\\", "/").strip()
    for allowed in allowed_paths:
        normalized_allowed = allowed.replace("\\", "/").strip().rstrip("/")
        if not normalized_allowed:
            continue
        if normalized_target == normalized_allowed or normalized_target.startswith(normalized_allowed + "/"):
            return True
    return False


def should_pause_for_goal(task_spec: dict | None = None) -> tuple[bool, str | None]:
    task_spec = task_spec or {}

    if task_spec.get("requires_human_approval", False):
        return True, "goal_requires_human_approval"

    if task_spec.get("involves_credentials", False):
        return True, "goal_involves_credentials"

    if task_spec.get("involves_payment", False):
        return True, "goal_involves_payment"

    if task_spec.get("irreversible_action_possible", False):
        return True, "goal_irreversible"

    if task_spec.get("ambiguity_level", "low") == "high":
        return True, "goal_too_ambiguous"

    return False, None


def should_pause(
    action: str,
    confidence: float = 1.0,
    context: dict | None = None,
) -> tuple[bool, str | None]:
    context = context or {}

    if action in HIGH_RISK_ACTIONS:
        return True, "high_risk_action"

    if confidence < 0.5:
        return True, "low_confidence"

    task_spec = context.get("task_spec", {}) or {}

    approved_tools = task_spec.get("approved_tools", []) or []
    allowed_tools = task_spec.get("allowed_tools", []) or []
    effective_tools = approved_tools or allowed_tools

    intended_write_path = context.get("intended_write_path")

    expected_tool = ACTION_TO_TOOL.get(action)
    if expected_tool and effective_tools and expected_tool not in effective_tools:
        return True, "tool_not_allowed"

    allowed_write_paths = task_spec.get("allowed_write_paths", []) or []
    if intended_write_path and allowed_write_paths:
        if not _is_path_allowed(intended_write_path, allowed_write_paths):
            return True, "write_path_not_allowed"

    return False, None