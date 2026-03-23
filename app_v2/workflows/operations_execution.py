from app_v2.workflows.base import BaseWorkflow


class OperationsExecutionWorkflow(BaseWorkflow):
    name = "operations_execution"

    def build_plan(self, task_spec, context: dict) -> list[dict]:
        steps = [
            {
                "id": 1,
                "kind": "analyze_task",
                "tool": "none",
                "goal": "Understand the operations/billing task and extract key entities.",
                "requires_approval": False,
            },
            {
                "id": 2,
                "kind": "research",
                "tool": "web_research",
                "goal": "Gather relevant web information or payer/portal context if needed.",
                "requires_approval": False,
            },
            {
                "id": 3,
                "kind": "browser_prep",
                "tool": "browser",
                "goal": "Prepare browser-based execution path if portal interaction is needed.",
                "requires_approval": False,
            },
            {
                "id": 4,
                "kind": "report",
                "tool": "report_write",
                "goal": "Produce findings and recommended next steps.",
                "requires_approval": False,
            },
        ]
        return steps