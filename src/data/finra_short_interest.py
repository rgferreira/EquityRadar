"""Official FINRA historical short-interest adapter and bounded backfill."""

import json
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

from src.data.database import save_positioning_history_snapshot


class FINRAShortInterestProvider:
    name = "FINRA Consolidated Short Interest"
    endpoint = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"

    def fetch_history(self, ticker: str) -> list[dict[str, object]]:
        normalized = ticker.strip().upper()
        body = json.dumps({
            "compareFilters": [{
                "compareType": "EQUAL", "fieldName": "symbolCode", "fieldValue": normalized,
            }],
            "limit": 5000,
        }).encode()
        request = Request(
            self.endpoint, data=body, method="POST",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
        if not isinstance(payload, list):
            raise RuntimeError("FINRA returned an unexpected short-interest response")
        rows = []
        for item in payload:
            if not isinstance(item, dict) or not item.get("settlementDate"):
                continue
            rows.append({
                "ticker": normalized,
                "reporting_date": str(item["settlementDate"]),
                "short": {
                    "shares_short": item.get("currentShortPositionQuantity"),
                    "shares_short_prior_month": item.get("previousShortPositionQuantity"),
                    "short_change_pct": item.get("changePercent"),
                    "days_to_cover": item.get("daysToCoverQuantity"),
                    "average_daily_volume": item.get("averageDailyVolumeQuantity"),
                },
                "snapshot_type": "historical_short_interest",
                "historical_components": ["short_interest"],
                "revision_flag": item.get("revisionFlag"),
            })
        return sorted(rows, key=lambda row: str(row["reporting_date"]))


def backfill_finra_short_history(
    ticker: str, provider: FINRAShortInterestProvider | None = None,
    db_path: str | Path | None = None,
) -> int:
    provider = provider or FINRAShortInterestProvider()
    rows = provider.fetch_history(ticker)
    fetched_at = datetime.now().isoformat(timespec="seconds")
    for row in rows:
        reporting_date = str(row["reporting_date"])
        save_positioning_history_snapshot(
            ticker, reporting_date, row, provider.name, reporting_date, fetched_at, db_path,
        )
    return len(rows)
