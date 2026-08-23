#!/bin/bash
# collect.sh — local/remote radar DATA collection wrapper
set -euo pipefail

INVOKE_PWD="$(pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
MMWK_CLI="$PROJECT_DIR/run.sh"
TOOL_NAME="collect"

# shellcheck disable=SC1091
. "$PROJECT_DIR/.tool_common.sh"

usage() {
    cat <<'EOF_USAGE'
collect.sh -- Collect radar DATA through the shared Python engine

USAGE:
  ./collect.sh --transport uart|usb --port PORT [collection-options]
  ./collect.sh --transport mqtt --did DID [collection-options]
  ./collect.sh --ctrl-transport uart|usb --data-transport mqtt [collection-options]
  ./collect.sh --did DID [registry-backed MQTT attach options]
  ./collect.sh --trigger none|radar-restart|device-reboot [advanced options]

The local UART/USB, host MQTT, split, and attach paths use the same Python
engine as `run.sh collect`. The registry form is a compatibility adapter that
resolves `device.yml` and invokes the same MQTT engine. The trigger form is an
explicit advanced pure-MQTT reconnect helper.
EOF_USAGE
}

local_engine_mode=false
for arg in "$@"; do
    case "$arg" in
        --transport|--transport=*|--port|--port=*|--raw-baud|--raw-baud=*|--ctrl-transport|--ctrl-transport=*|--data-transport|--data-transport=*|--broker|--broker=*|--mqtt-port|--mqtt-port=*|--mqtt-user|--mqtt-user=*|--mqtt-password|--mqtt-password=*|--mqtt-ca|--mqtt-ca=*|--cfg|--cfg=*|--data-output|--data-output=*|--resp-output|--resp-output=*|--wire-output|--wire-output=*|--summary-output|--summary-output=*|--events-output|--events-output=*|--allow-lossy|--overwrite)
            local_engine_mode=true
            break
            ;;
    esac
done

cmd_direct() {
    local server_state_dir=""
    local server_env_file=""
    local server_env=""
    local has_broker=false
    local forward_args=()
    local arg=""

    while [ $# -gt 0 ]; do
        arg="$1"
        case "$arg" in
            --server-state-dir)
                server_state_dir="${2:?missing value for --server-state-dir}"
                shift 2
                ;;
            --broker)
                has_broker=true
                forward_args+=("$1" "${2:?missing value for --broker}")
                shift 2
                ;;
            --broker=*)
                has_broker=true
                forward_args+=("$1")
                shift
                ;;
            -h|--help)
                setup_project_env
                usage
                "$PYTHON" -m mmwk.tools.collect_raw --help
                exit 0
                ;;
            *)
                forward_args+=("$1")
                shift
                ;;
        esac
    done

    setup_project_env
    server_state_dir="$(resolve_default_server_state_dir "$server_state_dir")"
    server_env_file="$server_state_dir/server.env"

    if [ "$has_broker" = false ] && [ -z "${MMWK_SERVER_MQTT_URI:-}" ] && [ -f "$server_env_file" ]; then
        server_env="$(<"$server_env_file")"
        MMWK_SERVER_MQTT_URI="$(extract_env_value_from_text "$server_env" "MMWK_SERVER_MQTT_URI")"
        export MMWK_SERVER_MQTT_URI
    fi

    cd "$INVOKE_PWD"
    exec "$PYTHON" -m mmwk.tools.collect_raw "${forward_args[@]}"
}

direct_mode=false
for arg in "$@"; do
    case "$arg" in
        --trigger|--trigger=*)
            direct_mode=true
            break
            ;;
    esac
done

if [ "$direct_mode" = true ]; then
    cmd_direct "$@"
fi

if [ "$local_engine_mode" = true ]; then
    setup_project_env
    cd "$INVOKE_PWD"
    exec "$MMWK_CLI" collect "$@"
fi

# Registry-backed compatibility mode. It remains useful after config.sh init,
# while explicit host/remote/split options above always go through `collect`.
did=""
duration=""
reboot=false
working_dir=""
mode="host"
attach=false

while [ $# -gt 0 ]; do
    case "$1" in
        --did)
            did="${2:?missing value for --did}"
            shift 2
            ;;
        --duration)
            duration="${2:?missing value for --duration}"
            shift 2
            ;;
        --reboot)
            reboot=true
            shift
            ;;
        --mode)
            mode="${2:?missing value for --mode}"
            shift 2
            ;;
        --attach)
            attach=true
            shift
            ;;
        --working)
            working_dir="${2:?missing value for --working}"
            shift 2
            ;;
        -h|--help)
            usage
            setup_project_env
            "$PYTHON" -m mmwk collect --help
            exit 0
            ;;
        *)
            die "Unknown argument: $1"
            ;;
    esac
done

[ -n "$did" ] || die "--did is required"

setup_project_env
working_dir="$(resolve_default_working_dir "$working_dir")"
if ! record_json="$(read_device_record_json "$working_dir" "$did" 2>&1)"; then
    die "$record_json"
fi
mqtt_server="$(json_value_from_text "$record_json" "mqtt_server")"
mqtt_port="$(json_value_from_text "$record_json" "mqtt_port")"
[ -n "$mqtt_server" ] || die "Device record missing mqtt_server: $did"
[ -n "$mqtt_port" ] || die "Device record missing mqtt_port: $did"

timestamp_prefix="$(compact_timestamp_now)_"
output_dir="$(abspath_path "$working_dir/data/$did" "$INVOKE_PWD")"
mkdir -p "$output_dir"

py_args=(
    -m
    mmwk.tools.collect_live
    --did
    "$did"
    --mqtt-server
    "$mqtt_server"
    --mqtt-port
    "$mqtt_port"
    --output-dir
    "$output_dir"
    --output-prefix
    "$timestamp_prefix"
)
if [ -n "$duration" ]; then
    py_args+=(--duration "$duration")
fi
if [ "$reboot" = true ]; then
    py_args+=(--reboot)
fi
if [ "$mode" != "host" ]; then
    py_args+=(--mode "$mode")
fi
if [ "$attach" = true ]; then
    py_args+=(--attach)
fi

log_info "Working dir: $working_dir"
log_info "Output dir: $output_dir"
log_info "Output prefix: $timestamp_prefix"
log_info "MQTT endpoint: $(mqtt_uri_from_host_port "$mqtt_server" "$mqtt_port")"

cd "$INVOKE_PWD"
exec "$PYTHON" "${py_args[@]}"
