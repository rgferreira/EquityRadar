"""Small append-only research evidence store. Never feeds the live score."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from urllib.parse import urlsplit

import requests

from src.data.database import get_connection, init_db

ALLOWED_HOSTS = {"www.federalreserve.gov", "markets.newyorkfed.org", "publicreporting.cftc.gov"}


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Research timestamp needs an explicit timezone")
    return dt.astimezone(timezone.utc)


def number(value):
    try:
        v = float(value)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def bounded_get(url, *, params=None):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.port:
        raise ValueError("Unsupported research provider")
    with requests.get(url, params=params, timeout=(5, 12), stream=True, allow_redirects=False) as response:
        if response.status_code != 200:
            raise RuntimeError(f"provider_http_{response.status_code}")
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > 3_000_000:
                raise ValueError("provider_response_too_large")
            chunks.append(chunk)
        return b"".join(chunks)


def schema(db_path=None):
    init_db(db_path)
    with get_connection(db_path) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS research_signal_batches (
            batch_id TEXT PRIMARY KEY, family TEXT NOT NULL, scope TEXT NOT NULL,
            observed_at TEXT NOT NULL, payload_json TEXT NOT NULL)""")
        con.execute("CREATE INDEX IF NOT EXISTS research_signal_lookup ON research_signal_batches(family,scope,observed_at)")
        con.execute("""CREATE TABLE IF NOT EXISTS research_signal_status (
            family TEXT NOT NULL, scope TEXT NOT NULL, attempted_at TEXT NOT NULL,
            status TEXT NOT NULL, error_code TEXT, batch_id TEXT,
            PRIMARY KEY(family,scope))""")


def save_batch(family, scope, payload, *, observed_at=None, db_path=None):
    """Identical payload is deduplicated; revisions preserve every earlier vintage."""
    observed_at = timestamp(observed_at or utcnow()).isoformat()
    encoded = canonical(payload)
    envelope = {"family": family, "scope": scope, "payload": payload, "observed_at": observed_at}
    batch_id = digest(envelope)
    schema(db_path)
    with get_connection(db_path) as con:
        # Deduplicate consecutive unchanged reads, not A->B->A revisions: the
        # return to A is a new vintage and must not reveal A before its re-release.
        con.execute("BEGIN IMMEDIATE")
        previous = con.execute("""SELECT batch_id,payload_json FROM research_signal_batches
            WHERE family=? AND scope=? ORDER BY observed_at DESC,batch_id DESC LIMIT 1""", (family, scope)).fetchone()
        if previous and previous["payload_json"] == encoded:
            batch_id = previous["batch_id"]
        else:
            con.execute("INSERT OR IGNORE INTO research_signal_batches VALUES (?,?,?,?,?)",
                        (batch_id, family, scope, observed_at, encoded))
    record_status(family, scope, "captured", batch_id=batch_id, now=observed_at, db_path=db_path)
    return batch_id


def record_status(family, scope, status, *, batch_id=None, error_code=None, now=None, db_path=None):
    schema(db_path)
    if status not in {"running", "captured", "empty", "failed"}:
        raise ValueError("Unsupported research status")
    # Codes only. Never persist a provider exception body, credential-bearing URL or traceback.
    if error_code and (len(error_code) > 80 or not all(c.isalnum() or c in "_-" for c in error_code)):
        error_code = "provider_error"
    with get_connection(db_path) as con:
        con.execute("""INSERT INTO research_signal_status VALUES (?,?,?,?,?,?)
            ON CONFLICT(family,scope) DO UPDATE SET attempted_at=excluded.attempted_at,
            status=excluded.status,error_code=excluded.error_code,
            batch_id=COALESCE(excluded.batch_id,research_signal_status.batch_id)""",
                    (family, scope, timestamp(now or utcnow()).isoformat(), status, error_code, batch_id))


def latest_batch(family, scope, *, as_of=None, db_path=None):
    schema(db_path)
    cutoff = (timestamp(as_of) if as_of else timestamp(utcnow())).isoformat()
    with get_connection(db_path) as con:
        row = con.execute("""SELECT * FROM research_signal_batches WHERE family=? AND scope=?
            AND observed_at<=? ORDER BY observed_at DESC,batch_id DESC LIMIT 1""", (family, scope, cutoff)).fetchone()
    return {**dict(row), "payload": json.loads(row["payload_json"])} if row else None


def statuses(db_path=None):
    schema(db_path)
    with get_connection(db_path) as con:
        return [dict(r) for r in con.execute("SELECT * FROM research_signal_status ORDER BY family,scope")]


def attempt(family, scope, fetch, *, db_path=None):
    record_status(family, scope, "running", db_path=db_path)
    try:
        payload = fetch()
        if not payload:
            record_status(family, scope, "empty", db_path=db_path)
            return {"scope": scope, "status": "empty"}
        batch_id = save_batch(family, scope, payload, db_path=db_path)
        return {"scope": scope, "status": "captured", "batch_id": batch_id}
    except Exception as exc:
        code = str(exc) if str(exc).startswith("provider_http_") else type(exc).__name__
        record_status(family, scope, "failed", error_code=code, db_path=db_path)
        return {"scope": scope, "status": "failed", "error_code": code}
