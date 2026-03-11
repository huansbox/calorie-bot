import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN: str = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID: int = int(os.environ["TELEGRAM_CHAT_ID"])
ANTHROPIC_API_KEY: str = os.environ["ANTHROPIC_API_KEY"]
SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_KEY: str = os.environ["SUPABASE_KEY"]

DAILY_CALORIE_GOAL: int = int(os.getenv("DAILY_CALORIE_GOAL", "2000"))
BMR: int = int(os.getenv("BMR", "1577"))
PUSH_HOUR: int = int(os.getenv("PUSH_HOUR", "8"))
DATA_DIR: Path = Path(os.getenv("DATA_DIR", "./data"))
MEDIA_DIR: Path = DATA_DIR / "media"
