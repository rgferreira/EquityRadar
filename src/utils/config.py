"""Runtime configuration."""

import os
import stat
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_local_dotenv(path: Path, *, override: bool = False) -> bool:
    """Load an available dotenv file without blocking on an evicted placeholder."""
    try:
        flags = path.stat().st_flags
    except (AttributeError, FileNotFoundError, OSError):
        flags = 0
    dataless_flag = getattr(stat, "SF_DATALESS", 0)
    if dataless_flag and flags & dataless_flag:
        return False
    return load_dotenv(path, override=override)


# Local operational settings survive iCloud eviction. Explicit process variables
# retain precedence; the project dotenv remains a compatibility fallback.
RUNTIME_CONFIG_PATH = Path.home() / "Library/Application Support/EquityRadar/config/runtime.env"
_load_local_dotenv(RUNTIME_CONFIG_PATH)
_load_local_dotenv(PROJECT_ROOT / ".env")
_load_local_dotenv(PROJECT_ROOT / ".env.alerts", override=True)

_default_database_path = (
    Path.home()
    / "Library"
    / "Application Support"
    / "EquityRadar"
    / "data"
    / "personal_equity_radar.db"
)
_database_setting = Path(os.getenv("EQUITY_RADAR_DB_PATH", str(_default_database_path)))
DATABASE_PATH = (
    _database_setting
    if _database_setting.is_absolute()
    else PROJECT_ROOT / _database_setting
)
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
