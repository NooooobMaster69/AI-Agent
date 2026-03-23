from __future__ import annotations

from pathlib import Path
from datetime import datetime

from app.config import WORKSPACE_DIR, RUNS_DIR, MAX_CODE_FILES, MAX_CODE_FILE_CHARS


CODE_EXTS = {".py", ".txt", ".md", ".json", ".yaml", ".yml", ".toml"}


def _safe_resolve_workspace_path(relative_path: str) -> Path:
    candidate = (WORKSPACE_DIR / relative_path).resolve()
    workspace_resolved = WORKSPACE_DIR.resolve()

    if not str(candidate).startswith(str(workspace_resolved)):
        raise ValueError(f"Refusing to access path outside workspace: {relative_path}")

    return candidate


def list_code_files() -> list[Path]:
    files: list[Path] = []
    for path in WORKSPACE_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in CODE_EXTS:
            files.append(path)
    return files[:MAX_CODE_FILES]


def read_workspace_file(relative_path: str) -> str:
    path = _safe_resolve_workspace_path(relative_path)
    return path.read_text(encoding="utf-8", errors="ignore")[:MAX_CODE_FILE_CHARS]


def build_code_index() -> str:
    files = list_code_files()
    if not files:
        return "No code files found inside workspace."

    chunks: list[str] = []
    for path in files:
        rel = path.relative_to(WORKSPACE_DIR)
        text = path.read_text(encoding="utf-8", errors="ignore")[:1200]
        chunks.append(f"### FILE: {rel}\n{text}\n")

    return "\n".join(chunks)


def find_relevant_files(likely_files: list[str], search_terms: list[str]) -> list[str]:
    files = list_code_files()
    ranked: list[tuple[int, str]] = []

    for path in files:
        rel = str(path.relative_to(WORKSPACE_DIR)).replace("\\", "/")
        score = 0

        is_test_file = rel.startswith("tests/") or "/tests/" in rel or rel.endswith("_test.py") or rel.startswith("test_") or "/test_" in rel

        for lf in likely_files:
            if lf and lf.lower() in rel.lower():
                score += 5

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[:4000].lower()
        except Exception:
            text = ""

        for term in search_terms:
            if term and term.lower() in rel.lower():
                score += 3
            if term and term.lower() in text:
                score += 2

        # 默认强烈惩罚测试文件，优先改生产代码
        if is_test_file:
            score -= 100

        if score > 0:
            ranked.append((score, rel))

    ranked.sort(reverse=True)
    return [rel for _, rel in ranked[:5]]

def backup_and_write_file(relative_path: str, new_content: str) -> str:
    normalized = relative_path.replace("\\", "/")

    is_test_file = (
        normalized.startswith("tests/")
        or "/tests/" in normalized
        or normalized.endswith("_test.py")
        or normalized.split("/")[-1].startswith("test_")
    )

    if is_test_file:
        raise ValueError(f"Refusing to modify test file: {relative_path}")

    target = _safe_resolve_workspace_path(relative_path)

    if not target.exists():
        raise FileNotFoundError(f"Target file does not exist: {relative_path}")

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    backup_dir = RUNS_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{stamp}__{target.name}.bak"
    backup_path = backup_dir / backup_name

    old_content = target.read_text(encoding="utf-8", errors="ignore")
    backup_path.write_text(old_content, encoding="utf-8")

    target.write_text(new_content, encoding="utf-8")
    return str(backup_path)