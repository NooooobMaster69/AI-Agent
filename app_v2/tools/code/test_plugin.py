import subprocess
import sys

from app.config import WORKSPACE_DIR


def run_pytest() -> str:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"],
            cwd=WORKSPACE_DIR,
            capture_output=True,
            text=True,
            timeout=120,
            shell=False,
        )
        output = []
        output.append(f"Return code: {result.returncode}")
        if result.stdout:
            output.append("\nSTDOUT:\n" + result.stdout)
        if result.stderr:
            output.append("\nSTDERR:\n" + result.stderr)
        return "\n".join(output).strip()
    except subprocess.TimeoutExpired:
        return "Pytest timed out after 120 seconds."
    except FileNotFoundError:
        return "pytest command not found."
    except Exception as e:
        return f"Failed to run pytest: {e}"