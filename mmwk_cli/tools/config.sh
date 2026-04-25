#!/bin/bash
# config.sh — registry-backed radar task wrapper with init/update/list subcommands
set -euo pipefail

INVOKE_PWD="$(pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MMWK_CLI="$PROJECT_DIR/mmwk_cli.sh"
SERVER_SH="$PROJECT_DIR/server.sh"
TOOL_NAME="config"

# shellcheck disable=SC1091
. "$SCRIPT_DIR/_tool_common.sh"

usage_main() {
    cat <<'EOF_USAGE'
config.sh -- Registry-backed radar task helper

USAGE:
  ./tools/config.sh <command> [options]

COMMANDS:
  init      Configure a UART-connected device and persist it into device.yml
  update    Update radar firmware or runtime cfg using device.yml
  list      List configured devices from device.yml

COMMON:
  --working DIR       Working directory root (default: ./collect if present,
                      else ~/.mmwk/collect if present, else create ./collect)
  -h, --help          Show help for the selected command

EXAMPLES:
  ./tools/config.sh init --port /dev/ttyUSB1
  ./tools/config.sh update --device-id 0123456789ab --fw ./firmware.bin
  ./tools/config.sh list
EOF_USAGE
}

usage_init() {
    cat <<'EOF_USAGE'
config.sh init -- Configure a UART-connected device and write device.yml

USAGE:
  ./tools/config.sh init --port PORT [options]

REQUIRED:
  --port PORT            UART serial port used for bring-up

OPTIONAL:
  --baudrate RATE        UART baudrate (default: 115200)
  --reset                Reset device before the first UART command
  --ssid SSID            Wi-Fi SSID to store on device
  --password PASS        Wi-Fi password to store on device
  --mqtt-server HOST     MQTT server host or URI (default: local machine)
  --mqtt-port PORT       MQTT server port (default: 1883)
  --http-server HOST     HTTP server host or base URL (default: local machine)
  --http-port PORT       HTTP server port (default: 8380)
  --server-state-dir DIR server.sh state dir (default: ./build_output/local_server)
  --working DIR          Working directory root for device.yml
  -h, --help             Show this help

NOTES:
  - `init` updates `<working>/device.yml` only after MQTT readiness verification succeeds.
  - If `--ssid` and `--password` are omitted, the tool only refreshes server binding info.
EOF_USAGE
}

usage_update() {
    cat <<'EOF_USAGE'
config.sh update -- Update radar firmware or runtime cfg using device.yml

USAGE:
  ./tools/config.sh update --device-id ID [options]

REQUIRED:
  --device-id ID        Device id stored in `<working>/device.yml`

OPTIONAL:
  --fw FILE             Radar firmware file path for OTA
  --cfg FILE            Radar cfg file path; with `--fw` it travels with OTA,
                        without `--fw` it is applied through `radar config apply`
  --force               Force OTA even when the version already matches
  --working DIR         Working directory root for device.yml
  -h, --help            Show this help

NOTES:
  - At least one of `--fw` or `--cfg` is required.
  - `update` resolves MQTT/HTTP endpoints from `<working>/device.yml`.
EOF_USAGE
}

usage_list() {
    cat <<'EOF_USAGE'
config.sh list -- List configured devices from device.yml

USAGE:
  ./tools/config.sh list [options]

OPTIONAL:
  --working DIR         Working directory root for device.yml
  -h, --help            Show this help
EOF_USAGE
}

