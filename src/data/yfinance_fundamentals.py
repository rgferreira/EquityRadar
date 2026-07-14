"""yfinance fallback adapter for provider-neutral company fundamentals."""

from datetime import datetime, timezone

import yfinance as yf

from src.data.fundamentals import Fundamentals


class YFinanceFundamentalsProvider:
    """Retrieve commonly available public-company fundamentals from Yahoo Finance."""

    name = "Yahoo Finance"

    @staticmethod
    def _number(value: object, *, positive: bool = False) -> float | None:
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return number if not positive or number > 0 else None

    @staticmethod
    def _reporting_date(info: dict[str, object]) -> str | None:
        value = info.get("mostRecentQuarter") or info.get("lastFiscalYearEnd")
        if value is None:
            return None
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).date().isoformat()
        except (TypeError, ValueError, OSError):
            return str(value) if value else None

    def fetch(self, ticker: str, current_price: float | None = None) -> Fundamentals:
        normalized = ticker.strip().upper()
        info = yf.Ticker(normalized).info
        trailing_pe = self._number(info.get("trailingPE"), positive=True)
        forward_pe = self._number(info.get("forwardPE"), positive=True)
        price_to_sales = self._number(info.get("priceToSalesTrailing12Months"), positive=True)
        revenue_growth = self._number(info.get("revenueGrowth"))
        eps_growth = self._number(info.get("earningsGrowth"))
        if not any((trailing_pe, forward_pe, price_to_sales, revenue_growth is not None, eps_growth is not None)):
            raise RuntimeError(f"Yahoo Finance returned no usable fundamentals for {normalized}")
        period_end = self._reporting_date(info)
        return Fundamentals(
            ticker=normalized,
            trailing_pe=trailing_pe,
            forward_pe=forward_pe,
            price_to_sales_ttm=price_to_sales,
            revenue_growth=revenue_growth,
            eps_growth=eps_growth,
            reporting_date=period_end,
            period_end=period_end,
            provider_name=self.name,
        )
