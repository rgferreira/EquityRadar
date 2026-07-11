"""Simple, transparent risk scoring (higher is lower risk)."""

import pandas as pd


def risk_score_details(metrics: dict[str, float | None], history: pd.DataFrame) -> dict[str, float | int | None]:
    """Return the risk score and its drawdown/volatility inputs."""
    drawdown_penalty = 0
    drawdown = metrics.get("drawdown_from_52w_high")
    if drawdown is not None:
        drawdown_penalty = min(40, int(abs(min(drawdown, 0))))

    volatility: float | None = None
    volatility_penalty = 0
    close = history["Close"].dropna()
    if len(close) > 2:
        volatility = float(close.pct_change().dropna().std() * (252 ** 0.5) * 100)
        if volatility > 60:
            volatility_penalty = 35
        elif volatility > 40:
            volatility_penalty = 20
        elif volatility > 25:
            volatility_penalty = 10
    return {
        "score": max(0, min(100 - drawdown_penalty - volatility_penalty, 100)),
        "drawdown": drawdown,
        "drawdown_penalty": drawdown_penalty,
        "annualized_volatility": volatility,
        "volatility_penalty": volatility_penalty,
    }

def calculate_risk_score(metrics: dict[str, float | None], history: pd.DataFrame) -> int:
    return int(risk_score_details(metrics, history)["score"])


def explain_risk_score(metrics: dict[str, float | None], history: pd.DataFrame) -> str:
    details = risk_score_details(metrics, history)
    parts = [f"Drawdown penalty: -{details['drawdown_penalty']} points"]
    if details["annualized_volatility"] is not None:
        parts.append(f"Annualized volatility: {details['annualized_volatility']:.1f}% (-{details['volatility_penalty']} points)")
    return "; ".join(parts)
