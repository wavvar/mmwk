#!/bin/bash
# collect.sh — registry-backed late-attach MQTT raw collection helper
set -euo pipefail

INVOKE_PWD="$(pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
MMWK_CLI="$PROJECT_DIR/run.sh"
SERVER_SH="$PROJECT_DIR/server.sh"
TOOL_NAME="collect"

# shellcheck disable=SC1091
. "$PROJECT_DIR/.tool_common.sh"

usage() {
    cat <<'EOF_USAGE'
collect.sh -- Collect radar raw data using device.yml

USAGE:
  ./collect.sh --device-id ID [options]
  ./collect.sh --trigger none|radar-restart|device-reboot [direct-options]

REQUIRED:
  --device-id ID        Device id stored in `<working>/device.yml`

OPTIONAL:
  --duration SEC        Capture duration in seconds; omit for Ctrl-C mode
  --reboot              Restart the radar service after subscribe-ready bootstrap so startup raw_resp is captured
  --working DIR         Working directory root for device.yml and data output
  --server-state-dir DIR
                       Direct mode server.sh state dir (default: ./build_output/local_server)
  -h, --help            Show this help

NOTES:
  - `collect.sh` reads MQTT connection info from `<working>/device.yml`.
  - Output files are written under `<working>/data/<device-id>/`.
  - Data and log outputs now share the same basename: `*_raw_data.sraw` and `*_raw_data.log`.
  - If `--duration` is omitted, press Ctrl-C to stop.
  - `--trigger` enables direct pure-MQTT mode and forwards options to
    `python -m mmwk.tools.collect_raw`.
EOF_USAGE
}

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

device_id=""
duration=""
reboot=false
working_dir=""

while [ $# -gt 0 ]; do
    case "$1" in
        --device-id)
            device_id="${2:?missing value for --device-id}"
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
        --working)
            working_dir="${2:?missing value for --working}"
            shift 2
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

[ -n "$device_id" ] || die "--device-id is required"

setup_project_env
working_dir="$(resolve_default_working_dir "$working_dir")"
if ! record_json="$(read_device_record_json "$working_dir" "$device_id" 2>&1)"; then
    die "$record_json"
fi
mqtt_server="$(json_value_from_text "$record_json" "mqtt_server")"
mqtt_port="$(json_value_from_text "$record_json" "mqtt_port")"
[ -n "$mqtt_server" ] || die "Device record missing mqtt_server: $device_id"
[ -n "$mqtt_port" ] || die "Device record missing mqtt_port: $device_id"

timestamp_prefix="$(compact_timestamp_now)_"
output_dir="$(abspath_path "$working_dir/data/$device_id" "$INVOKE_PWD")"
mkdir -p "$output_dir"

py_args=(
    -m
    mmwk.tools.collect_live
    --device-id
    "$device_id"
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

log_info "Working dir: $working_dir"
log_info "Output dir: $output_dir"
log_info "Output prefix: $timestamp_prefix"
log_info "MQTT endpoint: $(mqtt_uri_from_host_port "$mqtt_server" "$mqtt_port")"

cd "$INVOKE_PWD"
exec "$PYTHON" "${py_args[@]}"
