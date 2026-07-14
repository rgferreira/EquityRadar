from src.data.database import (
    acknowledge_model_gate_modal, get_connection, sync_model_gate_alert_state,
)
from src.model_gate_alerts import (
    EmailSettings, process_model_gate_alert, send_gate_clearance_email,
)


def test_gate_state_alerts_once_per_false_to_true_transition(tmp_path):
    database = tmp_path / "alerts.db"
    dormant = sync_model_gate_alert_state(
        "shadow-v1", gates_cleared=False, evidence_signature="a", db_path=database,
    )
    cleared = sync_model_gate_alert_state(
        "shadow-v1", gates_cleared=True, evidence_signature="b", db_path=database,
    )
    unchanged = sync_model_gate_alert_state(
        "shadow-v1", gates_cleared=True, evidence_signature="c", db_path=database,
    )

    assert dormant["email_status"] == "dormant"
    assert cleared["email_status"] == "pending"
    assert unchanged["email_status"] == "pending"
    acknowledge_model_gate_modal("shadow-v1", database)
    with get_connection(database) as connection:
        assert connection.execute(
            "SELECT modal_acknowledged_at FROM model_gate_alert_state"
        ).fetchone()[0] is not None

    sync_model_gate_alert_state(
        "shadow-v1", gates_cleared=False, evidence_signature="d", db_path=database,
    )
    second = sync_model_gate_alert_state(
        "shadow-v1", gates_cleared=True, evidence_signature="e", db_path=database,
    )
    assert second["email_status"] == "pending"
    assert second["modal_acknowledged_at"] is None


class FakeSMTP:
    messages = []

    def __init__(self, host, port, timeout):
        self.host, self.port, self.timeout = host, port, timeout

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        self.tls = True

    def login(self, username, password):
        self.credentials = (username, password)

    def send_message(self, message):
        self.messages.append(message)


def test_email_contains_review_boundary_and_no_financial_data():
    FakeSMTP.messages.clear()
    settings = EmailSettings(
        recipient="recipient@example.test", app_url="https://private.test/Model-tuning",
        host="smtp.example.test", port=587, username="sender@example.test",
        password="secret", sender="sender@example.test", use_tls=True,
    )
    send_gate_clearance_email(
        {"gate": {"passed": 6, "total": 6}}, settings, smtp_factory=FakeSMTP,
    )

    message = FakeSMTP.messages[0]
    body = message.get_content()
    assert message["To"] == "recipient@example.test"
    assert "does not promote or activate" in body
    assert "private.test/Model-tuning" in body
    assert "portfolio" not in body.lower()


def test_clearance_email_is_deduplicated_while_gates_remain_green(tmp_path, monkeypatch):
    FakeSMTP.messages.clear()
    report = {
        "gate": {
            "passed": 6, "total": 6,
            "criteria": [{"criterion": "Synthetic", "observed": "Pass", "passed": True}],
        },
    }
    monkeypatch.setattr(
        "src.model_gate_alerts.current_gate_evidence", lambda _path: (report, "evidence-1"),
    )
    settings = EmailSettings(
        recipient="recipient@example.test", host="smtp.example.test", port=587,
        username="", password="", sender="sender@example.test", use_tls=False,
    )

    _, first = process_model_gate_alert(
        db_path=tmp_path / "alerts.db", settings=settings, smtp_factory=FakeSMTP,
    )
    _, second = process_model_gate_alert(
        db_path=tmp_path / "alerts.db", settings=settings, smtp_factory=FakeSMTP,
    )

    assert first["email_status"] == "sent"
    assert second["email_status"] == "sent"
    assert len(FakeSMTP.messages) == 1
