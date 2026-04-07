#!/bin/bash
# mmwk_cli.sh — macOS/Linux shell wrapper for MMWK Sensor CLI
set -e

INVOKE_PWD="$(pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# cd to project root (where this script lives)
cd "$SCRIPT_DIR"

# ── Platform detection (macOS/Linux first; Windows is best-effort) ──
detect_platform() {
    case "$(uname -s)" in
        Darwin)  echo "macos" ;;
        Linux)   echo "linux" ;;
        MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
        *)       echo "unknown" ;;
    esac
}

PLATFORM="$(detect_platform)"

# ── Python detection (python3 → python, verify ≥3.10) ──
find_python() {
    for cmd in python3 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            local ver
            ver="$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)" || continue
            local major minor
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
    echo "Error: Python 3.10+ not found. Please install Python 3.10 or higher."
    exit 1
}

# ── Serial port detection ──
detect_serial_ports() {
    case "$PLATFORM" in
        macos)
            ls /dev/cu.usbserial-* /dev/cu.usbmodem* 2>/dev/null || true
            ;;
        linux)
            ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || true
            ;;
        windows)
            powershell.exe -Command "[System.IO.Ports.SerialPort]::GetPortNames()" 2>/dev/null || true
            ;;
    esac
}

# ── Venv management ──
setup_venv() {
    if [ ! -d venv ]; then
        echo "Creating virtual environment..."
        "$PYTHON" -m venv venv
    fi

    # Activate venv
    if [ -f venv/bin/activate ]; then
        . venv/bin/activate
    elif [ -f venv/Scripts/activate ]; then
        . venv/Scripts/activate
    fi

    # Install deps if stamp is missing or requirements.txt is newer
    if [ ! -f venv/.deps_installed ] || [ requirements.txt -nt venv/.deps_installed ]; then
        echo "Installing dependencies..."
        pip install -q -r requirements.txt
        touch venv/.deps_installed
    fi
}

# ── Help output ──
show_help() {
    local ports
    ports="$(detect_serial_ports)"

    cat <<'HEADER'
mmwk_cli.sh -- MMWK Sensor CLI Shell Wrapper

USAGE:
    ./mmwk_cli.sh <command> [subcommand] [options]

ENVIRONMENT:
    Recommended on macOS or Linux with bash and Python 3.10+.
    Windows-style shells may detect serial ports, but this wrapper is documented
    and supported as a shell entrypoint for macOS/Linux workflows.

COMMANDS:
    device hi              Device handshake
    device reboot          Reboot the device
    device ota             Update ESP firmware via HTTP OTA
    device startup         Configure radar startup mode
    device agent           Enable/disable built-in agent services
    device heartbeat       Configure system heartbeat
    radar flash            Flash firmware via chunk transfer
    radar ota              Flash firmware via HTTP OTA (optional end-to-end raw_resp capture)
    radar status           Query radar state
    radar version          Query firmware version
    radar raw              Configure/query raw forwarding
    radar debug            Configure/query debug diagnostics
    fw list                List firmware images
    fw set                 Set default boot firmware partition
    fw del                 Delete a firmware partition
    fw download            Download firmware image to device
    record start           Start recording
    record stop            Stop recording
    record trigger         Trigger event recording snippet
    collect                Subscribe MQTT raw_data/raw_resp and save raw data plus trimmed cmd_resp text
    network config         Set Wi-Fi credentials
    network mqtt           Get/Set MQTT configuration
    network prov           Wi-Fi provisioning control
    network status         Query Wi-Fi runtime/provisioning status
    network ntp            Configure NTP time sync
    tools                  List available MCP tools
    help                   List all device-supported commands

TRANSPORT OPTIONS:
    -p, --port PORT        Serial port
    -t, --transport TYPE   uart (default) or mqtt
    --broker HOST          MQTT broker address
    --device-id ID         Device ID for MQTT
    --baudrate RATE        Baudrate (default: 115200)
    --reset                DTR/RTS reset before connecting
    -v, --verbose          Debug logging

EXAMPLES:
    ./mmwk_cli.sh device hi -p /dev/cu.usbserial-0001
    ./mmwk_cli.sh device ota --fw mmwk_sensor_bridge_full.bin -p /dev/cu.usbserial-0001
    ./mmwk_cli.sh collect --duration 10 --data-output ./data_resp.sraw --resp-output ./cmd_resp.log -p /dev/cu.usbserial-0001
    ./mmwk_cli.sh radar ota --fw firmware.bin --raw-resp-output ./ota_cmd_resp.log -p /dev/cu.usbserial-0001
    ./mmwk_cli.sh radar flash --fw fw.bin --cfg config.cfg -p /dev/cu.usbserial-0001
HEADER

    echo ""
    echo "DETECTED SERIAL PORTS:"
    if [ -n "$ports" ]; then
        echo "$ports" | while IFS= read -r p; do
            echo "    $p"
        done
    else
        echo "    (none found)"
    fi

    echo ""
    echo "ENVIRONMENT: Python=$PYTHON  Platform=$PLATFORM  Venv=./venv"
}

# ── Main ──
if [ "$1" = "--help" ] || [ "$1" = "-h" ] || [ $# -eq 0 ]; then
    show_help
    exit 0
fi

setup_venv

RUNNER_PYTHON="$PYTHON"
if [ -n "${VIRTUAL_ENV:-}" ]; then
    if [ -x "$VIRTUAL_ENV/bin/python" ]; then
        RUNNER_PYTHON="$VIRTUAL_ENV/bin/python"
    elif [ -x "$VIRTUAL_ENV/Scripts/python.exe" ]; then
        RUNNER_PYTHON="$VIRTUAL_ENV/Scripts/python.exe"
    fi
fi

export PYTHONPATH="$SCRIPT_DIR/scripts"
cd "$INVOKE_PWD"
exec "$RUNNER_PYTHON" -m mmwk_cli "$@"
