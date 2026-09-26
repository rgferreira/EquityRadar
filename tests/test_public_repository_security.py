"""Guardrails for files that are safe to publish in the public repository."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_gitignore_covers_local_secrets_and_financial_data() -> None:
    rules = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    for required_rule in {
        ".env.*",
        "!.env.example",
        ".streamlit/secrets.toml",
        "*.db",
        "*.sqlite",
        "*.pem",
        "*.key",
        "*.p12",
        "*.pfx",
    }:
        assert required_rule in rules


def test_public_launcher_sources_do_not_expose_developer_home_paths() -> None:
    public_sources = [
        PROJECT_ROOT / "scripts/macos/equity-radar-control.zsh",
        PROJECT_ROOT / "scripts/macos/build-launcher.zsh",
        PROJECT_ROOT / "scripts/macos/EquityRadarLauncher.swift",
        PROJECT_ROOT / "scripts/macos/EquityRadarWidgetSupport.swift",
    ]

    for source in public_sources:
        content = source.read_text(encoding="utf-8")
        assert "/Users/" not in content, f"developer home path exposed in {source.name}"


def test_controller_resolves_checkout_and_materialized_launcher_copy(tmp_path):
    import os
    import subprocess

    text = (PROJECT_ROOT / "scripts/macos/equity-radar-control.zsh").read_text()
    prefix = text.split('APP="$PROJECT_ROOT/app.py"')[0]
    checkout = tmp_path / "checkout"
    (checkout / "scripts/macos").mkdir(parents=True)
    (checkout / "app.py").touch()
    materialized = tmp_path / "controller"
    materialized.mkdir()
    env = {k: v for k, v in os.environ.items() if k != "EQUITY_RADAR_PROJECT_ROOT"}
    for directory, expected in [(checkout / "scripts/macos", checkout),
                                (materialized, Path.home() / "Documents/PersonalEquityRadar")]:
        script = directory / "control.zsh"
        script.write_text(prefix + '\nprint -r -- "$PROJECT_ROOT"\n')
        assert subprocess.check_output(["zsh", str(script)], env=env, text=True).strip() == str(expected)
        assert subprocess.check_output(["zsh", str(script)], env={**env, "EQUITY_RADAR_PROJECT_ROOT": str(checkout)}, text=True).strip() == str(checkout)
