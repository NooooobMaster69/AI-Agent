from pydantic import BaseModel, Field
from typing import List


class Observation(BaseModel):
    source_type: str  # web / browser / file / code / model
    source_ref: str = ""
    summary: str = ""
    content_excerpt: str = ""
    confidence: float = 1.0
    risk_signals: List[str] = Field(default_factory=list)
