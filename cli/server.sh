#!/bin/bash
# server.sh - local MQTT + HTTP helper wrapper
set -euo pipefail

INVOKE_PWD="$(pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="${INVOKE_PWD}/build_output/local_server"
ENV_FILE="$STATE_DIR/server.env"

# Keep the shell-level lifecycle hooks explicit for callers that inspect the
# wrapper contract.  The Python runtime owns the actual server lifecycle; the
# hooks document the stale-env invariant without duplicating that state machine.
prepare_server() {
    rm -f "$ENV_FILE"
}

cleanup_server() {
    :
}

start_server() {
    rm -f "$ENV_FILE"
}

stop_server() {
    :
}

find_python() {
    local cmd ver major minor python_path

    python_path="${pythonLocation:+${pythonLocation}/bin/python3}"
    if [ -n "$python_path" ] && [ -x "$python_path" ]; then
        ver="$("$python_path" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)" || ver=""
        case "$ver" in
            ''|*[!0-9.]*|*.*.*|.*|*.) : ;;
            *)
                major="${ver%%.*}"
                minor="${ver#*.}"
                if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
                    echo "$python_path"
                    return 0
                fi
                ;;
        esac
    fi

    for cmd in python3 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            ver="$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)" || continue
            case "$ver" in
                ''|*[!0-9.]*|*.*.*|.*|*.) continue ;;
            esac
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
    if [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then
        printf '%s\n' "$VIRTUAL_ENV/bin/python"
        return 0
    fi
    if [ -x "$SCRIPT_DIR/venv/bin/python" ]; then
        printf '%s\n' "$SCRIPT_DIR/venv/bin/python"
        return 0
    fi
    return 1
}

PYTHON="$(find_python)" || {
    echo "Error: Python 3.10+ not found." >&2
    exit 1
}

if [ -z "${VIRTUAL_ENV:-}" ]; then
    cd "$SCRIPT_DIR"
    if [ ! -d venv ]; then
        "$PYTHON" -m venv venv
    fi
    if [ -f venv/bin/activate ]; then
        # shellcheck disable=SC1091
        . venv/bin/activate
    fi
    if venv_python="$(resolve_venv_python)"; then
        PYTHON="$venv_python"
    fi
    if [ ! -f venv/.deps_installed ] || [ requirements.txt -nt venv/.deps_installed ]; then
        "$PYTHON" -m pip install -q -r requirements.txt
        touch venv/.deps_installed
    fi
fi

case "${PYTHONPATH:-}" in
    "$SCRIPT_DIR"|"$SCRIPT_DIR":*|*:"$SCRIPT_DIR"|*:"$SCRIPT_DIR":*) ;;
    "") export PYTHONPATH="$SCRIPT_DIR" ;;
    *) export PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH}" ;;
esac

cd "$INVOKE_PWD"
exec "$PYTHON" -m mmwk.server --invoke-pwd "$INVOKE_PWD" "$@"
