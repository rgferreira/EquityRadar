"""Render every application page at desktop and phone widths with Chromium.

This is an explicit release check, separate from pytest. It uses a synthetic
browser profile, performs no form submissions, and writes no application data.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

from websockets.sync.client import connect


ROUTES = {
    "/": "Decision dashboard",
    "/Portfolio": "Portfolio",
    "/WhaleSeeker": "WhaleSeeker",
    "/Company": "Company detail",
    "/Journal": "Investment journal",
    "/Watchlist": "Watchlist management",
    "/Model-tuning": "Model tuning",
    "/Operations": "Provider health",
    "/Scenario-lab": "Scenario lab",
}
VIEWPORTS = {"desktop": (1440, 1000), "phone": (390, 844)}
ERROR_MARKERS = (
    "stException", "This app has encountered an error", "Traceback (most recent call last)",
    "OperationalError",
)
EXPECTED_CONTENT_STABILITY_SECONDS = 2.0


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


def _cdp_evaluate(socket: object, message_id: int, expression: str) -> dict[str, object]:
    socket.send(json.dumps({
        "id": message_id,
        "method": "Runtime.evaluate",
        "params": {"expression": expression, "returnByValue": True},
    }))
    while True:
        response = json.loads(socket.recv(timeout=5))
        if response.get("id") == message_id:
            return response


def _render_is_complete(status: dict[str, object], expected: str) -> bool:
    """Stop immediately for a rendered failure or a completed valid script."""
    html = str(status.get("html") or "")
    state = str(status.get("state") or "")
    if any(marker in html for marker in ERROR_MARKERS):
        return True
    return state == "notRunning" and expected in html


def render(chromium: Path, url: str, width: int, height: int, expected: str) -> str:
    """Render after Streamlit finishes, not after an arbitrary virtual-time budget."""
    profile = tempfile.TemporaryDirectory(prefix="equity-radar-chromium-")
    command = [
        str(chromium), "--headless=new", "--disable-gpu", "--no-sandbox",
        "--disable-background-timer-throttling", "--remote-debugging-port=0",
        "--remote-allow-origins=*", f"--user-data-dir={profile.name}",
        f"--window-size={width},{height}", url,
    ]
    process = subprocess.Popen(
        command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True,
        start_new_session=True,
    )
    html = ""
    expected_seen_at: float | None = None
    try:
        port_file = Path(profile.name) / "DevToolsActivePort"
        deadline = time.monotonic() + 30
        while not port_file.exists() and time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Chromium stopped before DevTools was ready")
            time.sleep(0.05)
        if not port_file.exists():
            raise RuntimeError("Chromium DevTools endpoint did not become ready")
        port = port_file.read_text(encoding="utf-8").splitlines()[0]
        page = None
        while page is None and time.monotonic() < deadline:
            with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as response:
                targets = json.load(response)
            page = next((item for item in targets if item.get("type") == "page"), None)
            if page is None:
                time.sleep(0.05)
        if page is None:
            raise RuntimeError("Chromium page target did not become ready")
        with connect(str(page["webSocketDebuggerUrl"]), open_timeout=5) as socket:
            message_id = 0
            while time.monotonic() < deadline:
                message_id += 1
                try:
                    response = _cdp_evaluate(socket, message_id, """
                        JSON.stringify({
                          html: document.querySelector('[data-testid="stMainBlockContainer"]')
                            ?.innerText || '',
                          ready: window.prerenderReady === true,
                          state: document.querySelector('[data-testid="stApp"]')
                            ?.getAttribute('data-test-script-state') || ''
                        })
                    """)
                except TimeoutError:
                    time.sleep(0.1)
                    continue
                value = (
                    response.get("result", {}).get("result", {}).get("value")
                    if isinstance(response, dict) else None
                )
                if isinstance(value, str):
                    status = json.loads(value)
                    html = str(status.get("html") or "")
                    if _render_is_complete(status, expected):
                        return html
                    if expected in html:
                        if expected_seen_at is None:
                            expected_seen_at = time.monotonic()
                        elif (
                            time.monotonic() - expected_seen_at
                            >= EXPECTED_CONTENT_STABILITY_SECONDS
                        ):
                            return html
                    else:
                        expected_seen_at = None
                time.sleep(0.1)
        raise RuntimeError(f"Streamlit did not finish rendering {url} within 30 seconds")
    finally:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)
        profile.cleanup()


def _assert_server_health(base_url: str) -> None:
    with urlopen(f"{base_url}/_stcore/health", timeout=5) as response:
        if response.read().decode().strip() != "ok":
            raise RuntimeError("Streamlit health endpoint is not ready")


def probe_route(
    base_url: str, route: str = "/", expected: str = "Decision dashboard",
) -> dict[str, object]:
    """Prove that a route starts a real Streamlit session without an error page."""
    _assert_server_health(base_url)
    chromium = find_chromium()
    dom = render(chromium, f"{base_url}{route}", 1280, 900, expected)
    errors = [marker for marker in ERROR_MARKERS if marker in dom]
    return {
        "route": route,
        "expected": expected,
        "passed": expected in dom and not errors,
        "errors": errors,
    }


def run(base_url: str) -> dict[str, object]:
    _assert_server_health(base_url)
    chromium = find_chromium()
    checks = []
    for viewport, (width, height) in VIEWPORTS.items():
        for route, expected in ROUTES.items():
            dom = ""
            attempts = 0
            for attempts in range(1, 4):
                dom = render(chromium, f"{base_url}{route}", width, height, expected)
                if expected in dom or any(marker in dom for marker in ERROR_MARKERS):
                    break
            errors = []
            if expected not in dom:
                errors.append(f"missing expected text: {expected}")
            for marker in ERROR_MARKERS:
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
    parser.add_argument("--probe-route")
    parser.add_argument("--probe-expected", default="Decision dashboard")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    if args.probe_route is not None:
        result = probe_route(base_url, args.probe_route, args.probe_expected)
        print(
            f"Route probe: {result['route']} "
            f"{'ready' if result['passed'] else 'failed'}"
        )
        return 0 if result["passed"] else 1
    report = run(base_url)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    passed = sum(check["passed"] for check in report["checks"])
    print(f"UI acceptance: {passed}/{len(report['checks'])} rendered route/viewport checks passed")
    print(f"Report: {output}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
