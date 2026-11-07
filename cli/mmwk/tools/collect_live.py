"""Live MQTT raw collection helper with task-oriented state reporting."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from mmwk.commands.collect import (
    _create_mqtt_client,
)
from mmwk.commands.collect_engine import (
    CollectionPlan,
    collect_mqtt,
    collect_reconnect_mqtt,
    reserve_output_files,
    resolve_mqtt_endpoint,
)
from mmwk.mqtt_topics import build_mqtt_topics
from mmwk.protocol_client import create_protocol_client
from mmwk.transport import create_transport


class CollectStatePrinter:
    """Print high-level state transitions once."""

    def __init__(
        self,
        stream,
        event_log_path: str | os.PathLike[str] | None = None,
        *,
        overwrite: bool = False,
    ):
        self.stream = stream
        self._seen = set()
        self._device_connected: bool | None = None
        self._event_log = None
        if event_log_path is not None:
            Path(event_log_path).parent.mkdir(parents=True, exist_ok=True)
            mode = "w" if overwrite else "x"
            self._event_log = open(event_log_path, mode, encoding="utf-8")

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


def _write_summary_json(path: str | os.PathLike[str], summary: dict, *, overwrite: bool = False):
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with reserve_output_files((out_path,), overwrite=overwrite) as outputs:
        handle = outputs.handles[out_path.expanduser().resolve()]
        handle.write((json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        handle.flush()


def run_collect_session(
    controller,
    *,
    duration: float | None,
    summary_path: str | os.PathLike[str],
    state_printer: CollectStatePrinter,
    overwrite: bool = False,
    sleep_fn=time.sleep,
    monotonic_fn=time.monotonic,
    poll_interval: float = 0.2,
) -> int:
    try:
        controller.start()
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
        _write_summary_json(summary_path, summary, overwrite=overwrite)
        return 0
    except KeyboardInterrupt:
        state_printer.mark("capture stopping")
        summary = dict(controller.stop())
        summary["interrupted"] = True
        _write_summary_json(summary_path, summary, overwrite=overwrite)
        return 130
    except Exception as exc:
        state_printer.mark("capture stopping")
        summary = dict(controller.stop())
        summary["interrupted"] = False
        summary["error"] = str(exc)
        _write_summary_json(summary_path, summary, overwrite=overwrite)
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
        mode: str = "host",
        attach: bool = False,
        overwrite: bool = False,
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
        self.mode = mode
        self.attach = bool(attach)
        self.overwrite = bool(overwrite)
        if self.reboot and self.attach:
            raise ValueError("reboot collection cannot borrow an attached raw route")
        if self.mode == "auto" and not self.attach and not self.reboot:
            raise ValueError("auto live collection requires --attach")

        output_stem = f"{self.output_prefix}raw_data"
        self.data_output = os.path.join(self.output_dir, f"{output_stem}.sraw")
        self.resp_output = os.path.join(self.output_dir, f"{output_stem}.log")

        self.transport = None
        self.mcp = None
        self._connected = False
        self._mqtt_connected_seen = False
        self._control_ready = False
        self._raw_forwarding_enabled = False
        self._restart_requested = False
        self._closed = False
        self._stop_event = threading.Event()
        self._worker = None
        self._worker_ready = threading.Event()
        self._engine_summary = None
        self._engine_error = None
        self._progress_phases = set()

    def start(self):
        outputs = [
            Path(self.data_output).expanduser().resolve(),
            Path(self.resp_output).expanduser().resolve(),
        ]
        if len(set(outputs)) != len(outputs):
            raise ValueError("live collection outputs must be distinct")
        if not self.overwrite:
            collision = next((path for path in outputs if path.exists()), None)
            if collision is not None:
                raise FileExistsError(collision)

        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        default_topics = build_mqtt_topics(
            did=self.did,
            prod=self.prod,
            oid=self.oid,
            cid=self.cid,
            include_raw_cmd=True,
        )
        self.data_topic = self.data_topic or default_topics["raw_data"]
        self.resp_topic = (
            ""
            if self.mode == "auto" or self.reboot
            else self.resp_topic or default_topics["raw_resp"]
        )
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
            mqtt_user=None,
            mqtt_password=None,
            mqtt_ca=None,
        )
        self.transport = create_transport(transport_args)
        self.mcp = create_protocol_client("cli", self.transport)
        self.mcp.initialize(timeout=self.timeout)
        self._control_ready = True

        def progress(phase: str, details: dict):
            self._progress_phases.add(phase)
            if phase == "mqtt_ready":
                self._connected = True
                self._mqtt_connected_seen = True
                self._worker_ready.set()
            elif phase == "reconnect_armed":
                self._restart_requested = True
                self._raw_forwarding_enabled = True
            elif phase == "control" and details.get("service") == "radar":
                self._raw_forwarding_enabled = True

        def worker():
            try:
                plan = CollectionPlan(
                    transport="mqtt",
                    mode="auto" if self.reboot else self.mode,
                    duration=2_147_483_647,
                    data_output=self.data_output,
                    resp_output=self.resp_output,
                    attach=self.attach,
                    overwrite=self.overwrite,
                    data_ready_timeout=self.timeout,
                    control_timeout=self.timeout,
                )
                collect_fn = collect_reconnect_mqtt if self.reboot else collect_mqtt
                collect_kwargs = {
                    "control": self.mcp,
                    "broker": self.broker,
                    "mqtt_port": self.mqtt_port,
                    "expected_did": self.did,
                    "data_topic": self.data_topic,
                    "prod": self.prod,
                    "oid": self.oid,
                    "cid": self.cid,
                    "client_factory": _create_mqtt_client,
                    "stop_event": self._stop_event,
                    "progress_callback": progress,
                }
                if not self.reboot:
                    collect_kwargs["resp_topic"] = self.resp_topic
                self._engine_summary = collect_fn(plan, **collect_kwargs)
            except BaseException as exc:
                self._engine_error = exc
            finally:
                self._worker_ready.set()
                if self.transport is not None:
                    try:
                        self.transport.close()
                    except Exception:
                        pass

        self._worker = threading.Thread(
            target=worker,
            name=f"mmwk-collect-live-{self.did}",
            daemon=True,
        )
        self._worker.start()
        self._worker_ready.wait(max(self.timeout, 0.1))
        if self._engine_error is not None:
            raise self._engine_error
        if not self._worker_ready.is_set():
            self._stop_event.set()
            raise TimeoutError("live collector did not reach MQTT-ready state")

    def poll(self, state_printer: CollectStatePrinter):
        if self._engine_error is not None:
            raise self._engine_error
        if self._mqtt_connected_seen:
            state_printer.mark("mqtt connected")
        if self._control_ready:
            state_printer.mark("control ready")
        if self._raw_forwarding_enabled:
            state_printer.mark("raw forwarding enabled")
        if self._restart_requested:
            state_printer.mark("radar restart requested")
        if "raw_cmd" in self._progress_phases:
            state_printer.mark("command traffic seen")
        if "data_ready" in self._progress_phases:
            state_printer.mark("raw data seen")
        if self._mqtt_connected_seen:
            state_printer.update_device_connected(self._connected)

    def stop(self) -> dict:
        if self._closed:
            return self._summary_dict(interrupted=False, error=str(self._engine_error or ""))
        self._closed = True
        self._stop_event.set()
        if self._worker is not None:
            self._worker.join(max(self.timeout + 5.0, 5.0))
            if self._worker.is_alive():
                raise TimeoutError("shared live collector did not finish cleanup")
        if self._engine_error is not None:
            return self._summary_dict(interrupted=False, error=str(self._engine_error))
        return self._summary_dict(interrupted=False, error="")

    def _summary_dict(self, *, interrupted: bool, error: str) -> dict:
        engine = self._engine_summary
        data_bytes = int(engine.data_bytes) if engine is not None else 0
        resp_bytes = int(engine.response_bytes) if engine is not None else 0
        endpoint = resolve_mqtt_endpoint(self.broker, self.mqtt_port)
        summary = CollectSummary(
            did=self.did,
            prod=self.prod,
            oid=self.oid,
            cid=self.cid,
            broker=f"{'mqtts' if endpoint.tls else 'mqtt'}://{endpoint.host}",
            mqtt_port=endpoint.port,
            data_topic=self.data_topic or "",
            resp_topic=self.resp_topic or "",
            data_output=self.data_output,
            resp_output=self.resp_output,
            data_messages=1 if data_bytes else 0,
            data_bytes=data_bytes,
            resp_messages=1 if resp_bytes else 0,
            resp_bytes=resp_bytes,
            raw_data_seen=bool(data_bytes > 0),
            command_traffic_seen=bool(resp_bytes > 0),
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
    parser.add_argument("--mode", choices=["host", "auto"], default="host", help="Radar ownership mode")
    parser.add_argument("--attach", action="store_true", help="Observe an existing auto MQTT DATA route")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing capture outputs")
    parser.add_argument("--data-topic", help="Raw data topic override")
    parser.add_argument("--resp-topic", help="Raw resp topic override")
    parser.add_argument(
        "--reboot",
        action="store_true",
        help="Subscribe, arm one-shot reconnect raw, reboot the device, and capture that generation",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    output_dir = os.path.abspath(args.output_dir)
    output_prefix = args.output_prefix or ""
    summary_path = os.path.join(output_dir, f"{output_prefix}summary.json")
    state_log_path = os.path.join(output_dir, f"{output_prefix}state_events.log")

    output_paths = tuple(
        Path(path).expanduser().resolve()
        for path in (
            os.path.join(output_dir, f"{output_prefix}raw_data.sraw"),
            os.path.join(output_dir, f"{output_prefix}raw_data.log"),
            summary_path,
            state_log_path,
        )
    )
    if len(set(output_paths)) != len(output_paths):
        print("Error: collection output paths must be distinct", file=sys.stderr)
        return 1
    if not args.overwrite:
        collisions = [str(path) for path in output_paths if path.exists()]
        if collisions:
            print(
                "Error: collection outputs already exist; pass --overwrite to replace them: "
                + ", ".join(collisions),
                file=sys.stderr,
            )
            return 1

    state_printer = CollectStatePrinter(
        sys.stdout,
        event_log_path=state_log_path,
        overwrite=args.overwrite,
    )
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
        mode=args.mode,
        attach=args.attach,
        overwrite=args.overwrite,
    )

    try:
        return run_collect_session(
            controller,
            duration=args.duration,
            summary_path=summary_path,
            state_printer=state_printer,
            overwrite=args.overwrite,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        state_printer.close()


if __name__ == "__main__":
    raise SystemExit(main())
