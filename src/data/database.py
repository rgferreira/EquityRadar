"""SQLite persistence for watchlist and investment journal."""

import sqlite3
import json
from collections.abc import Mapping
from pathlib import Path

from src.utils.config import DATABASE_PATH, PORTFOLIO_BASE_CURRENCY
from src.model_registry import (
    coverage_aware_shadow_registration, current_model_registration,
    previous_live_model_registration, technology_potential_shadow_registration,
)


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path or DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS watchlist (
                ticker TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS portfolio_holdings (
                ticker TEXT PRIMARY KEY,
                shares REAL NOT NULL CHECK(shares >= 0),
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ticker) REFERENCES watchlist(ticker)
            );
            CREATE TABLE IF NOT EXISTS journal_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                action TEXT NOT NULL CHECK(action IN ('watch', 'buy_candidate', 'reject', 'sell_review')),
                thesis TEXT,
                catalyst TEXT,
                main_risk TEXT,
                invalidation_condition TEXT,
                target_price REAL,
                time_horizon TEXT,
                conviction INTEGER NOT NULL CHECK(conviction BETWEEN 1 AND 5),
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS fundamentals_cache (
                ticker TEXT PRIMARY KEY,
                trailing_pe REAL,
                forward_pe REAL,
                price_to_sales_ttm REAL,
                revenue_growth REAL,
                eps_growth REAL,
                reporting_date TEXT,
                period_end TEXT,
                published_at TEXT,
                known_at TEXT,
                known_at_status TEXT,
                provider_name TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS industry_research_cache (
                ticker TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                provider_name TEXT NOT NULL,
                period_end TEXT,
                published_at TEXT,
                known_at TEXT,
                known_at_status TEXT,
                fetched_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS positioning_cache (
                ticker TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                provider_name TEXT NOT NULL,
                reporting_date TEXT,
                period_end TEXT,
                published_at TEXT,
                known_at TEXT,
                known_at_status TEXT,
                fetched_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS extended_hours_cache (
                ticker TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                provider_name TEXT NOT NULL,
                quote_date TEXT,
                fetched_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS positioning_history (
                ticker TEXT NOT NULL,
                snapshot_date TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                provider_name TEXT NOT NULL,
                reporting_date TEXT,
                period_end TEXT,
                published_at TEXT,
                known_at TEXT,
                known_at_status TEXT,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (ticker, snapshot_date)
            );
            CREATE TABLE IF NOT EXISTS portfolio_lots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                purchase_date TEXT,
                shares REAL NOT NULL CHECK(shares > 0),
                price_per_share REAL CHECK(price_per_share > 0),
                fees REAL NOT NULL DEFAULT 0 CHECK(fees >= 0),
                source TEXT NOT NULL DEFAULT 'manual',
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ticker) REFERENCES watchlist(ticker)
            );
            CREATE TABLE IF NOT EXISTS portfolio_sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                sale_date TEXT NOT NULL,
                shares REAL NOT NULL CHECK(shares > 0),
                price_per_share REAL NOT NULL CHECK(price_per_share > 0),
                fees REAL NOT NULL DEFAULT 0 CHECK(fees >= 0),
                cost_basis REAL,
                realized_pl REAL,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ticker) REFERENCES watchlist(ticker)
            );
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                snapshot_date TEXT PRIMARY KEY,
                total_value REAL NOT NULL CHECK(total_value >= 0),
                base_currency TEXT NOT NULL DEFAULT 'USD',
                priced_positions INTEGER NOT NULL CHECK(priced_positions >= 0),
                total_positions INTEGER NOT NULL CHECK(total_positions >= 0),
                captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS cash_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_date TEXT NOT NULL,
                transaction_type TEXT NOT NULL CHECK(transaction_type IN ('deposit','withdrawal','dividend','withholding_tax','fee','adjustment')),
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                ticker TEXT,
                notes TEXT,
                source_sale_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS portfolio_targets (
                ticker TEXT PRIMARY KEY,
                target_weight_pct REAL NOT NULL CHECK(target_weight_pct >= 0 AND target_weight_pct <= 100),
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ticker) REFERENCES watchlist(ticker)
            );
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_key TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS ui_preferences (
                preference_key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS backtest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                as_of_date TEXT NOT NULL,
                coverage TEXT NOT NULL,
                entry_score REAL NOT NULL,
                exit_score REAL NOT NULL,
                entry_signal TEXT NOT NULL,
                exit_signal TEXT NOT NULL,
                technical_score REAL NOT NULL,
                valuation_score REAL NOT NULL,
                risk_score REAL NOT NULL,
                outcome_1m REAL,
                outcome_3m REAL,
                outcome_6m REAL,
                outcome_12m REAL,
                inputs_json TEXT NOT NULL,
                model_version TEXT NOT NULL,
                simulation_source TEXT NOT NULL DEFAULT 'manual',
                suggestion_rationale TEXT,
                outcome_refreshed_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ticker, as_of_date, model_version)
            );
            CREATE TABLE IF NOT EXISTS model_registry (
                model_version TEXT PRIMARY KEY,
                config_json TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('legacy','candidate','champion','retired')),
                is_active INTEGER NOT NULL DEFAULT 0 CHECK(is_active IN (0,1)),
                is_champion INTEGER NOT NULL DEFAULT 0 CHECK(is_champion IN (0,1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                promoted_at TEXT,
                UNIQUE(model_version, config_hash)
            );
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_registered_model
                ON model_registry(is_active) WHERE is_active = 1;
            CREATE UNIQUE INDEX IF NOT EXISTS one_champion_model
                ON model_registry(is_champion) WHERE is_champion = 1;
            CREATE TABLE IF NOT EXISTS prediction_input_snapshots (
                input_snapshot_id TEXT PRIMARY KEY,
                input_json TEXT NOT NULL,
                input_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS prediction_snapshots (
                prediction_id TEXT PRIMARY KEY,
                input_snapshot_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                as_of_date TEXT NOT NULL,
                model_version TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                output_json TEXT NOT NULL,
                output_hash TEXT NOT NULL,
                simulation_source TEXT NOT NULL DEFAULT 'manual',
                suggestion_rationale TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ticker, as_of_date, model_version),
                FOREIGN KEY(input_snapshot_id) REFERENCES prediction_input_snapshots(input_snapshot_id),
                FOREIGN KEY(model_version, config_hash) REFERENCES model_registry(model_version, config_hash)
            );
            CREATE TABLE IF NOT EXISTS legacy_outcome_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                as_of_date TEXT NOT NULL,
                model_version TEXT NOT NULL,
                outcome_1m REAL,
                outcome_3m REAL,
                outcome_6m REAL,
                outcome_12m REAL,
                observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS outcome_label_observations (
                label_id TEXT PRIMARY KEY,
                prediction_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                label_version TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('available','pending','unavailable')),
                unavailable_reason TEXT,
                benchmark_ticker TEXT,
                benchmark_policy_version TEXT NOT NULL,
                timing_convention TEXT NOT NULL,
                cost_bps REAL NOT NULL,
                execution_date TEXT,
                security_entry_price REAL,
                benchmark_entry_price REAL,
                outcomes_json TEXT NOT NULL,
                max_drawdown_6m_pct REAL,
                outcome_hash TEXT NOT NULL,
                observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(prediction_id, label_version),
                FOREIGN KEY(prediction_id) REFERENCES prediction_snapshots(prediction_id)
            );
            CREATE TABLE IF NOT EXISTS evaluation_runs (
                evaluation_id TEXT PRIMARY KEY,
                evaluator_version TEXT NOT NULL,
                label_version TEXT NOT NULL,
                config_json TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                dataset_signature TEXT NOT NULL,
                report_json TEXT NOT NULL,
                report_hash TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('evaluated','insufficient_evidence')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(config_hash, dataset_signature)
            );
            CREATE TABLE IF NOT EXISTS challenger_experiment_runs (
                experiment_id TEXT PRIMARY KEY,
                challenger_version TEXT NOT NULL,
                config_json TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                dataset_signature TEXT NOT NULL,
                report_json TEXT NOT NULL,
                report_hash TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('evaluated','insufficient_evidence')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(config_hash, dataset_signature)
            );
            CREATE TABLE IF NOT EXISTS shadow_decision_snapshots (
                shadow_snapshot_id TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                as_of_date TEXT NOT NULL,
                surface TEXT NOT NULL,
                current_model_version TEXT NOT NULL,
                current_config_hash TEXT NOT NULL,
                challenger_model_version TEXT NOT NULL,
                challenger_config_hash TEXT NOT NULL,
                input_json TEXT NOT NULL,
                input_hash TEXT NOT NULL,
                current_output_json TEXT NOT NULL,
                current_output_hash TEXT NOT NULL,
                challenger_output_json TEXT NOT NULL,
                challenger_output_hash TEXT NOT NULL,
                entry_score_delta REAL NOT NULL,
                signal_changed INTEGER NOT NULL CHECK(signal_changed IN (0,1)),
                coverage_mode TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(current_model_version, current_config_hash)
                    REFERENCES model_registry(model_version, config_hash),
                FOREIGN KEY(challenger_model_version, challenger_config_hash)
                    REFERENCES model_registry(model_version, config_hash)
            );
            CREATE TABLE IF NOT EXISTS backtest_job_items (
                as_of_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('queued','running','completed','failed')),
                error TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(as_of_date, ticker)
            );
            CREATE TABLE IF NOT EXISTS simulation_suggestions (
                suggested_date TEXT PRIMARY KEY,
                trigger_type TEXT NOT NULL,
                rationale TEXT NOT NULL,
                priority REAL NOT NULL,
                evidence_json TEXT NOT NULL,
                source_signature TEXT NOT NULL,
                generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS model_gate_alert_state (
                candidate_model_version TEXT PRIMARY KEY,
                gates_cleared INTEGER NOT NULL CHECK(gates_cleared IN (0,1)),
                evidence_signature TEXT NOT NULL,
                modal_acknowledged_at TEXT,
                email_status TEXT NOT NULL CHECK(email_status IN (
                    'dormant','pending','configuration_required','sent','failed'
                )),
                email_attempted_at TEXT,
                email_sent_at TEXT,
                email_error TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS model_promotion_events (
                promoted_model_version TEXT PRIMARY KEY,
                previous_model_version TEXT NOT NULL,
                decision_type TEXT NOT NULL,
                gates_passed INTEGER NOT NULL,
                gates_total INTEGER NOT NULL,
                override_reason TEXT,
                rollback_model_version TEXT NOT NULL,
                superseded_by TEXT,
                promoted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS operation_runs (
                operation_key TEXT PRIMARY KEY,
                status TEXT NOT NULL CHECK(status IN ('idle','running','completed','failed')),
                started_at TEXT,
                completed_at TEXT,
                detail_json TEXT NOT NULL DEFAULT '{}',
                error TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS research_alerts (
                alert_id TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                severity TEXT NOT NULL CHECK(severity IN ('info','attention','critical')),
                title TEXT NOT NULL,
                detail TEXT NOT NULL,
                evidence_date TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                acknowledged_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ticker, alert_type, evidence_date)
            );
            CREATE TABLE IF NOT EXISTS provider_health_state (
                provider_key TEXT NOT NULL,
                ticker TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','running','healthy','failed')),
                last_attempt_at TEXT,
                last_success_at TEXT,
                last_error TEXT,
                cooldown_until TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(provider_key, ticker)
            );
            CREATE TABLE IF NOT EXISTS provider_health_transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_key TEXT NOT NULL,
                ticker TEXT NOT NULL,
                previous_status TEXT,
                new_status TEXT NOT NULL,
                occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)
        snapshot_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(portfolio_snapshots)")
        }
        cash_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(cash_transactions)")
        }
        if "source_sale_id" not in cash_columns:
            connection.execute("ALTER TABLE cash_transactions ADD COLUMN source_sale_id INTEGER")
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS cash_transactions_source_sale_unique
                ON cash_transactions(source_sale_id) WHERE source_sale_id IS NOT NULL
            """
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (migration_key) VALUES ('sale_cash_link_v1')"
        )
        promotion_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(model_promotion_events)")
        }
        if "superseded_by" not in promotion_columns:
            connection.execute("ALTER TABLE model_promotion_events ADD COLUMN superseded_by TEXT")
        if "base_currency" not in snapshot_columns:
            connection.execute(
                "ALTER TABLE portfolio_snapshots ADD COLUMN base_currency TEXT NOT NULL DEFAULT 'USD'"
            )
        backtest_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(backtest_runs)")
        }
        if "outcome_refreshed_at" not in backtest_columns:
            connection.execute("ALTER TABLE backtest_runs ADD COLUMN outcome_refreshed_at TEXT")
        if "simulation_source" not in backtest_columns:
            connection.execute("ALTER TABLE backtest_runs ADD COLUMN simulation_source TEXT NOT NULL DEFAULT 'manual'")
        if "suggestion_rationale" not in backtest_columns:
            connection.execute("ALTER TABLE backtest_runs ADD COLUMN suggestion_rationale TEXT")
        temporal_tables = (
            "fundamentals_cache", "industry_research_cache", "positioning_cache", "positioning_history",
        )
        for table in temporal_tables:
            existing_columns = {
                row["name"] for row in connection.execute(f"PRAGMA table_info({table})")
            }
            for column in ("period_end", "published_at", "known_at", "known_at_status"):
                if column not in existing_columns:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (migration_key) VALUES ('known_at_semantics_v1')"
        )
        promotion_applied = connection.execute(
            "SELECT 1 FROM schema_migrations WHERE migration_key='coverage_aware_live_promotion_v2'"
        ).fetchone()
        if not promotion_applied:
            connection.execute("UPDATE model_registry SET is_active=0, is_champion=0")
        for model in (
            previous_live_model_registration(), coverage_aware_shadow_registration(),
            current_model_registration(), technology_potential_shadow_registration(),
        ):
            existing_model = connection.execute(
                "SELECT config_hash, config_json FROM model_registry WHERE model_version = ?",
                (model["model_version"],),
            ).fetchone()
            if existing_model and (
                existing_model["config_hash"] != model["config_hash"]
                or existing_model["config_json"] != model["config_json"]
            ):
                raise RuntimeError("Registered model version has a different immutable configuration")
            connection.execute(
                """INSERT OR IGNORE INTO model_registry
                    (model_version, config_json, config_hash, status, is_active, is_champion)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                tuple(model[field] for field in (
                    "model_version", "config_json", "config_hash", "status", "is_active", "is_champion",
                )),
            )
        connection.execute(
            "UPDATE model_registry SET status='retired' WHERE model_version=? AND is_active=0",
            (coverage_aware_shadow_registration()["model_version"],),
        )
        if not promotion_applied:
            current = current_model_registration()
            previous = previous_live_model_registration()
            connection.execute(
                """UPDATE model_registry SET is_active=0, is_champion=0,
                   status=CASE WHEN status='champion' THEN 'retired' ELSE status END
                   WHERE model_version<>?""",
                (current["model_version"],),
            )
            connection.execute(
                """UPDATE model_registry SET is_active=1, is_champion=1, status='champion',
                   promoted_at=CURRENT_TIMESTAMP WHERE model_version=?""",
                (current["model_version"],),
            )
            connection.execute(
                "UPDATE model_registry SET status='retired' WHERE model_version=?",
                (previous["model_version"],),
            )
            connection.execute(
                """INSERT OR IGNORE INTO model_promotion_events
                   (promoted_model_version, previous_model_version, decision_type,
                    gates_passed, gates_total, override_reason, rollback_model_version)
                   VALUES (?, ?, 'explicit_human_all_gates', 6, 6, NULL, ?)""",
                (
                    current["model_version"], previous["model_version"], previous["model_version"],
                ),
            )
            connection.execute(
                "INSERT INTO schema_migrations (migration_key) VALUES ('coverage_aware_live_promotion_v2')"
            )
        connection.execute(
            """UPDATE model_promotion_events SET superseded_by=?
               WHERE promoted_model_version='coverage-aware-renormalized-v2-live'
               AND superseded_by IS NULL""",
            (current_model_registration()["model_version"],),
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (migration_key) VALUES ('model_registry_snapshots_v1')"
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (migration_key) VALUES ('relative_outcome_labels_v1')"
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (migration_key) VALUES ('purged_evaluator_v1')"
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (migration_key) VALUES ('offline_challenger_reports_v1')"
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (migration_key) VALUES ('inactive_shadow_snapshots_v1')"
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (migration_key) VALUES ('technology_potential_shadow_v1')"
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (migration_key) VALUES ('model_gate_alerts_v1')"
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (migration_key) VALUES ('operations_alerts_v1')"
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (migration_key) VALUES ('provider_health_state_v1')"
        )
        provenance_migrated = connection.execute(
            "SELECT 1 FROM schema_migrations WHERE migration_key = 'simulation_provenance_v1'"
        ).fetchone()
        if not provenance_migrated:
            connection.execute(
                """UPDATE backtest_runs
                SET simulation_source='suggested', suggestion_rationale=(
                    SELECT rationale FROM simulation_suggestions
                    WHERE simulation_suggestions.suggested_date=backtest_runs.as_of_date
                )
                WHERE as_of_date IN (SELECT suggested_date FROM simulation_suggestions)"""
            )
            connection.execute(
                "INSERT INTO schema_migrations (migration_key) VALUES ('simulation_provenance_v1')"
            )
        migrated = connection.execute(
            "SELECT 1 FROM schema_migrations WHERE migration_key = 'portfolio_holdings_to_lots_v1'"
        ).fetchone()
        if not migrated:
            connection.execute(
                """
                INSERT INTO portfolio_lots (ticker, shares, source, notes)
                SELECT ticker, shares, 'legacy', 'Migrated from aggregate holding; purchase details unknown'
                FROM portfolio_holdings WHERE shares > 0
                """
            )
            connection.execute(
                "INSERT INTO schema_migrations (migration_key) VALUES ('portfolio_holdings_to_lots_v1')"
            )


