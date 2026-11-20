#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
PYTHON3="$(command -v python3 || true)"

if [[ -z "$PYTHON3" ]]; then
  echo "python3 was not found. Install Python 3.11+ first." >&2
  exit 1
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON3" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$PROJECT_DIR/requirements.txt"

LABEL="com.quantlab.paper"
AGENT_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs/QuantLab"
PLIST="$AGENT_DIR/$LABEL.plist"
mkdir -p "$AGENT_DIR" "$LOG_DIR"

export PROJECT_DIR VENV_PYTHON="$VENV_DIR/bin/python" LOG_DIR PLIST LABEL
"$PYTHON3" <<'PY'
import os
import plistlib

label = os.environ["LABEL"]
project = os.environ["PROJECT_DIR"]
python = os.environ["VENV_PYTHON"]
logs = os.environ["LOG_DIR"]
plist_path = os.environ["PLIST"]

payload = {
    "Label": label,
    "ProgramArguments": [
        "/usr/bin/caffeinate", "-i",
        python, "-m", "quantlab.cli", "continuous",
        "--config", "config/settings.yaml",
    ],
    "WorkingDirectory": project,
    "RunAtLoad": True,
    "KeepAlive": True,
    "ProcessType": "Background",
    "StandardOutPath": os.path.join(logs, "paper.log"),
    "StandardErrorPath": os.path.join(logs, "paper-error.log"),
}
with open(plist_path, "wb") as handle:
    plistlib.dump(payload, handle)
PY

launchctl bootout "gui/$UID" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UID" "$PLIST"
launchctl enable "gui/$UID/$LABEL"
launchctl kickstart -k "gui/$UID/$LABEL"

echo "QuantLab continuous PAPER service installed and started."
echo "Project: $PROJECT_DIR"
echo "Heartbeat: $PROJECT_DIR/reports/continuous_heartbeat.json"
echo "Log: $LOG_DIR/paper.log"
echo "Error log: $LOG_DIR/paper-error.log"
echo "Stop: launchctl bootout gui/$UID $PLIST"
echo "The Mac will be kept awake while the paper service is running."
echo "This service only polls public data and simulates paper fills; no exchange orders are enabled."
