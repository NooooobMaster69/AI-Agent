from app_v2.workflows.base import BaseWorkflow


class ResearchWritingWorkflow(BaseWorkflow):
    name = "research_writing"

    def build_plan(self, task_spec, context: dict) -> list[dict]:
        user_goal = getattr(task_spec, "user_goal", "").strip()
        scoped_goal = user_goal or "the assigned task"

        steps = [
            {
                "id": 1,
                "kind": "understand_requirements",
                "tool": "none",
                "goal": f"Extract the assignment goals, constraints, and deliverables for: {scoped_goal}",
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
                "goal": f"Generate an outline and section plan for: {scoped_goal}",
                "requires_approval": False,
            },
            {
                "id": 4,
                "kind": "research_benchmarks",
                "tool": "web_research" if task_spec.needs_external_research else "none",
                "goal": f"Find current performance benchmark evidence for: {scoped_goal}",
                "requires_approval": False,
            },
            {
                "id": 5,
                "kind": "research_prices",
                "tool": "web_research" if task_spec.needs_external_research else "none",
                "goal": f"Find current price and value evidence for: {scoped_goal}",
                "requires_approval": False,
            },
            {
                "id": 6,
                "kind": "draft_sections",
                "tool": "report_write",
                "goal": "Draft section-by-section content with concrete suggestions and caveats.",
                "requires_approval": False,
            },
            {
                "id": 7,
                "kind": "final_report",
                "tool": "report_write",
                "goal": "Assemble a coherent final draft with recommendations only (no transactions).",
                "requires_approval": False,
            },
        ]
        return steps
