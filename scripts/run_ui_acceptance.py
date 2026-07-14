"""Render every application page at desktop and phone widths with Chromium.

This is an explicit release check, separate from pytest. It uses a synthetic
browser profile, performs no form submissions, and writes no application data.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen


ROUTES = {
    "/": "Decision dashboard",
    "/Portfolio": "Portfolio",
    "/Company": "Company detail",
    "/Journal": "Investment journal",
    "/Watchlist": "Watchlist management",
    "/Model-tuning": "Model tuning",
    "/Operations": "Provider health",
    "/Scenario-lab": "Scenario lab",
}
VIEWPORTS = {"desktop": (1440, 1000), "phone": (390, 844)}


def find_chromium() -> Path:
    configured = os.getenv("EQUITY_RADAR_CHROME_BIN")
    candidates = [Path(configured)] if configured else []
    candidates.extend(sorted(
        Path.home().glob(
            "Library/Caches/ms-playwright/chromium_headless_shell-*/"
            "chrome-headless-shell-mac-arm64/chrome-headless-shell"
        ), reverse=True,
    ))
    candidates.append(Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError("No Chromium executable found; set EQUITY_RADAR_CHROME_BIN")


def render(chromium: Path, url: str, width: int, height: int) -> str:
    command = [
        str(chromium), "--headless", "--disable-gpu", "--no-sandbox",
        f"--window-size={width},{height}", "--virtual-time-budget=5000",
        "--dump-dom", url,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
    if completed.returncode:
        raise RuntimeError(f"Chromium failed for {url}: {completed.stderr[-500:]}")
    return completed.stdout


def run(base_url: str) -> dict[str, object]:
    with urlopen(f"{base_url}/_stcore/health", timeout=5) as response:
        if response.read().decode().strip() != "ok":
            raise RuntimeError("Streamlit health endpoint is not ready")
    chromium = find_chromium()
    checks = []
    for viewport, (width, height) in VIEWPORTS.items():
        for route, expected in ROUTES.items():
            dom = ""
            attempts = 0
            for attempts in range(1, 4):
                dom = render(chromium, f"{base_url}{route}", width, height)
                if expected in dom or any(marker in dom for marker in (
                    "stException", "This app has encountered an error", "Traceback (most recent call last)",
                )):
                    break
            errors = []
            if expected not in dom:
                errors.append(f"missing expected text: {expected}")
            for marker in ("stException", "This app has encountered an error", "Traceback (most recent call last)"):
                if marker in dom:
                    errors.append(f"error marker: {marker}")
            checks.append({
                "viewport": viewport, "width": width, "height": height,
                "route": route, "expected": expected, "attempts": attempts,
                "passed": not errors, "errors": errors,
            })
    return {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "base_url": base_url,
        "chromium": str(chromium),
        "checks": checks,
        "passed": all(check["passed"] for check in checks),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8501")
    parser.add_argument("--output", default="work/ui-acceptance-latest.json")
    args = parser.parse_args()
    report = run(args.base_url.rstrip("/"))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    passed = sum(check["passed"] for check in report["checks"])
    print(f"UI acceptance: {passed}/{len(report['checks'])} rendered route/viewport checks passed")
    print(f"Report: {output}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