def sync_model_gate_alert_state(
    candidate_model_version: str, *, gates_cleared: bool, evidence_signature: str,
    db_path: str | Path | None = None,
) -> dict[str, object]:
    """Persist gate transitions without re-alerting for every new observation."""
    init_db(db_path)
    with get_connection(db_path) as connection:
        existing = connection.execute(
            "SELECT * FROM model_gate_alert_state WHERE candidate_model_version = ?",
            (candidate_model_version,),
        ).fetchone()
        if existing is None:
            connection.execute(
                """INSERT INTO model_gate_alert_state
                    (candidate_model_version, gates_cleared, evidence_signature, email_status)
                   VALUES (?, ?, ?, ?)""",
                (
                    candidate_model_version, int(gates_cleared), evidence_signature,
                    "pending" if gates_cleared else "dormant",
                ),
            )
        elif bool(existing["gates_cleared"]) != gates_cleared:
            connection.execute(
                """UPDATE model_gate_alert_state
                   SET gates_cleared=?, evidence_signature=?, modal_acknowledged_at=NULL,
                       email_status=?, email_attempted_at=NULL, email_sent_at=NULL,
                       email_error=NULL, updated_at=CURRENT_TIMESTAMP
                   WHERE candidate_model_version=?""",
                (
                    int(gates_cleared), evidence_signature,
                    "pending" if gates_cleared else "dormant", candidate_model_version,
                ),
            )
        else:
            connection.execute(
                """UPDATE model_gate_alert_state
                   SET evidence_signature=?, updated_at=CURRENT_TIMESTAMP
                   WHERE candidate_model_version=?""",
                (evidence_signature, candidate_model_version),
            )
        row = connection.execute(
            "SELECT * FROM model_gate_alert_state WHERE candidate_model_version = ?",
            (candidate_model_version,),
        ).fetchone()
        return dict(row)


