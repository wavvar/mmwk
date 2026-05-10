#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TRANSPORT_PY="${CLI_ROOT}/mmwk/transport.py"
CLI_PY="${CLI_ROOT}/mmwk/cli.py"
PROXY_PY="${CLI_ROOT}/mmwk/uart_proxy_server.py"

python_bin="${CLI_ROOT}/venv/bin/python"
if [ ! -x "$python_bin" ]; then
    python_bin="python3"
fi

"$python_bin" -m py_compile "$TRANSPORT_PY" "$CLI_PY" "$PROXY_PY"

"$python_bin" - "$TRANSPORT_PY" "$CLI_PY" "$PROXY_PY" <<'PY'
from pathlib import Path
import sys

transport = Path(sys.argv[1]).read_text(encoding="utf-8")
cli = Path(sys.argv[2]).read_text(encoding="utf-8")
proxy = Path(sys.argv[3]).read_text(encoding="utf-8")

required_transport = [
    "def _ensure_uart_proxy",
    "def _shutdown_uart_proxy",
    "MMWK_CLI_UART_PROXY_MODE",
    '"auto"',
    '"off"',
    "_shutdown_uart_proxy(port, baudrate)",
    "self._proxy_data_endpoint, self._proxy_ctrl_endpoint = _ensure_uart_proxy",
    "uart_proxy=getattr(args, 'uart_proxy', None)",
]
for needle in required_transport:
    if needle not in transport:
        raise SystemExit(f"transport.py missing UART proxy contract: {needle}")

if "--uart-proxy" not in cli or 'choices=["auto", "off"]' not in cli:
    raise SystemExit("cli.py must expose --uart-proxy auto|off")

required_proxy = [
    "class SerialProxy",
    "def reset_device",
    "def pump_serial_output",
    'command == "shutdown"',
    'MMWK_CLI_UART_PROXY_DATA=tcp://',
    'MMWK_CLI_UART_PROXY_CTRL=tcp://',
]
for needle in required_proxy:
    if needle not in proxy:
        raise SystemExit(f"uart_proxy_server.py missing contract: {needle}")
PY

"$python_bin" - "$CLI_ROOT" <<PY
import threading
import sys


sys.path.insert(0, sys.argv[1])
from mmwk import transport as transport

Transport = transport.UartTransport

events = []
transport_obj = Transport.__new__(Transport)
transport_obj.lock = threading.Lock()
transport_obj.log_history = []

def capture(payload):
    events.append(payload)


transport_obj.ingest_json = capture

transport_obj._process_line('{"type":"res","seq":1,"ok":true}')
transport_obj._process_line('W (123) sensor: {"type":"res","seq":2,"ok":true}')
transport_obj._process_line('W (124) "type":"res","seq":3,"ok":true}')

if len(events) != 3:
    raise SystemExit(f"Transport parser regression failed, parsed={len(events)} entries")
expected = [1, 2, 3]
actual = [msg.get("seq") for msg in events]
if actual != expected:
    raise SystemExit(f"Transport parser produced unexpected seq order: {actual}")

print("transport parser regression OK")
PY

echo "uart proxy transport contract OK"
