"""Print a read-only legacy-versus-current decision accuracy audit."""

from src.accuracy_audit import compare_accuracy_models
from src.data.database import get_backtest_runs, get_watchlist


def main() -> None:
    audit = compare_accuracy_models({ticker: get_backtest_runs(ticker) for ticker in get_watchlist()})
    print("Ticker   Previous        Current         Delta")
    for row in audit["tickers"]:
        print(
            f"{row['ticker']:<8} {row['legacy_accuracy']:>5.1f}% ({row['legacy_observations']:>2})  "
            f"{row['current_accuracy']:>5.1f}% ({row['current_observations']:>2})  {row['delta_pp']:+5.1f}pp"
        )
    print()
    print(
        f"Pooled: {audit['legacy_micro_accuracy']:.2f}% ({audit['legacy_observations']}) -> "
        f"{audit['current_micro_accuracy']:.2f}% ({audit['current_observations']})"
    )
    print(f"Ticker average: {audit['legacy_macro_accuracy']:.2f}% -> {audit['current_macro_accuracy']:.2f}%")
    print(
        f"Same confirmed episodes: {audit['same_episode_legacy_accuracy']:.2f}% -> "
        f"{audit['same_episode_current_accuracy']:.2f}%"
    )
    print("\nThree-cutoff sample-weighted moving accuracy")
    legacy = {row["as_of_date"]: row for row in audit["legacy_moving_curve"]}
    current = {row["as_of_date"]: row for row in audit["current_moving_curve"]}
    for cutoff in sorted(set(legacy) | set(current)):
        old, new = legacy.get(cutoff), current.get(cutoff)
        old_text = "—" if old is None else f"{old['moving_accuracy']:.1f}% ({old['observations']})"
        new_text = "—" if new is None else f"{new['moving_accuracy']:.1f}% ({new['observations']})"
        print(f"{cutoff}  {old_text:>12} -> {new_text}")


if __name__ == "__main__":
    main()
