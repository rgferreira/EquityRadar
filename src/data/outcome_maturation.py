"""Append-only horizon completion and an explicit current-label projection.

Raw v1 labels and frozen evaluation reports are never modified. Each completed
horizon retains its own adjusted-price vintage, timing and source payload hash.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from src.data.database import get_connection, get_outcome_labels, init_db
from src.outcome_labels import HORIZON_SESSIONS, RELATIVE_LABEL_VERSION

PROJECTION_VERSION = "immutable-horizon-completion-v1"


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def init_horizon_store(db_path=None):
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS prediction_horizon_outcomes (
            prediction_id TEXT NOT NULL, label_version TEXT NOT NULL,
            horizon TEXT NOT NULL CHECK(horizon IN ('1M','3M','6M')),
            payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
            observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(prediction_id,label_version,horizon))""")


def append_horizon(label, horizon, db_path=None):
    """First complete observation wins; later price revisions cannot rewrite it."""
    if horizon not in HORIZON_SESSIONS or not isinstance(label.get("outcomes", {}).get(horizon), Mapping):
        raise ValueError("Only a completed, supported horizon can be persisted")
    if label.get("label_version") != RELATIVE_LABEL_VERSION or label.get("status") != "available":
        raise ValueError("Unsupported outcome contract")
    init_horizon_store(db_path)
    payload = _canonical(label)
    with get_connection(db_path) as connection:
        cursor = connection.execute("""INSERT OR IGNORE INTO prediction_horizon_outcomes
            (prediction_id,label_version,horizon,payload_json,payload_hash)
            VALUES (?,?,?,?,?)""", (label["prediction_id"], label["label_version"], horizon,
                                   payload, hashlib.sha256(payload.encode()).hexdigest()))
        return bool(cursor.rowcount)


def get_current_outcome_labels(*, prediction_id=None, label_version=None, db_path=None):
    """Project original values plus missing matured horizons, with explicit lineage.

    This is deliberately separate from get_outcome_labels, the immutable archive
    reader. The financial label contract is unchanged; the projection has its own
    identity and hash. Entry prices inside horizon_provenance govern each horizon.
    """
    contract = label_version or RELATIVE_LABEL_VERSION
    originals = get_outcome_labels(prediction_id=prediction_id, label_version=contract, db_path=db_path)
    indexed = {str(row["prediction_id"]): dict(row) for row in originals}
    init_horizon_store(db_path)
    with get_connection(db_path) as connection:
        query = "SELECT * FROM prediction_horizon_outcomes WHERE label_version=?"
        params = [contract]
        if prediction_id:
            query += " AND prediction_id=?"
            params.append(prediction_id)
        supplements = [dict(row) for row in connection.execute(query, params)]
    fields = ("execution_date", "security_entry_price", "benchmark_entry_price",
              "benchmark_ticker", "cost_bps", "timing_convention", "outcome_hash")
    for row in indexed.values():
        row["horizon_provenance"] = {
            h: {**{k: row.get(k) for k in fields}, "observed_at": row.get("observed_at"),
                "source_label_id": row["label_id"]}
            for h, value in row["outcomes"].items() if isinstance(value, Mapping)
        }
    for stored in supplements:
        label = json.loads(stored["payload_json"])
        pid, horizon = stored["prediction_id"], stored["horizon"]
        if pid not in indexed:
            indexed[pid] = {**label, "outcomes": {}, "horizon_provenance": {},
                            "max_drawdown_6m_pct": None, "observed_at": stored["observed_at"]}
        row = indexed[pid]
        if isinstance(row["outcomes"].get(horizon), Mapping):
            continue
        row["outcomes"][horizon] = label["outcomes"][horizon]
        row["horizon_provenance"][horizon] = {
            **{k: label.get(k) for k in fields}, "observed_at": stored["observed_at"],
            "source_payload_hash": stored["payload_hash"],
        }
        row["status"], row["unavailable_reason"] = "available", None
        # A formerly pending label may have no execution metadata at all.
        for field in fields[:-1]:
            if row.get(field) is None:
                row[field] = label.get(field)
        if horizon == "6M":
            row["max_drawdown_6m_pct"] = label["max_drawdown_6m_pct"]
        row["observed_at"] = max(str(row.get("observed_at") or ""), stored["observed_at"])
    results = []
    for row in indexed.values():
        row["source_label_id"] = row.pop("label_id", None)
        row["source_outcome_hash"] = row.pop("outcome_hash", None)
        row["outcomes_json"] = _canonical(row["outcomes"])
        row["projection_version"] = PROJECTION_VERSION
        row["outcome_hash"] = hashlib.sha256(_canonical(row).encode()).hexdigest()
        row["label_id"] = hashlib.sha256(
            f"{row['prediction_id']}|{PROJECTION_VERSION}|{row['outcome_hash']}".encode()).hexdigest()
        results.append(row)
    return results
