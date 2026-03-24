from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class StepResult(BaseModel):
    step_id: str
    step_kind: str
    status: str = "completed"   # completed / failed / paused / skipped

    summary: str = ""
    output_text: str = ""

    artifacts: List[str] = Field(default_factory=list)
    findings: List[str] = Field(default_factory=list)

    confidence: float = 1.0
    pause_reason: Optional[str] = None

    raw_data: Dict[str, Any] = Field(default_factory=dict)