def acknowledge_model_gate_modal(
    candidate_model_version: str, db_path: str | Path | None = None,
) -> None:
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """UPDATE model_gate_alert_state SET modal_acknowledged_at=CURRENT_TIMESTAMP,
               updated_at=CURRENT_TIMESTAMP WHERE candidate_model_version=?""",
            (candidate_model_version,),
        )


def update_model_gate_email_status(
    candidate_model_version: str, status: str, *, error: str | None = None,
    db_path: str | Path | None = None,
) -> None:
    if status not in {"pending", "configuration_required", "sent", "failed"}:
        raise ValueError(f"Invalid model-gate email status: {status}")
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """UPDATE model_gate_alert_state
               SET email_status=?, email_attempted_at=CASE
                       WHEN ? IN ('sent','failed') THEN CURRENT_TIMESTAMP ELSE email_attempted_at END,
                   email_sent_at=CASE WHEN ?='sent' THEN CURRENT_TIMESTAMP ELSE email_sent_at END,
                   email_error=?, updated_at=CURRENT_TIMESTAMP
               WHERE candidate_model_version=?""",
            (status, status, status, error, candidate_model_version),
        )


DEFAULT_MODEL_GATE_EXCLUSIONS = ("SPY", "BTC-USD", "SPCX")


def get_model_gate_exclusions(db_path: str | Path | None = None) -> list[str]:
    """Return the persisted gate-only exclusion universe without deleting evidence."""
    init_db(db_path)
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT value_json FROM ui_preferences WHERE preference_key='model_gate_exclusions'"
        ).fetchone()
        if row is None:
            value = sorted(DEFAULT_MODEL_GATE_EXCLUSIONS)
            connection.execute(
                """INSERT INTO ui_preferences (preference_key, value_json, updated_at)
                   VALUES ('model_gate_exclusions', ?, CURRENT_TIMESTAMP)""",
                (json.dumps(value),),
            )
            return value
    return sorted({str(item).strip().upper() for item in json.loads(row["value_json"]) if str(item).strip()})


def save_model_gate_exclusions(
    tickers: list[str], db_path: str | Path | None = None,
) -> None:
    """Persist exclusions used only by promotion-readiness calculations."""
    normalized = sorted({ticker.strip().upper() for ticker in tickers if ticker.strip()})
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """INSERT INTO ui_preferences (preference_key, value_json, updated_at)
               VALUES ('model_gate_exclusions', ?, CURRENT_TIMESTAMP)
               ON CONFLICT(preference_key) DO UPDATE SET value_json=excluded.value_json,
                   updated_at=CURRENT_TIMESTAMP""",
            (json.dumps(normalized),),
        )


