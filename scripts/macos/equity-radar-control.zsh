#!/bin/zsh

# Standalone lifecycle control for Equity Radar. It intentionally uses absolute
# project paths so Finder/AppleScript launches do not depend on shell profiles.
set -u

PROJECT_ROOT="/Users/rafaelgonzalezferreira/Documents/PersonalEquityRadar"
APP="$PROJECT_ROOT/app.py"
SUPPORT_DIR="$HOME/Library/Application Support/EquityRadar"
VENV_DIR="$SUPPORT_DIR/venv-3.9"
PYTHON="$VENV_DIR/bin/python"
PYTHON_FORMULA="python@3.13"
BOOTSTRAP_PYTHON="/opt/homebrew/opt/$PYTHON_FORMULA/bin/python3.13"
REQUIREMENTS="$PROJECT_ROOT/requirements.txt"
RUNTIME_DIR="$SUPPORT_DIR/runtime"
DATA_DIR="$SUPPORT_DIR/data"
RUNTIME_DB="$DATA_DIR/personal_equity_radar.db"
LEGACY_DB="$PROJECT_ROOT/personal_equity_radar.db"
PID_FILE="$RUNTIME_DIR/equity-radar.pid"
LOG_FILE="$RUNTIME_DIR/streamlit.log"
SOURCE_STATE_FILE="$RUNTIME_DIR/source-state.sha256"
VERIFIED_PID_FILE="$RUNTIME_DIR/verified-dashboard.pid"
RUNTIME_SOURCE_DIR="$RUNTIME_DIR/source"
RUNTIME_SOURCE_NEXT="$RUNTIME_DIR/source.next"
RUNTIME_SOURCE_ROLLBACK="$RUNTIME_DIR/source.rollback"
RUNTIME_APP="$RUNTIME_SOURCE_DIR/app.py"
RUNTIME_ACCEPTANCE="$RUNTIME_DIR/run_ui_acceptance.py"
RUNTIME_CONFIG_DIR="$RUNTIME_SOURCE_DIR/.streamlit"
RUNTIME_CONFIG="$RUNTIME_CONFIG_DIR/config.toml"
SERVICE_LABEL="com.rgferreira.equityradar.server"
SERVICE_DOMAIN="gui/$(/usr/bin/id -u)"
SERVICE_TARGET="$SERVICE_DOMAIN/$SERVICE_LABEL"
SERVICE_PLIST="$RUNTIME_DIR/$SERVICE_LABEL.plist"
PORT=8501
URL=""
BIND_ADDRESS=""
ZEROTIER_CLI=""

for candidate in \
  /usr/local/bin/zerotier-cli \
  /opt/homebrew/bin/zerotier-cli \
  "/Library/Application Support/ZeroTier/One/zerotier-cli"; do
  if [[ -x "$candidate" ]]; then
    ZEROTIER_CLI="$candidate"
    break
  fi
done

/bin/mkdir -p "$RUNTIME_CONFIG_DIR" "$DATA_DIR"
/bin/chmod 700 "$DATA_DIR"

python_environment_ready() {
  [[ -x "$PYTHON" ]] || return 1
  "$PYTHON" -c 'import pandas, pyarrow, streamlit' >/dev/null 2>&1
}

