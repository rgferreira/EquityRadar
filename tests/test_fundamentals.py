from src.data.fmp import FMPProvider
from src.data.fundamentals import FallbackFundamentalsProvider, Fundamentals, get_fundamentals
from src.data.yfinance_fundamentals import YFinanceFundamentalsProvider


class StubFMP(FMPProvider):
    def __init__(self):
        super().__init__("test-key")

    def _get(self, endpoint, **params):
        if endpoint == "ratios-ttm":
            return [{"priceToEarningsRatioTTM": 22, "priceToSalesRatioTTM": 5}]
        if endpoint == "income-statement-growth":
            return [{"date": "2026-06-30", "growthRevenue": 0.11, "growthEPS": 0.2}]
        if endpoint == "analyst-estimates":
            return [{"date": "2099-12-31", "estimatedEpsAvg": 5}]
        return []


def test_fmp_adapter_normalizes_mocked_responses_and_derives_forward_pe():
    result = StubFMP().fetch("AAPL", current_price=100)
    assert result.trailing_pe == 22
    assert result.forward_pe == 20
    assert result.price_to_sales_ttm == 5
    assert result.revenue_growth == 0.11
    assert result.reporting_date == "2026-06-30"


class CountingProvider:
    name = "stub"

    def __init__(self):
        self.calls = 0

    def fetch(self, ticker, current_price=None):
        self.calls += 1
        return Fundamentals(ticker=ticker, trailing_pe=10, provider_name=self.name)


def test_daily_cache_avoids_second_provider_call(tmp_path):
    provider = CountingProvider()
    database = tmp_path / "radar.db"
    get_fundamentals("AAPL", provider, db_path=database)
    get_fundamentals("AAPL", provider, db_path=database)
    assert provider.calls == 1


def test_provider_error_preserves_stale_cache(tmp_path):
    provider = CountingProvider()
    database = tmp_path / "radar.db"
    first = get_fundamentals("AAPL", provider, db_path=database)

    def fail(*args, **kwargs):
        raise RuntimeError("provider down")

    provider.fetch = fail
    cached = get_fundamentals("AAPL", provider, force_refresh=True, db_path=database)
    assert cached == first


def test_fallback_provider_uses_second_adapter_when_primary_fails():
    primary = CountingProvider()
    primary.name = "primary"
    primary.fetch = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("plan blocked"))
    fallback = CountingProvider()
    fallback.name = "fallback"
    result = FallbackFundamentalsProvider([primary, fallback]).fetch("GOOG")
    assert result.trailing_pe == 10
    assert result.provider_name == "fallback"


def test_yfinance_adapter_normalizes_public_company_fields(monkeypatch):
    class StubTicker:
        info = {
            "trailingPE": 28.5,
            "forwardPE": 24.2,
            "priceToSalesTrailing12Months": 7.1,
            "revenueGrowth": 0.14,
            "earningsGrowth": 0.22,
            "mostRecentQuarter": 1719705600,
        }

    monkeypatch.setattr("src.data.yfinance_fundamentals.yf.Ticker", lambda ticker: StubTicker())
    result = YFinanceFundamentalsProvider().fetch("goog")
    assert result.ticker == "GOOG"
    assert result.trailing_pe == 28.5
    assert result.forward_pe == 24.2
    assert result.price_to_sales_ttm == 7.1
    assert result.revenue_growth == 0.14
    assert result.eps_growth == 0.22
    assert result.provider_name == "Yahoo Finance"
