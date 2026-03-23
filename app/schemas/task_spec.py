from pydantic import BaseModel, Field
from typing import List


class TaskSpec(BaseModel):
    user_goal: str = Field(description="Original user goal in one sentence")
    task_type: str = Field(
        description="Examples: code_task, business_research, browser_task, document_task"
    )

    must_do: List[str] = Field(default_factory=list)
    must_not_do: List[str] = Field(default_factory=list)
    deliverables: List[str] = Field(default_factory=list)

    # Agent first REQUESTS tools. The system should approve them separately.
    requested_tools: List[str] = Field(default_factory=list)
    approved_tools: List[str] = Field(default_factory=list)

    # Keep this for backward compatibility while the rest of the system
    # is still migrating away from the old field.
    allowed_tools: List[str] = Field(default_factory=list)

    allowed_write_paths: List[str] = Field(default_factory=list)
    risk_level: str = Field(description="low | medium | high")
    done_when: List[str] = Field(default_factory=list)

    requires_human_approval: bool = False
    has_external_side_effects: bool = False
    irreversible_action_possible: bool = False
    involves_credentials: bool = False
    involves_payment: bool = False
    involves_sensitive_data: bool = False

    ambiguity_level: str = Field(
        default="low",
        description="low | medium | high",
    )