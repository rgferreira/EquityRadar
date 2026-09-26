"""Official monetary/curve/credit context with conservative availability."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
import json
import xml.etree.ElementTree as ET

from src.data.research_signals import (attempt, bounded_get, latest_batch, number,
                                      timestamp, utcnow)

SERIES = {
    "nominal_2y": "H15_H15_RIFLGFCY02_N.B.XML",
    "nominal_10y": "H15_H15_RIFLGFCY10_N.B.XML",
    "real_10y": "H15_H15_RIFLGFCY10_XII_N.B.XML",
    "cp_aa_30d": "CP_RATES_RIFSPPNAAD30_N.B.xml",
    "cp_a2_30d": "CP_RATES_RIFSPPNA2P2D30_N.B.xml",
}
RATE_URL = "https://markets.newyorkfed.org/api/rates/all/latest.json"
POLICY_URL = "https://www.federalreserve.gov/feeds/press_monetary.xml"


def _local(element, name):
    return next((e.text for e in element.iter() if e.tag.split("}")[-1] == name), None)


def parse_series(raw, source_url):
    root = ET.fromstring(raw)
    channel = next(e for e in root if e.tag.split("}")[-1] == "channel")
    items = []
    for item in root:
        if item.tag.split("}")[-1] != "item":
            continue
        value, day = number(_local(item, "value")), _local(item, "observationPeriod")
        if value is None or not day:
            continue
        items.append({"period_end": day[:10], "value_pct": value,
                      "source_updated_at": _local(channel, "date"),
                      "published_at": None,
                      "publication_note": "Feed update metadata is not verified initial publication time"})
    if not items:
        raise ValueError("empty_macro_series")
    return {"source_url": source_url, "records": items, "raw_xml": raw.decode(),
            "availability": "first observation only; current vintage, no historical availability claim"}


def parse_policy(raw):
    root = ET.fromstring(raw)
    records = []
    for item in root.findall("./channel/item"):
        published = parsedate_to_datetime(item.findtext("pubDate")).isoformat()
        timestamp(published)
        url = item.findtext("link") or ""
        if not url.startswith("https://www.federalreserve.gov/"):
            continue
        records.append({"title": item.findtext("title"), "source_url": url,
                        "published_at": published, "publication_source": "official RSS pubDate"})
    return {"records": records, "source_url": POLICY_URL, "raw_xml": raw.decode()}


def refresh_macro(db_path=None):
    jobs = [(name, lambda file=file: parse_series(
        bounded_get("https://www.federalreserve.gov/feeds/Data/" + file),
        "https://www.federalreserve.gov/feeds/Data/" + file)) for name, file in SERIES.items()]
    jobs += [("policy_releases", lambda: parse_policy(bounded_get(POLICY_URL))),
             ("overnight_rates", lambda: {"source_url": RATE_URL,
                                          "records": json.loads(bounded_get(RATE_URL))["refRates"]})]
    with ThreadPoolExecutor(max_workers=3) as pool:
        return list(pool.map(lambda job: attempt("macro", job[0], job[1], db_path=db_path), jobs))


def macro_summary(db_path=None, *, as_of=None):
    now = timestamp(as_of or utcnow())
    series, references = {}, {}
    for name in SERIES:
        batch = latest_batch("macro", name, as_of=now.isoformat(), db_path=db_path)
        if not batch:
            series[name] = {"status": "unavailable", "value_pct": None}
            continue
        row = max(batch["payload"]["records"], key=lambda r: r["period_end"])
        age = (now.date() - timestamp(row["period_end"] + "T00:00:00+00:00").date()).days
        future_metadata = row.get("source_updated_at") and timestamp(row["source_updated_at"]) > now
        state = "fresh" if 0 <= age <= 7 and not future_metadata else "stale_or_unverified"
        series[name] = {**row, "status": state, "known_at": batch["observed_at"], "batch_id": batch["batch_id"]}
        references[name] = batch["batch_id"]
    def difference(a, b):
        x, y = series[a], series[b]
        return (x["value_pct"] - y["value_pct"] if x["status"] == y["status"] == "fresh"
                and x["period_end"] == y["period_end"] else None)
    rates_batch = latest_batch("macro", "overnight_rates", as_of=now.isoformat(), db_path=db_path)
    rates = {}
    if rates_batch:
        references["overnight_rates"] = rates_batch["batch_id"]
        for row in rates_batch["payload"]["records"]:
            if row.get("type") not in {"EFFR", "SOFR"}:
                continue
            day, value = row.get("effectiveDate"), number(row.get("percentRate"))
            if day and value is not None and 0 <= (now.date() - timestamp(day + "T00:00:00+00:00").date()).days <= 7:
                rates[row["type"]] = {"value_pct": value, "period_end": day,
                    "known_at": rates_batch["observed_at"], "published_at": None}
    policy = latest_batch("macro", "policy_releases", as_of=now.isoformat(), db_path=db_path)
    releases = []
    if policy:
        references["policy_releases"] = policy["batch_id"]
        releases = [{**r, "known_at": policy["observed_at"]} for r in policy["payload"]["records"]
                    if timestamp(r["published_at"]) <= now]
    return {"series": series, "rates": rates, "curve_10y_minus_2y_pp": difference("nominal_10y", "nominal_2y"),
            "credit_cp_a2_minus_aa_pp": difference("cp_a2_30d", "cp_aa_30d"),
            "policy_releases": releases[:5], "batch_references": references,
            "role": "context_only", "directional_weight": 0,
            "credit_definition": "30-day lower-grade minus AA nonfinancial commercial paper; not corporate bond OAS",
            "vintages": "revisions preserved from first capture; no ALFRED historical release reconstruction"}
