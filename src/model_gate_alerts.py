"""Transition-based modal and email alerts for shadow promotion readiness."""

from __future__ import annotations

import hashlib
import json
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Callable

from src.data.database import (
    get_model_gate_exclusions, get_outcome_labels, get_prediction_snapshots,
    get_shadow_decision_snapshots,
    sync_model_gate_alert_state, update_model_gate_email_status,
)
from src.model_registry import COVERAGE_AWARE_SHADOW_VERSION
from src.model_tuning import build_model_tuning_report, prepare_shadow_comparisons
from src.outcome_labels import RELATIVE_LABEL_VERSION
from src.utils.config import (
    MODEL_ALERT_APP_URL, MODEL_ALERT_EMAIL_TO, SMTP_FROM, SMTP_HOST, SMTP_PASSWORD,
    SMTP_PORT, SMTP_USERNAME, SMTP_USE_TLS,
)


@dataclass(frozen=True)
class EmailSettings:
    recipient: str = MODEL_ALERT_EMAIL_TO
    app_url: str = MODEL_ALERT_APP_URL
    host: str = SMTP_HOST
    port: int = SMTP_PORT
    username: str = SMTP_USERNAME
    password: str = SMTP_PASSWORD
    sender: str = SMTP_FROM
    use_tls: bool = SMTP_USE_TLS

    @property
    def configured(self) -> bool:
        authentication_ready = not self.username or bool(self.password)
        return bool(self.recipient and self.host and self.sender and authentication_ready)


def current_gate_evidence(db_path: str | Path | None = None) -> tuple[dict[str, object], str]:
    """Build the current gate report and a privacy-safe immutable evidence signature."""
    rows = prepare_shadow_comparisons(
        get_shadow_decision_snapshots(db_path=db_path),
        get_prediction_snapshots(db_path=db_path),
        get_outcome_labels(label_version=RELATIVE_LABEL_VERSION, db_path=db_path),
    )
    exclusions = set(get_model_gate_exclusions(db_path))
    gate_rows = [row for row in rows if row["ticker"] not in exclusions]
    report = build_model_tuning_report(gate_rows)
    signature_rows = [{
        "shadow_snapshot_id": row["shadow_snapshot_id"],
        "label_status": row["label_status"],
        "outcome_end_date": row["outcome_end_date"],
        "relative_return_pct": row["relative_return_pct"],
    } for row in gate_rows]
    signature = hashlib.sha256(
        json.dumps(
            {"excluded_tickers": sorted(exclusions), "evidence": signature_rows},
            sort_keys=True, separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return report, signature


def send_gate_clearance_email(
    report: dict[str, object], settings: EmailSettings,
    smtp_factory: Callable[..., object] = smtplib.SMTP,
) -> None:
    """Send a minimal research-status email containing no portfolio data."""
    if not settings.configured:
        raise ValueError("Model-gate email settings are incomplete")
    gate = report["gate"]
    message = EmailMessage()
    message["Subject"] = "Equity Radar: shadow model gates are all green"
    message["From"] = settings.sender
    message["To"] = settings.recipient
    lines = [
        "All mandatory Phase 3.9 shadow-model readiness gates are green.",
        f"Readiness: {gate['passed']}/{gate['total']} gates.",
        "This is an invitation to review the evidence; it does not promote or activate the model.",
    ]
    if settings.app_url:
        lines.append(f"Open the Model tuning decision center: {settings.app_url}")
    message.set_content("\n\n".join(lines))
    with smtp_factory(settings.host, settings.port, timeout=15) as smtp:
        if settings.use_tls:
            smtp.starttls()
        if settings.username:
            smtp.login(settings.username, settings.password)
        smtp.send_message(message)


def process_model_gate_alert(
    *, db_path: str | Path | None = None, settings: EmailSettings | None = None,
    smtp_factory: Callable[..., object] = smtplib.SMTP,
) -> tuple[dict[str, object], dict[str, object]]:
    """Synchronize one clearance transition and attempt its email exactly once."""
    report, signature = current_gate_evidence(db_path)
    all_green = bool(report["gate"]["passed"] == report["gate"]["total"])
    state = sync_model_gate_alert_state(
        COVERAGE_AWARE_SHADOW_VERSION, gates_cleared=all_green,
        evidence_signature=signature, db_path=db_path,
    )
    mail = settings or EmailSettings()
    if all_green and state["email_status"] in {"pending", "configuration_required"}:
        if not mail.configured:
            update_model_gate_email_status(
                COVERAGE_AWARE_SHADOW_VERSION, "configuration_required", db_path=db_path,
            )
        else:
            try:
                send_gate_clearance_email(report, mail, smtp_factory)
            except Exception as exc:
                update_model_gate_email_status(
                    COVERAGE_AWARE_SHADOW_VERSION, "failed", error=str(exc)[:500], db_path=db_path,
                )
            else:
                update_model_gate_email_status(
                    COVERAGE_AWARE_SHADOW_VERSION, "sent", db_path=db_path,
                )
        state = sync_model_gate_alert_state(
            COVERAGE_AWARE_SHADOW_VERSION, gates_cleared=True,
            evidence_signature=signature, db_path=db_path,
        )
    return report, state