def save_research_alerts(
    alerts: list[Mapping[str, object]], db_path: str | Path | None = None,
) -> int:
    """Persist deterministic research alerts without duplicating prior evidence."""
    init_db(db_path)
    inserted = 0
    with get_connection(db_path) as connection:
        for alert in alerts:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO research_alerts
                   (alert_id,ticker,alert_type,severity,title,detail,evidence_date,evidence_json)
                   VALUES (?,?,?,?,?,?,?,?)""",
                tuple(alert[field] for field in (
                    "alert_id", "ticker", "alert_type", "severity", "title", "detail",
                    "evidence_date", "evidence_json",
                )),
            )
            inserted += cursor.rowcount
    return inserted


def get_research_alerts(
    *, include_acknowledged: bool = False, db_path: str | Path | None = None,
) -> list[dict[str, object]]:
    init_db(db_path)
    query = "SELECT * FROM research_alerts"
    if not include_acknowledged:
        query += " WHERE acknowledged_at IS NULL"
    query += " ORDER BY evidence_date DESC, created_at DESC"
    with get_connection(db_path) as connection:
        return [dict(row) for row in connection.execute(query).fetchall()]


def acknowledge_research_alert(
    alert_id: str, db_path: str | Path | None = None,
) -> None:
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            "UPDATE research_alerts SET acknowledged_at=CURRENT_TIMESTAMP WHERE alert_id=?",
            (alert_id,),
        )


def record_provider_health(
    provider_key: str, ticker: str, status: str, *, error: str | None = None,
    cooldown_until: str | None = None, db_path: str | Path | None = None,
) -> None:
    """Persist operational provider state without storing provider payloads."""
    if status not in {"pending", "running", "healthy", "failed"}:
        raise ValueError(f"Invalid provider health status: {status}")
    normalized = ticker.strip().upper() or "*"
    with get_connection(db_path) as connection:
        previous = connection.execute(
            "SELECT status FROM provider_health_state WHERE provider_key=? AND ticker=?",
            (provider_key, normalized),
        ).fetchone()
        connection.execute(
            """INSERT INTO provider_health_state
               (provider_key,ticker,status,last_attempt_at,last_success_at,last_error,cooldown_until)
               VALUES (?,?,?,CURRENT_TIMESTAMP,
                       CASE WHEN ?='healthy' THEN CURRENT_TIMESTAMP END,?,?)
               ON CONFLICT(provider_key,ticker) DO UPDATE SET
                 status=excluded.status,last_attempt_at=CURRENT_TIMESTAMP,
                 last_success_at=CASE WHEN excluded.status='healthy' THEN CURRENT_TIMESTAMP
                                      ELSE provider_health_state.last_success_at END,
                 last_error=CASE WHEN excluded.status='failed' THEN excluded.last_error
                                 WHEN excluded.status='healthy' THEN NULL
                                 ELSE provider_health_state.last_error END,
                 cooldown_until=CASE WHEN excluded.status='failed' THEN excluded.cooldown_until
                                     WHEN excluded.status='healthy' THEN NULL
                                     ELSE provider_health_state.cooldown_until END,
                 updated_at=CURRENT_TIMESTAMP""",
            (provider_key, normalized, status, status, error, cooldown_until),
        )
        previous_status = str(previous["status"]) if previous else None
        if previous_status != status:
            connection.execute(
                """INSERT INTO provider_health_transitions
                   (provider_key,ticker,previous_status,new_status) VALUES (?,?,?,?)""",
                (provider_key, normalized, previous_status, status),
            )


def get_provider_health_states(
    db_path: str | Path | None = None,
) -> list[dict[str, object]]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        return [dict(row) for row in connection.execute(
            "SELECT * FROM provider_health_state ORDER BY provider_key,ticker"
        ).fetchall()]


def get_provider_health_transitions(
    db_path: str | Path | None = None,
) -> list[dict[str, object]]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        return [dict(row) for row in connection.execute(
            "SELECT * FROM provider_health_transitions ORDER BY occurred_at,id"
        ).fetchall()]


def save_backtest_run(run: Mapping[str, object], db_path: str | Path | None = None) -> None:
    """Persist a reproducible point-in-time simulation and its separated outcomes."""
    init_db(db_path)
    fields = (
        "ticker", "as_of_date", "coverage", "entry_score", "exit_score", "entry_signal", "exit_signal",
        "technical_score", "valuation_score", "risk_score", "outcome_1m", "outcome_3m",
        "outcome_6m", "outcome_12m", "inputs_json", "model_version",
        "simulation_source", "suggestion_rationale",
    )
    values = [
        (run.get(field) or "manual") if field == "simulation_source" else run.get(field)
        for field in fields
    ]
    with get_connection(db_path) as connection:
        connection.execute(
            f"""INSERT INTO backtest_runs ({', '.join(fields)}) VALUES ({', '.join('?' for _ in fields)})
            ON CONFLICT(ticker, as_of_date, model_version) DO NOTHING
            """,
            values,
        )


def get_backtest_runs(ticker: str | None = None, db_path: str | Path | None = None) -> list[dict[str, object]]:
    init_db(db_path)
    query = """WITH latest_outcomes AS (
        SELECT observations.* FROM legacy_outcome_observations AS observations
        JOIN (
            SELECT ticker, as_of_date, model_version, MAX(id) AS latest_id
            FROM legacy_outcome_observations GROUP BY ticker, as_of_date, model_version
        ) AS latest ON latest.latest_id = observations.id
    )
        SELECT backtest_runs.id, backtest_runs.ticker, backtest_runs.as_of_date,
        backtest_runs.coverage, backtest_runs.entry_score, backtest_runs.exit_score,
        backtest_runs.entry_signal, backtest_runs.exit_signal, backtest_runs.technical_score,
        backtest_runs.valuation_score, backtest_runs.risk_score,
        COALESCE(latest_outcomes.outcome_1m, backtest_runs.outcome_1m) AS outcome_1m,
        COALESCE(latest_outcomes.outcome_3m, backtest_runs.outcome_3m) AS outcome_3m,
        COALESCE(latest_outcomes.outcome_6m, backtest_runs.outcome_6m) AS outcome_6m,
        COALESCE(latest_outcomes.outcome_12m, backtest_runs.outcome_12m) AS outcome_12m,
        backtest_runs.inputs_json, backtest_runs.model_version, backtest_runs.simulation_source,
        backtest_runs.suggestion_rationale,
        COALESCE(latest_outcomes.observed_at, backtest_runs.outcome_refreshed_at) AS outcome_refreshed_at,
        backtest_runs.created_at,
        COALESCE(model_registry.is_active, 0) AS model_is_active,
        COALESCE(model_registry.is_champion, 0) AS model_is_champion,
        COALESCE(model_registry.status, 'legacy_unregistered') AS model_registry_status,
        CASE WHEN prediction_snapshots.prediction_id IS NULL THEN 0 ELSE 1 END AS has_prediction_snapshot
        FROM backtest_runs LEFT JOIN model_registry
        ON model_registry.model_version = backtest_runs.model_version
        LEFT JOIN latest_outcomes ON latest_outcomes.ticker = backtest_runs.ticker
        AND latest_outcomes.as_of_date = backtest_runs.as_of_date
        AND latest_outcomes.model_version = backtest_runs.model_version
        LEFT JOIN prediction_snapshots
        ON prediction_snapshots.ticker = backtest_runs.ticker
        AND prediction_snapshots.as_of_date = backtest_runs.as_of_date
        AND prediction_snapshots.model_version = backtest_runs.model_version"""
    params: tuple[object, ...] = ()
    if ticker:
        query += " WHERE backtest_runs.ticker = ?"
        params = (ticker.strip().upper(),)
    query += " ORDER BY backtest_runs.as_of_date DESC, backtest_runs.ticker"
    with get_connection(db_path) as connection:
        return [dict(row) for row in connection.execute(query, params).fetchall()]


def get_registered_models(db_path: str | Path | None = None) -> list[dict[str, object]]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        return [dict(row) for row in connection.execute(
            "SELECT * FROM model_registry ORDER BY created_at, model_version"
        ).fetchall()]


def get_model_promotion_event(
    model_version: str, db_path: str | Path | None = None,
) -> dict[str, object] | None:
    """Return immutable promotion provenance for one registered model."""
    init_db(db_path)
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM model_promotion_events WHERE promoted_model_version=?",
            (model_version,),
        ).fetchone()
        return dict(row) if row else None


def register_model(model: Mapping[str, object], db_path: str | Path | None = None) -> None:
    """Register an immutable model configuration; never mutate an existing version."""
    init_db(db_path)
    fields = ("model_version", "config_json", "config_hash", "status", "is_active", "is_champion")
    with get_connection(db_path) as connection:
        existing = connection.execute(
            "SELECT * FROM model_registry WHERE model_version = ?", (model["model_version"],)
        ).fetchone()
        if existing:
            if existing["config_hash"] != model["config_hash"] or existing["config_json"] != model["config_json"]:
                raise ValueError("Model version is already registered with a different configuration")
            return
        connection.execute(
            f"INSERT INTO model_registry ({', '.join(fields)}) VALUES ({', '.join('?' for _ in fields)})",
            tuple(model[field] for field in fields),
        )


def set_active_model(
    model_version: str, *, champion: bool = False, db_path: str | Path | None = None,
) -> None:
    """Explicitly activate a registered model; promotion is never inferred from its name."""
    init_db(db_path)
    with get_connection(db_path) as connection:
        if not connection.execute(
            "SELECT 1 FROM model_registry WHERE model_version = ?", (model_version,)
        ).fetchone():
            raise ValueError(f"Unknown registered model: {model_version}")
        connection.execute("UPDATE model_registry SET is_active = 0")
        connection.execute(
            "UPDATE model_registry SET is_active = 1 WHERE model_version = ?", (model_version,)
        )
        if champion:
            connection.execute("UPDATE model_registry SET is_champion = 0 WHERE is_champion = 1")
            connection.execute(
                """UPDATE model_registry SET is_champion = 1, status = 'champion',
                   promoted_at = CURRENT_TIMESTAMP WHERE model_version = ?""",
                (model_version,),
            )


def save_prediction_snapshot(
    snapshot: Mapping[str, object], db_path: str | Path | None = None,
) -> None:
    """Persist immutable input/prediction content, idempotently by identity."""
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """INSERT OR IGNORE INTO prediction_input_snapshots
               (input_snapshot_id, input_json, input_hash) VALUES (?, ?, ?)""",
            (snapshot["input_snapshot_id"], snapshot["input_json"], snapshot["input_hash"]),
        )
        stored_input = connection.execute(
            "SELECT input_json, input_hash FROM prediction_input_snapshots WHERE input_snapshot_id = ?",
            (snapshot["input_snapshot_id"],),
        ).fetchone()
        if stored_input["input_json"] != snapshot["input_json"] or stored_input["input_hash"] != snapshot["input_hash"]:
            raise ValueError("Immutable input snapshot conflict")
        fields = (
            "prediction_id", "input_snapshot_id", "ticker", "as_of_date", "model_version",
            "config_hash", "output_json", "output_hash", "simulation_source", "suggestion_rationale",
        )
        connection.execute(
            f"INSERT OR IGNORE INTO prediction_snapshots ({', '.join(fields)}) VALUES ({', '.join('?' for _ in fields)})",
            tuple(snapshot.get(field) for field in fields),
        )
        stored = connection.execute(
            "SELECT * FROM prediction_snapshots WHERE prediction_id = ?", (snapshot["prediction_id"],)
        ).fetchone()
        immutable_fields = fields[:8]
        if any(stored[field] != snapshot.get(field) for field in immutable_fields):
            raise ValueError("Immutable prediction snapshot conflict")


def get_prediction_snapshots(
    ticker: str | None = None, db_path: str | Path | None = None,
) -> list[dict[str, object]]:
    init_db(db_path)
    query = """SELECT prediction_snapshots.*, prediction_input_snapshots.input_json,
        prediction_input_snapshots.input_hash, model_registry.status AS model_status,
        model_registry.is_active, model_registry.is_champion
        FROM prediction_snapshots
        JOIN prediction_input_snapshots USING(input_snapshot_id)
        JOIN model_registry USING(model_version, config_hash)"""
    params: tuple[object, ...] = ()
    if ticker:
        query += " WHERE prediction_snapshots.ticker = ?"
        params = (ticker.strip().upper(),)
    query += " ORDER BY prediction_snapshots.as_of_date DESC, prediction_snapshots.ticker"
    with get_connection(db_path) as connection:
        return [dict(row) for row in connection.execute(query, params).fetchall()]


def get_prediction_snapshot(
    prediction_id: str, db_path: str | Path | None = None,
) -> dict[str, object] | None:
    snapshots = get_prediction_snapshots(db_path=db_path)
    return next((row for row in snapshots if row["prediction_id"] == prediction_id), None)


def save_outcome_label(
    label: Mapping[str, object], db_path: str | Path | None = None,
) -> None:
    """Persist one immutable, versioned outcome label per prediction."""
    init_db(db_path)
    fields = (
        "label_id", "prediction_id", "ticker", "label_version", "status",
        "unavailable_reason", "benchmark_ticker", "benchmark_policy_version",
        "timing_convention", "cost_bps", "execution_date", "security_entry_price",
        "benchmark_entry_price", "outcomes_json", "max_drawdown_6m_pct", "outcome_hash",
    )
    values = {
        **dict(label),
        "outcomes_json": json.dumps(
            label.get("outcomes") or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ),
    }
    with get_connection(db_path) as connection:
        connection.execute(
            f"INSERT OR IGNORE INTO outcome_label_observations ({', '.join(fields)}) "
            f"VALUES ({', '.join('?' for _ in fields)})",
            tuple(values.get(field) for field in fields),
        )
        stored = connection.execute(
            "SELECT * FROM outcome_label_observations WHERE prediction_id=? AND label_version=?",
            (label["prediction_id"], label["label_version"]),
        ).fetchone()
        if stored is None or stored["outcome_hash"] != label["outcome_hash"]:
            raise ValueError("Immutable outcome label conflict")


def get_outcome_labels(
    *, prediction_id: str | None = None, label_version: str | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, object]]:
    init_db(db_path)
    clauses: list[str] = []
    params: list[object] = []
    if prediction_id:
        clauses.append("prediction_id = ?")
        params.append(prediction_id)
    if label_version:
        clauses.append("label_version = ?")
        params.append(label_version)
    query = "SELECT * FROM outcome_label_observations"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY observed_at, ticker"
    with get_connection(db_path) as connection:
        rows = [dict(row) for row in connection.execute(query, params).fetchall()]
    for row in rows:
        row["outcomes"] = json.loads(str(row["outcomes_json"]))
    return rows


def get_evaluation_dataset(
    label_version: str, db_path: str | Path | None = None,
) -> list[dict[str, object]]:
    """Read immutable predictions joined only to the requested label contract."""
    init_db(db_path)
    query = """SELECT predictions.prediction_id, predictions.ticker, predictions.as_of_date,
        predictions.model_version, predictions.config_hash, predictions.output_json,
        predictions.output_hash, inputs.input_json, inputs.input_hash,
        labels.label_version, labels.status AS label_status, labels.outcomes_json,
        labels.outcome_hash, labels.execution_date, labels.benchmark_ticker,
        labels.timing_convention, labels.cost_bps, labels.max_drawdown_6m_pct
        FROM prediction_snapshots AS predictions
        JOIN prediction_input_snapshots AS inputs USING(input_snapshot_id)
        JOIN outcome_label_observations AS labels USING(prediction_id)
        WHERE labels.label_version = ?
        ORDER BY predictions.as_of_date, predictions.ticker"""
    with get_connection(db_path) as connection:
        return [dict(row) for row in connection.execute(query, (label_version,)).fetchall()]


def save_evaluation_run(
    report: Mapping[str, object], db_path: str | Path | None = None,
) -> None:
    """Persist an immutable offline report; this has no model-promotion side effect."""
    init_db(db_path)
    config_json = json.dumps(
        report["config"], sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )
    report_json = json.dumps(dict(report), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    fields = (
        "evaluation_id", "evaluator_version", "label_version", "config_json", "config_hash",
        "dataset_signature", "report_json", "report_hash", "status",
    )
    values = {
        **dict(report), "label_version": report["config"]["label_version"],
        "config_json": config_json, "report_json": report_json,
    }
    with get_connection(db_path) as connection:
        connection.execute(
            f"INSERT OR IGNORE INTO evaluation_runs ({', '.join(fields)}) "
            f"VALUES ({', '.join('?' for _ in fields)})",
            tuple(values[field] for field in fields),
        )
        stored = connection.execute(
            "SELECT report_hash FROM evaluation_runs WHERE evaluation_id = ?",
            (report["evaluation_id"],),
        ).fetchone()
        if stored is None or stored["report_hash"] != report["report_hash"]:
            raise ValueError("Immutable evaluation report conflict")


def get_evaluation_runs(db_path: str | Path | None = None) -> list[dict[str, object]]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        rows = [dict(row) for row in connection.execute(
            "SELECT * FROM evaluation_runs ORDER BY created_at DESC, evaluation_id"
        ).fetchall()]
    for row in rows:
        row["config"] = json.loads(str(row["config_json"]))
        row["report"] = json.loads(str(row["report_json"]))
    return rows


def save_challenger_experiment(
    report: Mapping[str, object], db_path: str | Path | None = None,
) -> None:
    """Persist an immutable research report without any model-registry mutation."""
    init_db(db_path)
    config_json = json.dumps(report["config"], sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    report_json = json.dumps(dict(report), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    fields = (
        "experiment_id", "challenger_version", "config_json", "config_hash",
        "dataset_signature", "report_json", "report_hash", "status",
    )
    values = {**dict(report), "config_json": config_json, "report_json": report_json}
    with get_connection(db_path) as connection:
        connection.execute(
            f"INSERT OR IGNORE INTO challenger_experiment_runs ({', '.join(fields)}) "
            f"VALUES ({', '.join('?' for _ in fields)})",
            tuple(values[field] for field in fields),
        )
        stored = connection.execute(
            "SELECT report_hash FROM challenger_experiment_runs WHERE experiment_id = ?",
            (report["experiment_id"],),
        ).fetchone()
        if stored is None or stored["report_hash"] != report["report_hash"]:
            raise ValueError("Immutable challenger experiment conflict")


def get_challenger_experiments(db_path: str | Path | None = None) -> list[dict[str, object]]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        rows = [dict(row) for row in connection.execute(
            "SELECT * FROM challenger_experiment_runs ORDER BY created_at DESC, experiment_id"
        ).fetchall()]
    for row in rows:
        row["config"] = json.loads(str(row["config_json"]))
        row["report"] = json.loads(str(row["report_json"]))
    return rows


def save_shadow_decision_snapshot(
    snapshot: Mapping[str, object], db_path: str | Path | None = None,
) -> None:
    """Append an immutable inactive-candidate comparison; never change model activity."""
    init_db(db_path)
    fields = (
        "shadow_snapshot_id", "ticker", "as_of_date", "surface",
        "current_model_version", "current_config_hash", "challenger_model_version",
        "challenger_config_hash", "input_json", "input_hash", "current_output_json",
        "current_output_hash", "challenger_output_json", "challenger_output_hash",
        "entry_score_delta", "signal_changed", "coverage_mode",
    )
    with get_connection(db_path) as connection:
        connection.execute(
            f"INSERT OR IGNORE INTO shadow_decision_snapshots ({', '.join(fields)}) "
            f"VALUES ({', '.join('?' for _ in fields)})",
            tuple(snapshot[field] for field in fields),
        )
        stored = connection.execute(
            "SELECT * FROM shadow_decision_snapshots WHERE shadow_snapshot_id = ?",
            (snapshot["shadow_snapshot_id"],),
        ).fetchone()
        immutable = fields
        if stored is None or any(stored[field] != snapshot[field] for field in immutable):
            raise ValueError("Immutable shadow decision conflict")


def get_shadow_decision_snapshots(
    ticker: str | None = None, db_path: str | Path | None = None,
) -> list[dict[str, object]]:
    init_db(db_path)
    query = "SELECT * FROM shadow_decision_snapshots"
    params: tuple[object, ...] = ()
    if ticker:
        query += " WHERE ticker = ?"
        params = (ticker.strip().upper(),)
    query += " ORDER BY as_of_date DESC, created_at DESC, ticker"
    with get_connection(db_path) as connection:
        return [dict(row) for row in connection.execute(query, params).fetchall()]


def update_backtest_outcomes(
    ticker: str, as_of_date: str, outcomes: Mapping[str, object],
    db_path: str | Path | None = None,
) -> None:
    """Append a legacy outcome observation; never rewrite the research row."""
    init_db(db_path)
    with get_connection(db_path) as connection:
        versions = connection.execute(
            "SELECT model_version FROM backtest_runs WHERE ticker=? AND as_of_date=?",
            (ticker.strip().upper(), as_of_date),
        ).fetchall()
        connection.executemany(
            """INSERT INTO legacy_outcome_observations
                (ticker, as_of_date, model_version, outcome_1m, outcome_3m, outcome_6m, outcome_12m)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [(
                ticker.strip().upper(), as_of_date, row["model_version"], outcomes.get("1M"),
                outcomes.get("3M"), outcomes.get("6M"), outcomes.get("12M"),
            ) for row in versions],
        )


