from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


class StepResult(BaseModel):
    step_id: str
    step_kind: str
    status: str = "completed"  # completed / failed / paused / skipped

    summary: str = ""
    output_text: str = ""

    artifacts: List[str] = Field(default_factory=list)
    findings: List[str] = Field(default_factory=list)

    confidence: float = 1.0
    risk_signals: List[str] = Field(default_factory=list)
    pause_reason: Optional[str] = None

    raw_data: Dict[str, Any] = Field(default_factory=dict)
