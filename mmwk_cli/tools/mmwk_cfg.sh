#!/bin/bash
# mmwk_cfg.sh — configure device Wi-Fi/MQTT settings over UART or MQTT
set -euo pipefail

INVOKE_PWD="$(pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MMWK_CLI="$PROJECT_DIR/mmwk_cli.sh"
SERVER_SH="$PROJECT_DIR/server.sh"

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

timestamp_now() {
    date '+%Y-%m-%d %H:%M:%S'
}

log_info() {
    printf '[%s] [mmwk_cfg] %s\n' "$(timestamp_now)" "$*"
}

log_warn() {
    printf '[%s] [mmwk_cfg] %s\n' "$(timestamp_now)" "$*" >&2
}

die() {
    log_warn "Error: $*"
    exit 1
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

extract_env_value_from_text() {
    local text="$1"
    local key="$2"
    "$PYTHON" - "$text" "$key" <<'PY'
import sys

raw = sys.argv[1]
key = sys.argv[2]
for line in raw.splitlines():
    if "=" not in line:
        continue
    current_key, value = line.split("=", 1)
    if current_key == key:
        print(value)
        break
PY
}

json_value_from_text() {
    local text="$1"
    shift
    "$PYTHON" - "$text" "$@" <<'PY'
import json
import sys

raw = sys.argv[1]
paths = sys.argv[2:]
try:
    data = json.loads(raw)
except Exception:
    raise SystemExit(0)

def lookup(obj, dotted):
    current = obj
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return ""
        current = current[part]
    if isinstance(current, str):
        return current.strip()
    return ""

for path in paths:
    value = lookup(data, path)
    if value:
        print(value)
        break
PY
}

usage() {
    cat <<'EOF_USAGE'
mmwk_cfg.sh -- Configure device Wi-Fi and MQTT settings

USAGE:
  ./tools/mmwk_cfg.sh [transport-options] [config-options]

TRANSPORT OPTIONS:
  --transport uart|mqtt  Control path used to push settings (default: uart)
  -p, --port PORT        Serial port for UART transport
  --baudrate RATE        UART baudrate (default: 115200)
  --reset                Reset device before connecting on UART
  --broker HOST          Current MQTT broker used for MQTT transport
  --mqtt-port PORT       Current MQTT broker port for MQTT transport (default: 1883)
  --device-id ID         Current MQTT device id for MQTT transport
  --cmd-topic TOPIC      Current MQTT command topic override
  --resp-topic TOPIC     Current MQTT response topic override
  --timeout SEC          Response timeout in seconds (default: 10)
  -v, --verbose          Enable verbose mmwk_cli logging

CONFIG OPTIONS:
  --ssid SSID            Wi-Fi SSID to store on device
  --password PASS        Wi-Fi password to store on device
  --mqtt-uri URI         MQTT broker URI to store on device
  --mqtt-user USER       MQTT username to store on device
  --mqtt-pass PASS       MQTT password to store on device
  --server-local         Start or reuse server.sh and use its MQTT URI
  --server-state-dir DIR server.sh state dir (default: ./output/local_server)
  --server-serve-dir DIR server.sh serve dir override
  --server-upload-dir DIR
                        server.sh upload dir override
  --server-host-ip IP    server.sh advertised host IP
  --server-target-ip IP  server.sh target IP for host IP auto-pick
  --server-mqtt-port PORT
                        Requested local MQTT listen port (default: 1883)
  --server-http-port PORT
                        Requested local HTTP listen port (default: 8380)
  --reboot               Reboot the device after pushing settings
  -h, --help             Show this help

NOTES:
  - Use --server-local when you want mmwk_cfg.sh to manage server.sh for you.
  - Wi-Fi and MQTT broker/auth settings can be pushed over UART or over an existing MQTT control path.
  - MQTT topic identity is fixed to the device Wi-Fi STA MAC and is no longer configurable.
  - The working directory should be the mmwk_cli directory.
EOF_USAGE
}

PYTHON="$(find_python)" || {
    echo "Error: Python 3.10+ not found. Please install Python 3.10 or higher." >&2
    exit 1
}

TRANSPORT="uart"
PORT=""
BAUDRATE="115200"
RESET=false
BROKER=""
MQTT_PORT="1883"
DEVICE_ID=""
CMD_TOPIC=""
RESP_TOPIC=""
TIMEOUT="10"
VERBOSE=false

SSID=""
PASSWORD=""
MQTT_URI=""
MQTT_USER=""
MQTT_PASS=""

SERVER_LOCAL=false
SERVER_STATE_DIR=""
SERVER_SERVE_DIR=""
SERVER_UPLOAD_DIR=""
SERVER_HOST_IP=""
SERVER_TARGET_IP=""
SERVER_MQTT_PORT="1883"
SERVER_HTTP_PORT="8380"

REBOOT=false

while [ $# -gt 0 ]; do
    case "$1" in
        --transport)
            TRANSPORT="${2:?missing value for --transport}"
            shift 2
            ;;
        -p|--port)
            PORT="${2:?missing value for --port}"
            shift 2
            ;;
        --baudrate)
            BAUDRATE="${2:?missing value for --baudrate}"
            shift 2
            ;;
        --reset)
            RESET=true
            shift
            ;;
        --broker)
            BROKER="${2:?missing value for --broker}"
            shift 2
            ;;
        --mqtt-port)
            MQTT_PORT="${2:?missing value for --mqtt-port}"
            shift 2
            ;;
        --device-id)
            DEVICE_ID="${2:?missing value for --device-id}"
            shift 2
            ;;
        --cmd-topic)
            CMD_TOPIC="${2:?missing value for --cmd-topic}"
            shift 2
            ;;
        --resp-topic)
            RESP_TOPIC="${2:?missing value for --resp-topic}"
            shift 2
            ;;
        --timeout)
            TIMEOUT="${2:?missing value for --timeout}"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        --ssid)
            SSID="${2:?missing value for --ssid}"
            shift 2
            ;;
        --password)
            PASSWORD="${2:?missing value for --password}"
            shift 2
            ;;
        --mqtt-uri)
            MQTT_URI="${2:?missing value for --mqtt-uri}"
            shift 2
            ;;
        --mqtt-user)
            MQTT_USER="${2:?missing value for --mqtt-user}"
            shift 2
            ;;
        --mqtt-pass)
            MQTT_PASS="${2:?missing value for --mqtt-pass}"
            shift 2
            ;;
        --server-local)
            SERVER_LOCAL=true
            shift
            ;;
        --server-state-dir)
            SERVER_STATE_DIR="${2:?missing value for --server-state-dir}"
            shift 2
            ;;
        --server-serve-dir)
            SERVER_SERVE_DIR="${2:?missing value for --server-serve-dir}"
            shift 2
            ;;
        --server-upload-dir)
            SERVER_UPLOAD_DIR="${2:?missing value for --server-upload-dir}"
            shift 2
            ;;
        --server-host-ip)
            SERVER_HOST_IP="${2:?missing value for --server-host-ip}"
            shift 2
            ;;
        --server-target-ip)
            SERVER_TARGET_IP="${2:?missing value for --server-target-ip}"
            shift 2
            ;;
        --server-mqtt-port)
            SERVER_MQTT_PORT="${2:?missing value for --server-mqtt-port}"
            shift 2
            ;;
        --server-http-port)
            SERVER_HTTP_PORT="${2:?missing value for --server-http-port}"
            shift 2
            ;;
        --reboot)
            REBOOT=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "Unknown argument: $1"
            ;;
    esac