repair_python_environment() {
  local brew="/opt/homebrew/bin/brew"
  local staging=""
  local rollback=""

  [[ -x "$brew" ]] || {
    print -u2 -r -- "Homebrew is required to repair the Equity Radar Python environment."
    return 1
  }
  print -r -- "Repairing the Equity Radar Python environment; this can take a few minutes..."
  if [[ ! -x "$BOOTSTRAP_PYTHON" ]]; then
    HOMEBREW_NO_AUTO_UPDATE=1 "$brew" install "$PYTHON_FORMULA" >>"$LOG_FILE" 2>&1 \
      || return 1
  fi

  # A Homebrew cleanup can remove the interpreter behind an otherwise intact
  # virtual environment. Restoring the same Python minor version is sufficient
  # and avoids a needless dependency reinstall.
  if python_environment_ready; then
    return 0
  fi

  [[ -r "$REQUIREMENTS" ]] || return 1
  staging="$(/usr/bin/mktemp -d "$SUPPORT_DIR/venv-build.XXXXXX")" || return 1
  if ! "$BOOTSTRAP_PYTHON" -m venv "$staging" \
      || ! "$staging/bin/python" -m pip install \
        --disable-pip-version-check -r "$REQUIREMENTS" >>"$LOG_FILE" 2>&1 \
      || ! "$staging/bin/python" -c 'import pandas, pyarrow, streamlit' >/dev/null 2>&1; then
    /bin/rm -rf "$staging"
    return 1
  fi

  rollback="$SUPPORT_DIR/venv.rollback.$(/bin/date +%Y%m%d%H%M%S)"
  if [[ -e "$VENV_DIR" || -L "$VENV_DIR" ]]; then
    /bin/mv "$VENV_DIR" "$rollback" || {
      /bin/rm -rf "$staging"
      return 1
    }
  fi
  if ! /bin/mv "$staging" "$VENV_DIR"; then
    [[ -e "$rollback" ]] && /bin/mv "$rollback" "$VENV_DIR"
    return 1
  fi
  python_environment_ready
}

ensure_python_environment() {
  python_environment_ready && return 0
  repair_python_environment && return 0
  print -u2 -r -- \
    "The Equity Radar Python environment could not be repaired safely. Check $LOG_FILE"
  return 1
}

prepare_runtime_database() {
  if [[ -s "$RUNTIME_DB" ]]; then
    /bin/chmod 600 "$RUNTIME_DB"
    return 0
  fi
  if [[ ! -s "$LEGACY_DB" ]]; then
    return 0
  fi

  # Documents can be managed by File Provider. Seed the live database into
  # Application Support with SQLite's online-backup API so WAL state is copied
  # consistently; retain the legacy file as a recoverable rollback snapshot.
  "$PYTHON" - "$LEGACY_DB" "$RUNTIME_DB" <<'PY'
import sqlite3
import sys
from pathlib import Path

source_path = Path(sys.argv[1])
destination_path = Path(sys.argv[2])
temporary_path = destination_path.with_suffix(".db.migrating")
temporary_path.unlink(missing_ok=True)
try:
    with sqlite3.connect(source_path) as source, sqlite3.connect(temporary_path) as destination:
        source.backup(destination)
        result = destination.execute("PRAGMA quick_check").fetchone()
        if not result or result[0] != "ok":
            raise sqlite3.DatabaseError("runtime database quick_check failed")
    temporary_path.replace(destination_path)
finally:
    temporary_path.unlink(missing_ok=True)
PY
  /bin/chmod 600 "$RUNTIME_DB"
}

port_pid() {
  /usr/sbin/lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | /usr/bin/head -n 1
}

zerotier_address() {
  [[ -n "$ZEROTIER_CLI" && -x "$ZEROTIER_CLI" ]] || return 1
  "$ZEROTIER_CLI" -j listnetworks 2>/dev/null | "$PYTHON" -c '
import ipaddress
import json
import sys

try:
    networks = json.load(sys.stdin)
except Exception:
    raise SystemExit(1)

addresses = []
for network in networks if isinstance(networks, list) else []:
    if network.get("status") != "OK":
        continue
    for value in network.get("assignedAddresses") or []:
        try:
            address = ipaddress.ip_interface(value).ip
        except ValueError:
            continue
        if address.version == 4 and not address.is_loopback:
            addresses.append(str(address))

addresses = sorted(set(addresses))
if len(addresses) != 1:
    raise SystemExit(1)
print(addresses[0])
'
}

configure_network_endpoint() {
  local address=""
  if ! address="$(zerotier_address)" || [[ -z "$address" ]]; then
    print -u2 -r -- \
      "ZeroTier must be online with exactly one assigned IPv4 address before Equity Radar can start."
    return 1
  fi
  BIND_ADDRESS="$address"
  URL="http://$BIND_ADDRESS:$PORT"
}

