from app_v2.schemas.task_spec_v2 import TaskSpecV2


def select_workflow(task_spec: TaskSpecV2) -> str:
    if task_spec.workflow_hint and task_spec.workflow_hint != "general":
        return task_spec.workflow_hint

    if task_spec.task_family == "operations":
        return "operations_execution"
    if task_spec.task_family == "research_writing":
        return "research_writing"
    if task_spec.task_family == "coding":
        return "coding_project"
    if task_spec.task_family == "multimedia":
        return "multimedia_project"

    return "research_writing"