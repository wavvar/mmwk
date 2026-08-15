"""Canonical CLI JSON control client."""

import copy
import json
import time

from mmwk._logging import logger
from mmwk.transport import RadarTransport


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


def _build_node_tool(profile: str) -> dict:
    actions = ["agent", "heartbeat", "info", "ota", "factory_reset"]
    actions.append("claim")
    if profile == "hub":
        actions.append("inquiry")
    else:
        actions.append("reboot")
    return _tool(
        "node",
        "Node-level configuration: agent flags, WDR local-control startup policy, "
        "heartbeat, identity probe, and ESP OTA.",
        {
            "action": _action_property(actions, "Operation"),
            "mqtt": {"type": "number", "description": "MQTT agent enable (0/1)"},
            "uart": {"type": "number", "description": "UART agent enable (0/1)"},
            "raw_auto": {"type": "number", "description": "Auto-enable raw stream on boot (0/1)"},
            "uart_split": {"type": "number", "description": "Split single-UART runtime data after sensorStart (0/1)"},
            "led": {"type": "number", "description": "LED error display enable (0/1)"},
            "reboot_ms": {"type": "number", "description": "Reboot threshold when MQTT stays disconnected"},
            "usb_ms": {
                "type": "integer",
                "minimum": 0,
                "maximum": 60000,
                "description": (
                    "WDR UART-to-USB CDC idle window in milliseconds "
                    "(0 disables auto-switch)"
                ),
            },
            "interval": {"type": "number", "description": "Heartbeat interval"},
            "fields": {"type": "array", "items": {"type": "string"}, "description": "Heartbeat fields"},
            "prod": {"type": "string", "description": "Product route segment for action=claim"},
            "oid": {"type": "string", "description": "Organization route segment for action=claim"},
            "cid": {"type": "string", "description": "Claimed device route segment for action=claim"},
            "endpoint": {"type": "string", "description": "Claim endpoint override"},
            "token": {"type": "string", "description": "One-time claim token"},
            "url": {"type": "string", "description": "ESP OTA firmware URL (.bin)"},
        },
        ["action"],
    )


def _build_proto_tool() -> dict:
    return _tool(
        "proto",
        "Inspect node public protocol directory.",
        {
            "action": _action_property(["list", "status", "manifest"], "Protocol inspection operation"),
            "name": {"type": "string", "description": "Target public protocol directory entry"},
        },
    )


def _build_radar_tool() -> dict:
    return _tool(
        "radar",
        "Radar runtime control: query status and start or stop the service.",
        {
            "action": _action_property(["status", "start", "stop"], "Runtime operation"),
            "mode": {
                "type": "string",
                "enum": ["auto", "host"],
                "description": "Persisted start mode for action=start",
            },
        },
        ["action"],
    )


def _build_radar_config_tool() -> dict:
    return _tool(
        "radar.config",
        "Read or apply the radar runtime configuration.",
        {
            "action": _action_property(["read", "apply"], "Config operation"),
            "gen": {"type": "boolean", "description": "Return generated config for action=read"},
            "enabled": {"type": "boolean", "description": "Data output enable"},
            "uri": {"type": "string", "description": "Raw MQTT broker URI"},
            "uart": {"type": "boolean", "description": "Mirror raw frames to UART notifications"},
        },
        ["action"],
    )


def _build_radar_fw_tool(profile: str) -> dict:
    actions = ["version", "flash", "ota", "list", "set", "switch", "del", "download"]
    if profile == "bridge":
        actions.append("storage")
    properties = {
        "action": _action_property(actions, "Firmware operation"),
        "index": {"type": "number", "description": "Firmware index"},
        "persist": {"type": "boolean", "description": "Persist target as default firmware for action=switch"},
        "source": {"type": "string", "description": "Firmware source URL/path"},
        "name": {"type": "string", "description": "Firmware name"},
        "version": {"type": "string", "description": "Firmware version"},
        "size": {"type": "number", "description": "Firmware size"},
    }
    if profile == "bridge":
        properties["op"] = {
            "type": "string",
            "enum": ["status", "cleanup"],
            "description": "Storage operation for action=storage",
        }
        properties["required"] = {
            "type": "number",
            "description": "Required bytes including firmware, config, and safety margin",
        }

    return _tool(
        "radar.fw",
        "Radar firmware catalog management and package acquisition.",
        properties,
        ["action"],
    )


