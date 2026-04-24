#!/bin/bash
# mmwk_raw.sh — pure-MQTT raw capture helper wrapper
set -euo pipefail

INVOKE_PWD="$(pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

find_python() {
    local cmd
    local ver
    local major
    local minor
    for cmd in python3 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            ver="$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)" || continue
            major="${ver%%.*}"
            minor="${ver#*.}"
            if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

setup_venv() {
    if [ ! -d venv ]; then
        echo "Creating virtual environment..."
        "$PYTHON" -m venv venv
    fi

    if [ -f venv/bin/activate ]; then
        . venv/bin/activate
    elif [ -f venv/Scripts/activate ]; then
        . venv/Scripts/activate
    fi

    if [ ! -f venv/.deps_installed ] || [ requirements.txt -nt venv/.deps_installed ]; then
        echo "Installing dependencies..."
        pip install -q -r requirements.txt
        touch venv/.deps_installed
    fi
}

abspath_path() {
    "$PYTHON" - "$1" "${2:-$PWD}" <<'PY'
import os
import sys

path = sys.argv[1]
base = sys.argv[2]
if os.path.isabs(path):
    print(os.path.abspath(path))
else:
    print(os.path.abspath(os.path.join(base, path)))
PY
}

extract_env_value() {
    local env_file="$1"
    local key="$2"
    "$PYTHON" - "$env_file" "$key" <<'PY'
import sys

env_path = sys.argv[1]
key = sys.argv[2]

with open(env_path, "r", encoding="utf-8") as fp:
    for line in fp:
        line = line.rstrip("\n")
        if "=" not in line:
            continue
        current_key, value = line.split("=", 1)
        if current_key == key:
            print(value)
            break
PY
}

show_help() {
    cat <<'EOF_HELP'
mmwk_raw.sh -- Pure-MQTT raw capture helper

USAGE:
  ./tools/mmwk_raw.sh [wrapper-options] --trigger {none|radar-restart|device-reboot} [tool-options]

WRAPPER OPTIONS:
  --server-state-dir DIR  Auto-load the broker from DIR/server.env when --broker and
                          MMWK_SERVER_MQTT_URI are both absent.
                          Default: ./output/local_server
  -h, --help              Show wrapper help, then forwarded tool help.

NOTES:
  - Runtime control and raw capture remain pure MQTT.
  - mmwk_raw.sh auto-loads the broker from server.sh state when available.
  - The working directory should be the mmwk_cli directory.

FORWARDED TOOL HELP:
EOF_HELP
}

PYTHON="$(find_python)" || {
    echo "Error: Python 3.10+ not found. Please install Python 3.10 or higher." >&2
    exit 1
}

SERVER_STATE_DIR=""
SHOW_HELP=false
FORWARD_ARGS=()

while [ $# -gt 0 ]; do
    case "$1" in
        --server-state-dir)
            SERVER_STATE_DIR="${2:?missing value for --server-state-dir}"
            shift 2
            ;;
        -h|--help)
            SHOW_HELP=true
            FORWARD_ARGS+=("$1")
            shift
            ;;
        *)
            FORWARD_ARGS+=("$1")
            shift
            ;;
    esac
done

cd "$PROJECT_DIR"
setup_venv
export PYTHONPATH="$PROJECT_DIR/scripts"

if [ -z "$SERVER_STATE_DIR" ]; then
    SERVER_STATE_DIR="$INVOKE_PWD/output/local_server"
fi
SERVER_STATE_DIR="$(abspath_path "$SERVER_STATE_DIR" "$INVOKE_PWD")"
SERVER_ENV_FILE="$SERVER_STATE_DIR/server.env"

has_forward_broker=false
for arg in "${FORWARD_ARGS[@]}"; do
    case "$arg" in
        --broker|--broker=*)
            has_forward_broker=true
            break
            ;;
    esac
done

if [ "$has_forward_broker" = false ] && [ -z "${MMWK_SERVER_MQTT_URI:-}" ] && [ -f "$SERVER_ENV_FILE" ]; then
    resolved_mqtt_uri="$(extract_env_value "$SERVER_ENV_FILE" "MMWK_SERVER_MQTT_URI")"
    if [ -n "$resolved_mqtt_uri" ]; then
        export MMWK_SERVER_MQTT_URI="$resolved_mqtt_uri"
    fi
fi

if [ "$SHOW_HELP" = true ]; then
    show_help
    "$PYTHON" -m mmwk_cli.tools.collect_raw --help
    exit 0
fi

cd "$INVOKE_PWD"
exec "$PYTHON" -m mmwk_cli.tools.collect_raw "${FORWARD_ARGS[@]}"