listener_on_zerotier_address() {
  local pid="${1:-}"
  [[ "$pid" == <-> && -n "$BIND_ADDRESS" ]] || return 1
  /usr/sbin/lsof -nP -a -p "$pid" -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null \
    | /usr/bin/awk -v endpoint="$BIND_ADDRESS:$PORT" \
      'NR > 1 && $9 == endpoint { found=1 } END { exit !found }'
}

is_equity_radar_pid() {
  local pid="${1:-}"
  [[ "$pid" == <-> ]] || return 1
  /bin/kill -0 "$pid" 2>/dev/null || return 1
  local command
  command="$(/bin/ps -p "$pid" -o command= 2>/dev/null)"
  [[ "$command" == *"streamlit"* && "$command" == *"app.py"* ]]
}

running_pid() {
  local pid=""
  if [[ -f "$PID_FILE" ]]; then
    pid="$(<"$PID_FILE")"
    if is_equity_radar_pid "$pid"; then
      print -r -- "$pid"
      return 0
    fi
    /bin/rm -f "$PID_FILE"
  fi
  pid="$(port_pid)"
  if is_equity_radar_pid "$pid"; then
    print -r -- "$pid" > "$PID_FILE"
    print -r -- "$pid"
    return 0
  fi
  return 1
}

hydrate_project_sources() {
  # Documents may be managed by macOS File Provider. Reading source files once
  # before launch materializes any placeholders so Streamlit cannot fail later
  # while lazily loading a page module.
  local source_paths=(
    "$APP"
    "$PROJECT_ROOT/pages"
    "$PROJECT_ROOT/src"
    "$PROJECT_ROOT/scripts/run_ui_acceptance.py"
  )
  if ! /usr/bin/find "${source_paths[@]}" -type f \( \
      -name '*.py' -o -name '*.toml' -o -name '*.css' \
    \) -print0 | /usr/bin/xargs -0 -P 8 -n 1 /bin/cat >/dev/null 2>>"$LOG_FILE"; then
    print -u2 -r -- "Project source files could not be made locally available. Check $LOG_FILE"
    return 1
  fi
}

source_revision() {
  /usr/bin/find -s "$APP" "$PROJECT_ROOT/pages" "$PROJECT_ROOT/src" \
    -type f -name '*.py' -exec /usr/bin/shasum -a 256 {} + \
    | /usr/bin/shasum -a 256 | /usr/bin/awk '{print $1}'
}

dashboard_ready() {
  "$PYTHON" "$RUNTIME_ACCEPTANCE" \
    --base-url "$URL" --probe-route / --probe-expected "Decision dashboard" \
    >>"$LOG_FILE" 2>&1
}

prepare_runtime_config() {
  local project_config="$PROJECT_ROOT/.streamlit/config.toml"
  local project_flags=""
  /bin/mkdir -p "$RUNTIME_CONFIG_DIR"
  project_flags="$(/usr/bin/stat -f '%Sf' "$project_config" 2>/dev/null || true)"

  # Run Streamlit from local Application Support rather than Documents. Keep a
  # local copy of the UI config there so an offloaded project config can never
  # block launcher startup.
  if [[ -r "$project_config" && "$project_flags" != *dataless* ]]; then
    /bin/cp "$project_config" "$RUNTIME_CONFIG"
    return 0
  fi
  if [[ -s "$RUNTIME_CONFIG" ]]; then
    return 0
  fi
  /bin/cat > "$RUNTIME_CONFIG" <<'EOF'
[theme]
base = "dark"
baseFontSize = 14
metricValueFontSize = "1.8rem"
headingFontSizes = ["2.35rem", "1.85rem", "1.45rem", "1.2rem", "1rem", "0.9rem"]
headingFontWeights = [750, 700, 675, 650, 625, 600]

[browser]
gatherUsageStats = false

[server]
headless = true
EOF
}