wait_for_radar_running() {
    local verify_timeout_sec="${1:-60}"
    local verify_poll_sec="${2:-2}"
    local mqtt_server="$3"
    local mqtt_port="$4"
    local device_id="$5"
    local deadline=""
    local status_output=""
    local radar_state=""

    deadline=$(( $(date +%s) + verify_timeout_sec ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        status_output=""
        radar_state=""

        if status_output="$(run_mmwk_cli radar status --transport mqtt --device-id "$device_id" --broker "$mqtt_server" --mqtt-port "$mqtt_port" 2>/dev/null)"
        then
            radar_state="$(json_value_from_text "$status_output" "state" "data.state")"
            if [ "$radar_state" = "running" ]; then
                return 0
            fi
        fi

        sleep "$verify_poll_sec"
    done

    return 1
}

cmd_init() {
    local port=""
    local baudrate="115200"
    local reset=false
    local ssid=""
    local password=""
    local mqtt_server=""
    local mqtt_port="1883"
    local http_server=""
    local http_port="8380"
    local server_state_dir=""
    local working_dir=""
    local server_env=""
    local local_mqtt_uri=""
    local local_http_base_url=""
    local mqtt_uri=""
    local http_base_url=""
    local node_info_text=""
    local device_id=""
    local network_status_text=""
    local mqtt_state=""

    while [ $# -gt 0 ]; do
        case "$1" in
            --port)
                port="${2:?missing value for --port}"
                shift 2
                ;;
            --baudrate)
                baudrate="${2:?missing value for --baudrate}"
                shift 2
                ;;
            --reset)
                reset=true
                shift
                ;;
            --ssid)
                ssid="${2:?missing value for --ssid}"
                shift 2
                ;;
            --password)
                password="${2:?missing value for --password}"
                shift 2
                ;;
            --mqtt-server)
                mqtt_server="${2:?missing value for --mqtt-server}"
                shift 2
                ;;
            --mqtt-port)
                mqtt_port="${2:?missing value for --mqtt-port}"
                shift 2
                ;;
            --http-server)
                http_server="${2:?missing value for --http-server}"
                shift 2
                ;;
            --http-port)
                http_port="${2:?missing value for --http-port}"
                shift 2
                ;;
            --server-state-dir)
                server_state_dir="${2:?missing value for --server-state-dir}"
                shift 2
                ;;
            --working)
                working_dir="${2:?missing value for --working}"
                shift 2
                ;;
            -h|--help)
                usage_init
                exit 0
                ;;
            *)
                die "Unknown argument for init: $1"
                ;;
        esac
    done

    [ -n "$port" ] || die "--port is required"
    if { [ -n "$ssid" ] && [ -z "$password" ]; } || { [ -z "$ssid" ] && [ -n "$password" ]; }; then
        die "--ssid and --password must be provided together"
    fi

    setup_project_env
    working_dir="$(resolve_default_working_dir "$working_dir")"
    server_state_dir="$(resolve_default_server_state_dir "$server_state_dir")"

    if [ -z "$mqtt_server" ] || [ -z "$http_server" ]; then
        log_info "Resolving local server defaults"
        server_env="$(server_env_text "$server_state_dir" "$mqtt_port" "$http_port")"

        if [ -z "$mqtt_server" ]; then
            local_mqtt_uri="$(extract_env_value_from_text "$server_env" "MMWK_SERVER_MQTT_URI")"
            [ -n "$local_mqtt_uri" ] || die "server.sh env did not return MMWK_SERVER_MQTT_URI"
            mapfile -t mqtt_parts < <(split_mqtt_uri "$local_mqtt_uri" "$mqtt_port")
            mqtt_server="${mqtt_parts[0]}"
            mqtt_port="${mqtt_parts[1]}"
        fi

        if [ -z "$http_server" ]; then
            local_http_base_url="$(extract_env_value_from_text "$server_env" "MMWK_SERVER_HTTP_BASE_URL")"
            [ -n "$local_http_base_url" ] || die "server.sh env did not return MMWK_SERVER_HTTP_BASE_URL"
            mapfile -t http_parts < <(split_http_base_url "$local_http_base_url" "$http_port")
            http_server="${http_parts[0]}"
            http_port="${http_parts[1]}"
        fi
    fi

    mqtt_uri="$(mqtt_uri_from_host_port "$mqtt_server" "$mqtt_port")"
    http_base_url="$(http_base_url_from_host_port "$http_server" "$http_port")"

    uart_args=(--transport uart --port "$port" --baudrate "$baudrate")
    if [ "$reset" = true ]; then
        uart_args+=(--reset)
    fi

    log_info "Reading device identity over UART"
    node_info_text="$(run_mmwk_cli node info "${uart_args[@]}")"
    device_id="$(json_value_from_text "$node_info_text" "id" "client_id")"
    [ -n "$device_id" ] || die "Failed to detect device id from node info"

    if [ -n "$ssid" ]; then
        log_info "Applying Wi-Fi settings"
        run_mmwk_cli network wifi --ssid "$ssid" --pass "$password" "${uart_args[@]}" >/dev/null
    fi

    log_info "Applying MQTT settings for $mqtt_uri"
    run_mmwk_cli network mqtt --uri "$mqtt_uri" "${uart_args[@]}" >/dev/null

    log_info "Rebooting device"
    run_mmwk_cli node reboot "${uart_args[@]}" >/dev/null

    log_info "Verifying MQTT readiness over UART"
    mqtt_state=""
    for _ in $(seq 1 15); do
        network_status_text="$(run_mmwk_cli network status "${uart_args[@]}")"
        mqtt_state="$(json_value_from_text "$network_status_text" "mqtt_state" "data.mqtt_state")"
        if [ "$mqtt_state" = "connected" ]; then
            break
        fi
        sleep 1
    done
    [ "$mqtt_state" = "connected" ] || die "Expected network status mqtt_state=connected, got '${mqtt_state:-missing}'"

    log_info "Verifying MQTT control path"
    run_mmwk_cli node info --transport mqtt --device-id "$device_id" --broker "$mqtt_server" --mqtt-port "$mqtt_port" >/dev/null

    write_device_record "$working_dir" "$device_id" "$mqtt_server" "$mqtt_port" "$http_server" "$http_port" "$ssid"

    printf 'device-id: %s\n' "$device_id"
    printf 'working-dir: %s\n' "$working_dir"
    printf 'device-file: %s\n' "$(device_registry_path "$working_dir")"
    printf 'mqtt-uri: %s\n' "$mqtt_uri"
    printf 'http-base-url: %s\n' "$http_base_url"
    printf './tools/config.sh update --device-id %s --working %s --fw ./firmware.bin\n' \
        "$device_id" "$working_dir"
    printf './tools/collect.sh --device-id %s --working %s --duration 10\n' \
        "$device_id" "$working_dir"
}

