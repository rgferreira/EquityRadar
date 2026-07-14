"""Runtime configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".env.alerts", override=True)

DATABASE_PATH = Path(os.getenv("EQUITY_RADAR_DB_PATH", PROJECT_ROOT / "personal_equity_radar.db"))
FMP_API_KEY = os.getenv("FMP_API_KEY", "")
PORTFOLIO_BASE_CURRENCY = os.getenv("PORTFOLIO_BASE_CURRENCY", "USD").strip().upper()

# Optional, local-only email delivery for model-gate clearance notifications.
MODEL_ALERT_EMAIL_TO = os.getenv("MODEL_ALERT_EMAIL_TO", "").strip()
MODEL_ALERT_APP_URL = os.getenv("MODEL_ALERT_APP_URL", "").strip()
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USERNAME).strip()
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").strip().lower() in {"1", "true", "yes", "on"}
