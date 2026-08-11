#!/bin/zsh

# Standalone lifecycle control for Equity Radar. Resolve the checkout from this
# script so the repository does not publish or depend on a developer home path.
set -u

SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${SCRIPT_DIR:h:h}"
PYTHON="$PROJECT_ROOT/.venv/bin/python"
APP="$PROJECT_ROOT/app.py"
WORK_DIR="$PROJECT_ROOT/work"
PID_FILE="$WORK_DIR/equity-radar.pid"
LOG_FILE="$WORK_DIR/streamlit.log"
PORT=8501
URL="http://127.0.0.1:$PORT"

mkdir -p "$WORK_DIR"

port_pid() {
  /usr/sbin/lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | /usr/bin/head -n 1
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
    "$PROJECT_ROOT/.streamlit"
  )
  if ! /usr/bin/find "${source_paths[@]}" -type f \( \
      -name '*.py' -o -name '*.toml' -o -name '*.css' \
    \) -print0 | /usr/bin/xargs -0 -P 8 -n 1 /bin/cat >/dev/null 2>>"$LOG_FILE"; then
    print -u2 -r -- "Project source files could not be made locally available. Check $LOG_FILE"
    return 1
  fi
}

start_server() {
  local pid=""
  if pid="$(running_pid)"; then
    /usr/bin/open "$URL"
    print -r -- "Equity Radar is already running. Dashboard opened."
    return 0
  fi
  local occupied
  occupied="$(port_pid)"
  if [[ -n "$occupied" ]]; then
    print -u2 -r -- "Port $PORT is occupied by another application (PID $occupied)."
    return 2
  fi
  if [[ ! -x "$PYTHON" ]]; then
    print -u2 -r -- "Python environment not found at $PYTHON"
    return 3
  fi
  if ! hydrate_project_sources; then
    return 7
  fi
  cd "$PROJECT_ROOT" || return 4
  nohup "$PYTHON" -m streamlit run "$APP" --server.port "$PORT" \
    --server.address 127.0.0.1 \
    > "$LOG_FILE" 2>&1 </dev/null &
  pid=$!
  print -r -- "$pid" > "$PID_FILE"
  local attempt
  for attempt in {1..50}; do
    if /usr/bin/curl -fsS --max-time 1 "$URL/_stcore/health" >/dev/null 2>&1; then
      /usr/bin/open "$URL"
      print -r -- "Equity Radar started successfully. Dashboard opened."
      return 0
    fi
    if ! /bin/kill -0 "$pid" 2>/dev/null; then
      /bin/rm -f "$PID_FILE"
      print -u2 -r -- "Equity Radar stopped during startup. Check $LOG_FILE"
      return 5
    fi
    /bin/sleep .2
  done
  print -u2 -r -- "Equity Radar is starting but did not become healthy within 10 seconds. Check $LOG_FILE"
  return 6
}

stop_server() {
  local pid=""
  if ! pid="$(running_pid)"; then
    /bin/rm -f "$PID_FILE"
    print -r -- "Equity Radar is already stopped."
    return 0
  fi
  /bin/kill "$pid" 2>/dev/null || true
  local attempt
  for attempt in {1..30}; do
    if ! /bin/kill -0 "$pid" 2>/dev/null; then
      /bin/rm -f "$PID_FILE"
      print -r -- "Equity Radar stopped successfully."
      return 0
    fi
    /bin/sleep .2
  done
  /bin/kill -KILL "$pid" 2>/dev/null || true
  /bin/rm -f "$PID_FILE"
  print -r -- "Equity Radar required a forced stop and is now closed."
}

status_server() {
  local pid=""
  if pid="$(running_pid)"; then
    print -r -- "running (PID $pid)"
  else
    print -r -- "stopped"
    return 1
  fi
}

case "${1:-}" in
  start) start_server ;;
  stop) stop_server ;;
  status) status_server ;;
  *) print -u2 -r -- "Usage: $0 {start|stop|status}"; exit 64 ;;
esac
