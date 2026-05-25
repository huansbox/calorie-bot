import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN: str = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID: int = int(os.environ["TELEGRAM_CHAT_ID"])
SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_KEY: str = os.environ["SUPABASE_KEY"]

AI_PROVIDER: str = os.getenv("AI_PROVIDER", "gemini")  # "gemini" or "claude"
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_CLI_PATH: str = os.getenv("CLAUDE_CLI_PATH", "/root/.local/bin/claude")

BMR: int = int(os.getenv("BMR", "1577"))
PUSH_HOUR: int = int(os.getenv("PUSH_HOUR", "8"))
DATA_DIR: Path = Path(os.getenv("DATA_DIR", "./data"))
MEDIA_DIR: Path = DATA_DIR / "media"
COROS_TOKEN_PATH: Path = Path(os.getenv("COROS_TOKEN_PATH", str(DATA_DIR / "coros-token.json")))
