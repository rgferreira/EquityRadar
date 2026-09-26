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
    ]

    for source in public_sources:
        content = source.read_text(encoding="utf-8")
        assert "/Users/" not in content, f"developer home path exposed in {source.name}"
