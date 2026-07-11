"""Financial Modeling Prep adapter for the provider-neutral fundamentals interface."""

import json
from datetime import date
from urllib.parse import urlencode
from urllib.request import urlopen

from src.data.fundamentals import Fundamentals


class FMPProvider:
    name = "Financial Modeling Prep"

    def __init__(self, api_key: str, base_url: str = "https://financialmodelingprep.com/stable"):
        if not api_key:
            raise ValueError("FMP_API_KEY is not configured")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def _get(self, endpoint: str, **params: object) -> list[dict[str, object]]:
        query = urlencode({**params, "apikey": self.api_key})
        with urlopen(f"{self.base_url}/{endpoint}?{query}", timeout=10) as response:
            payload = json.load(response)
        if isinstance(payload, dict) and payload.get("Error Message"):
            raise RuntimeError(str(payload["Error Message"]))
        return payload if isinstance(payload, list) else []

    def _optional_get(self, endpoint: str, **params: object) -> list[dict[str, object]]:
        try:
            return self._get(endpoint, **params)
        except Exception:
            return []

    @staticmethod
    def _number(value: object, positive: bool = False) -> float | None:
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return number if not positive or number > 0 else None

    def fetch(self, ticker: str, current_price: float | None = None) -> Fundamentals:
        ratios = self._optional_get("ratios-ttm", symbol=ticker)
        growth = self._optional_get("income-statement-growth", symbol=ticker, limit=1)
        ratio = ratios[0] if ratios else {}
        growth_row = growth[0] if growth else {}

        trailing_pe = self._number(
            ratio.get("priceToEarningsRatioTTM", ratio.get("priceEarningsRatioTTM")), positive=True
        )
        price_to_sales = self._number(
            ratio.get("priceToSalesRatioTTM", ratio.get("priceSalesRatioTTM")), positive=True
        )
        revenue_growth = self._number(growth_row.get("growthRevenue"))
        eps_growth = self._number(growth_row.get("growthEPS"))

        # Analyst estimates are not guaranteed on Basic/free. Use them opportunistically only.
        forward_pe = None
        if current_price and current_price > 0:
            estimates = self._optional_get(
                "analyst-estimates", symbol=ticker, period="annual", page=0, limit=10
            )
            future = sorted(
                (
                    row for row in estimates
                    if str(row.get("date", "")) > date.today().isoformat()
                ),
                key=lambda row: str(row.get("date", "")),
            )
            if future:
                consensus_eps = self._number(
                    future[0].get("estimatedEpsAvg", future[0].get("estimatedEps")), positive=True
                )
                if consensus_eps:
                    forward_pe = current_price / consensus_eps

        reporting_date = str(growth_row.get("date") or ratio.get("date") or "") or None
        if not any((trailing_pe, forward_pe, price_to_sales, revenue_growth is not None, eps_growth is not None)):
            raise RuntimeError(f"FMP returned no usable fundamentals for {ticker}")
        return Fundamentals(
            ticker=ticker,
            trailing_pe=trailing_pe,
            forward_pe=forward_pe,
            price_to_sales_ttm=price_to_sales,
            revenue_growth=revenue_growth,
            eps_growth=eps_growth,
            reporting_date=reporting_date,
            provider_name=self.name,
        )