cmd_update() {
    local device_id=""
    local fw_path=""
    local cfg_path=""
    local force=false
    local working_dir=""
    local record_json=""
    local mqtt_server=""
    local mqtt_port=""
    local http_server=""
    local http_port=""
    local http_base_url=""

    while [ $# -gt 0 ]; do
        case "$1" in
            --device-id)
                device_id="${2:?missing value for --device-id}"
                shift 2
                ;;
            --fw)
                fw_path="${2:?missing value for --fw}"
                shift 2
                ;;
            --cfg)
                cfg_path="${2:?missing value for --cfg}"
                shift 2
                ;;
            --force)
                force=true
                shift
                ;;
            --working)
                working_dir="${2:?missing value for --working}"
                shift 2
                ;;
            -h|--help)
                usage_update
                exit 0
                ;;
            *)
                die "Unknown argument for update: $1"
                ;;
        esac
    done

    [ -n "$device_id" ] || die "--device-id is required"
    if [ -z "$fw_path" ] && [ -z "$cfg_path" ]; then
        die "At least one of --fw or --cfg is required"
    fi

    setup_project_env
    working_dir="$(resolve_default_working_dir "$working_dir")"
    if ! record_json="$(read_device_record_json "$working_dir" "$device_id" 2>&1)"; then
        die "$record_json"
    fi
    mqtt_server="$(json_value_from_text "$record_json" "mqtt_server")"
    mqtt_port="$(json_value_from_text "$record_json" "mqtt_port")"
    http_server="$(json_value_from_text "$record_json" "http_server")"
    http_port="$(json_value_from_text "$record_json" "http_port")"
    [ -n "$mqtt_server" ] || die "Device record missing mqtt_server: $device_id"
    [ -n "$mqtt_port" ] || die "Device record missing mqtt_port: $device_id"

    if [ -n "$fw_path" ]; then
        fw_path="$(abspath_path "$fw_path" "$INVOKE_PWD")"
        [ -f "$fw_path" ] || die "Firmware file not found: $fw_path"
    fi
    if [ -n "$cfg_path" ]; then
        cfg_path="$(abspath_path "$cfg_path" "$INVOKE_PWD")"
        [ -f "$cfg_path" ] || die "Config file not found: $cfg_path"
    fi

    mqtt_args=(--transport mqtt --device-id "$device_id" --broker "$mqtt_server" --mqtt-port "$mqtt_port")

    if [ -n "$fw_path" ]; then
        [ -n "$http_server" ] || die "Device record missing http_server: $device_id"
        [ -n "$http_port" ] || die "Device record missing http_port: $device_id"
        http_base_url="$(http_base_url_from_host_port "$http_server" "$http_port")"

        ota_cmd=(radar fw ota --fw "$fw_path" --base-url "$http_base_url")
        if [ -n "$cfg_path" ]; then
            ota_cmd+=(--cfg "$cfg_path")
        fi
        if [ "$force" = true ]; then
            ota_cmd+=(--force)
        fi

        log_info "Starting radar OTA for $device_id"
        run_mmwk_cli "${ota_cmd[@]}" "${mqtt_args[@]}" >/dev/null

        log_info "Waiting for radar runtime to recover"
        if ! wait_for_radar_running 60 2 "$mqtt_server" "$mqtt_port" "$device_id"; then
            die "Radar OTA completed but runtime verification did not recover within 60s"
        fi

        log_info "Verifying radar firmware version"
        run_mmwk_cli radar fw version "${mqtt_args[@]}" >/dev/null
    else
        log_info "Applying runtime radar cfg for $device_id"
        run_mmwk_cli radar config apply --welcome --no-verify --cfg "$cfg_path" "${mqtt_args[@]}" >/dev/null

        log_info "Waiting for radar runtime to recover"
        if ! wait_for_radar_running 60 2 "$mqtt_server" "$mqtt_port" "$device_id"; then
            die "Radar cfg apply completed but runtime verification did not recover within 60s"
        fi
    fi

    log_info "Verifying radar runtime status"
    run_mmwk_cli radar status "${mqtt_args[@]}" >/dev/null

    printf 'device-id: %s\n' "$device_id"
    printf 'working-dir: %s\n' "$working_dir"
    printf 'device-file: %s\n' "$(device_registry_path "$working_dir")"
    printf 'mqtt-uri: %s\n' "$(mqtt_uri_from_host_port "$mqtt_server" "$mqtt_port")"
    if [ -n "$fw_path" ]; then
        printf 'http-base-url: %s\n' "$http_base_url"
        printf 'firmware: %s\n' "$fw_path"
    fi
    if [ -n "$cfg_path" ]; then
        printf 'config: %s\n' "$cfg_path"
    fi
}

cmd_list() {
    local working_dir=""
    local lines=""

    while [ $# -gt 0 ]; do
        case "$1" in
            --working)
                working_dir="${2:?missing value for --working}"
                shift 2
                ;;
            -h|--help)
                usage_list
                exit 0
                ;;
            *)
                die "Unknown argument for list: $1"
                ;;
        esac
    done

    setup_project_env
    working_dir="$(resolve_default_working_dir "$working_dir")"
    if ! lines="$(list_device_records "$working_dir" 2>&1)"; then
        die "$lines"
    fi

    printf 'working-dir: %s\n' "$working_dir"
    printf 'device-file: %s\n' "$(device_registry_path "$working_dir")"
    if [ -z "$lines" ]; then
        printf 'no devices configured\n'
        return 0
    fi

    printf 'device-id\tmqtt\thttp\n'
    printf '%s\n' "$lines"
}

subcommand="${1:-}"
case "$subcommand" in
    init)
        shift
        cmd_init "$@"
        ;;
    update)
        shift
        cmd_update "$@"
        ;;
    list)
        shift
        cmd_list "$@"
        ;;
    ""|-h|--help)
        usage_main
        ;;
    *)
        die "Unknown command: $subcommand"
        ;;
esac
