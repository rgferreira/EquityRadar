"""Industry classification, self-configuring peers, and analyst sentiment retrieval."""

from datetime import datetime, timedelta
from math import log10
from pathlib import Path

import pandas as pd
import yfinance as yf

from src.data.database import get_cached_industry_research, save_industry_research
from src.data.temporal import observed_at_fetch
from src.data.fmp import FMPProvider
from src.utils.config import FMP_API_KEY


CURATED_PEERS: dict[str, list[str]] = {
    "ZS": ["PANW", "CRWD", "FTNT", "S", "OKTA"],
    "AAPL": ["MSFT", "GOOG", "AMZN", "META", "DELL"],
    "GOOG": ["META", "MSFT", "AMZN", "TTD", "PINS"],
    "GOOGL": ["META", "MSFT", "AMZN", "TTD", "PINS"],
    "MSFT": ["ORCL", "GOOG", "AMZN", "CRM", "ADBE"],
    "NVDA": ["AMD", "AVGO", "QCOM", "INTC", "MRVL"],
    "MU": ["WDC", "STX", "INTC", "TXN", "NXPI"],
    "ASML": ["AMAT", "LRCX", "KLAC", "TER", "ONTO"],
    "GLNG": ["FLNG", "GLOP", "CLCO", "LPG", "NAT"],
    "SPCX": ["RKLB", "LMT", "NOC", "RTX", "BA"],
}


def _number(value: object, *, positive: bool = False) -> float | None:
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return result if not positive or result > 0 else None


def _row(frame: object, key: str) -> dict[str, object]:
    if not isinstance(frame, pd.DataFrame) or frame.empty or key not in frame.index:
        return {}
    return {str(k): v for k, v in frame.loc[key].dropna().to_dict().items()}