done

[ "$TRANSPORT" = "uart" ] || [ "$TRANSPORT" = "mqtt" ] || die "--transport must be uart or mqtt"

if { [ -n "$SSID" ] && [ -z "$PASSWORD" ]; } || { [ -z "$SSID" ] && [ -n "$PASSWORD" ]; }; then
    die "--ssid and --password must be provided together"
fi

if [ "$TRANSPORT" = "uart" ] && [ -z "$PORT" ]; then
    die "--port is required when --transport uart"
fi

if [ "$SERVER_LOCAL" = true ] && [ -n "$MQTT_URI" ]; then
    die "--server-local already resolves the broker URI; do not combine it with --mqtt-uri"
fi

WIFI_REQUESTED=false
if [ -n "$SSID" ]; then
    WIFI_REQUESTED=true
fi

MQTT_REQUESTED=false
if [ -n "$MQTT_URI" ] || [ -n "$MQTT_USER" ] || [ -n "$MQTT_PASS" ] || [ "$SERVER_LOCAL" = true ]; then
    MQTT_REQUESTED=true
fi

if [ "$WIFI_REQUESTED" = false ] && [ "$MQTT_REQUESTED" = false ] && [ "$REBOOT" = false ]; then
    die "No configuration action requested. Pass Wi-Fi options, MQTT options, --server-local, or --reboot."
fi

TRANSPORT_ARGS=(--transport "$TRANSPORT" --timeout "$TIMEOUT")
if [ "$TRANSPORT" = "uart" ]; then
    TRANSPORT_ARGS+=(--port "$PORT" --baudrate "$BAUDRATE")
    if [ "$RESET" = true ]; then
        TRANSPORT_ARGS+=(--reset)
    fi
else
    if [ -n "$BROKER" ]; then
        TRANSPORT_ARGS+=(--broker "$BROKER")
    fi
    if [ -n "$MQTT_PORT" ]; then
        TRANSPORT_ARGS+=(--mqtt-port "$MQTT_PORT")
    fi
    if [ -n "$DEVICE_ID" ]; then
        TRANSPORT_ARGS+=(--device-id "$DEVICE_ID")
    fi
    if [ -n "$CMD_TOPIC" ]; then
        TRANSPORT_ARGS+=(--cmd-topic "$CMD_TOPIC")
    fi
    if [ -n "$RESP_TOPIC" ]; then
        TRANSPORT_ARGS+=(--resp-topic "$RESP_TOPIC")
    fi