def _build_radar_raw_tool() -> dict:
    return _tool(
        "radar.raw",
        "Inspect raw recorder state, update raw config, and trigger raw recordings.",
        {
            "action": _action_property(
                ["status", "config_get", "config_set", "start", "stop", "trigger"],
                "Raw operation",
            ),
            "config": {"type": "object", "description": "radar.raw config patch payload for config_set"},
            "patch": {"type": "object", "description": "Alias of config for config_set"},
            "uri": {"type": "string", "description": "Upload target URI for start"},
            "event": {"type": "string", "description": "Trigger event name for trigger"},
            "duration_s": {"type": "number", "description": "Trigger duration in seconds for trigger"},
        },
        ["action"],
    )


def _build_radar_diag_tool() -> dict:
    return _tool(
        "radar.diag",
        "Radar diagnostics and calibration control.",
        {
            "action": _action_property(["debug", "calib"], "Diagnostic operation"),
            "op": {
                "type": "string",
                "enum": ["set", "get", "clear", "snapshot", "reset"],
                "description": "Debug/calibration sub-operation",
            },
            "calibration": {"type": "string", "description": "Calibration line payload for action=calib op=set"},
            "packets": {"type": "boolean", "description": "Enable packet counters"},
            "frames": {"type": "boolean", "description": "Enable frame counters"},
        },
        ["action"],
    )


def _build_stream_tool() -> dict:
    return _tool(
        "stream",
        "Host-to-device binary stream control for MQTT data-plane transfers.",
        {
            "action": _action_property(["open", "status", "abort", "close"], "Stream operation"),
            "direction": {
                "type": "string",
                "enum": ["host_to_device"],
                "description": "Stream direction for action=open",
            },
            "purpose": {
                "type": "string",
                "enum": ["ota"],
                "description": "Stream purpose for action=open",
            },
            "target": {
                "type": "string",
                "enum": ["esp", "radar"],
                "description": "OTA target for action=open",
            },
            "object": {
                "type": "string",
                "enum": ["firmware", "config", "bundle"],
                "description": "Transferred object for action=open",
            },
            "size": {"type": "number", "description": "Total stream size in bytes for action=open"},
            "sha256": {"type": "string", "description": "SHA-256 hex digest for action=open"},
            "content_type": {"type": "string", "description": "Content type for action=open"},
            "metadata": {"type": "object", "description": "Optional metadata for action=open"},
            "chunk_size": {"type": "number", "description": "Requested frame payload size"},
            "window": {"type": "number", "description": "Requested ACK window"},
            "expires_ms": {"type": "number", "description": "Requested stream lease duration"},
            "reason": {"type": "string", "description": "Abort reason"},
        },
        ["action"],
    )


def _canonical_tools(profile: str) -> list[dict]:
    tools = [
        _build_radar_tool(),
        _build_radar_config_tool(),
        _build_radar_fw_tool(profile),
        _build_radar_raw_tool(),
        _build_radar_diag_tool(),
    ]

    if profile == "bridge":
        tools.append(_build_stream_tool())

    if profile == "hub":
        tools.extend(
            [
                _tool(
                    "scene",
                    "Scene orchestration for grouped runtime presets.",
                    {
                        "action": _action_property(["read", "set", "apply", "wait"], "Scene operation"),
                        "config": {"type": "object", "description": "Scene config payload"},
                        "patch": {"type": "object", "description": "Scene config patch"},
                    },
                    ["action"],
                ),
            ]
        )

    tools.extend(
        [
            _build_node_tool(profile),
            _build_proto_tool(),
            _tool(
                "network",
                "Network configuration: WiFi and 4G settings, preferred network, provisioning AP, NTP time sync, MQTT settings, runtime status.",
                {
                    "action": _action_property(["wifi", "4g", "priority", "prov", "ntp", "mqtt", "status", "diag"], "Operation"),
                    "ssid": {"type": "string", "description": "WiFi SSID"},
                    "pass": {"type": "string", "description": "WiFi, 4G, or MQTT password"},
                    "apn": {"type": "string", "description": "4G APN"},
                    "pref": {"type": "string", "enum": ["wifi", "4g"], "description": "Preferred network"},
                    "enable": {"type": "number", "description": "Provisioning enable (0/1)"},
                    "server": {"type": "string", "description": "NTP server"},
                    "tz_offset": {"type": "number", "description": "Timezone offset in seconds"},
                    "interval": {"type": "number", "description": "NTP update interval"},
                    "uri": {"type": "string", "description": "MQTT broker URI"},
                    "user": {"type": "string", "description": "MQTT username"},
                },
                ["action"],
            ),
            _tool(
                "endpoint",
                "Read Matter-oriented endpoint descriptors and runtime state.",
                {
                    "action": _action_property(["list", "describe", "read", "config_get", "config_set"], "Endpoint operation"),
                    "id": {"type": "string", "description": "Endpoint id"},
                    "config": {"type": "object", "description": "Config patch payload"},
                    "patch": {"type": "object", "description": "Alias of config for config_set"},
                },
                ["action"],
            ),
        ]
    )
    return tools


