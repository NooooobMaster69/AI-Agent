from app_v2.workflows.base import BaseWorkflow


class CodingProjectWorkflow(BaseWorkflow):
    name = "coding_project"

    def build_plan(self, task_spec, context: dict) -> list[dict]:
        return [
            {
                "id": 1,
                "kind": "inspect_codebase",
                "tool": "filesystem_read",
                "goal": "Inspect the codebase and identify relevant files.",
                "requires_approval": False,
            },
            {
                "id": 2,
                "kind": "analyze_code",
                "tool": "code_inspection",
                "goal": "Analyze likely root causes and required changes.",
                "requires_approval": False,
            },
            {
                "id": 3,
                "kind": "test",
                "tool": "run_tests",
                "goal": "Run tests if available.",
                "requires_approval": False,
            },
            {
                "id": 4,
                "kind": "report",
                "tool": "report_write",
                "goal": "Summarize findings and proposed actions.",
                "requires_approval": False,
            },
        ]