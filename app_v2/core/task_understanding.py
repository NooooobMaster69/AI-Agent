import re
from app_v2.schemas.task_spec_v2 import TaskSpecV2


def has_word(text: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", text) is not None


def has_any_word(text: str, words: list[str]) -> bool:
    return any(has_word(text, w) for w in words)


def infer_task_spec(task: str) -> TaskSpecV2:
    text = task.lower()

    requested_tools = ["filesystem_read", "report_write"]
    deliverables = []
    deliverable_types = []
    success_criteria = []

    task_family = "general"
    workflow_hint = "general"

    needs_external_research = False
    needs_example_analysis = False
    needs_longform_output = False
    needs_browser_execution = False
    needs_local_files = False
    needs_code_changes = False
    needs_media_processing = False

    risk_level = "medium"

    operations_words = ["billing", "claim", "denial", "auth", "portal", "payer", "eligibility"]
    writing_words = ["article", "essay", "report", "paper", "proposal", "write", "chapter"]
    coding_words = ["code", "bug", "fix", "pytest", "repo", "refactor", "python"]
    multimedia_words = ["video", "audio", "voice", "podcast", "edit", "subtitle"]

    credential_words = ["login", "password", "credential", "credentials", "2fa", "otp"]
    payment_words = ["payment", "payments", "charge", "charges", "purchase", "buy", "checkout"]
    write_action_words = ["submit", "upload", "send", "delete", "rebill", "appeal"]

    if has_any_word(text, operations_words):
        task_family = "operations"
        workflow_hint = "operations_execution"
        requested_tools += ["web_research", "browser"]
        needs_external_research = True
        needs_browser_execution = True
        deliverables = ["operations summary", "next-step recommendations"]
        deliverable_types = ["report"]
        success_criteria = [
            "Task is classified",
            "Relevant actions are proposed",
            "Findings are saved",
        ]

    elif "business plan" in text or has_any_word(text, writing_words):
        task_family = "research_writing"
        workflow_hint = "research_writing"
        requested_tools += ["web_research"]
        needs_external_research = True
        needs_longform_output = True
        if has_any_word(text, ["example", "sample"]):
            needs_example_analysis = True
            needs_local_files = True
        deliverables = ["outline", "research notes", "draft report"]
        deliverable_types = ["document"]
        success_criteria = [
            "Outline is generated",
            "Research questions are generated",
            "Draft sections are created",
        ]

    elif has_any_word(text, coding_words):
        task_family = "coding"
        workflow_hint = "coding_project"
        requested_tools += ["code_inspection", "run_tests", "write_files"]
        needs_code_changes = True
        needs_local_files = True
        deliverables = ["code changes", "test results", "summary"]
        deliverable_types = ["code", "report"]
        success_criteria = [
            "Relevant files are identified",
            "Proposed changes are produced",
            "Tests are run if possible",
        ]

    elif has_any_word(text, multimedia_words):
        task_family = "multimedia"
        workflow_hint = "multimedia_project"
        requested_tools += ["filesystem_read"]
        needs_media_processing = True
        needs_local_files = True
        deliverables = ["media plan", "asset list", "production steps"]
        deliverable_types = ["report"]
        success_criteria = [
            "Media task is understood",
            "Production steps are listed",
        ]

    else:
        task_family = "general"
        workflow_hint = "research_writing"
        requested_tools += ["web_research"]
        needs_external_research = True
        deliverables = ["project plan", "summary"]
        deliverable_types = ["report"]
        success_criteria = [
            "Task is understood",
            "A reasonable workflow is selected",
        ]

    if has_any_word(text, credential_words):
        risk_level = "high"

    if has_any_word(text, payment_words):
        risk_level = "high"

    has_external_write_action = has_any_word(text, write_action_words + payment_words)
    is_read_only_goal = not has_external_write_action

    return TaskSpecV2(
        user_goal=task,
        task_family=task_family,
        workflow_hint=workflow_hint,
        deliverables=deliverables,
        deliverable_types=deliverable_types,
        requested_tools=list(dict.fromkeys(requested_tools)),
        risk_level=risk_level,
        needs_external_research=needs_external_research,
        needs_example_analysis=needs_example_analysis,
        needs_longform_output=needs_longform_output,
        needs_browser_execution=needs_browser_execution,
        needs_local_files=needs_local_files,
        needs_code_changes=needs_code_changes,
        needs_media_processing=needs_media_processing,
        success_criteria=success_criteria,
        involves_credentials=has_any_word(text, credential_words),
        involves_payment=has_any_word(text, payment_words),
        is_read_only_goal=is_read_only_goal,
        has_external_write_action=has_external_write_action,
    )
