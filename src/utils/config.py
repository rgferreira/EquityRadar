"""Runtime configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = Path(os.getenv("EQUITY_RADAR_DB_PATH", PROJECT_ROOT / "personal_equity_radar.db"))
FMP_API_KEY = os.getenv("FMP_API_KEY", "")
PORTFOLIO_BASE_CURRENCY = os.getenv("PORTFOLIO_BASE_CURRENCY", "USD").strip().upper()
