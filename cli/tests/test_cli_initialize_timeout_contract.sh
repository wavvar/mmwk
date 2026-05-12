#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

python_bin="${CLI_ROOT}/venv/bin/python"
if [ ! -x "$python_bin" ]; then
    python_bin="python3"
fi

"$python_bin" - "$CLI_ROOT" <<'PY'
import json
import sys

sys.path.insert(0, sys.argv[1])

from mmwk.control_cli_client import ControlCliClient


class SlowProxyLikeTransport:
    def __init__(self):
        self._msg_id = 0
        self.sent = []
        self.wait_timeouts = []

    def next_msg_id(self):
        self._msg_id += 1
        return self._msg_id

    def send_json(self, request):
        self.sent.append(request)

    def wait_for_response(self, msg_id, timeout):
        self.wait_timeouts.append(timeout)
        return {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "name": "mmwk_sensor_bridge",
                                "version": "1.4.0",
                            }
                        ),
                    }
                ]
            }
        }


transport = SlowProxyLikeTransport()
client = ControlCliClient(transport)
client.initialize(timeout=15)

if len(transport.sent) != 1:
    raise SystemExit(f"initialize should send one node info request when it receives a response, got {len(transport.sent)}")

first_timeout = transport.wait_timeouts[0]
if first_timeout < 5.0:
    raise SystemExit(f"initialize must not force a 2s node-info timeout under slow UART proxy paths, got {first_timeout}")

print("CLI initialize timeout contract OK")
PY