class YahooIndustryResearchProvider:
    name = "Yahoo Finance + FMP peer discovery"

    def __init__(self, fmp_provider: FMPProvider | None = None):
        self.fmp_provider = fmp_provider or (FMPProvider(FMP_API_KEY) if FMP_API_KEY else None)

    def _profile(self, ticker: str) -> dict[str, object]:
        info = yf.Ticker(ticker).info
        revenue = _number(info.get("totalRevenue"), positive=True)
        free_cash_flow = _number(info.get("freeCashflow"))
        return {
            "ticker": ticker,
            "company_name": info.get("longName") or info.get("shortName"),
            "quote_type": info.get("quoteType"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "sector_key": info.get("sectorKey"),
            "industry_key": info.get("industryKey"),
            "country": info.get("country"),
            "market_cap": _number(info.get("marketCap"), positive=True),
            "forward_pe": _number(info.get("forwardPE"), positive=True),
            "price_to_sales": _number(info.get("priceToSalesTrailing12Months"), positive=True),
            "revenue_growth": _number(info.get("revenueGrowth")),
            "operating_margin": _number(info.get("operatingMargins")),
            "profit_margin": _number(info.get("profitMargins")),
            "gross_margin": _number(info.get("grossMargins")),
            "free_cash_flow_margin": free_cash_flow / revenue if free_cash_flow is not None and revenue else None,
            "net_debt": (_number(info.get("totalDebt")) or 0) - (_number(info.get("totalCash")) or 0),
        }

    @staticmethod
    def _region(country: object) -> str:
        return {
            "United States": "US", "Canada": "CA", "United Kingdom": "GB",
            "Netherlands": "NL", "Germany": "DE", "France": "FR",
            "Switzerland": "CH", "Japan": "JP", "Taiwan": "TW",
        }.get(str(country), "US")

    def _fmp_candidates(self, ticker: str) -> list[str]:
        if self.fmp_provider is None:
            return []
        rows = self.fmp_provider._optional_get("stock-peers", symbol=ticker)
        candidates: list[str] = []
        for row in rows:
            values = row.get("peersList", row.get("peers", row.get("symbol")))
            if isinstance(values, list):
                candidates.extend(str(value).upper() for value in values)
            elif isinstance(values, str) and values.upper() != ticker:
                candidates.append(values.upper())
        return candidates

    def _yahoo_candidates(self, profile: dict[str, object]) -> list[str]:
        industry_key = profile.get("industry_key")
        if not industry_key:
            return []
        try:
            frame = yf.Industry(str(industry_key), region=self._region(profile.get("country"))).top_companies
            return [str(symbol).upper() for symbol in frame.index.tolist()]
        except Exception:
            return []

    @staticmethod
    def _similarity(target: dict[str, object], candidate: dict[str, object]) -> tuple[float, list[str]]:
        score, reasons = 0.0, []
        if candidate.get("industry") and candidate.get("industry") == target.get("industry"):
            score += 40; reasons.append("same industry")
        if candidate.get("sector") and candidate.get("sector") == target.get("sector"):
            score += 15; reasons.append("same sector")
        target_cap, candidate_cap = _number(target.get("market_cap"), positive=True), _number(candidate.get("market_cap"), positive=True)
        if target_cap and candidate_cap:
            cap_points = max(0.0, 25 - 20 * abs(log10(candidate_cap / target_cap)))
            score += cap_points
            reasons.append(f"market-cap proximity {cap_points:.0f}/25")
        for field, label in (("revenue_growth", "growth"), ("operating_margin", "margin")):
            target_value, candidate_value = _number(target.get(field)), _number(candidate.get(field))
            if target_value is not None and candidate_value is not None:
                points = max(0.0, 10 - abs(candidate_value - target_value) * 25)
                score += points
                reasons.append(f"{label} proximity {points:.0f}/10")
        return round(score, 1), reasons

    def _discover_peers(self, ticker: str, profile: dict[str, object]) -> tuple[list[str], str, list[dict[str, object]]]:
        curated = CURATED_PEERS.get(ticker)
        if curated:
            candidates, source = curated, "curated"
        else:
            fmp = self._fmp_candidates(ticker)
            yahoo = self._yahoo_candidates(profile)
            candidates = list(dict.fromkeys([*fmp, *yahoo]))
            source = "FMP + Yahoo industry" if fmp else "Yahoo industry"
        ranked: list[tuple[float, dict[str, object], list[str]]] = []
        for symbol in candidates[:15]:
            if symbol == ticker:
                continue
            try:
                candidate = self._profile(symbol)
                if str(candidate.get("quote_type") or "").upper() not in {"EQUITY", ""}:
                    continue
                if candidate.get("forward_pe") is None and candidate.get("price_to_sales") is None:
                    continue
                similarity, reasons = self._similarity(profile, candidate)
                ranked.append((similarity, candidate, reasons))
            except Exception:
                continue
        ranked.sort(key=lambda item: item[0], reverse=True)
        selected = ranked[:5]
        selection = [
            {"ticker": str(candidate["ticker"]), "similarity_score": score, "reasons": reasons, "source": source}
            for score, candidate, reasons in selected
        ]
        return [str(candidate["ticker"]) for _, candidate, _ in selected], source, selection

    def fetch(
        self, ticker: str, *, existing_peer_symbols: list[str] | None = None,
        existing_snapshot: dict[str, object] | None = None,
    ) -> dict[str, object]:
        normalized = ticker.strip().upper()
        security = yf.Ticker(normalized)
        profile = self._profile(normalized)
        quote_type = str(profile.get("quote_type") or "").upper()
        if quote_type in {"ETF", "MUTUALFUND", "INDEX"}:
            return {
                "profile": profile,
                "applicable": False,
                "not_applicable_reason": f"Industry calibration is not applicable to {quote_type.lower()} instruments.",
                "peers": [], "peer_profiles": [], "recommendations": {},
                "eps_revisions": {}, "price_targets": {},
            }
        if existing_peer_symbols:
            peers = existing_peer_symbols
            peer_source = str((existing_snapshot or {}).get("peer_source") or "cached membership")
            peer_selection = list((existing_snapshot or {}).get("peer_selection") or [])
            membership_fetched_at = str((existing_snapshot or {}).get("peer_membership_fetched_at") or datetime.now().isoformat(timespec="seconds"))
        else:
            peers, peer_source, peer_selection = self._discover_peers(normalized, profile)
            membership_fetched_at = datetime.now().isoformat(timespec="seconds")
        peer_profiles = []
        for peer in peers:
            try:
                peer_profile = self._profile(peer)
                if peer_profile.get("forward_pe") is not None or peer_profile.get("price_to_sales") is not None:
                    peer_profiles.append(peer_profile)
            except Exception:
                continue

        recommendations = security.get_recommendations()
        recommendation_row: dict[str, object] = {}
        if isinstance(recommendations, pd.DataFrame) and not recommendations.empty:
            recommendation_row = {
                str(key): value for key, value in recommendations.iloc[0].dropna().to_dict().items()
            }
        eps_revisions = security.get_eps_revisions()
        revision_row = _row(eps_revisions, "+1y") or _row(eps_revisions, "0y")
        targets = security.get_analyst_price_targets() or {}
        current_price = _number(targets.get("current"), positive=True)
        median_target = _number(targets.get("median"), positive=True)
        return {
            "profile": profile,
            "applicable": True,
            "peers": peers,
            "peer_profiles": peer_profiles,
            "peer_source": peer_source,
            "peer_selection": peer_selection,
            "peer_membership_fetched_at": membership_fetched_at,
            "peer_discovery_status": "ready" if len(peer_profiles) >= 3 else "limited",
            "next_peer_discovery_at": (
                datetime.now() + (timedelta(days=30) if len(peer_profiles) >= 3 else timedelta(days=7))
            ).isoformat(timespec="seconds"),
            "recommendations": recommendation_row,
            "eps_revisions": revision_row,
            "price_targets": {
                "current": current_price,
                "low": _number(targets.get("low"), positive=True),
                "high": _number(targets.get("high"), positive=True),
                "mean": _number(targets.get("mean"), positive=True),
                "median": median_target,
                "median_upside_pct": (
                    (median_target / current_price - 1) * 100
                    if median_target and current_price else None
                ),
            },
        }


def get_industry_research(
    ticker: str, provider: YahooIndustryResearchProvider, *, force_refresh: bool = False,
    db_path: str | Path | None = None,
) -> dict[str, object] | None:
    """Return a daily industry snapshot, preserving stale data on provider errors."""
    normalized = ticker.strip().upper()
    cached = get_cached_industry_research(normalized, db_path)
    if cached and not force_refresh:
        if datetime.fromisoformat(str(cached["fetched_at"])).date() == datetime.now().date():
            return cached
    try:
        payload = provider.fetch(normalized)
        fetched_at = datetime.now().isoformat(timespec="seconds")
        temporal = observed_at_fetch(fetched_at)
        payload["provider_name"] = provider.name
        payload["fetched_at"] = fetched_at
        payload.update(temporal.as_dict())
        save_industry_research(normalized, payload, provider.name, fetched_at, db_path)
        return payload
    except Exception:
        return cached
