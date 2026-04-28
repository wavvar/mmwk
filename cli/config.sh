#!/bin/bash
# config.sh — registry-backed radar task wrapper with init/update/list/search subcommands
set -euo pipefail

INVOKE_PWD="$(pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
MMWK_CLI="$PROJECT_DIR/run.sh"
SERVER_SH="$PROJECT_DIR/server.sh"
TOOL_NAME="config"

# shellcheck disable=SC1091
. "$PROJECT_DIR/.tool_common.sh"

usage_main() {
    cat <<'EOF_USAGE'
config.sh -- Registry-backed radar task helper

USAGE:
  ./config.sh <command> [options]

COMMANDS:
  init      Configure a UART-connected device and persist it into device.yml
  set       Configure device Wi-Fi and MQTT settings over UART or MQTT
  search    Discover MMWK devices over mDNS
  update    Update radar firmware or runtime cfg using device.yml
  list      List configured devices from device.yml

COMMON:
  --working DIR       Working directory root (default: ./collect if present,
                      else ~/.mmwk/collect if present, else create ./collect)
  -h, --help          Show help for the selected command

EXAMPLES:
  ./config.sh init --port /dev/ttyUSB1
  ./config.sh set --server-local --ssid YOUR_WIFI --password YOUR_PASSWORD --port /dev/ttyUSB1 --reboot
  ./config.sh search
  ./config.sh update --device-id 0123456789ab --fw ./firmware.bin
  ./config.sh list
EOF_USAGE
}

