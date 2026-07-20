# macOS launcher

`Equity Radar Launcher.app` is a native SwiftUI utility that does not require Codex:

- **Start everything** starts the Streamlit server, waits for its health endpoint, opens the Dashboard, and thereby starts the server-lifetime refresh and backup scheduler.
- **Stop everything** stops only the verified Equity Radar process listening on port 8501.

The app calls `scripts/macos/equity-radar-control.zsh`, which can also be used from Terminal:

```zsh
scripts/macos/equity-radar-control.zsh start
scripts/macos/equity-radar-control.zsh status
scripts/macos/equity-radar-control.zsh stop
```

Runtime PID and log files live under `work/` and are not committed. The launcher is idempotent: repeated Start or Stop actions are safe.
It behaves like a normal macOS app: it does not hide or minimize other applications, and **Quit Equity Radar Launcher** / **⌘Q** remains available.

On Macs where the repository is inside an iCloud/File Provider-managed Documents folder, keep the Python environment on local storage and expose it to the launcher through the conventional `.venv` path. The current installation uses:

```text
.venv -> ~/Library/Application Support/EquityRadar/venv-3.9
```

This prevents macOS from offloading thousands of dependency files while preserving every existing launcher command. The pre-migration environment may be retained temporarily as `.venv-cloud-backup-<date>` for rollback; it must remain untracked.

Rebuild the Desktop app with:

```zsh
scripts/macos/build-launcher.zsh
```

Installation is atomic: an existing launcher is held only inside the temporary build directory and restored if installation fails. A successful rebuild leaves exactly one installed launcher app.
