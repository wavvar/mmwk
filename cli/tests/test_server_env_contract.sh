#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SERVER_SH="${CLI_ROOT}/server.sh"

if [ ! -x "${SERVER_SH}" ]; then
    echo "FAIL: server.sh not found or not executable at ${SERVER_SH}" >&2
    exit 1
fi

if ! grep -q 'local http_bind_addresses=(0.0.0.0 127.0.0.1)' "${SERVER_SH}"; then
    echo "FAIL: server.sh must try 0.0.0.0 before 127.0.0.1 for detached HTTP startup" >&2
    exit 1
fi

if ! grep -q 'TCP_PROBE_PYTHON=' "${SERVER_SH}" || ! grep -q '"$TCP_PROBE_PYTHON" - "$host" "$port"' "${SERVER_SH}"; then
    echo "FAIL: server.sh TCP probes must use a stable Python executable independent from runtime venv setup" >&2
    exit 1
fi

if ! grep -q 'HTTP_START_TIMEOUT_SEC="${MMWK_HTTP_START_TIMEOUT_SEC:-8}"' "${SERVER_SH}"; then
    echo "FAIL: server.sh default HTTP attempt timeout must leave time for fallback bind addresses" >&2
    exit 1
fi

if [ "$(uname -s)" = "Darwin" ] && [ "${GITHUB_ACTIONS:-}" = "true" ]; then
    echo "SKIP: hosted macOS does not expose detached Python HTTP listeners reliably; live server contract runs on Linux"
    exit 0
fi

if ! command -v mosquitto >/dev/null 2>&1; then
    echo "SKIP: mosquitto not installed"
    exit 0
fi

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "${PYTHON_BIN}" ]; then
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="$(command -v python3)"
    elif command -v python >/dev/null 2>&1; then
        PYTHON_BIN="$(command -v python)"
    else
        echo "SKIP: python not available"
        exit 0
    fi
fi

TMPDIR="$(mktemp -d)"
trap 'rm -rf "${TMPDIR}"' EXIT

mkdir -p "${TMPDIR}/serve_dir"
printf 'ok-server-payload' > "${TMPDIR}/serve_dir/fw.bin"
STATE_DIR="${TMPDIR}/state"

START_LOG="${TMPDIR}/server-start.log"
WAIT_SECONDS=60

print_start_log() {
    echo "--- server start log (${START_LOG}) ---" >&2
    sed -n '1,240p' "${START_LOG}" >&2
}

print_state_logs() {
    local server_log
    local http_log
    local mqtt_log

    server_log="${STATE_DIR}/server.log"
    http_log="${STATE_DIR}/http.log"
    mqtt_log="${STATE_DIR}/mosquitto.log"

    echo "--- server state log (${server_log}) ---" >&2
    sed -n '1,240p' "${server_log}" >&2

    echo "--- server http log (${http_log}) ---" >&2
    sed -n '1,240p' "${http_log}" >&2

    echo "--- server mqtt log (${mqtt_log}) ---" >&2
    sed -n '1,240p' "${mqtt_log}" >&2
}

# Start server in detached mode from a deterministic IP/port pair.
"${SERVER_SH}" start \
    --state-dir "${STATE_DIR}" \
    --serve-dir "${TMPDIR}/serve_dir" \
    --host-ip 127.0.0.1 \
    --mqtt-port 1889 \
    --http-port 8389 \
    >"${START_LOG}" 2>&1 || {
    echo "FAIL: server start command failed" >&2
    print_start_log
    print_state_logs
    exit 1
}

wait_for_ready() {
    local deadline
    local status
    deadline=$(( $(date +%s) + WAIT_SECONDS ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        if status="$(${SERVER_SH} status --state-dir "${STATE_DIR}" 2>/dev/null)"; then
            if echo "$status" | grep -Eq 'MQTT Up[[:space:]]*: yes' && echo "$status" | grep -Eq 'HTTP Up[[:space:]]*: yes'; then
                return 0
            fi
        fi
        sleep 0.5
    done
    return 1
}

if ! wait_for_ready; then
    echo "FAIL: server did not become ready" >&2
    print_start_log
    print_state_logs
    exit 1
fi

ENV_CONTENT="$(${SERVER_SH} env --state-dir "${STATE_DIR}")"

required_env=(
    "MMWK_SERVER_HOST_IP=127.0.0.1"
    "MMWK_SERVER_MQTT_URI="
    "MMWK_SERVER_HTTP_BASE_URL="
    "MMWK_SERVER_STATE_DIR=${STATE_DIR}"
    "MMWK_SERVER_SERVE_DIR=${TMPDIR}/serve_dir"
    "MMWK_SERVER_UPLOAD_DIR=${STATE_DIR}/uploads"
)

for key in "${required_env[@]}"; do
    if ! printf '%s\n' "$ENV_CONTENT" | grep -q "^${key}"; then
        echo "FAIL: missing env key/value prefix ${key}" >&2
        exit 1
    fi
done

MQTT_URI="$(printf '%s\n' "$ENV_CONTENT" | awk -F= '$1 == "MMWK_SERVER_MQTT_URI" {print $2}')"
HTTP_BASE="$(printf '%s\n' "$ENV_CONTENT" | awk -F= '$1 == "MMWK_SERVER_HTTP_BASE_URL" {print $2}')"

if [ -z "$MQTT_URI" ] || [ -z "$HTTP_BASE" ]; then
    echo "FAIL: env output missing MQTT or HTTP URL" >&2
    exit 1
fi

${PYTHON_BIN} - "$HTTP_BASE" <<'PY'
import sys
import urllib.request

base = sys.argv[1].rstrip('/') + '/'

with urllib.request.urlopen(f"{base}healthz", timeout=8) as response:
    body = response.read().decode('utf-8')
    assert body == '{"status":"ok"}', body

with urllib.request.urlopen(f"{base}fw.bin", timeout=8) as response:
    body = response.read()
    assert body == b"ok-server-payload", body

print("HTTP health and payload checks passed")
PY

"${SERVER_SH}" stop --state-dir "${STATE_DIR}"

STOP_TIMEOUT=$(( $(date +%s) + 8 ))
while [ "$(date +%s)" -lt "$STOP_TIMEOUT" ]; do
    status="$(${SERVER_SH} status --state-dir "${STATE_DIR}" 2>/dev/null || true)"
    if ! (echo "$status" | grep -Eq 'MQTT Up\s*: yes' || echo "$status" | grep -Eq 'HTTP Up\s*: yes'); then
        echo "server.sh public env contract test OK"
        exit 0
    fi
    sleep 0.5
done

echo "FAIL: server still reported running after stop" >&2
exit 1