usage_init() {
    cat <<'EOF_USAGE'
config.sh init -- Configure a UART-connected device and write device.yml

USAGE:
  ./config.sh init --port PORT [options]

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
  ./config.sh update --device-id ID [options]

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

usage_set() {
    cat <<'EOF_USAGE'
config.sh set -- Configure device Wi-Fi and MQTT settings without writing device.yml

USAGE:
  ./config.sh set [transport-options] [config-options]

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
  -v, --verbose          Enable verbose run.sh logging

CONFIG OPTIONS:
  --ssid SSID            Wi-Fi SSID to store on device
  --password PASS        Wi-Fi password to store on device
  --mqtt-uri URI         MQTT broker URI to store on device
  --mqtt-user USER       MQTT username to store on device
  --mqtt-pass PASS       MQTT password to store on device
  --server-local         Start or reuse server.sh and use its MQTT URI
  --server-state-dir DIR server.sh state dir (default: ./build_output/local_server)
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
EOF_USAGE
}

usage_list() {
    cat <<'EOF_USAGE'
config.sh list -- List configured devices from device.yml

USAGE:
  ./config.sh list [options]

OPTIONAL:
  --working DIR         Working directory root for device.yml
  -h, --help            Show this help
EOF_USAGE
}

usage_search() {
    cat <<'EOF_USAGE'
config.sh search -- Discover MMWK devices over mDNS

USAGE:
  ./config.sh search [options]

OPTIONAL:
  --timeout SEC        mDNS browse duration (default: 3)
  --json               Print machine-readable JSON
  --ap-iface IFACE     Temporarily add --ap-cidr to this host interface
  --ap-cidr CIDR       Host address for device AP discovery (default: 192.168.4.2/24)
  --keep-ap-alias      Leave the temporary AP address configured after search
  -h, --help           Show this help

EXAMPLES:
  ./config.sh search
  ./config.sh search --json
  ./config.sh search --ap-iface wlan0 --ap-cidr 192.168.4.2/24
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
    printf './config.sh update --device-id %s --working %s --fw ./firmware.bin\n' \
        "$device_id" "$working_dir"
    printf './collect.sh --device-id %s --working %s --duration 10\n' \
        "$device_id" "$working_dir"
}

cmd_set() {
    local transport="uart"
    local port=""
    local baudrate="115200"
    local reset=false
    local broker=""
    local mqtt_port="1883"
    local device_id=""
    local cmd_topic=""
    local resp_topic=""
    local timeout="10"
    local verbose=false
    local ssid=""
    local password=""
    local mqtt_uri=""
    local mqtt_user=""
    local mqtt_pass=""
    local server_local=false
    local server_state_dir=""
    local server_serve_dir=""
    local server_upload_dir=""
    local server_host_ip=""
    local server_target_ip=""
    local server_mqtt_port="1883"
    local server_http_port="8380"
    local reboot=false
    local wifi_requested=false
    local mqtt_requested=false
    local config_changed=false
    local server_env=""
    local start_cmd=()
    local transport_args=()
    local mqtt_cmd=()

    while [ $# -gt 0 ]; do
        case "$1" in
            --transport)
                transport="${2:?missing value for --transport}"
                shift 2
                ;;
            -p|--port)
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
            --broker)
                broker="${2:?missing value for --broker}"
                shift 2
                ;;
            --mqtt-port)
                mqtt_port="${2:?missing value for --mqtt-port}"
                shift 2
                ;;
            --device-id)
                device_id="${2:?missing value for --device-id}"
                shift 2
                ;;
            --cmd-topic)
                cmd_topic="${2:?missing value for --cmd-topic}"
                shift 2
                ;;
            --resp-topic)
                resp_topic="${2:?missing value for --resp-topic}"
                shift 2
                ;;
            --timeout)
                timeout="${2:?missing value for --timeout}"
                shift 2
                ;;
            -v|--verbose)
                verbose=true
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
            --mqtt-uri)
                mqtt_uri="${2:?missing value for --mqtt-uri}"
                shift 2
                ;;
            --mqtt-user)
                mqtt_user="${2:?missing value for --mqtt-user}"
                shift 2
                ;;
            --mqtt-pass)
                mqtt_pass="${2:?missing value for --mqtt-pass}"
                shift 2
                ;;
            --server-local)
                server_local=true
                shift
                ;;
            --server-state-dir)
                server_state_dir="${2:?missing value for --server-state-dir}"
                shift 2
                ;;
            --server-serve-dir)
                server_serve_dir="${2:?missing value for --server-serve-dir}"
                shift 2
                ;;
            --server-upload-dir)
                server_upload_dir="${2:?missing value for --server-upload-dir}"
                shift 2
                ;;
            --server-host-ip)
                server_host_ip="${2:?missing value for --server-host-ip}"
                shift 2
                ;;
            --server-target-ip)
                server_target_ip="${2:?missing value for --server-target-ip}"
                shift 2
                ;;
            --server-mqtt-port)
                server_mqtt_port="${2:?missing value for --server-mqtt-port}"
                shift 2
                ;;
            --server-http-port)
                server_http_port="${2:?missing value for --server-http-port}"
                shift 2
                ;;
            --reboot)
                reboot=true
                shift
                ;;
            -h|--help)
                usage_set
                exit 0
                ;;
            *)
                die "Unknown argument for set: $1"
                ;;
        esac
    done

    [ "$transport" = "uart" ] || [ "$transport" = "mqtt" ] || die "--transport must be uart or mqtt"
    if { [ -n "$ssid" ] && [ -z "$password" ]; } || { [ -z "$ssid" ] && [ -n "$password" ]; }; then
        die "--ssid and --password must be provided together"
    fi
    if [ "$transport" = "uart" ] && [ -z "$port" ]; then
        die "--port is required when --transport uart"
    fi
    if [ "$server_local" = true ] && [ -n "$mqtt_uri" ]; then
        die "--server-local already resolves the broker URI; do not combine it with --mqtt-uri"
    fi

    [ -n "$ssid" ] && wifi_requested=true
    if [ -n "$mqtt_uri" ] || [ -n "$mqtt_user" ] || [ -n "$mqtt_pass" ] || [ "$server_local" = true ]; then
        mqtt_requested=true
    fi
    if [ "$wifi_requested" = false ] && [ "$mqtt_requested" = false ] && [ "$reboot" = false ]; then
        die "No configuration action requested. Pass Wi-Fi options, MQTT options, --server-local, or --reboot."
    fi

    setup_project_env
    server_state_dir="$(resolve_default_server_state_dir "$server_state_dir")"

    if [ "$server_local" = true ]; then
        start_cmd=(bash "$SERVER_SH" start --state-dir "$server_state_dir" --mqtt-port "$server_mqtt_port" --http-port "$server_http_port")
        [ -z "$server_serve_dir" ] || start_cmd+=(--serve-dir "$server_serve_dir")
        [ -z "$server_upload_dir" ] || start_cmd+=(--upload-dir "$server_upload_dir")
        [ -z "$server_host_ip" ] || start_cmd+=(--host-ip "$server_host_ip")
        [ -z "$server_target_ip" ] || start_cmd+=(--target-ip "$server_target_ip")

        log_info "Starting or reusing local server via server.sh"
        "${start_cmd[@]}" >/dev/null
        server_env="$(bash "$SERVER_SH" env --state-dir "$server_state_dir")"
        mqtt_uri="$(extract_env_value_from_text "$server_env" "MMWK_SERVER_MQTT_URI")"
        [ -n "$mqtt_uri" ] || die "server.sh env did not return MMWK_SERVER_MQTT_URI"
        log_info "Resolved local MQTT URI: $mqtt_uri"
    fi

    transport_args=(--transport "$transport" --timeout "$timeout")
    if [ "$transport" = "uart" ]; then
        transport_args+=(--port "$port" --baudrate "$baudrate")
        [ "$reset" = false ] || transport_args+=(--reset)
    else
        [ -z "$broker" ] || transport_args+=(--broker "$broker")
        [ -z "$mqtt_port" ] || transport_args+=(--mqtt-port "$mqtt_port")
        [ -z "$device_id" ] || transport_args+=(--device-id "$device_id")
        [ -z "$cmd_topic" ] || transport_args+=(--cmd-topic "$cmd_topic")
        [ -z "$resp_topic" ] || transport_args+=(--resp-topic "$resp_topic")
    fi
    [ "$verbose" = false ] || transport_args+=(--verbose)

    if [ "$wifi_requested" = true ]; then
        log_info "Applying Wi-Fi settings over $transport"
        run_mmwk_cli network wifi --ssid "$ssid" --pass "$password" "${transport_args[@]}" >/dev/null
        config_changed=true
    fi

    if [ "$mqtt_requested" = true ]; then
        mqtt_cmd=(network mqtt)
        [ -z "$mqtt_uri" ] || mqtt_cmd+=(--uri "$mqtt_uri")
        [ -z "$mqtt_user" ] || mqtt_cmd+=(--user "$mqtt_user")
        [ -z "$mqtt_pass" ] || mqtt_cmd+=(--pass "$mqtt_pass")
        [ "${#mqtt_cmd[@]}" -gt 2 ] || die "MQTT configuration was requested but no MQTT fields were resolved"

        log_info "Applying MQTT settings over $transport"
        run_mmwk_cli "${mqtt_cmd[@]}" "${transport_args[@]}" >/dev/null
        config_changed=true
    fi

    if [ "$reboot" = true ]; then
        log_info "Rebooting device over $transport"
        run_mmwk_cli node reboot "${transport_args[@]}" >/dev/null
    elif [ "$config_changed" = true ]; then
        log_info "Configuration updated. Reboot the device to apply Wi-Fi/MQTT changes."
    fi

    [ -z "$mqtt_uri" ] || printf 'mqtt-uri: %s\n' "$mqtt_uri"
    printf 'server-state-dir: %s\n' "$server_state_dir"
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

cmd_search() {
    if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
        usage_search
        exit 0
    fi

    setup_project_env
    "$PYTHON" -m mmwk.discovery "$@"
}

subcommand="${1:-}"
case "$subcommand" in
    init)
        shift
        cmd_init "$@"
        ;;
    set)
        shift
        cmd_set "$@"
        ;;
    search)
        shift
        cmd_search "$@"
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
