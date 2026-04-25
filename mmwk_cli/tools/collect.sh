#!/bin/bash
# collect.sh — registry-backed late-attach MQTT raw collection helper
set -euo pipefail

INVOKE_PWD="$(pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MMWK_CLI="$PROJECT_DIR/mmwk_cli.sh"
SERVER_SH="$PROJECT_DIR/server.sh"
TOOL_NAME="collect"

# shellcheck disable=SC1091
. "$SCRIPT_DIR/_tool_common.sh"

usage() {
    cat <<'EOF_USAGE'
collect.sh -- Collect radar raw data using device.yml

USAGE:
  ./tools/collect.sh --device-id ID [options]

REQUIRED:
  --device-id ID        Device id stored in `<working>/device.yml`

OPTIONAL:
  --duration SEC        Capture duration in seconds; omit for Ctrl-C mode
  --reboot              Restart the radar service after subscribe-ready bootstrap so startup raw_resp is captured
  --working DIR         Working directory root for device.yml and data output
  -h, --help            Show this help

NOTES:
  - `collect.sh` reads MQTT connection info from `<working>/device.yml`.
  - Output files are written under `<working>/data/<device-id>/`.
  - Data and log outputs now share the same basename: `*_raw_data.sraw` and `*_raw_data.log`.
  - If `--duration` is omitted, press Ctrl-C to stop.
EOF_USAGE
}

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
    mmwk_cli.tools.collect_live
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
