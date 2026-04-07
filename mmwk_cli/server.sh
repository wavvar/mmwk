#!/bin/bash
# server.sh — local MQTT + HTTP helper for radar OTA and collect workflows
set -euo pipefail

INVOKE_PWD="$(pwd)"
cd "$(dirname "$0")"

detect_platform() {
    case "$(uname -s)" in
        Darwin) echo "macos" ;;
        Linux) echo "linux" ;;
        MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
        *) echo "unknown" ;;
    esac
}

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

PYTHON="$(find_python)" || {
    echo "Error: Python 3.10+ not found."
    exit 1
}

timestamp_now() {
    date '+%Y-%m-%d %H:%M:%S'
}

log_info() {
    printf '[%s] [server] %s\n' "$(timestamp_now)" "$*"
}

log_warn() {
    printf '[%s] [server] %s\n' "$(timestamp_now)" "$*" >&2
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

usage() {
    cat <<'EOF_USAGE'
server.sh -- local MQTT + HTTP helper for flash/collect

USAGE:
  ./server.sh start  [options]
  ./server.sh run    [options]
  ./server.sh stop   [--state-dir DIR]
  ./server.sh status [--state-dir DIR]
  ./server.sh env    [--state-dir DIR]

OPTIONS:
  --state-dir DIR    State/log/pid directory (default: ./output/local_server)
  --serve-dir DIR    Directory exposed by HTTP server (default: current working directory)
  --upload-dir DIR   Directory for HTTP POST upload dumps (default: <state-dir>/uploads)
  --device-ota       Publish fixed-name bridge OTA artifact
  --device-ota-board NAME
                     Board name for bridge OTA artifact lookup
  --host-ip IP       Advertised host IP for device access
  --target-ip IP     Device/runtime IP used to auto-pick the best host IP
  --mqtt-port PORT   MQTT listen port (default: 1883)
  --http-port PORT   HTTP listen port (default: 8380)

ENV FILE:
  <state-dir>/server.env
    MMWK_SERVER_HOST_IP
    MMWK_SERVER_MQTT_URI
    MMWK_SERVER_HTTP_BASE_URL
    MMWK_SERVER_STATE_DIR
    MMWK_SERVER_SERVE_DIR
    MMWK_SERVER_DEVICE_OTA_BOARD
    MMWK_SERVER_DEVICE_OTA_DIR
    MMWK_SERVER_DEVICE_OTA_PATH
    MMWK_SERVER_DEVICE_OTA_URL
    MMWK_SERVER_DEVICE_OTA_VERSION
EOF_USAGE
}

SUBCOMMAND="${1:-}"
if [ -z "$SUBCOMMAND" ] || [ "$SUBCOMMAND" = "-h" ] || [ "$SUBCOMMAND" = "--help" ]; then
    usage
    exit 0
fi
shift || true

STATE_DIR=""
SERVE_DIR=""
UPLOAD_DIR=""
HOST_IP=""
TARGET_IP=""
MQTT_PORT="1883"
HTTP_PORT="8380"
DEVICE_OTA=false
DEVICE_OTA_BOARD=""
DEVICE_OTA_DIR=""
DEVICE_OTA_PATH=""
DEVICE_OTA_URL=""
DEVICE_OTA_VERSION=""

while [ $# -gt 0 ]; do
    case "$1" in
        --state-dir)
            STATE_DIR="${2:?missing value for --state-dir}"
            shift 2
            ;;
        --serve-dir)
            SERVE_DIR="${2:?missing value for --serve-dir}"
            shift 2
            ;;
        --upload-dir)
            UPLOAD_DIR="${2:?missing value for --upload-dir}"
            shift 2
            ;;
        --device-ota)
            DEVICE_OTA=true
            shift
            ;;
        --device-ota-board)
            DEVICE_OTA_BOARD="${2:?missing value for --device-ota-board}"
            shift 2
            ;;
        --host-ip)
            HOST_IP="${2:?missing value for --host-ip}"
            shift 2
            ;;
        --target-ip)
            TARGET_IP="${2:?missing value for --target-ip}"
            shift 2
            ;;
        --mqtt-port)
            MQTT_PORT="${2:?missing value for --mqtt-port}"
            shift 2
            ;;
        --http-port)
            HTTP_PORT="${2:?missing value for --http-port}"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

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