def set_backtest_job_item(
    as_of_date: str, ticker: str, status: str, error: str | None = None,
    db_path: str | Path | None = None,
) -> None:
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """INSERT INTO backtest_job_items (as_of_date, ticker, status, error, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(as_of_date, ticker) DO UPDATE SET status=excluded.status,
                error=excluded.error, updated_at=CURRENT_TIMESTAMP""",
            (as_of_date, ticker.strip().upper(), status, error),
        )


def get_backtest_job_items(as_of_date: str, db_path: str | Path | None = None) -> list[dict[str, object]]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM backtest_job_items WHERE as_of_date = ? ORDER BY ticker", (as_of_date,)
        ).fetchall()
    return [dict(row) for row in rows]


def add_ticker(ticker: str, db_path: str | Path | None = None) -> None:
    normalized = ticker.strip().upper()
    if not normalized:
        raise ValueError("Ticker cannot be empty")
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute("INSERT OR IGNORE INTO watchlist (ticker) VALUES (?)", (normalized,))


def remove_ticker(ticker: str, db_path: str | Path | None = None) -> None:
    normalized = ticker.strip().upper()
    init_db(db_path)
    with get_connection(db_path) as connection:
        holding = connection.execute(
            "SELECT 1 FROM portfolio_holdings WHERE ticker = ?", (normalized,)
        ).fetchone()
        if holding:
            raise ValueError(f"{normalized} is in the portfolio. Mark it as not owned first.")
        connection.execute("DELETE FROM watchlist WHERE ticker = ?", (normalized,))


def get_watchlist(db_path: str | Path | None = None) -> list[str]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        return [row["ticker"] for row in connection.execute("SELECT ticker FROM watchlist ORDER BY ticker")]