fi
if [ "$VERBOSE" = true ]; then
    TRANSPORT_ARGS+=(--verbose)
fi

run_mmwk_cli() {
    bash "$MMWK_CLI" "$@" "${TRANSPORT_ARGS[@]}"
}

ensure_server_local() {
    local status_output=""
    local env_output=""
    local start_cmd=(bash "$SERVER_SH" start --state-dir "$SERVER_STATE_DIR" --mqtt-port "$SERVER_MQTT_PORT" --http-port "$SERVER_HTTP_PORT")

    status_output="$(bash "$SERVER_SH" status --state-dir "$SERVER_STATE_DIR" 2>/dev/null || true)"
    if printf '%s' "$status_output" | grep -Fq 'MQTT Up   : yes' && printf '%s' "$status_output" | grep -Fq 'HTTP Up   : yes'; then
        log_info "Reusing local server from $SERVER_STATE_DIR"
    else
        log_info "Starting local server via server.sh"
        if [ -n "$SERVER_SERVE_DIR" ]; then
            start_cmd+=(--serve-dir "$SERVER_SERVE_DIR")
        fi
        if [ -n "$SERVER_UPLOAD_DIR" ]; then
            start_cmd+=(--upload-dir "$SERVER_UPLOAD_DIR")
        fi
        if [ -n "$SERVER_HOST_IP" ]; then
            start_cmd+=(--host-ip "$SERVER_HOST_IP")
        fi
        if [ -n "$SERVER_TARGET_IP" ]; then
            start_cmd+=(--target-ip "$SERVER_TARGET_IP")
        fi
        "${start_cmd[@]}"
    fi

    env_output="$(bash "$SERVER_SH" env --state-dir "$SERVER_STATE_DIR")" || die "Failed to read server.sh env from $SERVER_STATE_DIR"
    MQTT_URI="$(extract_env_value_from_text "$env_output" "MMWK_SERVER_MQTT_URI")"
    SERVER_HTTP_BASE_URL="$(extract_env_value_from_text "$env_output" "MMWK_SERVER_HTTP_BASE_URL")"
    [ -n "$MQTT_URI" ] || die "server.sh env did not return MMWK_SERVER_MQTT_URI"
    log_info "Resolved local MQTT URI: $MQTT_URI"
    if [ -n "${SERVER_HTTP_BASE_URL:-}" ]; then
        log_info "Resolved local HTTP base: $SERVER_HTTP_BASE_URL"
    fi
}

if [ -z "$SERVER_STATE_DIR" ]; then
    SERVER_STATE_DIR="$INVOKE_PWD/output/local_server"
fi
SERVER_STATE_DIR="$(abspath_path "$SERVER_STATE_DIR" "$INVOKE_PWD")"

if [ "$SERVER_LOCAL" = true ]; then
    ensure_server_local
fi

CONFIG_CHANGED=false

if [ "$WIFI_REQUESTED" = true ]; then
    log_info "Applying Wi-Fi settings over $TRANSPORT"
    run_mmwk_cli network config --ssid "$SSID" --password "$PASSWORD"
    CONFIG_CHANGED=true
fi

if [ "$MQTT_REQUESTED" = true ]; then
    MQTT_CMD=(network mqtt)
    if [ -n "$MQTT_URI" ]; then
        MQTT_CMD+=(--mqtt-uri "$MQTT_URI")
    fi
    if [ -n "$MQTT_USER" ]; then
        MQTT_CMD+=(--mqtt-user "$MQTT_USER")
    fi
    if [ -n "$MQTT_PASS" ]; then
        MQTT_CMD+=(--mqtt-pass "$MQTT_PASS")
    fi

    if [ "${#MQTT_CMD[@]}" -le 2 ]; then
        die "MQTT configuration was requested but no MQTT fields were resolved"
    fi

    log_info "Applying MQTT settings over $TRANSPORT"
    run_mmwk_cli "${MQTT_CMD[@]}"
    CONFIG_CHANGED=true
fi

if [ "$REBOOT" = true ]; then
    log_info "Rebooting device over $TRANSPORT"
    run_mmwk_cli device reboot
elif [ "$CONFIG_CHANGED" = true ]; then
    log_info "Configuration updated. Reboot the device to apply Wi-Fi/MQTT changes."
fi

if [ "$SERVER_LOCAL" = true ]; then
    log_info "Local server state dir: $SERVER_STATE_DIR"
fi
if [ -n "$MQTT_URI" ]; then
    log_info "Configured MQTT URI: $MQTT_URI"
fi
