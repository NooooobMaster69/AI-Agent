import json
from openai import OpenAI

from app.config import OPENAI_API_KEY, OPENAI_MODEL


def _extract_json(text: str) -> dict:
    text = text.strip()

    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()

    return json.loads(text)


class OpenAIPlanner:
    def __init__(self) -> None:
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model = OPENAI_MODEL

    def ask_json(self, system_prompt: str, user_prompt: str) -> dict:
        response = self.client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        text = response.output_text.strip()
        return _extract_json(text)

    def make_task_spec(self, task: str, workspace_summary: str) -> dict:
        system_prompt = """
    You are the task-spec planner of a local AI agent.
    Return ONLY valid JSON.
    Do not use markdown fences.

    Schema:
    {
    "user_goal": "string",
    "task_type": "code_task | business_research | browser_task | document_task | general_task",
    "must_do": ["string"],
    "must_not_do": ["string"],
    "deliverables": ["string"],

    "requested_tools": ["string"],
    "approved_tools": ["string"],
    "allowed_tools": ["string"],

  
    "allowed_write_paths": ["string"],
    "risk_level": "low | medium | high",
    "done_when": ["string"],

    "requires_human_approval": true,     
    "has_external_side_effects": false,
    "irreversible_action_possible": false,
    "involves_credentials": false,
    "involves_payment": false,
    "involves_sensitive_data": false,
    "ambiguity_level": "low | medium | high"
    }

Rules:
- requested_tools must use ONLY these exact names:
  ["filesystem_read", "code_inspection", "run_tests", "web_research", "browser", "review", "report_write", "write_files", "shell"]
- approved_tools should usually be [] because the system will approve tools later.
- allowed_tools should match requested_tools for backward compatibility.
- For research tasks, requested_tools may include "web_research", "browser", "code_inspection", and "report_write" when needed.
- For code tasks, request only the minimum tools needed.
- For code tasks that require modifying existing source files, requested_tools should include "write_files".
- Do not invent tool names like "web_search".
- Be practical and conservative.
- Mark requires_human_approval=true for tasks involving credentials, payments, submission, deletion, or unclear irreversible actions.
- Mark has_external_side_effects=true if the task may affect an external website, third party, account, or real-world system.
- Mark irreversible_action_possible=true if the task may delete, submit, send, or overwrite important data.
- Mark ambiguity_level="high" if the user goal is too unclear for safe autonomous execution.
"""
        user_prompt = f"""
    Task:
    {task}

    Workspace summary:
    {workspace_summary}
    """
        result = self.ask_json(system_prompt, user_prompt)

        # Backward-compatible normalization
        requested_tools = result.get("requested_tools", result.get("allowed_tools", []))
        if not isinstance(requested_tools, list):
            requested_tools = []

        result["requested_tools"] = requested_tools
        result.setdefault("approved_tools", [])

        # Keep old flow alive for now
        result["allowed_tools"] = result.get("allowed_tools", requested_tools) or requested_tools

        result.setdefault("requires_human_approval", False)
        result.setdefault("has_external_side_effects", False)
        result.setdefault("irreversible_action_possible", False)
        result.setdefault("involves_credentials", False)
        result.setdefault("involves_payment", False)
        result.setdefault("involves_sensitive_data", False)
        result.setdefault("ambiguity_level", "low")

        return result
    
    def make_plan(self, task: str, workspace_summary: str, task_spec: dict) -> dict:
        system_prompt = """
You are the planning brain of a local AI agent.
Return ONLY valid JSON.
Do not use markdown fences.

Schema:
{
  "goal": "string",
  "steps": [
    {"id": 1, "action": "inspect_workspace | local_summarize | run_tests | pause_for_review | web_research_stub | browser_stub | final_report", "reason": "string"}
  ],
  "done_when": ["string", "string"]
}

Rules:
- Use the task_spec as the primary contract for planning.
- Do not include run_tests unless the task_spec implies code verification.
- Do not plan code changes unless the task explicitly requires them.
- Keep the plan short and practical.
"""
        user_prompt = f"""
Task:
{task}

Task spec:
{json.dumps(task_spec, indent=2, ensure_ascii=False)}

Workspace summary:
{workspace_summary}
"""
        return self.ask_json(system_prompt, user_prompt)

    def make_fix_plan(self, task: str, test_output: str, code_index: str) -> dict:
        system_prompt = """
You are a debugging planner for a local AI agent.
Return ONLY valid JSON.
Do not use markdown fences.

Schema:
{
  "likely_files": ["relative/path.py"],
  "search_terms": ["function_name", "error_word"],
  "fix_goal": "short sentence"
}
"""
        user_prompt = f"""
Task:
{task}

Test output:
{test_output}

Code index:
{code_index}
"""
        return self.ask_json(system_prompt, user_prompt)

    def review(
        self,
        task: str,
        workspace_summary: str,
        local_summary: str,
        test_output: str,
        change_log: str,
    ) -> str:
        response = self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are the reviewer of a local AI agent. "
                        "Write a concise final report in markdown. "
                        "Start with a section called 'Task Result' that directly answers the user's task. "
                        "For research or summarization tasks, synthesize the actual answer from the Local model summary "
                        "and any available evidence. Do not only describe the process. "
                        "After that, include: task goal, what was inspected, task classification, key findings, "
                        "whether code changes were made, whether tests were run, and the most important next step."
                    ),
                },
                {
                    "role": "user",
                    "content": f"""
Task:
{task}

Workspace summary:
{workspace_summary}

Local model summary:
{local_summary}

Pytest output:
{test_output}

Change log:
{change_log}
""",
                },
            ],
        )
        return response.output_text.strip()