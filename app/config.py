from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = BASE_DIR / "workspace"
RUNS_DIR = BASE_DIR / "runs"
ARTIFACTS_DIR = BASE_DIR / "artifacts"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
LOCAL_MODEL = os.getenv("LOCAL_MODEL", "deepseek-r1:32b")
LOCAL_FAST_MODEL = os.getenv("LOCAL_FAST_MODEL", "deepseek-r1:14b")

MAX_FILE_CHARS = 12000
MAX_CODE_FILE_CHARS = 16000
MAX_STEPS = 8
MAX_FIX_ROUNDS = 3
MAX_CODE_FILES = 40