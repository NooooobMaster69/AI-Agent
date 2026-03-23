from pydantic import BaseModel
from typing import List


class FixPlan(BaseModel):
    likely_files: List[str]
    search_terms: List[str]
    fix_goal: str


class FileRewrite(BaseModel):
    relative_path: str
    reason: str
    new_content: str