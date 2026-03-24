from pydantic import BaseModel, Field
from typing import Any, Dict, List, Literal, Optional


ResumeDecisionType = Literal["continue", "continue_with_limits", "ask_human", "stop"]


class ResumeDecision(BaseModel):
    run_id: str
    decision: ResumeDecisionType = "continue"
    rationale: str = ""

    updated_allowed_tools: List[str] = Field(default_factory=list)
    updated_allowed_write_paths: List[str] = Field(default_factory=list)

    plan_patch: Dict[str, Any] = Field(default_factory=dict)
    human_questions: List[str] = Field(default_factory=list)
    valid_until: Optional[str] = None
