#!/usr/bin/env bash
# Restart Streamlit in background (nohup).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PORT="${PORT:-8502}"
LOG_DIR="$ROOT/logs"
PID_FILE="$LOG_DIR/streamlit.pid"
LOG_FILE="$LOG_DIR/streamlit.log"
CONDA_ENV="${CONDA_ENV:-fitness_agent}"

mkdir -p "$LOG_DIR"

stop_old() {
  if [[ -f "$PID_FILE" ]]; then
    old_pid="$(cat "$PID_FILE" || true)"
    if [[ -n "${old_pid}" ]] && kill -0 "$old_pid" 2>/dev/null; then
      kill "$old_pid" 2>/dev/null || true
      sleep 1
      kill -9 "$old_pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
  fi

  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "${pids}" ]]; then
      # shellcheck disable=SC2086
      kill $pids 2>/dev/null || true
      sleep 1
      # shellcheck disable=SC2086
      kill -9 $pids 2>/dev/null || true
    fi
  fi
}

resolve_python() {
  if [[ -n "${CONDA_PREFIX:-}" && "$(basename "$CONDA_PREFIX")" == "$CONDA_ENV" ]]; then
    echo "$CONDA_PREFIX/bin/python"
    return
  fi
  if command -v conda >/dev/null 2>&1; then
    local conda_py
    conda_py="$(conda run -n "$CONDA_ENV" python -c 'import sys; print(sys.executable)' 2>/dev/null || true)"
    if [[ -n "${conda_py}" && -x "${conda_py}" ]]; then
      echo "$conda_py"
      return
    fi
  fi
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    echo "$ROOT/.venv/bin/python"
    return
  fi
  command -v python3 || command -v python
}

stop_old

PYTHON_BIN="$(resolve_python)"
if [[ -z "${PYTHON_BIN}" || ! -x "${PYTHON_BIN}" ]]; then
  echo "找不到 Python（期望 conda 环境 ${CONDA_ENV} 或 .venv）" >&2
  exit 1
fi

nohup "$PYTHON_BIN" -m streamlit run "$ROOT/app.py" \
  --server.port "$PORT" \
  --server.headless true \
  --browser.gatherUsageStats false \
  >>"$LOG_FILE" 2>&1 &

echo $! >"$PID_FILE"
echo "已启动 pid=$(cat "$PID_FILE")  http://localhost:${PORT}"
echo "日志: $LOG_FILE"
