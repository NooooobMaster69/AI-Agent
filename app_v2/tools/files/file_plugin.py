from pathlib import Path
from app.config import WORKSPACE_DIR, ARTIFACTS_DIR, MAX_FILE_CHARS


TEXT_EXTS = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".csv"}


def list_workspace_files() -> list[Path]:
    files: list[Path] = []
    for path in WORKSPACE_DIR.rglob("*"):
        if path.is_file():
            files.append(path)
    return files


def read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:MAX_FILE_CHARS]
    except Exception as e:
        return f"[ERROR reading {path.name}: {e}]"


def inspect_workspace() -> str:
    files = list_workspace_files()
    if not files:
        return "Workspace is empty."

    chunks: list[str] = []
    for path in files[:20]:
        rel = path.relative_to(WORKSPACE_DIR)
        chunks.append(f"\n### FILE: {rel}\n")
        if path.suffix.lower() in TEXT_EXTS:
            chunks.append(read_text_file(path))
        else:
            chunks.append("[Non-text file omitted]")

    return "\n".join(chunks)


def save_artifact(filename: str, content: str) -> Path:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    target = ARTIFACTS_DIR / filename
    target.write_text(content, encoding="utf-8")
    return target