def _compat_content_result(payload: dict) -> dict:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload),
            }
        ]
    }


def _scene_payload_to_legacy_hub(payload: dict) -> dict:
    if not isinstance(payload, dict):
        payload = {}

    config = payload.get("config")
    if not isinstance(config, dict):
        config = payload

    pose = config.get("sensor_pose")
    room = config.get("room_boundary")
    scene_profile = config.get("scene_profile")

    legacy = {
        "sensor": "hub",
        "pos": pose if isinstance(pose, dict) else {},
        "room": room if isinstance(room, dict) else {},
        "zones": config.get("zones") if isinstance(config.get("zones"), list) else [],
        "gates": config.get("gates") if isinstance(config.get("gates"), list) else [],
        "app": scene_profile.get("app") if isinstance(scene_profile, dict) else None,
        "mode": scene_profile.get("mode") if isinstance(scene_profile, dict) else None,
    }

    if "calibration_ref" in config:
        legacy["calibration"] = config.get("calibration_ref")

    return legacy


def _legacy_hub_to_scene_config(arguments: dict) -> dict:
    config = {}
    pos = arguments.get("pos")
    room = arguments.get("room")
    zones = arguments.get("zones")
    gates = arguments.get("gates")

    if isinstance(pos, dict):
        config["sensor_pose"] = dict(pos)
    if isinstance(room, dict):
        config["room_boundary"] = dict(room)
    if isinstance(zones, list):
        config["zones"] = list(zones)
    if isinstance(gates, list):
        config["gates"] = list(gates)
    if "app" in arguments or "mode" in arguments:
        config["scene_profile"] = {
            "app": arguments.get("app"),
            "mode": arguments.get("mode"),
        }
    if "calibration" in arguments:
        config["calibration_ref"] = arguments.get("calibration")

    return config


def _route_canonical_tool_call(name: str, arguments: dict) -> tuple[str, dict]:
    return name, dict(arguments or {})


