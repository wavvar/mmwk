"""Live MQTT raw collection helper with task-oriented state reporting."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from mmwk.commands.collect import (
    CollectCommand,
    _MqttRawCaptureSession,
    _build_raw_restore_args,
    _create_mqtt_client,
    _parse_broker_endpoint,
)
from mmwk.mqtt_topics import build_mqtt_topics
from mmwk.protocol_client import create_protocol_client
from mmwk.transport import create_transport


class CollectStatePrinter:
    """Print high-level state transitions once."""

    def __init__(self, stream, event_log_path: str | os.PathLike[str] | None = None):
        self.stream = stream
        self._seen = set()
        self._device_connected: bool | None = None
        self._event_log = None
        if event_log_path is not None:
            Path(event_log_path).parent.mkdir(parents=True, exist_ok=True)
            self._event_log = open(event_log_path, "a", encoding="utf-8")

    def close(self):
        if self._event_log is not None:
            self._event_log.close()
            self._event_log = None

    def _emit(self, state: str):
        line = f"[collect] {state}"
        print(line, file=self.stream)
        flush = getattr(self.stream, "flush", None)
        if callable(flush):
            flush()
        if self._event_log is not None:
            self._event_log.write(line + "\n")
            self._event_log.flush()

    def mark(self, state: str):
        if state in self._seen:
            return
        self._seen.add(state)
        self._emit(state)

    def update_device_connected(self, connected: bool):
        if self._device_connected is None:
            self._device_connected = connected
            if connected:
                return
            self.mark("device disconnected")
            return

        if connected == self._device_connected:
            return

        self._device_connected = connected
        if connected:
            self.mark("device reconnected")
        else:
            self.mark("device disconnected")


@dataclass
class CollectSummary:
    did: str
    prod: str
    oid: str
    cid: str
    broker: str
    mqtt_port: int
    data_topic: str
    resp_topic: str
    data_output: str
    resp_output: str
    data_messages: int
    data_bytes: int
    resp_messages: int
    resp_bytes: int
    raw_data_seen: bool
    command_traffic_seen: bool
    interrupted: bool = False
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "did": self.did,
            "prod": self.prod,
            "oid": self.oid,
            "cid": self.cid,
            "broker": self.broker,
            "mqtt_port": self.mqtt_port,
            "raw_data": self.data_topic,
            "raw_resp": self.resp_topic,
            "data_output": self.data_output,
            "resp_output": self.resp_output,
            "data_messages": self.data_messages,
            "data_bytes": self.data_bytes,
            "resp_messages": self.resp_messages,
            "resp_bytes": self.resp_bytes,
            "raw_data_seen": self.raw_data_seen,
            "command_traffic_seen": self.command_traffic_seen,
            "interrupted": self.interrupted,
            "error": self.error,
        }


def _write_summary_json(path: str | os.PathLike[str], summary: dict):
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_collect_session(
    controller,
    *,
    duration: float | None,
    summary_path: str | os.PathLike[str],
    state_printer: CollectStatePrinter,
    sleep_fn=time.sleep,
    monotonic_fn=time.monotonic,
    poll_interval: float = 0.2,
) -> int:
    controller.start()
    try:
        if duration is None:
            while True:
                controller.poll(state_printer)
                sleep_fn(poll_interval)
        else:
            deadline = monotonic_fn() + max(float(duration), 0.0)
            while monotonic_fn() < deadline:
                controller.poll(state_printer)
                sleep_fn(poll_interval)

        state_printer.mark("capture stopping")
        summary = dict(controller.stop())
        summary["interrupted"] = False
        _write_summary_json(summary_path, summary)
        return 0
    except KeyboardInterrupt:
        state_printer.mark("capture stopping")
        summary = dict(controller.stop())
        summary["interrupted"] = True
        _write_summary_json(summary_path, summary)
        return 130
    except Exception as exc:
        state_printer.mark("capture stopping")
        summary = dict(controller.stop())
        summary["interrupted"] = False
        summary["error"] = str(exc)
        _write_summary_json(summary_path, summary)
        raise


class _LiveCollectController:
    def __init__(
        self,
        *,
        did: str,
        prod: str = "mmwk",
        oid: str = "mmwk",
        cid: str = "",
        broker: str,
        mqtt_port: int,
        output_dir: str,
        output_prefix: str = "",
        data_topic: str | None = None,
        resp_topic: str | None = None,
        timeout: float = 10.0,
        reboot: bool = False,
    ):
        self.did = did
        self.prod = prod or "mmwk"
        self.oid = oid or "mmwk"
        self.cid = cid or ""
        self.broker = broker
        self.mqtt_port = int(mqtt_port)
        self.output_dir = os.path.abspath(output_dir)
        self.output_prefix = output_prefix or ""
        self.data_topic = data_topic
        self.resp_topic = resp_topic
        self.timeout = float(timeout)
        self.reboot = bool(reboot)

        output_stem = f"{self.output_prefix}raw_data"
        self.data_output = os.path.join(self.output_dir, f"{output_stem}.sraw")
        self.resp_output = os.path.join(self.output_dir, f"{output_stem}.log")

        self.transport = None
        self.mcp = None
        self.collector = None
        self.client = None
        self.capture_session = None
        self.data_fout = None
        self.resp_fout = None
        self.restore_raw_args = None
        self._connected = False
        self._mqtt_connected_seen = False
        self._control_ready = False
        self._raw_forwarding_enabled = False
        self._restart_requested = False
        self._closed = False

    def start(self):
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        self.data_fout = open(self.data_output, "wb")
        self.resp_fout = open(self.resp_output, "wb")

        transport_args = SimpleNamespace(
            transport="mqtt",
            broker=self.broker,
            mqtt_port=self.mqtt_port,
            did=self.did,
            prod=self.prod,
            oid=self.oid,
            cid=self.cid,
            cmd_topic=None,
            resp_topic=None,
            mqtt_qos=1,
            mqtt_delay=0.05,
        )
        self.transport = create_transport(transport_args)
        self.mcp = create_protocol_client("cli", self.transport)
        self.mcp.initialize(timeout=self.timeout)
        self._control_ready = True

        self.collector = CollectCommand(self.mcp)
        hi = self.collector._hydrate_hi(self.collector._load_hi(timeout=self.timeout), timeout=self.timeout)
        raw_state = self.collector._tool_json("radar.raw", {"action": "config_get"}, timeout=self.timeout)
        self.restore_raw_args = _build_raw_restore_args(raw_state)

        default_topics = build_mqtt_topics(
            did=self.did,
            prod=self.prod,
            oid=self.oid,
            cid=self.cid,
            include_raw_cmd=True,
        )
        raw_cfg = raw_state.get("config", raw_state) if isinstance(raw_state, dict) else {}
        self.data_topic = (
            self.data_topic
            or raw_cfg.get("raw_data")
            or hi.get("raw_data")
            or default_topics["raw_data"]
        )
        self.resp_topic = (
            self.resp_topic
            or raw_cfg.get("raw_resp")
            or hi.get("raw_resp")
            or default_topics["raw_resp"]
        )

        host, port = _parse_broker_endpoint(self.broker, self.mqtt_port)
        self.capture_session = _MqttRawCaptureSession(
            self.data_topic,
            self.resp_topic,
            self.data_fout,
            self.resp_fout,
        )
        self.client = _create_mqtt_client(client_id=f"mmwk_collect_live_{int(time.time())}")
        self.capture_session.bind_client(self.client)

        original_on_connect = self.client.on_connect

        def on_connect(client, userdata, flags, rc):
            self._connected = rc == 0
            if self._connected:
                self._mqtt_connected_seen = True
            if original_on_connect is not None:
                original_on_connect(client, userdata, flags, rc)

        def on_disconnect(client, userdata, rc):
            self._connected = False

        self.client.on_connect = on_connect
        self.client.on_disconnect = on_disconnect
        self.client.connect(host, port, 60)
        self.client.loop_start()

        wait_deadline = time.time() + max(self.timeout, 5.0)
        while not self.capture_session.subscribed.is_set() and time.time() < wait_deadline:
            if self.capture_session.connect_error["rc"] is not None:
                raise RuntimeError(f"MQTT connect failed with rc={self.capture_session.connect_error['rc']}")
            if self.capture_session.subscribe_error["message"] is not None:
                raise RuntimeError(self.capture_session.subscribe_error["message"])
            time.sleep(0.1)

        if not self.capture_session.subscribed.is_set():
            raise TimeoutError("Timed out waiting for MQTT subscribe-ready state")

        self.mcp.call_tool(
            "radar.raw",
            {"action": "config_set", "config": {"enabled": True}},
            timeout=self.timeout,
        )
        self._raw_forwarding_enabled = True
        if self.reboot:
            self.mcp.call_tool(
                "radar",
                {"action": "start"},
                timeout=self.timeout,
            )
            self._restart_requested = True

    def poll(self, state_printer: CollectStatePrinter):
        if self._mqtt_connected_seen:
            state_printer.mark("mqtt connected")
        if self._control_ready:
            state_printer.mark("control ready")
        if self._raw_forwarding_enabled:
            state_printer.mark("raw forwarding enabled")
        if self._restart_requested:
            state_printer.mark("radar restart requested")
        if self.capture_session and self.capture_session.stats["resp_messages"] > 0:
            state_printer.mark("command traffic seen")
        if self.capture_session and self.capture_session.stats["data_messages"] > 0:
            state_printer.mark("raw data seen")
        if self._mqtt_connected_seen:
            state_printer.update_device_connected(self._connected)

    def stop(self) -> dict:
        if self._closed:
            return self._summary_dict(interrupted=False, error="")
        self._closed = True

        if self.client is not None:
            try:
                self.client.loop_stop()
            except Exception:
                pass
            try:
                self.client.disconnect()
            except Exception:
                pass

        if self.mcp is not None and self.restore_raw_args is not None:
            try:
                self.mcp.call_tool("radar.raw", self.restore_raw_args, timeout=self.timeout)
            except Exception:
                pass

        if self.transport is not None:
            try:
                self.transport.close()
            except Exception:
                pass

        if self.data_fout is not None:
            self.data_fout.close()
            self.data_fout = None
        if self.resp_fout is not None:
            self.resp_fout.close()
            self.resp_fout = None

        return self._summary_dict(interrupted=False, error="")

    def _summary_dict(self, *, interrupted: bool, error: str) -> dict:
        stats = self.capture_session.stats if self.capture_session is not None else {
            "data_messages": 0,
            "data_bytes": 0,
            "resp_messages": 0,
            "resp_bytes": 0,
        }
        summary = CollectSummary(
            did=self.did,
            prod=self.prod,
            oid=self.oid,
            cid=self.cid,
            broker=self.broker,
            mqtt_port=self.mqtt_port,
            data_topic=self.data_topic or "",
            resp_topic=self.resp_topic or "",
            data_output=self.data_output,
            resp_output=self.resp_output,
            data_messages=int(stats.get("data_messages", 0)),
            data_bytes=int(stats.get("data_bytes", 0)),
            resp_messages=int(stats.get("resp_messages", 0)),
            resp_bytes=int(stats.get("resp_bytes", 0)),
            raw_data_seen=bool(stats.get("data_messages", 0) > 0),
            command_traffic_seen=bool(stats.get("resp_messages", 0) > 0),
            interrupted=interrupted,
            error=error,
        )
        return summary.to_dict()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mmwk.tools.collect_live",
        description="Live MQTT raw collection with high-level state reporting",
    )
    parser.add_argument("--did", required=True, help="Radar DID")
    parser.add_argument("--prod", default="mmwk", help="Product route segment (default: mmwk)")
    parser.add_argument("--oid", default="mmwk", help="Organization route segment (default: mmwk)")
    parser.add_argument("--cid", default="", help="Claimed route id; takes precedence over --did")
    parser.add_argument("--mqtt-server", required=True, help="MQTT broker host or URI")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port (default: 1883)")
    parser.add_argument("--duration", type=float, help="Capture duration in seconds; omit for Ctrl-C mode")
    parser.add_argument("--output-dir", required=True, help="Output directory for raw_data.sraw/raw_data.log")
    parser.add_argument("--output-prefix", default="", help="Optional prefix for output file names")
    parser.add_argument("--timeout", type=float, default=10.0, help="Control/MQTT timeout in seconds")
    parser.add_argument("--data-topic", help="Raw data topic override")
    parser.add_argument("--resp-topic", help="Raw resp topic override")
    parser.add_argument(
        "--reboot",
        action="store_true",
        help="Restart the radar service after subscribe-ready bootstrap so startup raw_resp is captured",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    output_dir = os.path.abspath(args.output_dir)
    output_prefix = args.output_prefix or ""
    summary_path = os.path.join(output_dir, f"{output_prefix}summary.json")
    state_log_path = os.path.join(output_dir, f"{output_prefix}state_events.log")

    state_printer = CollectStatePrinter(sys.stdout, event_log_path=state_log_path)
    state_printer.mark("server ready")

    controller = _LiveCollectController(
        did=args.did,
        prod=args.prod,
        oid=args.oid,
        cid=args.cid,
        broker=args.mqtt_server,
        mqtt_port=args.mqtt_port,
        output_dir=output_dir,
        output_prefix=output_prefix,
        data_topic=args.data_topic,
        resp_topic=args.resp_topic,
        timeout=args.timeout,
        reboot=args.reboot,
    )

    try:
        return run_collect_session(
            controller,
            duration=args.duration,
            summary_path=summary_path,
            state_printer=state_printer,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        state_printer.close()


if __name__ == "__main__":
    raise SystemExit(main())
