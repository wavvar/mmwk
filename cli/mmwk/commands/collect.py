"""Host-side MQTT collection command (raw UART bytes -> host files)."""

import json
from pathlib import Path
from urllib.parse import urlparse

import paho.mqtt.client as mqtt

from mmwk._logging import logger
from mmwk.commands.collect_engine import MqttCaptureSession


def _parse_broker_endpoint(raw_broker: str, default_port: int) -> tuple[str, int]:
    """Parse broker URI/host string and return (host, port)."""
    broker = (raw_broker or "").strip()
    if not broker:
        return "localhost", default_port

    if "://" in broker:
        parsed = urlparse(broker)
        host = parsed.hostname or "localhost"
        port = parsed.port or default_port
        return host, int(port)

    if broker.count(":") == 1:
        host, maybe_port = broker.rsplit(":", 1)
        if maybe_port.isdigit():
            return host, int(maybe_port)

    return broker, default_port


def _unwrap_tool_data(payload: dict | list) -> dict:
    if isinstance(payload, dict):
        status = payload.get("status")
        if isinstance(status, dict):
            raw = status.get("raw")
            if isinstance(raw, dict):
                return raw
        if all(key in payload for key in ("mode", "ctrl", "data")):
            return payload
        for key in ("data", "config", "state"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                return nested
        if payload:
            return payload
    return {}


def _build_raw_restore_args(payload: dict | list) -> dict:
    raw = _unwrap_tool_data(payload)
    mode = raw.get("mode") if raw.get("mode") in {"off", "runtime", "reconnect"} else "off"
    restore = {"action": "raw", "mode": mode}
    if mode == "off":
        restore["channel"] = "both"
    else:
        ctrl = raw.get("ctrl_route", raw.get("ctrl"))
        data = raw.get("data_route", raw.get("data"))
        route_names = {"wire", "mqtt", "both", "off"}
        if isinstance(ctrl, str) and isinstance(data, str) and ctrl in route_names and data in route_names:
            restore["ctrl"] = ctrl
            restore["data"] = data
        elif isinstance(data, str) and data in route_names:
            restore["channel"] = data
        else:
            restore["channel"] = "both"
        baud = raw.get("baud", raw.get("current_baud"))
        if baud not in (None, "") and data in {"wire", "both"}:
            restore["baud"] = baud
        if raw.get("escape") not in (None, ""):
            restore["escape"] = raw["escape"]
    return restore


def _build_raw_restore_args_for_trigger_none(payload: dict | list) -> dict:
    return _build_raw_restore_args(payload)


def _create_mqtt_client(client_id: str) -> mqtt.Client:
    callback_api_version = getattr(mqtt, "CallbackAPIVersion", None)
    if callback_api_version is not None:
        try:
            return mqtt.Client(
                callback_api_version=callback_api_version.VERSION1,
                client_id=client_id,
            )
        except TypeError:
            pass
    return mqtt.Client(client_id=client_id)


_MqttRawCaptureSession = MqttCaptureSession


class CollectCommand:
    """Subscribe MQTT topics and persist raw UART byte streams."""

    def __init__(self, mcp_client=None):
        self.mcp = mcp_client

    def execute(
        self,
        duration: int,
        data_output: str | None,
        resp_output: str | None,
        broker: str,
        mqtt_port: int,
        did: str,
        prod: str = "mmwk",
        oid: str = "mmwk",
        cid: str = "",
        data_topic: str = "",
        resp_topic: str = "",
        resp_optional: bool = False,
        mode: str = "host",
        attach: bool = False,
        overwrite: bool = False,
        timeout: float = 10.0,
        cfg_path: str | None = None,
        summary_output: str | None = None,
        events_output: str | None = None,
        wire_output: str | None = None,
        mqtt_username: str = "",
        mqtt_password: str = "",
        mqtt_ca: str | None = None,
    ) -> bool:
        """Compatibility entrypoint around the shared MQTT collection engine."""
        from mmwk.commands.collect_engine import CollectionPlan, collect_mqtt

        if resp_optional and not attach:
            logger.error("--resp-optional is valid only for a borrowed attach session")
            return False
        explicit_outputs = [
            Path(value).expanduser().resolve()
            for value in (
                data_output,
                resp_output,
                wire_output,
                summary_output,
                events_output,
            )
            if value
        ]
        if len(set(explicit_outputs)) != len(explicit_outputs):
            logger.error("collection output paths must be distinct")
            return False
        if not overwrite:
            collisions = [str(path) for path in explicit_outputs if path.exists()]
            if collisions:
                logger.error(
                    "Collection outputs already exist; pass --overwrite to replace them: %s",
                    ", ".join(collisions),
                )
                return False
        try:
            plan = CollectionPlan(
                transport="mqtt",
                mode=mode,
                duration=duration,
                cfg_path=cfg_path,
                data_output=data_output,
                resp_output=resp_output,
                wire_output=wire_output,
                summary_output=summary_output,
                events_output=events_output,
                attach=attach,
                overwrite=overwrite,
                data_ready_timeout=timeout,
                control_timeout=timeout,
            )
            self.last_summary = collect_mqtt(
                plan,
                control=self.mcp,
                broker=broker,
                mqtt_port=mqtt_port,
                expected_did=did or None,
                data_topic=data_topic or None,
                resp_topic=resp_topic or None,
                prod=prod,
                oid=oid,
                cid=cid,
                mqtt_username=mqtt_username,
                mqtt_password=mqtt_password,
                mqtt_ca=mqtt_ca,
                client_factory=_create_mqtt_client,
            )
            print(json.dumps(self.last_summary.as_dict(), indent=2))
            return True
        except Exception as exc:
            logger.error("Collection failed: %s", exc)
            return False

    def execute_trigger_none(
        self,
        duration: int,
        data_output: str | None,
        resp_output: str | None,
        broker: str,
        mqtt_port: int,
        did: str,
        prod: str = "mmwk",
        oid: str = "mmwk",
        cid: str = "",
        data_topic: str = "",
        resp_topic: str = "",
        resp_optional: bool = False,
        overwrite: bool = False,
        timeout: float = 10.0,
    ) -> bool:
        if resp_optional:
            logger.error(
                "trigger=none no longer treats missing responses as success; "
                "use collect --mode auto --attach for a borrowed DATA-only route"
            )
            return False
        return self.execute(
            duration=duration,
            data_output=data_output,
            resp_output=resp_output,
            broker=broker,
            mqtt_port=mqtt_port,
            did=did,
            prod=prod,
            oid=oid,
            cid=cid,
            data_topic=data_topic,
            resp_topic=resp_topic,
            mode="host",
            attach=False,
            overwrite=overwrite,
            timeout=timeout,
        )