prepare_runtime_source_copy() {
  # Streamlit lazily reopens page and imported module files. No runtime path may
  # point back into Documents/File Provider, even after a successful hydration.
  /bin/rm -rf "$RUNTIME_SOURCE_NEXT"
  /bin/mkdir -p "$RUNTIME_SOURCE_NEXT"
  /usr/bin/ditto "$APP" "$RUNTIME_SOURCE_NEXT/app.py" || return 1
  /usr/bin/ditto "$PROJECT_ROOT/pages" "$RUNTIME_SOURCE_NEXT/pages" || return 1
  /usr/bin/ditto "$PROJECT_ROOT/src" "$RUNTIME_SOURCE_NEXT/src" || return 1
  /usr/bin/ditto "$PROJECT_ROOT/scripts/run_ui_acceptance.py" "$RUNTIME_ACCEPTANCE" || return 1

  # Publish only a complete tree. Keep the immediately previous tree as a
  # local rollback; no database or research evidence is part of this rotation.
  /bin/rm -rf "$RUNTIME_SOURCE_ROLLBACK"
  if [[ -e "$RUNTIME_SOURCE_DIR" || -L "$RUNTIME_SOURCE_DIR" ]]; then
    /bin/mv "$RUNTIME_SOURCE_DIR" "$RUNTIME_SOURCE_ROLLBACK" || return 1
  fi
  if ! /bin/mv "$RUNTIME_SOURCE_NEXT" "$RUNTIME_SOURCE_DIR"; then
    [[ -e "$RUNTIME_SOURCE_ROLLBACK" ]] \
      && /bin/mv "$RUNTIME_SOURCE_ROLLBACK" "$RUNTIME_SOURCE_DIR"
    return 1
  fi
}

service_loaded() {
  /bin/launchctl print "$SERVICE_TARGET" >/dev/null 2>&1
}

prepare_launch_agent() {
  /bin/cat > "$SERVICE_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$SERVICE_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>-m</string>
    <string>streamlit</string>
    <string>run</string>
    <string>$RUNTIME_APP</string>
    <string>--server.port</string>
    <string>$PORT</string>
    <string>--server.address</string>
    <string>$BIND_ADDRESS</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$RUNTIME_DIR</string>
  <key>RunAtLoad</key>
  <true/>
  <key>Umask</key>
  <integer>63</integer>
  <key>StandardOutPath</key>
  <string>$LOG_FILE</string>
  <key>StandardErrorPath</key>
  <string>$LOG_FILE</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key>
    <string>$HOME</string>
    <key>EQUITY_RADAR_DB_PATH</key>
    <string>$RUNTIME_DB</string>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
</dict>
</plist>
EOF
  /usr/bin/plutil -lint "$SERVICE_PLIST" >/dev/null
}