class ControlCliClient:
    """Canonical CLI JSON control client over UART/MQTT transport."""

    def __init__(
        self,
        transport: RadarTransport,
        request_key: str = None,
        request_retries: int = 1,
        request_retry_delay: float = 1.0,
    ):
        self.transport = transport
        self.request_key = request_key or ""
        self.request_retries = max(1, int(request_retries))
        self.request_retry_delay = max(0.0, float(request_retry_delay))
        self._initialized = False
        self._server_name = ""
        self._compat_interval = {
            "sensor": "interval",
            "tracker_ms": 500,
            "vs_ms": 3000,
            "presence_ms": 1000,
        }
        self._compat_stay = {
            "sensor": "stay",
            "threshold_sec": 0,
        }
        self._compat_policy = {
            "measurement_profile": "default",
            "summary_interval_ms": self._compat_interval["vs_ms"],
            "report_interval_ms": self._compat_interval["presence_ms"],
            "tracker_ms": self._compat_interval["tracker_ms"],
            "quality_threshold_default": 0,
            "raw_record_enabled_default": False,
            "raw_record_max_duration_sec": 0,
        }

    def initialize(self, timeout: float = 10.0) -> dict:
        """Wait until canonical CLI control is responsive using node/info."""
        deadline = time.time() + timeout
        attempt = 0
        last_error = None

        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                break

            attempt += 1
            try:
                result = self.call_tool("node", {"action": "info"}, timeout=max(0.1, remaining))
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
                    "protocolVersion": "control.v1.1",
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

        return [copy.deepcopy(tool) for tool in _canonical_tools(profile)]

    def _call_transport_tool(self, name: str, arguments: dict, timeout: float) -> dict:
        last_error = None

        for attempt in range(1, self.request_retries + 1):
            msg_id = self.transport.next_msg_id()
            call_arguments = dict(arguments or {})
            action = call_arguments.pop("action", None)
            request = {
                "type": "req",
                "seq": msg_id,
                "service": name,
                "args": call_arguments,
            }
            if action is not None:
                request["action"] = action
            if self.request_key:
                request["key"] = self.request_key

            try:
                self.transport.send_json(request)
                resp = self.transport.wait_for_response(msg_id, timeout=timeout)
            except Exception as exc:
                last_error = exc
            else:
                if resp:
                    if "error" in resp:
                        err = resp["error"]
                        raise RuntimeError(f"Tool '{name}' error [{err.get('code')}]: {err.get('message')}")
                    return resp.get("result", {})
                last_error = TimeoutError(f"Timeout waiting for tool '{name}' response")

            if attempt < self.request_retries:
                logger.warning(
                    "Tool '%s' request attempt %d/%d failed: %s",
                    name,
                    attempt,
                    self.request_retries,
                    last_error,
                )
                time.sleep(self.request_retry_delay)

        raise last_error

    def _compat_hub_call(self, arguments: dict, timeout: float) -> dict:
        sensor = arguments.get("sensor")
        action = arguments.get("action")

        if sensor == "hub":
            if action in (None, "set"):
                scene_result = self._call_transport_tool(
                    "scene",
                    {"action": "set", "config": _legacy_hub_to_scene_config(arguments)},
                    timeout,
                )
                payload = json.loads(self.extract_text(scene_result))
                return _compat_content_result(_scene_payload_to_legacy_hub(payload))

            if action in ("get", "show"):
                scene_result = self._call_transport_tool("scene", {"action": "read"}, timeout)
                payload = json.loads(self.extract_text(scene_result))
                return _compat_content_result(_scene_payload_to_legacy_hub(payload))

            if action == "apply":
                self._call_transport_tool("scene", {"action": "apply"}, timeout)
                return _compat_content_result({})

            raise RuntimeError(f"Tool 'hub' error [-32602]: Unsupported hub action '{action}'")

        if sensor == "interval":
            if action not in (None, "get"):
                raise RuntimeError(f"Tool 'hub' error [-32602]: Unsupported interval action '{action}'")
            if action != "get":
                for key in ("tracker_ms", "vs_ms", "presence_ms"):
                    if key in arguments:
                        self._compat_interval[key] = arguments.get(key)
            return _compat_content_result(dict(self._compat_interval))

        if sensor == "stay":
            if action not in (None, "get"):
                raise RuntimeError(f"Tool 'hub' error [-32602]: Unsupported stay action '{action}'")
            if action != "get" and "threshold_sec" in arguments:
                self._compat_stay["threshold_sec"] = arguments.get("threshold_sec")
            return _compat_content_result(dict(self._compat_stay))

        raise RuntimeError(f"Tool 'hub' error [-32601]: Unknown tool")

    def _compat_policy_call(self, arguments: dict) -> dict:
        action = arguments.get("action")

        if action == "set":
            profile = arguments.get("profile")
            if profile:
                self._compat_policy["measurement_profile"] = profile

            if "summary_interval_ms" in arguments:
                self._compat_policy["summary_interval_ms"] = arguments.get("summary_interval_ms")
                self._compat_interval["vs_ms"] = arguments.get("summary_interval_ms")
            if "report_interval_ms" in arguments:
                self._compat_policy["report_interval_ms"] = arguments.get("report_interval_ms")
                self._compat_interval["presence_ms"] = arguments.get("report_interval_ms")
            if "tracker_ms" in arguments:
                self._compat_policy["tracker_ms"] = arguments.get("tracker_ms")
                self._compat_interval["tracker_ms"] = arguments.get("tracker_ms")
            for key in (
                "quality_threshold_default",
                "raw_record_enabled_default",
                "raw_record_max_duration_sec",
            ):
                if key in arguments:
                    self._compat_policy[key] = arguments.get(key)

            return _compat_content_result(
                {
                    "schema": "policy.v1.config",
                    "id": "mgmt.policy",
                    "config": dict(self._compat_policy),
                }
            )

        if action == "explain":
            return _compat_content_result(
                {
                    "schema": "policy.v1.explain",
                    "id": "mgmt.policy",
                    "config": dict(self._compat_policy),
                    "state": {
                        "effective_summary_interval_ms": self._compat_interval["vs_ms"],
                        "effective_report_interval_ms": self._compat_interval["presence_ms"],
                        "effective_tracker_ms": self._compat_interval["tracker_ms"],
                    },
                }
            )

        raise RuntimeError(f"Tool 'policy' error [-32602]: Unsupported policy action '{action}'")

    def call_tool(self, name: str, arguments: dict, timeout: float = 30.0) -> dict:
        """Call a canonical CLI service and wait for the normalized response."""
        arguments = dict(arguments or {})

        if name == "hub":
            return self._compat_hub_call(arguments, timeout)
        if name == "policy":
            return self._compat_policy_call(arguments)

        routed_name, routed_arguments = _route_canonical_tool_call(name, arguments)
        return self._call_transport_tool(routed_name, routed_arguments, timeout)

    def extract_text(self, result: dict) -> str:
        """Extract text from the normalized content envelope."""
        content = result.get("content", [])
        if content and isinstance(content, list):
            return content[0].get("text", "")
        return json.dumps(result)
