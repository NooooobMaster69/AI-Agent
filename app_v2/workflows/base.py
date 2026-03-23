from abc import ABC, abstractmethod
from typing import Any


class BaseWorkflow(ABC):
    name = "base"

    @abstractmethod
    def build_plan(self, task_spec, context: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError

    def summarize(self, task_spec, context: dict[str, Any]) -> str:
        return f"Workflow {self.name} prepared for task: {task_spec.user_goal}"