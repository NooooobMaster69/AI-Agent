ALLOWED_TOOL_NAMES = {
    "filesystem_read",
    "code_inspection",
    "run_tests",
    "web_research",
    "browser",
    "review",
    "report_write",
    "write_files",
    "shell",
}


BASE_SAFE_TOOLS = {
    "filesystem_read",
    "code_inspection",
    "web_research",
    "report_write",
}


RISK_TOOL_MATRIX = {
    "low": {
        "filesystem_read",
        "code_inspection",
        "run_tests",
        "web_research",
        "browser",
        "review",
        "report_write",
        "write_files",
    },
    "medium": {
        "filesystem_read",
        "code_inspection",
        "run_tests",
        "web_research",
        "browser",
        "review",
        "report_write",
    },
    "high": {
        "filesystem_read",
        "code_inspection",
        "web_research",
        "review",
        "report_write",
    },
}


def _normalize_tools(tools: list[str] | None) -> list[str]:
    if not tools:
        return []
    cleaned: list[str] = []
    for tool in tools:
        if not isinstance(tool, str):
            continue
        t = tool.strip()
        if not t:
            continue
        if t in ALLOWED_TOOL_NAMES and t not in cleaned:
            cleaned.append(t)
    return cleaned


def approve_tools(task_spec: dict | None = None) -> list[str]:
    task_spec = task_spec or {}

    requested_tools = _normalize_tools(task_spec.get("requested_tools"))
    risk_level = str(task_spec.get("risk_level", "medium")).lower().strip()

    if risk_level not in RISK_TOOL_MATRIX:
        risk_level = "medium"

    allowed_for_risk = set(RISK_TOOL_MATRIX[risk_level])

    approved = [tool for tool in requested_tools if tool in allowed_for_risk]

    # 高风险目标，即使模型申请了更多工具，也先强制收紧
    if (
        task_spec.get("requires_human_approval", False)
        or task_spec.get("involves_credentials", False)
        or task_spec.get("involves_payment", False)
        or task_spec.get("irreversible_action_possible", False)
        or task_spec.get("ambiguity_level", "low") == "high"
    ):
        approved = [tool for tool in approved if tool in BASE_SAFE_TOOLS]

    return approved