start_server() {
  local pid=""
  local current_revision=""
  local verified_pid=""
  if ! ensure_python_environment; then
    return 3
  fi
  if ! prepare_runtime_database; then
    print -u2 -r -- "The runtime database could not be prepared safely."
    return 15
  fi
  if ! configure_network_endpoint; then
    return 14
  fi
  if pid="$(running_pid)"; then
    [[ -f "$VERIFIED_PID_FILE" ]] && verified_pid="$(<"$VERIFIED_PID_FILE")"
    if [[ "$verified_pid" == "$pid" ]] \
        && listener_on_zerotier_address "$pid" \
        && /usr/bin/curl -fsS --max-time 2 "$URL/_stcore/health" >/dev/null 2>&1 \
        && dashboard_ready; then
      /usr/bin/open "$URL" >/dev/null 2>&1 </dev/null
      print -r -- "Equity Radar is already running and the ZeroTier Dashboard route is verified."
      return 0
    fi
  fi
  if ! hydrate_project_sources; then
    return 7
  fi
  current_revision="$(source_revision)" || return 12
  if [[ -n "$pid" ]]; then
    stop_server >/dev/null
  fi
  local occupied
  occupied="$(port_pid)"
  if [[ -n "$occupied" ]]; then
    print -u2 -r -- "Port $PORT is occupied by another application (PID $occupied)."
    return 2
  fi
  if ! prepare_runtime_source_copy; then
    print -u2 -r -- "The local Streamlit source copy could not be prepared atomically."
    return 9
  fi
  if ! prepare_runtime_config; then
    print -u2 -r -- "The local Streamlit configuration could not be prepared."
    return 8
  fi
  if ! prepare_launch_agent; then
    print -u2 -r -- "The local launch service could not be prepared."
    return 10
  fi
  if service_loaded; then
    /bin/launchctl kickstart -k "$SERVICE_TARGET" || return 11
  else
    /bin/launchctl bootstrap "$SERVICE_DOMAIN" "$SERVICE_PLIST" || return 11
  fi
  local attempt
  for attempt in {1..50}; do
    if /usr/bin/curl -fsS --max-time 1 "$URL/_stcore/health" >/dev/null 2>&1; then
      pid="$(port_pid)"
      if listener_on_zerotier_address "$pid" && dashboard_ready; then
        print -r -- "$pid" > "$PID_FILE"
        print -r -- "$current_revision" > "$SOURCE_STATE_FILE"
        print -r -- "$pid" > "$VERIFIED_PID_FILE"
        /usr/bin/open "$URL" >/dev/null 2>&1 </dev/null
        print -r -- "Equity Radar started successfully. ZeroTier route and Dashboard verified."
        return 0
      fi
      /bin/rm -f "$PID_FILE" "$VERIFIED_PID_FILE"
      print -u2 -r -- "Streamlit is healthy but the Dashboard did not render. Check $LOG_FILE"
      return 13
    fi
    /bin/sleep .2
  done
  /bin/rm -f "$PID_FILE" "$VERIFIED_PID_FILE"
  print -u2 -r -- "Equity Radar is starting but did not become healthy within 10 seconds. Check $LOG_FILE"
  return 6
}

restart_server() {
  stop_server >/dev/null
  start_server
}

stop_server() {
  local pid=""
  if ! pid="$(running_pid)"; then
    if service_loaded; then
      /bin/launchctl bootout "$SERVICE_TARGET" >/dev/null 2>&1 || true
    fi
    /bin/rm -f "$PID_FILE" "$VERIFIED_PID_FILE"
    print -r -- "Equity Radar is already stopped."
    return 0
  fi
  if service_loaded; then
    /bin/launchctl bootout "$SERVICE_TARGET" >/dev/null 2>&1 || true
  else
    /bin/kill "$pid" 2>/dev/null || true
  fi
  local attempt
  for attempt in {1..30}; do
    if ! /bin/kill -0 "$pid" 2>/dev/null; then
      /bin/rm -f "$PID_FILE" "$VERIFIED_PID_FILE"
      print -r -- "Equity Radar stopped successfully."
      return 0
    fi
    /bin/sleep .2
  done
  /bin/kill -KILL "$pid" 2>/dev/null || true
  /bin/rm -f "$PID_FILE" "$VERIFIED_PID_FILE"
  print -r -- "Equity Radar required a forced stop and is now closed."
}

status_server() {
  local pid=""
  if [[ ! -x "$PYTHON" ]] || ! configure_network_endpoint; then
    return 14
  fi
  if ! pid="$(running_pid)"; then
    print -r -- "stopped"
    return 1
  fi
  if ! listener_on_zerotier_address "$pid" \
      || ! /usr/bin/curl -fsS --max-time 2 "$URL/_stcore/health" >/dev/null 2>&1 \
      || ! dashboard_ready; then
    print -u2 -r -- "running, but the ZeroTier Dashboard route is not reachable"
    return 15
  fi
  print -r -- "running; ZeroTier route and Dashboard verified"
}

case "${1:-}" in
  start) start_server ;;
  restart) restart_server ;;
  stop) stop_server ;;
  status) status_server ;;
  *) print -u2 -r -- "Usage: $0 {start|restart|stop|status}"; exit 64 ;;
esac
