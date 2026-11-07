#!/bin/bash
# run.sh — macOS/Linux shell wrapper for MMWK Sensor CLI
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
            case "$ver" in
                ''|*[!0-9.]*|*.*.*|.*|*.) continue ;;
            esac
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

resolve_venv_python() {
    if [ -n "${VIRTUAL_ENV:-}" ]; then
        if [ -x "$VIRTUAL_ENV/bin/python" ]; then
            printf '%s\n' "$VIRTUAL_ENV/bin/python"
            return 0
        fi
        if [ -x "$VIRTUAL_ENV/Scripts/python.exe" ]; then
            printf '%s\n' "$VIRTUAL_ENV/Scripts/python.exe"
            return 0
        fi
    fi

    if [ -x "$PWD/venv/bin/python" ]; then
        printf '%s\n' "$PWD/venv/bin/python"
        return 0
    fi
    if [ -x "$PWD/venv/Scripts/python.exe" ]; then
        printf '%s\n' "$PWD/venv/Scripts/python.exe"
        return 0
    fi

    return 1
}

python_supports_inline_code() {
    local candidate="${1:-}"
    local output=""

    [ -n "$candidate" ] || return 1
    [ -x "$candidate" ] || return 1

    output="$("$candidate" -c 'print("mmwk-inline-ok")' 2>/dev/null || true)"
    [ "$output" = "mmwk-inline-ok" ]
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
    local venv_python=""

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

    venv_python="$(resolve_venv_python || true)"
    if [ -n "$venv_python" ]; then
        PYTHON="$venv_python"
    fi

    if [ -n "$venv_python" ] && python_supports_inline_code "$venv_python" && ! "$venv_python" - <<'PY' >/dev/null 2>&1
import serial  # noqa: F401
import paho.mqtt.client  # noqa: F401
PY
    then
        rm -f venv/.deps_installed
    fi

    # Install deps if stamp is missing or requirements.txt is newer
    if [ ! -f venv/.deps_installed ] || [ requirements.txt -nt venv/.deps_installed ]; then
        if [ -z "$venv_python" ] || ! python_supports_inline_code "$venv_python"; then
            echo "Error: usable venv python not available for dependency installation."
            exit 1
        fi
        echo "Installing dependencies..."
        "$venv_python" -m pip install -q -r requirements.txt
        touch venv/.deps_installed
    fi
}

# ── Help output ──
show_help() {
    local ports
    ports="$(detect_serial_ports)"

    cat <<'HEADER'
run.sh -- MMWK Sensor CLI Shell Wrapper

USAGE:
    ./run.sh <command> [subcommand] [options]

ENVIRONMENT:
    Recommended on macOS or Linux with bash and Python 3.10+.
    Windows-style shells may detect serial ports, but this wrapper is documented
    and supported as a shell entrypoint for macOS/Linux workflows.

COMMANDS:
    node info             Node status handshake
    node claim            Claim route identity and credentials
    node reboot           Reboot the node
    node ota              Update ESP firmware via HTTP or MQTT stream OTA
    node agent            Enable/disable built-in agent services
    node heartbeat        Configure system heartbeat
    proto list            List node public protocol directory entries
    proto status          Show public protocol directory status
    proto manifest        Show public protocol manifest
    radar fw flash        Flash firmware via chunk transfer
    radar fw ota          Flash firmware via HTTP or MQTT stream OTA
    radar fw list         List firmware images
    radar fw set          Set default boot firmware partition
    radar fw switch       Switch the running firmware image immediately
    radar fw del          Delete a firmware partition
    radar fw download     Download firmware image to device
    radar fw version      Query running firmware version
    radar start           Start or restart radar service
    radar stop            Stop radar service
    radar status          Query radar state
    radar config apply    Reconfigure runtime radar contract
    radar config read     Read current radar cfg text
    radar raw status      Query raw route state
    radar raw runtime     Open a raw route (wire, MQTT, or both)
    radar raw reconnect   Arm one-shot MQTT DATA after reconnect
    radar raw off         Close the selected raw route
    radar record status   Query recorder state
    radar record config   Get or update recorder config
    radar record start    Start recorder
    radar record stop     Stop recorder
    radar record trigger Trigger a recording window
    radar diag            Manage/query radar diagnostics
    endpoint list         List active endpoint ids
    endpoint describe     Describe an endpoint
    endpoint read         Read endpoint state
    endpoint config       Read or write endpoint config
    scene read            Show active scene config
    scene set             Update scene config
    scene apply           Apply current scene
    scene wait            Wait until radar is ready after scene apply
    collect               Collect radar data through local host UART/USB, MQTT, or split routes
    network wifi          Set Wi-Fi credentials
    network 4g            Get/Set 4G configuration
    network priority      Get/Set preferred network: wifi or 4g
    network mqtt          Get/Set MQTT configuration
    network prov          Wi-Fi provisioning control
    network status        Query network runtime status
    network ntp           Configure NTP time sync

TRANSPORT OPTIONS:
    -p, --port PORT        Serial port
    -t, --transport TYPE   uart (default), usb (WDR/WSR USB CDC), or mqtt
    --broker HOST          MQTT broker address
    --did DID              DID for MQTT route fallback
    --prod PROD            Product route segment (default: mmwk)
    --oid OID              Organization route segment (default: mmwk)
    --cid CID              Claimed route id; takes precedence over --did
    --baudrate RATE        UART baudrate (USB CDC is fixed at 115200)
    --usb-wait-ms N        Host USB CDC enumeration budget; default 0 (WDR/WSR USB only)
    --reset                DTR/RTS reset before connecting (UART only)
    --uart-proxy auto|off  Reuse a persistent local UART proxy (UART only)
    -v, --verbose          Debug logging

EXAMPLES:
    ./run.sh node info -p /dev/cu.usbserial-0001
    ./run.sh node info --transport usb --usb-wait-ms 8000
    ./run.sh radar status --transport usb --port /dev/ttyACM0 --did DEVICE_ID
    ./run.sh node ota --fw mmwk_sensor_bridge_full.bin -p /dev/cu.usbserial-0001
    ./run.sh node ota --target esp --transport mqtt --ota-transport mqtt --fw app.bin --broker mqtt://127.0.0.1:1883 --did DEVICE_ID
    ./run.sh collect --transport uart --port /dev/cu.usbserial-0001 --duration 10 \
        --data-output ./data_resp.sraw --resp-output ./cmd_resp.log
    ./run.sh radar fw ota --fw firmware.bin --raw-resp-output ./ota_cmd_resp.log -p /dev/cu.usbserial-0001
    ./run.sh radar fw ota --transport mqtt --ota-transport mqtt --fw firmware.bin --cfg radar.cfg --broker mqtt://127.0.0.1:1883 --did DEVICE_ID
    ./run.sh radar fw flash --fw fw.bin --cfg config.cfg -p /dev/cu.usbserial-0001
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

export PYTHONPATH="$SCRIPT_DIR"
cd "$INVOKE_PWD"
exec "$RUNNER_PYTHON" -m mmwk "$@"
