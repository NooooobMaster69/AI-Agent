import json
from ollama import chat

from app.config import LOCAL_MODEL, LOCAL_FAST_MODEL


def _extract_json_block(text: str) -> dict:
    text = text.strip()

    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()

    return json.loads(text)


class LocalWorker:
    def __init__(self, model: str | None = None) -> None:
        self.model = model or LOCAL_MODEL

    def summarize(self, text: str, fast: bool = False) -> str:
        model_name = LOCAL_FAST_MODEL if fast else self.model

        response = chat(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a local worker model. "
                        "Summarize project files, requirements, and code context. "
                        "Be concrete and concise."
                    ),
                },
                {
                    "role": "user",
                    "content": text,
                },
            ],
        )

        return response["message"]["content"].strip()

    def rewrite_file(
        self,
        task: str,
        test_output: str,
        relative_path: str,
        current_content: str,
        fix_goal: str,
        related_context: str = "",
    ) -> dict:
        response = chat(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a local code-fixing worker. "
                        "Do not modify test files unless the user explicitly asks for test changes. "
                        "Return ONLY valid JSON, no markdown fences. "
                        "You must rewrite exactly one existing file and return the FULL new file content.\n\n"
                        "Schema:\n"
                        "{\n"
                        '  "relative_path": "path/to/file.py",\n'
                        '  "reason": "short explanation",\n'
                        '  "new_content": "full file content"\n'
                        "}\n"
                    ),
                },
                {
                    "role": "user",
                    "content": f"""
Task:
{task}

Fix goal:
{fix_goal}

Failing test output:
{test_output}

Target file:
{relative_path}

Current file content:
{current_content}

Related context:
{related_context}

Rewrite the target file so the tests are more likely to pass.
Return only JSON.
""",
                },
            ],
        )

        return _extract_json_block(response["message"]["content"])