"""Canonical CLI JSON control client."""

import copy
import json
import time

from mmwk_cli._logging import logger
from mmwk_cli.transport import RadarTransport


def _tool(name: str, description: str, properties: dict | None = None, required: list | None = None) -> dict:
    schema = {
        "type": "object",
        "properties": properties or {},
    }
    if required:
        schema["required"] = list(required)
    return {
        "name": name,
        "description": description,
        "inputSchema": schema,
    }


def _action_property(actions: list[str], description: str) -> dict:
    return {
        "type": "string",
        "enum": list(actions),
        "description": description,
    }


def _build_device_tool(profile: str) -> dict:
    actions = ["startup", "agent", "heartbeat", "hi", "ota"]
    if profile == "hub":
        actions.append("inquiry")
    else:
        actions.append("reboot")
    return _tool(
        "device",
        "Device-level configuration: startup mode, agent flags, heartbeat, hi, and ESP OTA.",
        {
            "action": _action_property(actions, "Operation"),
            "mode": {"type": "string", "enum": ["auto", "host"], "description": "Startup mode"},
            "mqtt_en": {"type": "number", "description": "MQTT agent enable (0/1)"},
            "uart_en": {"type": "number", "description": "UART agent enable (0/1)"},
            "raw_auto": {"type": "number", "description": "Auto-enable raw stream on boot (0/1)"},
            "single_uart_split": {"type": "number", "description": "Split single-UART runtime data after sensorStart (0/1)"},
            "disconnect_reboot_ms": {"type": "number", "description": "Reboot threshold when MQTT stays disconnected"},
            "interval": {"type": "number", "description": "Heartbeat interval"},
            "fields": {"type": "array", "items": {"type": "string"}, "description": "Heartbeat fields"},
            "url": {"type": "string", "description": "ESP OTA firmware URL (.bin)"},
        },
        ["action"],
    )


