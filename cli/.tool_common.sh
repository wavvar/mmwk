#!/bin/bash
# .tool_common.sh — shared shell helpers for task-oriented CLI tools

find_python() {
    local cmd
    local ver
    local major
    local minor

    for cmd in python3 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            ver="$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)" || continue
            case "$ver" in
                ''|*[!0-9.]*|*.*.*|.*|*.) continue ;;
            esac
            major="${ver%%.*}"
            minor="${ver#*.}"
            if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
                printf '%s\n' "$cmd"
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

    if [ -x "$PROJECT_DIR/venv/bin/python" ]; then
        printf '%s\n' "$PROJECT_DIR/venv/bin/python"
        return 0
    fi
    if [ -x "$PROJECT_DIR/venv/Scripts/python.exe" ]; then
        printf '%s\n' "$PROJECT_DIR/venv/Scripts/python.exe"
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

setup_venv() {
    local venv_python=""
    local requirements_file="$PROJECT_DIR/requirements.txt"

    if [ ! -d "$PROJECT_DIR/venv" ]; then
        "$PYTHON" -m venv "$PROJECT_DIR/venv"
    fi

    if [ -f "$PROJECT_DIR/venv/bin/activate" ]; then
        # shellcheck disable=SC1091
        . "$PROJECT_DIR/venv/bin/activate"
    elif [ -f "$PROJECT_DIR/venv/Scripts/activate" ]; then
        # shellcheck disable=SC1091
        . "$PROJECT_DIR/venv/Scripts/activate"
    fi

    venv_python="$(resolve_venv_python || true)"
    if [ -n "$venv_python" ]; then
        PYTHON="$venv_python"
    fi

    # An empty requirements file is a valid lightweight CLI fixture (and a
    # useful offline mode).  Do not probe optional runtime imports or invoke
    # pip in that case; the probe would invalidate a fresh stamp on systems
    # where the bootstrap interpreter has no pip module.
    if [ ! -s "$requirements_file" ]; then
        return 0
    fi

    if [ -n "$venv_python" ] && python_supports_inline_code "$venv_python" && ! "$venv_python" - <<'PY' >/dev/null 2>&1
import serial  # noqa: F401
import paho.mqtt.client  # noqa: F401
PY
    then
        rm -f "$PROJECT_DIR/venv/.deps_installed"
    fi

    if [ ! -f "$PROJECT_DIR/venv/.deps_installed" ] || [ "$PROJECT_DIR/requirements.txt" -nt "$PROJECT_DIR/venv/.deps_installed" ]; then
        if [ -z "$venv_python" ] || ! python_supports_inline_code "$venv_python"; then
            echo "Error: usable venv python not available for dependency installation." >&2
            exit 1
        fi
        "$venv_python" -m pip install -q -r "$PROJECT_DIR/requirements.txt"
        touch "$PROJECT_DIR/venv/.deps_installed"
    fi
}

setup_project_env() {
    local bootstrap_python=""
    local old_pwd=""

    bootstrap_python="$(find_python)" || {
        echo "Error: Python 3.10+ not found." >&2
        exit 1
    }

    PYTHON="$bootstrap_python"
    old_pwd="$PWD"
    cd "$PROJECT_DIR"
    setup_venv
    cd "$old_pwd"

    export PYTHONPATH="$PROJECT_DIR"
}

timestamp_now() {
    date '+%Y-%m-%d %H:%M:%S'
}

log_info() {
    printf '[%s] [%s] %s\n' "$(timestamp_now)" "$TOOL_NAME" "$*"
}

log_warn() {
    printf '[%s] [%s] %s\n' "$(timestamp_now)" "$TOOL_NAME" "$*" >&2
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
    if current is None:
        return ""
    return str(current).strip()

for path in paths:
    value = lookup(data, path)
    if value:
        print(value)
        break
PY
}

ensure_parent_dir() {
    mkdir -p "$(dirname "$1")"
}

resolve_default_server_state_dir() {
    if [ -n "${1:-}" ]; then
        printf '%s\n' "$(abspath_path "$1" "$INVOKE_PWD")"
    else
        printf '%s\n' "$(abspath_path "./build_output/local_server" "$INVOKE_PWD")"
    fi
}

