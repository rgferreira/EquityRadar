# macOS launcher

`Equity Radar Launcher.app` provides two Finder-friendly actions that do not require Codex:

- **Start everything** starts the Streamlit server, waits for its health endpoint, opens the Dashboard, and thereby starts the server-lifetime refresh and backup scheduler.
- **Stop everything** stops only the verified Equity Radar process listening on port 8501.

The app calls `scripts/macos/equity-radar-control.zsh`, which can also be used from Terminal:

```zsh
scripts/macos/equity-radar-control.zsh start
scripts/macos/equity-radar-control.zsh status
scripts/macos/equity-radar-control.zsh stop
```

Runtime PID and log files live under `work/` and are not committed. The launcher is idempotent: repeated Start or Stop actions are safe.