def _canonical_tools(profile: str) -> list[dict]:
    tools = [
        _tool(
            "radar",
            "Radar service control: OTA update, UART flash, status query/set, raw data config, and debug diagnostics.",
            {
                "action": _action_property(
                    ["ota", "flash", "status", "switch", "cfg", "raw", "debug", "version", "calib"],
                    "Operation to perform",
                ),
                "base": {"type": "string", "description": "OTA base URL"},
                "firmware": {"type": "string", "description": "Firmware filename"},
                "config": {"type": "string", "description": "Config filename"},
                "welcome": {"type": "boolean", "description": "Whether the target firmware emits welcome/startup text"},
                "verify": {"type": "boolean", "description": "Whether to verify version substring inside welcome text"},
                "version": {"type": "string", "description": "Version substring / target version"},
                "fw_topic": {"type": "string", "description": "Firmware topic override (HUB mode)"},
                "cert_url": {"type": "string", "description": "Certificate URL for OTA validation (HUB mode)"},
                "force": {"type": "boolean", "description": "Force update"},
                "prog_intvl": {"type": "number", "description": "Progress report interval"},
                "firmware_size": {"type": "number", "description": "Flash firmware size"},
                "config_size": {"type": "number", "description": "Flash config size"},
                "chunk_size": {"type": "number", "description": "Flash chunk size"},
                "reboot_delay": {"type": "number", "description": "ESP reboot delay after flash success (BRIDGE mode)"},
                "set": {"type": "string", "enum": ["start", "stop"], "description": "Start/stop radar"},
                "index": {"type": "number", "description": "Firmware index for action=switch"},
                "persist": {"type": "boolean", "description": "Persist target as default firmware for action=switch"},
                "gen": {"type": "boolean", "description": "Return generated config for action=cfg"},
                "mode": {"type": "string", "enum": ["auto", "host"], "description": "Start mode"},
                "enabled": {"type": "boolean", "description": "Data output enable"},
                "uri": {"type": "string", "description": "Raw MQTT broker URI"},
                "uart_enabled": {"type": "boolean", "description": "Mirror raw frames to UART notifications"},
                "op": {"type": "string", "enum": ["set", "get", "clear", "snapshot", "reset"], "description": "Debug/calibration sub-operation"},
                "calibration": {"type": "string", "description": "Calibration line payload for action=calib op=set"},
                "packets": {"type": "boolean", "description": "Enable packet counters"},
                "frames": {"type": "boolean", "description": "Enable frame counters"},
            },
            ["action"],
        ),
        _tool(
            "record",
            "SD card/flash recording control: start, stop, or trigger recording.",
            {
                "action": _action_property(["start", "stop", "trigger"], "Operation"),
                "uri": {"type": "string", "description": "Recording URI"},
                "event": {"type": "string", "description": "Trigger event name"},
                "duration_sec": {"type": "number", "description": "Trigger duration in seconds"},
            },
            ["action"],
        ),
        _tool(
            "uart_data",
            "UART firmware chunk transfer control: stream chunks, complete, or cancel.",
            {
                "action": _action_property(["complete", "cancel"], "Control action"),
                "file": {"type": "string", "description": "File type, usually firmware or config"},
                "seq": {"type": "number", "description": "Chunk sequence number"},
                "data": {"type": "string", "description": "Base64 chunk payload"},
            },
        ),
        _tool(
            "fw",
            "Firmware catalog management (advanced).",
            {
                "action": _action_property(["info", "list", "set", "del", "download"], "Operation"),
                "index": {"type": "number", "description": "Firmware index"},
                "source": {"type": "string", "description": "Firmware source URL/path"},
                "name": {"type": "string", "description": "Firmware name"},
                "version": {"type": "string", "description": "Firmware version"},
                "size": {"type": "number", "description": "Firmware size"},
            },
            ["action"],
        ),
    ]

    if profile == "hub":
        tools.extend(
            [
                _tool(
                    "hub",
                    "Hub-specific grouped entity orchestration.",
                    {
                        "action": _action_property(["show", "set", "apply"], "Hub operation"),
                        "config": {"type": "object", "description": "Hub config payload"},
                        "patch": {"type": "object", "description": "Hub config patch"},
                    },
                    ["action"],
                ),
                _tool(
                    "scene",
                    "Scene orchestration for grouped runtime presets.",
                    {
                        "action": _action_property(["show", "set", "apply", "wait_ready"], "Scene operation"),
                        "config": {"type": "object", "description": "Scene config payload"},
                        "patch": {"type": "object", "description": "Scene config patch"},
                    },
                    ["action"],
                ),
                _tool(
                    "policy",
                    "Policy inspection and update helpers.",
                    {
                        "action": _action_property(["show", "set", "explain"], "Policy operation"),
                        "config": {"type": "object", "description": "Policy config payload"},
                        "profile": {"type": "string", "description": "Policy profile"},
                        "summary_interval_ms": {"type": "number", "description": "Summary interval"},
                        "report_interval_ms": {"type": "number", "description": "Report interval"},
                    },
                    ["action"],
                ),
            ]
        )

    tools.extend(
        [
            _build_device_tool(profile),
            _tool(
                "network",
                "Network configuration: WiFi credentials, provisioning AP, NTP time sync, MQTT settings, runtime status.",
                {
                    "action": _action_property(["config", "prov", "ntp", "mqtt", "status"], "Operation"),
                    "ssid": {"type": "string", "description": "WiFi SSID"},
                    "password": {"type": "string", "description": "WiFi password"},
                    "enable": {"type": "number", "description": "Provisioning enable (0/1)"},
                    "server": {"type": "string", "description": "NTP server"},
                    "tz_offset": {"type": "number", "description": "Timezone offset in seconds"},
                    "interval": {"type": "number", "description": "NTP update interval"},
                    "mqtt_uri": {"type": "string", "description": "MQTT broker URI"},
                    "mqtt_user": {"type": "string", "description": "MQTT username"},
                    "mqtt_pass": {"type": "string", "description": "MQTT password"},
                },
                ["action"],
            ),
            _tool("catalog", "Return the current capability catalog exposed by this device."),
            _tool(
                "entity",
                "Read capability entity descriptors and runtime state.",
                {
                    "action": _action_property(["describe", "read_state", "read_config", "write_config"], "Capability operation"),
                    "entity": {"type": "string", "description": "Capability entity id"},
                    "config": {"type": "object", "description": "Config patch payload"},
                    "patch": {"type": "object", "description": "Alias of config for write_config"},
                },
                ["action", "entity"],
            ),
            _tool(
                "adapter",
                "Inspect device-side protocol adapter projections.",
                {
                    "action": _action_property(["list", "status", "manifest"], "Adapter operation"),
                    "protocol": {"type": "string", "description": "Target adapter protocol"},
                },
            ),
            _tool(
                "raw_capture",
                "Capability-first raw capture recording and config control.",
                {
                    "action": _action_property(
                        ["status", "config_get", "config_set", "record_start", "record_stop", "record_trigger"],
                        "Raw capture operation",
                    ),
                    "config": {"type": "object", "description": "raw_capture.v1.config patch payload for config_set"},
                    "patch": {"type": "object", "description": "Alias of config for config_set"},
                    "uri": {"type": "string", "description": "Upload target URI for record_start"},
                    "event": {"type": "string", "description": "Trigger event name for record_trigger"},
                    "duration_sec": {"type": "number", "description": "Trigger duration in seconds for record_trigger"},
                },
                ["action"],
            ),
            _tool("help", "Return command overview and a documentation URL."),
        ]
    )
    return tools