resolve_default_working_dir() {
    local requested="${1:-}"
    local pwd_candidate=""
    local home_candidate=""

    if [ -n "$requested" ]; then
        pwd_candidate="$(abspath_path "$requested" "$INVOKE_PWD")"
        mkdir -p "$pwd_candidate"
        printf '%s\n' "$pwd_candidate"
        return 0
    fi

    pwd_candidate="$(abspath_path "./collect" "$INVOKE_PWD")"
    if [ -d "$pwd_candidate" ]; then
        printf '%s\n' "$pwd_candidate"
        return 0
    fi

    if [ -n "${HOME:-}" ]; then
        home_candidate="$(abspath_path ".mmwk/collect" "$HOME")"
        if [ -d "$home_candidate" ]; then
            printf '%s\n' "$home_candidate"
            return 0
        fi
    fi

    mkdir -p "$pwd_candidate"
    printf '%s\n' "$pwd_candidate"
}

device_registry_path() {
    printf '%s\n' "$1/device.yml"
}

compact_timestamp_now() {
    if [ -n "${MMWK_TEST_COLLECT_TIMESTAMP:-}" ]; then
        printf '%s\n' "$MMWK_TEST_COLLECT_TIMESTAMP"
    else
        date '+%Y%m%d-%H%M%S'
    fi
}

read_device_registry_json() {
    local working_dir="$1"
    local registry_path=""

    registry_path="$(device_registry_path "$working_dir")"
    "$PYTHON" - "$registry_path" <<'PY'
import json
import os
import sys

path = sys.argv[1]

if not os.path.exists(path):
    print(json.dumps({"devices": {}}))
    raise SystemExit(0)

with open(path, "r", encoding="utf-8") as fp:
    raw = fp.read().strip()

if not raw:
    print(json.dumps({"devices": {}}))
    raise SystemExit(0)

try:
    data = json.loads(raw)
except Exception as exc:
    raise SystemExit(f"invalid device registry JSON: {exc}")

if not isinstance(data, dict):
    raise SystemExit("device registry root must be an object")

devices = data.get("devices")
if devices is None:
    data["devices"] = {}
elif not isinstance(devices, dict):
    raise SystemExit("device registry 'devices' must be an object")

print(json.dumps(data))
PY
}

read_device_record_json() {
    local working_dir="$1"
    local did="$2"
    local registry_path=""

    registry_path="$(device_registry_path "$working_dir")"
    "$PYTHON" - "$registry_path" "$did" <<'PY'
import json
import os
import sys

path = sys.argv[1]
did = sys.argv[2]

if not os.path.exists(path):
    raise SystemExit(f"device registry not found: {path}")

with open(path, "r", encoding="utf-8") as fp:
    raw = fp.read().strip()

if not raw:
    raise SystemExit(f"device registry is empty: {path}")

try:
    data = json.loads(raw)
except Exception as exc:
    raise SystemExit(f"invalid device registry JSON: {exc}")

if not isinstance(data, dict):
    raise SystemExit("device registry root must be an object")

devices = data.get("devices")
if not isinstance(devices, dict):
    raise SystemExit("device registry 'devices' must be an object")

record = devices.get(did)
if not isinstance(record, dict):
    raise SystemExit(f"DID not found in registry: {did}")

print(json.dumps(record))
PY
}

write_device_record() {
    local working_dir="$1"
    local did="$2"
    local mqtt_server="$3"
    local mqtt_port="$4"
    local http_server="$5"
    local http_port="$6"
    local ssid="${7:-}"
    local registry_path=""

    registry_path="$(device_registry_path "$working_dir")"
    "$PYTHON" - "$registry_path" "$did" "$mqtt_server" "$mqtt_port" "$http_server" "$http_port" "$ssid" <<'PY'
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

path, did, mqtt_server, mqtt_port, http_server, http_port, ssid = sys.argv[1:8]
data = {"devices": {}}

if os.path.exists(path):
    with open(path, "r", encoding="utf-8") as fp:
        raw = fp.read().strip()
    if raw:
        try:
            data = json.loads(raw)
        except Exception as exc:
            raise SystemExit(f"invalid device registry JSON: {exc}")

if not isinstance(data, dict):
    raise SystemExit("device registry root must be an object")

devices = data.get("devices")
if devices is None:
    devices = {}
    data["devices"] = devices
elif not isinstance(devices, dict):
    raise SystemExit("device registry 'devices' must be an object")

record = devices.get(did)
if not isinstance(record, dict):
    record = {"did": did}

record["did"] = did
record["mqtt_server"] = mqtt_server
record["mqtt_port"] = int(mqtt_port)
record["mqtt_uri"] = f"mqtt://{mqtt_server}:{int(mqtt_port)}"
record["http_server"] = http_server
record["http_port"] = int(http_port)
record["http_base_url"] = f"http://{http_server}:{int(http_port)}/"
if ssid:
    record["ssid"] = ssid
record["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
devices[did] = record

parent = os.path.dirname(path)
if parent:
    os.makedirs(parent, exist_ok=True)

fd, tmp_path = tempfile.mkstemp(prefix=".device.", suffix=".tmp", dir=parent or None)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=2, sort_keys=True)
        fp.write("\n")
    os.replace(tmp_path, path)
finally:
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)
PY
}