git_common_root() {
    local common_dir=""

    common_dir="$(git rev-parse --git-common-dir 2>/dev/null || true)"
    if [ -z "$common_dir" ]; then
        return 1
    fi

    if [[ "$common_dir" != /* ]]; then
        common_dir="$(cd "$PWD" && cd "$common_dir" && pwd)"
    else
        common_dir="$(cd "$common_dir" && pwd)"
    fi

    (cd "$common_dir/.." && pwd)
}

resolve_public_package_root() {
    local common_root=""
    local candidate=""

    candidate="$(abspath_path "../mmwk")"
    if [ -d "$candidate" ]; then
        printf '%s\n' "$(cd "$candidate" && pwd -P)"
        return 0
    fi

    common_root="$(git_common_root || true)"
    if [ -n "$common_root" ]; then
        candidate="${common_root}/../mmwk"
        if [ -d "$candidate" ]; then
            printf '%s\n' "$(cd "$candidate" && pwd -P)"
            return 0
        fi
    fi

    printf '%s\n' "$candidate"
}

resolve_device_ota_dir() {
    local package_root=""
    package_root="$(resolve_public_package_root)"
    printf '%s\n' "${package_root}/firmwares/esp/${DEVICE_OTA_BOARD}"
}

configure_device_ota_mode() {
    if [ "$DEVICE_OTA" != "true" ]; then
        return 0
    fi

    if [ -z "$DEVICE_OTA_BOARD" ]; then
        echo "Error: --device-ota requires --device-ota-board" >&2
        exit 1
    fi

    DEVICE_OTA_DIR="$(resolve_device_ota_dir)"
    DEVICE_OTA_PATH="${DEVICE_OTA_DIR}/mmwk_sensor_bridge_full.bin"
    if [ -f "${DEVICE_OTA_DIR}/mmwk_sensor_bridge.version" ]; then
        DEVICE_OTA_VERSION="$(tr -d '\r\n' < "${DEVICE_OTA_DIR}/mmwk_sensor_bridge.version")"
    else
        DEVICE_OTA_VERSION=""
    fi
}

if [ -z "$STATE_DIR" ]; then
    STATE_DIR="${INVOKE_PWD}/output/local_server"
fi

configure_device_ota_mode

if [ -z "$SERVE_DIR" ]; then
    if [ "$DEVICE_OTA" = "true" ]; then
        SERVE_DIR="$DEVICE_OTA_DIR"
    else
        SERVE_DIR="$INVOKE_PWD"
    fi
fi
if [ -z "$UPLOAD_DIR" ]; then
    UPLOAD_DIR="$STATE_DIR/uploads"
fi

STATE_DIR="$(abspath_path "$STATE_DIR" "$INVOKE_PWD")"
SERVE_DIR="$(abspath_path "$SERVE_DIR" "$INVOKE_PWD")"
UPLOAD_DIR="$(abspath_path "$UPLOAD_DIR" "$INVOKE_PWD")"

MQTT_PID_FILE="$STATE_DIR/mosquitto.pid"
HTTP_PID_FILE="$STATE_DIR/http.pid"
SERVER_PID_FILE="$STATE_DIR/server.pid"
ENV_FILE="$STATE_DIR/server.env"
MQTT_LOG="$STATE_DIR/mosquitto.log"
HTTP_LOG="$STATE_DIR/http.log"
SERVER_LOG="$STATE_DIR/server.log"
MOSQ_CONF="$STATE_DIR/mosquitto.conf"
STOP_FILE="$STATE_DIR/stop.request"
PREPARED_HOST_IP=""

is_pid_running() {
    local pid="$1"
    [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1
}

read_pid_file() {
    local path="$1"
    if [ -f "$path" ]; then
        tr -d '[:space:]' < "$path"
    fi
}

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Error: required command not found: $1" >&2
        exit 1
    fi
}

wait_for_tcp() {
    local host="$1"
    local port="$2"
    local timeout_sec="${3:-15}"
    local start_ts
    start_ts="$(date +%s)"
    while true; do
        if "$PYTHON" - "$host" "$port" <<'PY' >/dev/null 2>&1
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
s = socket.socket()
s.settimeout(1.0)
try:
    s.connect((host, port))
except Exception:
    sys.exit(1)
finally:
    s.close()
PY
        then
            return 0
        fi
        if [ $(( $(date +%s) - start_ts )) -ge "$timeout_sec" ]; then
            return 1
        fi
        sleep 1
    done
}

tcp_connects() {
    local host="$1"
    local port="$2"
    "$PYTHON" - "$host" "$port" <<'PY' >/dev/null 2>&1
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
s = socket.socket()
s.settimeout(1.0)
try:
    s.connect((host, port))
except Exception:
    sys.exit(1)
finally:
    s.close()
PY
}

port_is_available() {
    "$PYTHON" - "$1" <<'PY' >/dev/null 2>&1
import socket
import sys

port = int(sys.argv[1])
s = socket.socket()
try:
    s.bind(("0.0.0.0", port))
except OSError:
    sys.exit(1)
finally:
    s.close()
PY
}

pick_available_port() {
    local requested="$1"
    local candidate
    for candidate in "$requested" $(seq $((requested + 1)) $((requested + 9))); do
        if port_is_available "$candidate"; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

detect_host_ip() {
    if [ -n "$HOST_IP" ]; then
        printf '%s\n' "$HOST_IP"
        return 0
    fi
    setup_venv >/dev/null
    PYTHONPATH=scripts "$PYTHON" - "$TARGET_IP" <<'PY'
import sys
from mmwk_cli.http_server import get_local_ip

target_ip = sys.argv[1] if len(sys.argv) > 1 else ""
print(get_local_ip(target_ip=target_ip or None))
PY
}

read_env_value() {
    local key="$1"
    if [ ! -f "$ENV_FILE" ]; then
        return 0
    fi
    "$PYTHON" - "$ENV_FILE" "$key" <<'PY'
import sys

env_path = sys.argv[1]
key = sys.argv[2]

with open(env_path, "r", encoding="utf-8") as fp:
    for line in fp:
        line = line.rstrip("\n")
        if not line or "=" not in line:
            continue
        k, value = line.split("=", 1)
        if k == key:
            print(value)
            break
PY
}

parse_url_port() {
    local raw_url="$1"
    local default_port="$2"
    "$PYTHON" - "$raw_url" "$default_port" <<'PY'
import sys
from urllib.parse import urlparse

raw = (sys.argv[1] or "").strip()
default = int(sys.argv[2])

if not raw:
    print(default)
    raise SystemExit(0)

if "://" not in raw:
    raw = f"tcp://{raw}"

parsed = urlparse(raw)
print(parsed.port or default)
PY
}

load_state_runtime() {
    local mqtt_uri
    local http_base
    local device_ota_board
    local device_ota_dir
    local device_ota_path
    local device_ota_url
    local device_ota_version

    mqtt_uri="$(read_env_value "MMWK_SERVER_MQTT_URI")"
    if [ -n "$mqtt_uri" ]; then
        MQTT_PORT="$(parse_url_port "$mqtt_uri" "$MQTT_PORT")"
    fi

    http_base="$(read_env_value "MMWK_SERVER_HTTP_BASE_URL")"
    if [ -n "$http_base" ]; then
        HTTP_PORT="$(parse_url_port "$http_base" "$HTTP_PORT")"
    fi

    device_ota_board="$(read_env_value "MMWK_SERVER_DEVICE_OTA_BOARD")"
    device_ota_dir="$(read_env_value "MMWK_SERVER_DEVICE_OTA_DIR")"
    device_ota_path="$(read_env_value "MMWK_SERVER_DEVICE_OTA_PATH")"
    device_ota_url="$(read_env_value "MMWK_SERVER_DEVICE_OTA_URL")"
    device_ota_version="$(read_env_value "MMWK_SERVER_DEVICE_OTA_VERSION")"

    DEVICE_OTA_BOARD="$device_ota_board"
    DEVICE_OTA_DIR="$device_ota_dir"
    DEVICE_OTA_PATH="$device_ota_path"
    DEVICE_OTA_URL="$device_ota_url"
    DEVICE_OTA_VERSION="$device_ota_version"
    if [ -n "$DEVICE_OTA_BOARD" ] || [ -n "$DEVICE_OTA_PATH" ] || [ -n "$DEVICE_OTA_URL" ]; then
        DEVICE_OTA=true
    else
        DEVICE_OTA=false
    fi
}

write_env_file() {
    local resolved_host_ip="$1"
    local device_ota_url=""
    if [ "$DEVICE_OTA" = "true" ]; then
        device_ota_url="http://$resolved_host_ip:$HTTP_PORT/mmwk_sensor_bridge_full.bin"
    fi
    cat > "$ENV_FILE" <<EOF_ENV
MMWK_SERVER_HOST_IP=$resolved_host_ip
MMWK_SERVER_MQTT_URI=mqtt://$resolved_host_ip:$MQTT_PORT
MMWK_SERVER_HTTP_BASE_URL=http://$resolved_host_ip:$HTTP_PORT/
MMWK_SERVER_STATE_DIR=$STATE_DIR
MMWK_SERVER_SERVE_DIR=$SERVE_DIR
MMWK_SERVER_UPLOAD_DIR=$UPLOAD_DIR
MMWK_SERVER_DEVICE_OTA_BOARD=$DEVICE_OTA_BOARD
MMWK_SERVER_DEVICE_OTA_DIR=$DEVICE_OTA_DIR
MMWK_SERVER_DEVICE_OTA_PATH=$DEVICE_OTA_PATH
MMWK_SERVER_DEVICE_OTA_URL=$device_ota_url
MMWK_SERVER_DEVICE_OTA_VERSION=$DEVICE_OTA_VERSION
EOF_ENV
    log_info "Env File   : $ENV_FILE"
}

ensure_not_running() {
    local mqtt_pid
    local http_pid
    local server_pid

    mqtt_pid="$(read_pid_file "$MQTT_PID_FILE")"
    http_pid="$(read_pid_file "$HTTP_PID_FILE")"
    server_pid="$(read_pid_file "$SERVER_PID_FILE")"
    if is_pid_running "$mqtt_pid" || is_pid_running "$http_pid" || is_pid_running "$server_pid"; then
        echo "Error: server already running in $STATE_DIR" >&2
        exit 1
    fi
}

prepare_server() {
    local resolved_host_ip
    local requested_mqtt_port="$MQTT_PORT"
    local requested_http_port="$HTTP_PORT"

    if [ "$DEVICE_OTA" = "true" ] && [ ! -f "$DEVICE_OTA_PATH" ]; then
        echo "Error: device OTA artifact not found: $DEVICE_OTA_PATH" >&2
        exit 1
    fi

    require_command mosquitto
    mkdir -p "$STATE_DIR" "$UPLOAD_DIR"
    rm -f "$STOP_FILE"
    ensure_not_running

    log_info "Preparing local server"
    log_info "State Dir   : $STATE_DIR"
    log_info "Serve Dir   : $SERVE_DIR"
    log_info "Upload Dir  : $UPLOAD_DIR"
    log_info "Requested MQTT Port: $requested_mqtt_port"
    log_info "Requested HTTP Port: $requested_http_port"

    resolved_host_ip="$(detect_host_ip | tr -d '[:space:]')"
    if [ -z "$resolved_host_ip" ] || [ "$resolved_host_ip" = "0.0.0.0" ]; then
        echo "Error: could not determine a usable host IP. Pass --host-ip explicitly." >&2
        exit 1
    fi

    MQTT_PORT="$(pick_available_port "$MQTT_PORT")" || {
        echo "Error: could not find a free MQTT port near $MQTT_PORT" >&2
        exit 1
    }
    HTTP_PORT="$(pick_available_port "$HTTP_PORT")" || {
        echo "Error: could not find a free HTTP port near $HTTP_PORT" >&2
        exit 1
    }

    cat > "$MOSQ_CONF" <<EOF_MOSQ
allow_anonymous true
persistence false
listener $MQTT_PORT 0.0.0.0
EOF_MOSQ

    : > "$MQTT_LOG"
    : > "$HTTP_LOG"
    PREPARED_HOST_IP="$resolved_host_ip"
    log_info "Resolved Host IP : $resolved_host_ip"
    log_info "Resolved MQTT Port: $MQTT_PORT"
    log_info "Resolved HTTP Port: $HTTP_PORT"
}

cleanup_server() {
    local mqtt_pid
    local http_pid
    local server_pid

    mqtt_pid="$(read_pid_file "$MQTT_PID_FILE")"
    http_pid="$(read_pid_file "$HTTP_PID_FILE")"
    server_pid="$(read_pid_file "$SERVER_PID_FILE")"

    if is_pid_running "$http_pid"; then
        kill "$http_pid" >/dev/null 2>&1 || true
    fi
    if is_pid_running "$mqtt_pid"; then
        kill "$mqtt_pid" >/dev/null 2>&1 || true
    fi
    if [ -n "$server_pid" ] && [ "$server_pid" != "$$" ] && is_pid_running "$server_pid"; then
        kill "$server_pid" >/dev/null 2>&1 || true
    fi

    rm -f "$HTTP_PID_FILE" "$MQTT_PID_FILE" "$SERVER_PID_FILE" "$STOP_FILE"
}

handle_server_signal() {
    : > "$STOP_FILE"
    cleanup_server
    exit 0
}

start_children() {
    local mqtt_pid
    local http_pid

    log_info "MQTT Log   : $MQTT_LOG"
    log_info "HTTP Log   : $HTTP_LOG"
    nohup mosquitto -c "$MOSQ_CONF" -v >>"$MQTT_LOG" 2>&1 </dev/null &
    mqtt_pid="$!"
    echo "$mqtt_pid" > "$MQTT_PID_FILE"
    log_info "Starting mosquitto (pid=$mqtt_pid)"

    if ! wait_for_tcp 127.0.0.1 "$MQTT_PORT" 15; then
        echo "Error: mosquitto failed to start. See $MQTT_LOG" >&2
        return 1
    fi
    log_info "mosquitto is listening on 127.0.0.1:$MQTT_PORT"

    setup_venv >/dev/null
    nohup env PYTHONPATH=scripts "$PYTHON" -m mmwk_cli.local_http_server \
        --serve-dir "$SERVE_DIR" \
        --bind 0.0.0.0 \
        --port "$HTTP_PORT" \
        --upload-dir "$UPLOAD_DIR" >>"$HTTP_LOG" 2>&1 </dev/null &
    http_pid="$!"
    echo "$http_pid" > "$HTTP_PID_FILE"
    log_info "Starting HTTP server (pid=$http_pid)"

    if ! wait_for_tcp 127.0.0.1 "$HTTP_PORT" 15; then
        echo "Error: HTTP server failed to start. See $HTTP_LOG" >&2
        return 1
    fi
    log_info "HTTP server is listening on 127.0.0.1:$HTTP_PORT"

    return 0
}

print_server_summary() {
    local resolved_host_ip="$1"
    local device_ota_url=""
    if [ "$DEVICE_OTA" = "true" ]; then
        device_ota_url="http://$resolved_host_ip:$HTTP_PORT/mmwk_sensor_bridge_full.bin"
    fi
    write_env_file "$resolved_host_ip"

    echo "Local server started"
    echo "  Host IP   : $resolved_host_ip"
    echo "  MQTT URI  : mqtt://$resolved_host_ip:$MQTT_PORT"
    echo "  HTTP Base : http://$resolved_host_ip:$HTTP_PORT/"
    echo "  Serve Dir : $SERVE_DIR"
    echo "  Upload Dir: $UPLOAD_DIR"
    echo "  State Dir : $STATE_DIR"
    echo "  MQTT Log  : $MQTT_LOG"
    echo "  HTTP Log  : $HTTP_LOG"
    echo "  Env File  : $ENV_FILE"
    if [ "$DEVICE_OTA" = "true" ]; then
        echo "  Device OTA Board  : $DEVICE_OTA_BOARD"
        echo "  Device OTA Dir    : $DEVICE_OTA_DIR"
        echo "  Device OTA Path   : $DEVICE_OTA_PATH"
        echo "  Device OTA URL    : $device_ota_url"
        if [ -n "$DEVICE_OTA_VERSION" ]; then
            echo "  Device OTA Version: $DEVICE_OTA_VERSION"
        fi
    fi
}

run_server() {
    local resolved_host_ip

    prepare_server
    resolved_host_ip="$PREPARED_HOST_IP"
    echo "$$" > "$SERVER_PID_FILE"
    log_info "Supervisor PID: $$"

    trap cleanup_server EXIT
    trap handle_server_signal INT TERM

    if ! start_children; then
        exit 1
    fi

    print_server_summary "$resolved_host_ip"

    while true; do
        if [ -f "$STOP_FILE" ]; then
            log_info "Stop request detected"
            break
        fi
        if ! is_pid_running "$(read_pid_file "$MQTT_PID_FILE")"; then
            echo "Error: mosquitto exited unexpectedly. See $MQTT_LOG" >&2
            return 1
        fi
        if ! is_pid_running "$(read_pid_file "$HTTP_PID_FILE")"; then
            echo "Error: HTTP server exited unexpectedly. See $HTTP_LOG" >&2
            return 1
        fi
        if ! tcp_connects 127.0.0.1 "$MQTT_PORT"; then
            echo "Error: mosquitto is no longer listening on port $MQTT_PORT" >&2
            return 1
        fi
        if ! tcp_connects 127.0.0.1 "$HTTP_PORT"; then
            echo "Error: HTTP server is no longer listening on port $HTTP_PORT" >&2
            return 1
        fi
        sleep 1
    done
}

start_server() {
    local server_pid
    local attempts
    local run_cmd=("$0" run
        --state-dir "$STATE_DIR"
        --serve-dir "$SERVE_DIR"
        --upload-dir "$UPLOAD_DIR"
        --mqtt-port "$MQTT_PORT"
        --http-port "$HTTP_PORT")

    mkdir -p "$STATE_DIR"
    rm -f "$STOP_FILE"
    ensure_not_running
    : > "$SERVER_LOG"
    log_info "Server Log : $SERVER_LOG"

    if [ -n "$HOST_IP" ]; then
        run_cmd+=(--host-ip "$HOST_IP")
    fi
    if [ -n "$TARGET_IP" ]; then
        run_cmd+=(--target-ip "$TARGET_IP")
    fi
    if [ "$DEVICE_OTA" = "true" ]; then
        run_cmd+=(--device-ota --device-ota-board "$DEVICE_OTA_BOARD")
    fi

    nohup "${run_cmd[@]}" >>"$SERVER_LOG" 2>&1 </dev/null &
    server_pid="$!"
    log_info "Launching detached supervisor (pid=$server_pid)"

    for attempts in $(seq 1 20); do
        if [ -f "$ENV_FILE" ]; then
            load_state_runtime
            if tcp_connects 127.0.0.1 "$MQTT_PORT" && tcp_connects 127.0.0.1 "$HTTP_PORT"; then
                cat "$SERVER_LOG"
                return 0
            fi
        fi
        if ! is_pid_running "$server_pid"; then
            echo "Error: detached server supervisor exited. See $SERVER_LOG" >&2
            [ -f "$SERVER_LOG" ] && sed -n '1,120p' "$SERVER_LOG" >&2
            exit 1
        fi
        sleep 1
    done

    echo "Error: timed out waiting for detached server to become ready. See $SERVER_LOG" >&2
    exit 1
}

stop_server() {
    local server_pid
    local mqtt_pid
    local http_pid
    local attempt

    : > "$STOP_FILE"
    server_pid="$(read_pid_file "$SERVER_PID_FILE")"
    mqtt_pid="$(read_pid_file "$MQTT_PID_FILE")"
    http_pid="$(read_pid_file "$HTTP_PID_FILE")"

    if [ -n "$server_pid" ] && [ "$server_pid" != "$$" ] && is_pid_running "$server_pid"; then
        kill "$server_pid" >/dev/null 2>&1 || true
        for attempt in $(seq 1 20); do
            if ! is_pid_running "$server_pid" && ! is_pid_running "$mqtt_pid" && ! is_pid_running "$http_pid"; then
                break
            fi
            sleep 0.2
        done
    else
        cleanup_server
    fi

    rm -f "$STOP_FILE" "$SERVER_PID_FILE" "$MQTT_PID_FILE" "$HTTP_PID_FILE"
    log_info "State Dir : $STATE_DIR"
    echo "Local server stopped"
}

status_server() {
    local mqtt_pid
    local http_pid
    local server_pid
    local mqtt_running="no"
    local http_running="no"
    local server_running="no"
    local mqtt_listening="no"
    local http_listening="no"

    load_state_runtime

    mqtt_pid="$(read_pid_file "$MQTT_PID_FILE")"
    http_pid="$(read_pid_file "$HTTP_PID_FILE")"
    server_pid="$(read_pid_file "$SERVER_PID_FILE")"
    if is_pid_running "$mqtt_pid"; then
        mqtt_running="yes"
    fi
    if is_pid_running "$http_pid"; then
        http_running="yes"
    fi
    if is_pid_running "$server_pid"; then
        server_running="yes"
    fi
    if tcp_connects 127.0.0.1 "$MQTT_PORT"; then
        mqtt_listening="yes"
    fi
    if tcp_connects 127.0.0.1 "$HTTP_PORT"; then
        http_listening="yes"
    fi

    echo "State Dir : $STATE_DIR"
    echo "Server Log: $SERVER_LOG"
    echo "MQTT Log  : $MQTT_LOG"
    echo "HTTP Log  : $HTTP_LOG"
    echo "Server PID: ${server_pid:-}"
    echo "MQTT PID  : ${mqtt_pid:-}"
    echo "HTTP PID  : ${http_pid:-}"
    echo "Server Up : $server_running"
    echo "MQTT Port : $MQTT_PORT"
    echo "HTTP Port : $HTTP_PORT"
    echo "Device OTA Mode : $DEVICE_OTA"
    echo "Device OTA Board: $DEVICE_OTA_BOARD"
    echo "Device OTA Dir  : $DEVICE_OTA_DIR"
    echo "Device OTA Path : $DEVICE_OTA_PATH"
    echo "Device OTA URL  : $DEVICE_OTA_URL"
    echo "Device OTA Ver  : $DEVICE_OTA_VERSION"
    echo "MQTT Listen: $mqtt_listening"
    echo "HTTP Listen: $http_listening"
    echo "MQTT Up   : $([ "$mqtt_running" = "yes" ] && [ "$mqtt_listening" = "yes" ] && echo yes || echo no)"
    echo "HTTP Up   : $([ "$http_running" = "yes" ] && [ "$http_listening" = "yes" ] && echo yes || echo no)"
    if [ -f "$ENV_FILE" ]; then
        echo "Env File  : $ENV_FILE"
        cat "$ENV_FILE"
    fi
}

env_server() {
    if [ ! -f "$ENV_FILE" ]; then
        echo "Error: env file not found: $ENV_FILE" >&2
        exit 1
    fi
    cat "$ENV_FILE"
}

case "$SUBCOMMAND" in
    start)
        start_server
        ;;
    run)
        run_server
        ;;
    stop)
        stop_server
        ;;
    status)
        status_server
        ;;
    env)
        env_server
        ;;
    *)
        echo "Unknown subcommand: $SUBCOMMAND" >&2
        usage >&2
        exit 1
        ;;
esac
