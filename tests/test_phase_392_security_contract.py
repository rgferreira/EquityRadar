from pathlib import Path


def test_phase_392_runtime_dependencies_use_audited_versions():
    requirements = Path("requirements.txt").read_text(encoding="utf-8")

    assert "pyarrow==25.0.1" in requirements
    assert "GitPython==3.1.59" in requirements
    assert "pyarrow==19.0.1" not in requirements


def test_local_launcher_does_not_expose_private_research_to_the_lan():
    control = Path("scripts/macos/equity-radar-control.zsh").read_text(encoding="utf-8")

    assert "--server.address" in control
    assert "127.0.0.1" in control
    assert "0.0.0.0" not in control
