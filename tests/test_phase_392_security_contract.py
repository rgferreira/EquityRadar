from pathlib import Path


def test_phase_392_runtime_dependencies_use_audited_versions():
    requirements = Path("requirements.txt").read_text(encoding="utf-8")

    assert "pyarrow==25.0.1" in requirements
    assert "GitPython==3.1.60" in requirements
    assert "pyarrow==19.0.1" not in requirements


def test_launcher_binds_only_to_the_active_zerotier_address():
    control = Path("scripts/macos/equity-radar-control.zsh").read_text(encoding="utf-8")

    assert "--server.address" in control
    assert "0.0.0.0" not in control
    assert "zerotier-cli" in control
    assert 'network.get("status") != "OK"' in control
    assert 'network.get("assignedAddresses")' in control
    assert 'BIND_ADDRESS="$address"' in control
    assert 'listener_on_zerotier_address "$pid"' in control
    assert "ZeroTier route and Dashboard verified" in control