list_device_records() {
    local working_dir="$1"
    local registry_path=""

    registry_path="$(device_registry_path "$working_dir")"
    "$PYTHON" - "$registry_path" <<'PY'
import json
import os
import sys

path = sys.argv[1]

if not os.path.exists(path):
    raise SystemExit(0)

with open(path, "r", encoding="utf-8") as fp:
    raw = fp.read().strip()

if not raw:
    raise SystemExit(0)

try:
    data = json.loads(raw)
except Exception as exc:
    raise SystemExit(f"invalid device registry JSON: {exc}")

devices = data.get("devices", {})
if not isinstance(devices, dict):
    raise SystemExit("device registry 'devices' must be an object")

for did in sorted(devices):
    record = devices.get(did)
    if not isinstance(record, dict):
        continue
    mqtt_server = record.get("mqtt_server", "")
    mqtt_port = record.get("mqtt_port", "")
    http_server = record.get("http_server", "")
    http_port = record.get("http_port", "")
    mqtt_uri = f"mqtt://{mqtt_server}:{mqtt_port}" if mqtt_server and mqtt_port != "" else ""
    http_base_url = f"http://{http_server}:{http_port}/" if http_server and http_port != "" else ""
    print(f"{did}\t{mqtt_uri}\t{http_base_url}")
PY
}

server_env_text() {
    local state_dir="$1"
    local mqtt_port="$2"
    local http_port="$3"
    local host_ip="${4:-}"
    local start_cmd=(bash "$SERVER_SH" start --state-dir "$state_dir" --mqtt-port "$mqtt_port" --http-port "$http_port")

    [ -z "$host_ip" ] || start_cmd+=(--host-ip "$host_ip")
    "${start_cmd[@]}" >/dev/null
    bash "$SERVER_SH" env --state-dir "$state_dir"
}

split_mqtt_uri() {
    local raw_uri="$1"
    local default_port="$2"
    "$PYTHON" - "$raw_uri" "$default_port" <<'PY'
from urllib.parse import urlparse
import sys

raw = sys.argv[1].strip()
default_port = int(sys.argv[2])

if not raw:
    raise SystemExit(1)

if "://" in raw:
    parsed = urlparse(raw)
    host = parsed.hostname or "localhost"
    port = parsed.port or default_port
else:
    host = raw
    port = default_port
    if raw.count(":") == 1:
        maybe_host, maybe_port = raw.rsplit(":", 1)
        if maybe_port.isdigit():
            host = maybe_host
            port = int(maybe_port)

print(host)
print(port)
PY
}

split_http_base_url() {
    local raw_url="$1"
    local default_port="$2"
    "$PYTHON" - "$raw_url" "$default_port" <<'PY'
from urllib.parse import urlparse
import sys

raw = sys.argv[1].strip()
default_port = int(sys.argv[2])

if not raw:
    raise SystemExit(1)

if "://" not in raw:
    raw = f"http://{raw}"

parsed = urlparse(raw)
host = parsed.hostname or "localhost"
port = parsed.port or default_port

print(host)
print(port)
PY
}

mqtt_uri_from_host_port() {
    printf 'mqtt://%s:%s\n' "$1" "$2"
}

http_base_url_from_host_port() {
    printf 'http://%s:%s/\n' "$1" "$2"
}

run_mmwk_cli() {
    bash "$MMWK_CLI" "$@"
}