def save_dashboard_order(tickers: list[str], db_path: str | Path | None = None) -> None:
    normalized = [str(ticker).strip().upper() for ticker in tickers if str(ticker).strip()]
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO ui_preferences (preference_key, value_json, updated_at)
            VALUES ('decision_dashboard_order', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(preference_key) DO UPDATE SET
                value_json=excluded.value_json, updated_at=CURRENT_TIMESTAMP
            """,
            (json.dumps(normalized),),
        )


def get_dashboard_order(db_path: str | Path | None = None) -> list[str]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT value_json FROM ui_preferences WHERE preference_key = 'decision_dashboard_order'"
        ).fetchone()
    if not row:
        return []
    value = json.loads(row["value_json"])
    return [str(ticker) for ticker in value] if isinstance(value, list) else []


def save_active_backtest(as_of_date: str | None, db_path: str | Path | None = None) -> None:
    """Persist the Time Machine selection across navigation and browser reloads."""
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """INSERT INTO ui_preferences (preference_key, value_json, updated_at)
            VALUES ('active_backtest_date', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(preference_key) DO UPDATE SET value_json=excluded.value_json,
                updated_at=CURRENT_TIMESTAMP""",
            (json.dumps(as_of_date),),
        )


def get_active_backtest(db_path: str | Path | None = None) -> str | None:
    init_db(db_path)
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT value_json FROM ui_preferences WHERE preference_key='active_backtest_date'"
        ).fetchone()
    return json.loads(row["value_json"]) if row else None


def replace_simulation_suggestions(
    suggestions: list[Mapping[str, object]], source_signature: str,
    db_path: str | Path | None = None,
) -> None:
    """Atomically replace the system's ranked cutoff recommendations."""
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute("DELETE FROM simulation_suggestions")
        connection.executemany(
            """INSERT INTO simulation_suggestions
            (suggested_date, trigger_type, rationale, priority, evidence_json, source_signature)
            VALUES (?, ?, ?, ?, ?, ?)""",
            [(
                str(item["suggested_date"]), str(item["trigger_type"]), str(item["rationale"]),
                float(item["priority"]), json.dumps(item.get("evidence", {})), source_signature,
            ) for item in suggestions],
        )


def get_simulation_suggestions(db_path: str | Path | None = None) -> list[dict[str, object]]:
    """Return ranked suggestions with stored evidence decoded."""
    init_db(db_path)
    with get_connection(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM simulation_suggestions ORDER BY priority DESC, suggested_date DESC"
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["evidence"] = json.loads(str(item.pop("evidence_json")))
        result.append(item)
    return result


def set_portfolio_holding(
    ticker: str,
    owned: bool,
    shares: float = 0,
    db_path: str | Path | None = None,
) -> None:
    """Record ownership. A portfolio ticker is always added to the watchlist."""
    normalized = ticker.strip().upper()
    if not normalized:
        raise ValueError("Ticker cannot be empty")
    if shares < 0:
        raise ValueError("Shares cannot be negative")
    if owned and shares <= 0:
        raise ValueError("Owned holdings must have more than zero shares")

    add_ticker(normalized, db_path)
    with get_connection(db_path) as connection:
        if owned:
            connection.execute(
                """
                INSERT INTO portfolio_holdings (ticker, shares, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(ticker) DO UPDATE SET
                    shares = excluded.shares,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (normalized, shares),
            )
            existing_legacy = connection.execute(
                "SELECT id FROM portfolio_lots WHERE ticker = ? AND source = 'legacy' ORDER BY id LIMIT 1",
                (normalized,),
            ).fetchone()
            if existing_legacy:
                connection.execute(
                    "UPDATE portfolio_lots SET shares = ? WHERE id = ?",
                    (shares, existing_legacy["id"]),
                )
            elif not connection.execute(
                "SELECT 1 FROM portfolio_lots WHERE ticker = ?", (normalized,)
            ).fetchone():
                connection.execute(
                    "INSERT INTO portfolio_lots (ticker, shares, source, notes) VALUES (?, ?, 'legacy', ?)",
                    (normalized, shares, "Aggregate holding; purchase details unknown"),
                )
        else:
            connection.execute("DELETE FROM portfolio_holdings WHERE ticker = ?", (normalized,))
            connection.execute("DELETE FROM portfolio_lots WHERE ticker = ?", (normalized,))


def get_portfolio_holdings(db_path: str | Path | None = None) -> list[dict[str, object]]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        return [
            dict(row)
            for row in connection.execute(
                "SELECT ticker, shares, updated_at FROM portfolio_holdings ORDER BY ticker"
            )
        ]


def _sync_portfolio_holding(ticker: str, connection: sqlite3.Connection) -> None:
    total = connection.execute(
        "SELECT COALESCE(SUM(shares), 0) AS shares FROM portfolio_lots WHERE ticker = ?", (ticker,)
    ).fetchone()["shares"]
    if total > 0:
        connection.execute(
            """
            INSERT INTO portfolio_holdings (ticker, shares, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(ticker) DO UPDATE SET shares=excluded.shares, updated_at=CURRENT_TIMESTAMP
            """,
            (ticker, total),
        )
    else:
        connection.execute("DELETE FROM portfolio_holdings WHERE ticker = ?", (ticker,))


def add_portfolio_lot(lot: Mapping[str, object], db_path: str | Path | None = None) -> int:
    normalized = str(lot.get("ticker", "")).strip().upper()
    shares = float(lot.get("shares", 0) or 0)
    price = float(lot.get("price_per_share", 0) or 0)
    fees = float(lot.get("fees", 0) or 0)
    purchase_date = str(lot.get("purchase_date", "")).strip()
    if not normalized:
        raise ValueError("Ticker cannot be empty")
    if shares <= 0 or price <= 0:
        raise ValueError("Shares and price per share must be greater than zero")
    if fees < 0:
        raise ValueError("Fees cannot be negative")
    if not purchase_date:
        raise ValueError("Purchase date is required")
    add_ticker(normalized, db_path)
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO portfolio_lots
                (ticker, purchase_date, shares, price_per_share, fees, source, notes)
            VALUES (?, ?, ?, ?, ?, 'manual', ?)
            """,
            (normalized, purchase_date, shares, price, fees, lot.get("notes")),
        )
        _sync_portfolio_holding(normalized, connection)
        return int(cursor.lastrowid)


def get_portfolio_lots(
    ticker: str | None = None, db_path: str | Path | None = None
) -> list[dict[str, object]]:
    init_db(db_path)
    query, params = "SELECT * FROM portfolio_lots", []
    if ticker:
        query += " WHERE ticker = ?"
        params.append(ticker.strip().upper())
    query += " ORDER BY COALESCE(purchase_date, '0000-00-00') DESC, id DESC"
    with get_connection(db_path) as connection:
        return [dict(row) for row in connection.execute(query, params)]


def update_portfolio_lot(
    lot_id: int, lot: Mapping[str, object], db_path: str | Path | None = None
) -> None:
    init_db(db_path)
    with get_connection(db_path) as connection:
        existing = connection.execute("SELECT * FROM portfolio_lots WHERE id = ?", (lot_id,)).fetchone()
        if not existing:
            raise ValueError(f"Portfolio lot {lot_id} does not exist")
        ticker = str(lot.get("ticker", existing["ticker"])).strip().upper()
        shares = float(lot.get("shares", existing["shares"]) or 0)
        price_value = lot.get("price_per_share", existing["price_per_share"])
        price = float(price_value) if price_value not in (None, "") else None
        fees = float(lot.get("fees", existing["fees"]) or 0)
        purchase_date = lot.get("purchase_date", existing["purchase_date"])
        if shares <= 0 or (price is not None and price <= 0) or fees < 0:
            raise ValueError("Lot values must be positive and fees cannot be negative")
        add_ticker(ticker, db_path)
        connection.execute(
            """
            UPDATE portfolio_lots SET ticker=?, purchase_date=?, shares=?, price_per_share=?,
                fees=?, notes=? WHERE id=?
            """,
            (ticker, purchase_date, shares, price, fees, lot.get("notes", existing["notes"]), lot_id),
        )
        _sync_portfolio_holding(existing["ticker"], connection)
        if ticker != existing["ticker"]:
            _sync_portfolio_holding(ticker, connection)


def delete_portfolio_lot(lot_id: int, db_path: str | Path | None = None) -> None:
    init_db(db_path)
    with get_connection(db_path) as connection:
        existing = connection.execute("SELECT ticker FROM portfolio_lots WHERE id = ?", (lot_id,)).fetchone()
        if not existing:
            raise ValueError(f"Portfolio lot {lot_id} does not exist")
        connection.execute("DELETE FROM portfolio_lots WHERE id = ?", (lot_id,))
        _sync_portfolio_holding(existing["ticker"], connection)


def record_portfolio_sale(
    sale: Mapping[str, object], db_path: str | Path | None = None
) -> int:
    """Record a sale and consume open lots FIFO. Unknown legacy costs produce unknown P&L."""
    normalized = str(sale.get("ticker", "")).strip().upper()
    shares_to_sell = float(sale.get("shares", 0) or 0)
    sale_price = float(sale.get("price_per_share", 0) or 0)
    fees = float(sale.get("fees", 0) or 0)
    currency = str(sale.get("currency", PORTFOLIO_BASE_CURRENCY)).strip().upper()
    sale_date = str(sale.get("sale_date", "")).strip()
    if not normalized or not sale_date or not currency:
        raise ValueError("Ticker, sale date, and currency are required")
    if shares_to_sell <= 0 or sale_price <= 0 or fees < 0:
        raise ValueError("Sale shares/price must be positive and fees cannot be negative")
    init_db(db_path)
    with get_connection(db_path) as connection:
        available = connection.execute(
            "SELECT COALESCE(SUM(shares), 0) AS shares FROM portfolio_lots WHERE ticker = ?",
            (normalized,),
        ).fetchone()["shares"]
        if shares_to_sell > available + 1e-9:
            raise ValueError(f"Cannot sell {shares_to_sell:g} shares; only {available:g} are available")
        lots = connection.execute(
            """
            SELECT * FROM portfolio_lots WHERE ticker = ?
            ORDER BY CASE WHEN purchase_date IS NULL THEN 0 ELSE 1 END, purchase_date, id
            """,
            (normalized,),
        ).fetchall()
        remaining, cost_basis, cost_known = shares_to_sell, 0.0, True
        for lot in lots:
            if remaining <= 1e-9:
                break
            consumed = min(remaining, float(lot["shares"]))
            if lot["price_per_share"] is None:
                cost_known = False
            else:
                lot_fee_share = float(lot["fees"]) * consumed / float(lot["shares"])
                cost_basis += consumed * float(lot["price_per_share"]) + lot_fee_share
            leftover = float(lot["shares"]) - consumed
            if leftover <= 1e-9:
                connection.execute("DELETE FROM portfolio_lots WHERE id = ?", (lot["id"],))
            else:
                remaining_fee = float(lot["fees"]) * leftover / float(lot["shares"])
                connection.execute(
                    "UPDATE portfolio_lots SET shares = ?, fees = ? WHERE id = ?",
                    (leftover, remaining_fee, lot["id"]),
                )
            remaining -= consumed
        known_cost = cost_basis if cost_known else None
        proceeds = shares_to_sell * sale_price - fees
        realized_pl = proceeds - cost_basis if cost_known else None
        cursor = connection.execute(
            """
            INSERT INTO portfolio_sales
                (ticker, sale_date, shares, price_per_share, fees, cost_basis, realized_pl, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (normalized, sale_date, shares_to_sell, sale_price, fees, known_cost, realized_pl, sale.get("notes")),
        )
        sale_id = int(cursor.lastrowid)
        connection.execute(
            """
            INSERT INTO cash_transactions
                (transaction_date, transaction_type, amount, currency, ticker, notes, source_sale_id)
            VALUES (?, 'adjustment', ?, ?, ?, ?, ?)
            """,
            (
                sale_date, proceeds, currency, normalized,
                "Automatically posted net proceeds from recorded sale.", sale_id,
            ),
        )
        _sync_portfolio_holding(normalized, connection)
        return sale_id


def ensure_sale_cash_transaction(
    sale_id: int,
    currency: str = PORTFOLIO_BASE_CURRENCY,
    db_path: str | Path | None = None,
) -> int:
    """Create the missing net-proceeds cash entry for an existing sale exactly once."""
    normalized_currency = currency.strip().upper()
    if not normalized_currency:
        raise ValueError("Sale currency is required")
    init_db(db_path)
    with get_connection(db_path) as connection:
        sale = connection.execute(
            "SELECT * FROM portfolio_sales WHERE id = ?", (sale_id,),
        ).fetchone()
        if not sale:
            raise ValueError(f"Portfolio sale {sale_id} does not exist")
        existing = connection.execute(
            "SELECT id FROM cash_transactions WHERE source_sale_id = ?", (sale_id,),
        ).fetchone()
        if existing:
            return int(existing["id"])
        proceeds = float(sale["shares"]) * float(sale["price_per_share"]) - float(sale["fees"])
        cursor = connection.execute(
            """
            INSERT INTO cash_transactions
                (transaction_date, transaction_type, amount, currency, ticker, notes, source_sale_id)
            VALUES (?, 'adjustment', ?, ?, ?, ?, ?)
            """,
            (
                sale["sale_date"], proceeds, normalized_currency, sale["ticker"],
                "Reconciled net proceeds from recorded sale.", sale_id,
            ),
        )
        return int(cursor.lastrowid)


def get_portfolio_sales(
    ticker: str | None = None, db_path: str | Path | None = None
) -> list[dict[str, object]]:
    init_db(db_path)
    query, params = "SELECT * FROM portfolio_sales", []
    if ticker:
        query += " WHERE ticker = ?"
        params.append(ticker.strip().upper())
    query += " ORDER BY sale_date DESC, id DESC"
    with get_connection(db_path) as connection:
        return [dict(row) for row in connection.execute(query, params)]


def save_portfolio_snapshot(
    snapshot_date: str,
    total_value: float,
    priced_positions: int,
    total_positions: int,
    base_currency: str = "USD",
    db_path: str | Path | None = None,
) -> None:
    if total_value < 0 or priced_positions < 0 or total_positions < 0:
        raise ValueError("Snapshot values cannot be negative")
    if priced_positions > total_positions:
        raise ValueError("Priced positions cannot exceed total positions")
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO portfolio_snapshots
                (snapshot_date, total_value, base_currency, priced_positions, total_positions, captured_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(snapshot_date) DO UPDATE SET
                total_value=excluded.total_value,
                base_currency=excluded.base_currency,
                priced_positions=excluded.priced_positions,
                total_positions=excluded.total_positions,
                captured_at=CURRENT_TIMESTAMP
            """,
            (snapshot_date, total_value, base_currency.strip().upper(), priced_positions, total_positions),
        )


def get_portfolio_snapshots(db_path: str | Path | None = None) -> list[dict[str, object]]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        return [
            dict(row) for row in connection.execute(
                "SELECT * FROM portfolio_snapshots ORDER BY snapshot_date"
            )
        ]


def add_cash_transaction(
    transaction: Mapping[str, object], db_path: str | Path | None = None
) -> int:
    transaction_type = str(transaction.get("transaction_type", ""))
    allowed = {"deposit", "withdrawal", "dividend", "withholding_tax", "fee", "adjustment"}
    if transaction_type not in allowed:
        raise ValueError("Unsupported cash transaction type")
    amount = float(transaction.get("amount", 0) or 0)
    if amount == 0:
        raise ValueError("Cash transaction amount cannot be zero")
    # Outflows are stored as negative amounts regardless of how the UI supplied them.
    if transaction_type in {"withdrawal", "withholding_tax", "fee"}:
        amount = -abs(amount)
    elif transaction_type in {"deposit", "dividend"}:
        amount = abs(amount)
    currency = str(transaction.get("currency", "")).strip().upper()
    transaction_date = str(transaction.get("transaction_date", "")).strip()
    if not currency or not transaction_date:
        raise ValueError("Transaction date and currency are required")
    ticker = str(transaction.get("ticker", "")).strip().upper() or None
    init_db(db_path)
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO cash_transactions
                (transaction_date, transaction_type, amount, currency, ticker, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (transaction_date, transaction_type, amount, currency, ticker, transaction.get("notes")),
        )
        return int(cursor.lastrowid)


def get_cash_transactions(db_path: str | Path | None = None) -> list[dict[str, object]]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        return [
            dict(row) for row in connection.execute(
                "SELECT * FROM cash_transactions ORDER BY transaction_date DESC, id DESC"
            )
        ]


def delete_cash_transaction(transaction_id: int, db_path: str | Path | None = None) -> None:
    init_db(db_path)
    with get_connection(db_path) as connection:
        linked_sale = connection.execute(
            "SELECT source_sale_id FROM cash_transactions WHERE id = ?", (transaction_id,),
        ).fetchone()
        if linked_sale and linked_sale["source_sale_id"] is not None:
            raise ValueError("Automatic sale-proceeds entries cannot be deleted independently")
        cursor = connection.execute("DELETE FROM cash_transactions WHERE id = ?", (transaction_id,))
        if cursor.rowcount == 0:
            raise ValueError(f"Cash transaction {transaction_id} does not exist")


def set_portfolio_target(
    ticker: str, target_weight_pct: float, db_path: str | Path | None = None
) -> None:
    normalized = ticker.strip().upper()
    if not 0 <= target_weight_pct <= 100:
        raise ValueError("Target weight must be between 0 and 100")
    add_ticker(normalized, db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO portfolio_targets (ticker, target_weight_pct, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(ticker) DO UPDATE SET
                target_weight_pct=excluded.target_weight_pct, updated_at=CURRENT_TIMESTAMP
            """,
            (normalized, target_weight_pct),
        )


def get_portfolio_targets(db_path: str | Path | None = None) -> list[dict[str, object]]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM portfolio_targets ORDER BY ticker")]


def save_fundamentals(
    fundamentals: Mapping[str, object], db_path: str | Path | None = None
) -> None:
    """Upsert a normalized provider response into the daily cache."""
    init_db(db_path)
    fields = (
        "ticker", "trailing_pe", "forward_pe", "price_to_sales_ttm",
        "revenue_growth", "eps_growth", "reporting_date", "period_end", "published_at",
        "known_at", "known_at_status", "provider_name", "fetched_at",
    )
    with get_connection(db_path) as connection:
        connection.execute(
            f"""
            INSERT INTO fundamentals_cache ({', '.join(fields)})
            VALUES ({', '.join('?' for _ in fields)})
            ON CONFLICT(ticker) DO UPDATE SET
                trailing_pe=excluded.trailing_pe,
                forward_pe=excluded.forward_pe,
                price_to_sales_ttm=excluded.price_to_sales_ttm,
                revenue_growth=excluded.revenue_growth,
                eps_growth=excluded.eps_growth,
                reporting_date=excluded.reporting_date,
                period_end=excluded.period_end,
                published_at=excluded.published_at,
                known_at=excluded.known_at,
                known_at_status=excluded.known_at_status,
                provider_name=excluded.provider_name,
                fetched_at=excluded.fetched_at
            """,
            [fundamentals.get(field) for field in fields],
        )


def get_cached_fundamentals(
    ticker: str, db_path: str | Path | None = None
) -> dict[str, object] | None:
    init_db(db_path)
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM fundamentals_cache WHERE ticker = ?", (ticker.strip().upper(),)
        ).fetchone()
        return dict(row) if row else None


def save_industry_research(
    ticker: str, payload: Mapping[str, object], provider_name: str, fetched_at: str,
    db_path: str | Path | None = None,
) -> None:
    """Persist a normalized industry/analyst research snapshot."""
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO industry_research_cache
                (ticker, payload_json, provider_name, period_end, published_at, known_at,
                 known_at_status, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET payload_json=excluded.payload_json,
                provider_name=excluded.provider_name, period_end=excluded.period_end,
                published_at=excluded.published_at, known_at=excluded.known_at,
                known_at_status=excluded.known_at_status, fetched_at=excluded.fetched_at
            """,
            (ticker.strip().upper(), json.dumps(payload), provider_name, payload.get("period_end"),
             payload.get("published_at"), payload.get("known_at"), payload.get("known_at_status"), fetched_at),
        )


def get_cached_industry_research(
    ticker: str, db_path: str | Path | None = None,
) -> dict[str, object] | None:
    """Return the normalized cached industry snapshot, if present."""
    init_db(db_path)
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM industry_research_cache WHERE ticker = ?",
            (ticker.strip().upper(),),
        ).fetchone()
    if not row:
        return None
    payload = json.loads(row["payload_json"])
    payload.update({field: row[field] for field in (
        "provider_name", "period_end", "published_at", "known_at", "known_at_status", "fetched_at",
    )})
    return payload


def save_extended_hours_quote(
    ticker: str, payload: Mapping[str, object], provider_name: str,
    quote_date: str | None, fetched_at: str, db_path: str | Path | None = None,
) -> None:
    """Persist the latest extended-hours quote snapshot."""
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """INSERT INTO extended_hours_cache
                (ticker, payload_json, provider_name, quote_date, fetched_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(ticker) DO UPDATE SET payload_json=excluded.payload_json,
                   provider_name=excluded.provider_name, quote_date=excluded.quote_date,
                   fetched_at=excluded.fetched_at""",
            (ticker.strip().upper(), json.dumps(payload), provider_name, quote_date, fetched_at),
        )


def get_cached_extended_hours_quote(
    ticker: str, db_path: str | Path | None = None,
) -> dict[str, object] | None:
    """Return the latest cached extended-hours quote, if present."""
    init_db(db_path)
    with get_connection(db_path) as connection:
        row = connection.execute(
            """SELECT payload_json, provider_name, quote_date, fetched_at
               FROM extended_hours_cache WHERE ticker = ?""",
            (ticker.strip().upper(),),
        ).fetchone()
    if not row:
        return None
    payload = json.loads(row["payload_json"])
    payload.update({
        "provider_name": row["provider_name"], "quote_date": row["quote_date"],
        "fetched_at": row["fetched_at"],
    })
    return payload


def save_positioning_snapshot(
    ticker: str, payload: Mapping[str, object], provider_name: str,
    reporting_date: str | None, fetched_at: str, db_path: str | Path | None = None,
) -> None:
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO positioning_cache
                (ticker, payload_json, provider_name, reporting_date, period_end, published_at,
                 known_at, known_at_status, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET payload_json=excluded.payload_json,
                provider_name=excluded.provider_name, reporting_date=excluded.reporting_date,
                period_end=excluded.period_end, published_at=excluded.published_at,
                known_at=excluded.known_at, known_at_status=excluded.known_at_status,
                fetched_at=excluded.fetched_at
            """,
            (ticker.strip().upper(), json.dumps(payload), provider_name, reporting_date,
             payload.get("period_end"), payload.get("published_at"), payload.get("known_at"),
             payload.get("known_at_status"), fetched_at),
        )
        connection.execute(
            """
            INSERT INTO positioning_history
                (ticker, snapshot_date, payload_json, provider_name, reporting_date, period_end,
                 published_at, known_at, known_at_status, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, snapshot_date) DO NOTHING
            """,
            (ticker.strip().upper(), fetched_at[:10], json.dumps(payload), provider_name, reporting_date,
             payload.get("period_end"), payload.get("published_at"), payload.get("known_at"),
             payload.get("known_at_status"), fetched_at),
        )


def get_cached_positioning(
    ticker: str, db_path: str | Path | None = None,
) -> dict[str, object] | None:
    init_db(db_path)
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM positioning_cache WHERE ticker = ?",
            (ticker.strip().upper(),),
        ).fetchone()
    if not row:
        return None
    payload = json.loads(row["payload_json"])
    payload.update({
        field: row[field] for field in (
            "provider_name", "reporting_date", "period_end", "published_at", "known_at",
            "known_at_status", "fetched_at",
        )
    })
    return payload


def get_positioning_history(ticker: str, db_path: str | Path | None = None) -> list[dict[str, object]]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM positioning_history WHERE ticker = ? ORDER BY snapshot_date",
            (ticker.strip().upper(),),
        ).fetchall()
    return [{**json.loads(row["payload_json"]), **{
        "snapshot_date": row["snapshot_date"], "provider_name": row["provider_name"],
        **{field: row[field] for field in (
            "reporting_date", "period_end", "published_at", "known_at", "known_at_status", "fetched_at",
        )},
    }} for row in rows]


def save_positioning_history_snapshot(
    ticker: str, snapshot_date: str, payload: Mapping[str, object], provider_name: str,
    reporting_date: str | None, fetched_at: str, db_path: str | Path | None = None,
) -> None:
    """Append historical evidence without rewriting an existing legacy observation."""
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO positioning_history
                (ticker, snapshot_date, payload_json, provider_name, reporting_date, period_end,
                 published_at, known_at, known_at_status, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, snapshot_date) DO NOTHING
            """,
            (ticker.strip().upper(), snapshot_date, json.dumps(payload), provider_name, reporting_date,
             payload.get("period_end"), payload.get("published_at"), payload.get("known_at"),
             payload.get("known_at_status"), fetched_at),
        )


def add_journal_entry(entry: Mapping[str, object], db_path: str | Path | None = None) -> None:
    required = {"ticker", "entry_date", "action", "conviction"}
    missing = required - entry.keys()
    if missing:
        raise ValueError(f"Missing journal fields: {', '.join(sorted(missing))}")
    init_db(db_path)
    fields = ("ticker", "entry_date", "action", "thesis", "catalyst", "main_risk", "invalidation_condition", "target_price", "time_horizon", "conviction", "notes")
    values = [entry.get(field) for field in fields]
    values[0] = str(values[0]).strip().upper()
    with get_connection(db_path) as connection:
        connection.execute(
            f"INSERT INTO journal_entries ({', '.join(fields)}) VALUES ({', '.join('?' for _ in fields)})",
            values,
        )


def update_journal_entry(
    entry_id: int, entry: Mapping[str, object], db_path: str | Path | None = None
) -> None:
    required = {"ticker", "entry_date", "action", "conviction"}
    missing = required - entry.keys()
    if missing:
        raise ValueError(f"Missing journal fields: {', '.join(sorted(missing))}")
    init_db(db_path)
    fields = ("ticker", "entry_date", "action", "thesis", "catalyst", "main_risk", "invalidation_condition", "target_price", "time_horizon", "conviction", "notes")
    values = [entry.get(field) for field in fields]
    values[0] = str(values[0]).strip().upper()
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            f"UPDATE journal_entries SET {', '.join(f'{field} = ?' for field in fields)} WHERE id = ?",
            [*values, entry_id],
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Journal entry {entry_id} does not exist")


def delete_journal_entry(entry_id: int, db_path: str | Path | None = None) -> None:
    init_db(db_path)
    with get_connection(db_path) as connection:
        cursor = connection.execute("DELETE FROM journal_entries WHERE id = ?", (entry_id,))
        if cursor.rowcount == 0:
            raise ValueError(f"Journal entry {entry_id} does not exist")


def get_journal_entries(ticker: str | None = None, db_path: str | Path | None = None, action: str | None = None, conviction: int | None = None) -> list[dict[str, object]]:
    init_db(db_path)
    query = "SELECT * FROM journal_entries"
    filters, params = [], []
    if ticker:
        filters.append("ticker = ?")
        params.append(ticker.strip().upper())
    if action:
        filters.append("action = ?")
        params.append(action)
    if conviction:
        filters.append("conviction = ?")
        params.append(str(conviction))
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY entry_date DESC, id DESC"
    with get_connection(db_path) as connection:
        return [dict(row) for row in connection.execute(query, params)]
