# macOS launcher

`Equity Radar.app` is a native SwiftUI utility that does not require Codex:

- **Start everything** starts Streamlit, verifies that a real Dashboard session renders without an error page, and only then opens it. When a verified process is already running, it opens immediately without re-reading the iCloud-managed source tree.
- **Stop everything** stops only the verified Equity Radar process listening on port 8501.

The app calls `scripts/macos/equity-radar-control.zsh`, which can also be used from Terminal:

```zsh
scripts/macos/equity-radar-control.zsh start
scripts/macos/equity-radar-control.zsh restart
scripts/macos/equity-radar-control.zsh status
scripts/macos/equity-radar-control.zsh stop
```

Runtime PID and log files live under
`~/Library/Application Support/EquityRadar/runtime/`, outside the
iCloud/File Provider-managed repository, and are not committed. This keeps
Start/Stop reliable even when macOS has offloaded files inside Documents.
The controller runs Streamlit as a per-user `launchd` service, so it survives
the launcher window closing and is stopped cleanly by **Stop everything**.
The launcher is idempotent: repeated Start or Stop actions are safe. A verified
running PID takes the fast path and does not re-read an iCloud-managed source
tree. `restart` is the explicit, mandatory post-change command for development
and release checks; it performs hydration, source fingerprinting and a real route probe. The
server resolves the single active ZeroTier IPv4 address at startup and binds only
to it, never to `0.0.0.0`. This keeps private research off the ordinary LAN while
allowing the authorised mobile route. Health, listener address and the rendered
Dashboard route are checked through ZeroTier before the launcher opens the
Dashboard on the Mac. The source fingerprint records exactly what the explicit
post-change restart verified. ZeroTier availability on the Mac and mobile is an
operational prerequisite managed by the user.
The verified process ID is retained separately, so repeated **Start** actions
open immediately while an unexpected `launchd` replacement must pass the real
route probe again.
The native UI is also single-instance. macOS rejects additional instances, the
Swift process holds an advisory lock under Application Support, and a launch
from any non-canonical copy delegates to the running app in
`~/Applications/Equity Radar.app`. The app declares one fixed SwiftUI window,
so reopen events activate that window instead of creating another one.
The persistent **Start server on launch** switch is enabled by default. When it
is on, opening the canonical app runs the same idempotent path as **Start
everything**. If ZeroTier or a local dependency is not ready yet after login,
the app retries with exponential backoff capped at 30 seconds until startup is
verified or the switch is turned off. Turning it off cancels pending retries and
the setting remains disabled across later launches.
Browser opening is detached from the controller's captured output so the native
launcher receives its final status promptly instead of waiting on descriptors
inherited by the browser process.
Cold startup initializes SQLite synchronously before the maintenance scheduler
can run. Bootstrap callers are serialized inside the server process, managed
connections close their descriptors, and SQLite uses WAL with a 30-second busy
timeout. The route probe waits for Streamlit's script to finish, requires the
Dashboard title inside the main content container rather than the navigation,
and rejects rendered exceptions including `OperationalError`; a healthy HTTP
endpoint alone is not acceptance.
The native bundle declares why it needs access to the Documents folder: the
local source tree and SQLite database live there. On first launch after an
install or signature change, macOS may ask the user to grant that access before
the launcher can hydrate the project and start the server. The Swift process
preflights a small project marker read so the permission is attributed to Equity
Radar itself before its shell controller enumerates the source tree.
It behaves like a normal macOS app: it does not hide or minimize other applications, and **Quit Equity Radar Launcher** / **⌘Q** remains available.
Its native icon follows the shared CodexWatch and Relay visual family: a dark
navy glass tile, cyan/indigo/violet illumination, and a distinct equity-radar
mark. The 1024 px master and generated macOS `.icns` live under
`scripts/macos/Resources/`; both Xcode and Command Line Tools builds package the
same icon.
At runtime the SwiftUI app also assigns that resource to
`NSApplication.applicationIconImage`, and the installer refreshes the canonical
bundle registration. This prevents the Dock from retaining the generic icon
after closing and reopening the launcher.

On Macs where the repository is inside an iCloud/File Provider-managed Documents folder, keep the Python environment on local storage and expose it to the launcher through the conventional `.venv` path. The current installation uses:

```text
.venv -> ~/Library/Application Support/EquityRadar/venv-3.9
```

This prevents macOS from offloading thousands of dependency files while preserving every existing launcher command. The pre-migration environment may be retained temporarily as `.venv-cloud-backup-<date>` for rollback; it must remain untracked.

Rebuild the native app with:

```zsh
scripts/macos/build-launcher.zsh
```

Installation is atomic: an existing launcher is held only inside the temporary
build directory and restored if installation fails. The canonical signed bundle
lives at `~/Applications/Equity Radar.app`; the familiar Desktop item is a
symbolic link to it. This prevents iCloud/File Provider from reattaching Finder
metadata inside the widget and invalidating the code signature after installation.

If full Xcode is unavailable, the same command rebuilds the main SwiftUI binary
with Command Line Tools, preserves the existing widget, applies a local ad-hoc
signature, verifies it strictly, and only then replaces the installed copy. It
must not apply an Apple Development identity without Xcode's managed provisioning
profile: doing so produces an App Group entitlement that `amfid` rejects. At runtime the launcher
copies its sealed controller to Application Support and runs that local copy via
`/bin/zsh`; this avoids intermittent macOS blocking when a piped process executes
a script directly from inside a signed app bundle. Widget source changes still
require full Xcode.
