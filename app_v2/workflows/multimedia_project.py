from app_v2.workflows.base import BaseWorkflow


class MultimediaProjectWorkflow(BaseWorkflow):
    name = "multimedia_project"

    def build_plan(self, task_spec, context: dict) -> list[dict]:
        return [
            {
                "id": 1,
                "kind": "analyze_media_task",
                "tool": "filesystem_read",
                "goal": "Understand the media project requirements and source assets.",
                "requires_approval": False,
            },
            {
                "id": 2,
                "kind": "production_plan",
                "tool": "report_write",
                "goal": "Produce a media production plan and asset checklist.",
                "requires_approval": False,
            },
        ]