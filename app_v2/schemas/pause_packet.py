from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


class PausePacket(BaseModel):
    run_id: str
    reason: str

    current_step_id: str = ""
    current_step_kind: str = ""
    task: str = ""

    recent_findings: List[str] = Field(default_factory=list)
    recent_artifacts: List[str] = Field(default_factory=list)
    recent_step_results: List[Dict[str, Any]] = Field(default_factory=list)

    question_for_cloud: str = ""
    decision_path: Optional[str] = None
