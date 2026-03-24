from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class RunState(BaseModel):
    run_id: str
    task: str
    current_phase: str = "intake"

    spec: Dict[str, Any] = Field(default_factory=dict)

    completed_steps: List[str] = Field(default_factory=list)
    pending_steps: List[str] = Field(default_factory=list)

    completed_step_ids: List[str] = Field(default_factory=list)
    pending_step_ids: List[str] = Field(default_factory=list)

    findings: List[str] = Field(default_factory=list)
    artifacts: List[str] = Field(default_factory=list)

    step_results: List[Dict[str, Any]] = Field(default_factory=list)
    observations: List[Dict[str, Any]] = Field(default_factory=list)

    current_step_id: Optional[str] = None
    current_step_kind: Optional[str] = None

    paused: bool = False
    pause_reason: Optional[str] = None
    approval_required: bool = False
    approval_context: Dict[str, Any] = Field(default_factory=dict)

    last_action: Optional[str] = None
    last_action_result: Optional[str] = None
    last_confidence: float = 1.0

    failure_count: int = 0

    final_status: str = "running"