from app_v2.workflows.base import BaseWorkflow


class ResearchWritingWorkflow(BaseWorkflow):
    name = "research_writing"

    def build_plan(self, task_spec, context: dict) -> list[dict]:
        steps = [
            {
                "id": 1,
                "kind": "understand_requirements",
                "tool": "none",
                "goal": "Extract the assignment goals, constraints, and deliverables.",
                "requires_approval": False,
            },
            {
                "id": 2,
                "kind": "analyze_examples",
                "tool": "filesystem_read" if task_spec.needs_example_analysis else "none",
                "goal": "Analyze example structure if examples are provided.",
                "requires_approval": False,
            },
            {
                "id": 3,
                "kind": "outline",
                "tool": "report_write",
                "goal": "Generate an outline and section plan.",
                "requires_approval": False,
            },
            {
                "id": 4,
                "kind": "research",
                "tool": "web_research" if task_spec.needs_external_research else "none",
                "goal": "Collect supporting facts, benchmarks, and references.",
                "requires_approval": False,
            },
            {
                "id": 5,
                "kind": "draft_sections",
                "tool": "report_write",
                "goal": "Draft section-by-section content.",
                "requires_approval": False,
            },
            {
                "id": 6,
                "kind": "final_report",
                "tool": "report_write",
                "goal": "Assemble a coherent final draft.",
                "requires_approval": False,
            },
        ]
        return steps