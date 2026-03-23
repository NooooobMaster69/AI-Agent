from pydantic import BaseModel, Field
from typing import List, Literal


RiskLevel = Literal["low", "medium", "high"]
TaskFamily = Literal["operations", "research_writing", "coding", "multimedia", "mixed", "general"]


class TaskSpecV2(BaseModel):
    user_goal: str = Field(description="Original user goal in one sentence")

    task_family: TaskFamily = "general"
    workflow_hint: str = "general"

    must_do: List[str] = Field(default_factory=list)
    must_not_do: List[str] = Field(default_factory=list)

    deliverables: List[str] = Field(default_factory=list)
    deliverable_types: List[str] = Field(default_factory=list)

    requested_tools: List[str] = Field(default_factory=list)
    approved_tools: List[str] = Field(default_factory=list)
    allowed_tools: List[str] = Field(default_factory=list)

    allowed_write_paths: List[str] = Field(default_factory=lambda: ["artifacts", "runs"])

    risk_level: RiskLevel = "medium"
    ambiguity_level: str = "low"

    needs_external_research: bool = False
    needs_example_analysis: bool = False
    needs_longform_output: bool = False
    needs_browser_execution: bool = False
    needs_local_files: bool = False
    needs_code_changes: bool = False
    needs_media_processing: bool = False

    success_criteria: List[str] = Field(default_factory=list)

    requires_human_approval: bool = False
    has_external_side_effects: bool = False
    irreversible_action_possible: bool = False
    involves_credentials: bool = False
    involves_payment: bool = False
    involves_sensitive_data: bool = False
    is_read_only_goal: bool = True
    has_external_write_action: bool = False