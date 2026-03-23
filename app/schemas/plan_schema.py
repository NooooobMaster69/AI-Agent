from pydantic import BaseModel, Field
from typing import List


class PlanStep(BaseModel):
    id: int
    action: str = Field(
    description="inspect_workspace | local_summarize | run_tests | pause_for_review | web_research_stub | browser_stub | final_report"
    )
    reason: str


class Plan(BaseModel):
    goal: str
    steps: List[PlanStep]
    done_when: List[str]