class ControlCliClient:
    """Canonical CLI JSON control client over UART/MQTT transport."""

    def __init__(self, transport: RadarTransport):
        self.transport = transport
        self._initialized = False
        self._server_name = ""

    def initialize(self, timeout: float = 10.0) -> dict:
        """Wait until canonical CLI control is responsive using device/hi."""
        deadline = time.time() + timeout
        attempt = 0
        last_error = None

        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                break

            attempt += 1
            try:
                result = self.call_tool("device", {"action": "hi"}, timeout=min(2.0, remaining))
                text = self.extract_text(result)
                payload = json.loads(text)
                if not isinstance(payload, dict):
                    payload = {}
                self._initialized = True
                self._server_name = str(payload.get("name", "") or "")
                logger.info(
                    "Connected to %s v%s via CLI",
                    payload.get("name", "?"),
                    payload.get("version", "?"),
                )
                return {
                    "protocolVersion": "control.v1",
                    "serverInfo": {
                        "name": payload.get("name", "?"),
                        "version": payload.get("version", "?"),
                    },
                }
            except Exception as exc:
                last_error = exc
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                sleep_sec = min(0.5, remaining)
                logger.debug(
                    "CLI initialize attempt %d failed (%s); retrying in %.1fs",
                    attempt,
                    exc,
                    sleep_sec,
                )
                time.sleep(sleep_sec)

        raise RuntimeError(f"CLI initialize failed: {last_error}")

    def tools_list(self, timeout: float = 10.0) -> list:
        """Return canonical tool metadata, using help as a discovery/fallback hint."""
        result = self.call_tool("help", {}, timeout=timeout)
        text = self.extract_text(result)
        try:
            payload = json.loads(text)
        except Exception:
            payload = {}

        commands = payload.get("commands", "")
        hinted_names = []
        if isinstance(commands, str):
            hinted_names = [item.strip() for item in commands.split(",") if item.strip()]

        profile = "hub" if (
            self._server_name.endswith("_hub") or
            self._server_name.endswith("hub") or
            "hub" in hinted_names
        ) else "bridge"

        canonical_tools = _canonical_tools(profile)
        canonical_by_name = {tool["name"]: tool for tool in canonical_tools}
        ordered_names = [tool["name"] for tool in canonical_tools]

        for name in hinted_names:
            if name not in ordered_names:
                ordered_names.append(name)

        tools = []
        for name in ordered_names:
            tool = canonical_by_name.get(name)
            if tool is not None:
                tools.append(copy.deepcopy(tool))
            else:
                tools.append({"name": name, "description": ""})
        return tools

    def call_tool(self, name: str, arguments: dict, timeout: float = 30.0) -> dict:
        """Call a canonical CLI service and wait for the normalized response."""
        msg_id = self.transport.next_msg_id()
        arguments = dict(arguments or {})
        action = arguments.pop("action", None)
        request = {
            "type": "req",
            "seq": msg_id,
            "service": name,
            "args": arguments,
        }
        if action is not None:
            request["action"] = action

        self.transport.send_json(request)
        resp = self.transport.wait_for_response(msg_id, timeout=timeout)
        if not resp:
            raise TimeoutError(f"Timeout waiting for tool '{name}' response")
        if "error" in resp:
            err = resp["error"]
            raise RuntimeError(f"Tool '{name}' error [{err.get('code')}]: {err.get('message')}")
        return resp.get("result", {})

    def extract_text(self, result: dict) -> str:
        """Extract text from the normalized content envelope."""
        content = result.get("content", [])
        if content and isinstance(content, list):
            return content[0].get("text", "")
        return json.dumps(result)
