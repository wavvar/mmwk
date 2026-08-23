"""Shared host/remote radar raw collection primitives.

The engine deliberately keeps transport mechanics separate from the public CLI
argument surface.  Local wire sessions are byte-oriented after the raw route is
opened; MQTT sessions remain chunk-oriented and are implemented by the existing
MQTT collector entrypoints.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Iterable, Mapping


MAX_EXTERNAL_UART_BAUD = 1_000_000
DEFAULT_PARSED_BAUD = 115_200
DEFAULT_RAW_BAUD = 1_000_000
RAW_SWITCH_SETTLE_SECONDS = 0.15
RAW_ESCAPE_GUARD_SECONDS = 1.25


@dataclass(frozen=True)
class LiveIdentity:
    """Normalized identity used to prevent collecting from the wrong device."""

    did: str
    board: str = ""
    source_field: str = "did"

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "LiveIdentity":
        if not isinstance(payload, Mapping):
            raise ValueError("node info must be an object")
        for field_name in ("did", "id", "client_id"):
            value = payload.get(field_name)
            if isinstance(value, str) and value.strip():
                return cls(
                    did=value.strip().lower(),
                    board=str(payload.get("board") or "").strip().lower(),
                    source_field=field_name,
                )
        raise ValueError("node info did not include did, id, or client_id")

    def require_match(self, expected: str | None) -> None:
        if expected and self.did != expected.strip().lower():
            raise ValueError(f"device identity mismatch: expected {expected!r}, got {self.did!r}")


@dataclass(frozen=True)
class CollectionPlan:
    """Immutable collection intent shared by local and MQTT entrypoints."""

    transport: str = "uart"
    port: str | None = None
    baudrate: int = DEFAULT_PARSED_BAUD
    raw_baud: int | None = None
    escape: str = "+++"
    mode: str = "host"
    duration: int = 10
    cfg_path: str | None = None
    data_output: str = "radar.sraw"
    resp_output: str = "radar-cmd.log"
    wire_output: str | None = None
    attach: bool = False
    allow_lossy: bool = False
    overwrite: bool = False
    ctrl_transport: str | None = None
    data_transport: str | None = None

    def __post_init__(self) -> None:
        # Keep the convenience default for a direct local UART session while
        # leaving MQTT, native USB, and split MQTT-DATA plans baudless. A
        # single static default would reject a valid MQTT plan before its
        # DATA route is opened.
        if (self.raw_baud is None and self.transport == "uart" and
                self.ctrl_transport is None and self.data_transport is None):
            object.__setattr__(self, "raw_baud", DEFAULT_RAW_BAUD)

    def validate(self) -> None:
        if self.transport not in {"uart", "usb", "mqtt"}:
            raise ValueError(f"unsupported collection transport: {self.transport}")
        if self.mode not in {"host", "auto"}:
            raise ValueError("collection mode must be host or auto")
        if self.duration < 1:
            raise ValueError("duration must be positive")
        if self.baudrate <= 0:
            raise ValueError("baudrate must be positive")
        if self.transport == "usb" and self.raw_baud is not None:
            raise ValueError("--raw-baud is not valid for native USB CDC")
        if self.raw_baud is not None and self.raw_baud > MAX_EXTERNAL_UART_BAUD:
            raise ValueError("raw UART baud is capped at 1000000 for current adapters")
        if (not isinstance(self.escape, str) or not (1 <= len(self.escape) <= 16) or
                any(ord(char) < 0x20 or ord(char) > 0x7e for char in self.escape)):
            raise ValueError("escape must be 1-16 printable characters")
        if self.mode == "auto" and self.transport in {"uart", "usb"}:
            raise ValueError("auto raw is MQTT DATA-only; use --transport mqtt --attach")
        for value in (self.ctrl_transport, self.data_transport):
            if value is not None and value not in {"uart", "usb", "mqtt"}:
                raise ValueError("ctrl/data transport must be uart, usb, or mqtt")
        split_selected = self.ctrl_transport is not None or self.data_transport is not None
        if split_selected and (self.ctrl_transport is None or self.data_transport is None):
            raise ValueError("split collection requires both --ctrl-transport and --data-transport")
        data_transport = self.data_transport if split_selected else self.transport
        local_selected = {self.ctrl_transport, self.data_transport} & {"uart", "usb"}
        if self.raw_baud is not None and data_transport != "uart":
            raise ValueError("--raw-baud is valid only when DATA uses an external UART")
        if self.port is None and (self.transport in {"uart", "usb"} or local_selected):
            raise ValueError("local collection requires --port")


@dataclass(frozen=True)
class OutputSet:
    data: Path
    response: Path
    wire: Path | None = None
    summary: Path | None = None
    events: Path | None = None

    def paths(self) -> tuple[Path, ...]:
        """Return the complete output set without duplicate paths."""
        values = (self.data, self.response, self.wire, self.summary, self.events)
        result: list[Path] = []
        seen: set[Path] = set()
        for value in values:
            if value is None:
                continue
            path = Path(value).expanduser().resolve()
            if path in seen:
                raise ValueError(f"collection outputs must be distinct: {path}")
            seen.add(path)
            result.append(path)
        return tuple(result)


class ReservedOutputFiles(ExitStack):
    """Exit stack with reserved handles and optional atomic replacements."""

    def __init__(self) -> None:
        super().__init__()
        self.handles: dict[Path, BinaryIO] = {}
        self._replacements: list[tuple[Path, Path]] = []
        self._closed = False
        self._discard = False

    def discard(self) -> None:
        """Close handles and remove overwrite temporaries without replacing targets."""
        self._discard = True
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        # ExitStack.close() dispatches through self.__exit__(), which is
        # overridden below to distinguish commit from discard.  Call the
        # base finalizer directly so every reserved handle is actually closed.
        super().__exit__(None, None, None)
        for temporary, target in self._replacements:
            if self._discard:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass
                continue
            os.replace(temporary, target)

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is not None:
            self.discard()
        else:
            self.close()
        return False


def reserve_output_files(paths: Iterable[str | os.PathLike[str]], *, overwrite: bool = False) -> ReservedOutputFiles:
    """Reserve every collection output before any device mutation.

    Non-overwrite reservations use exclusive create and are rolled back only
    when a later reservation fails.  The returned ``ExitStack`` owns the open
    handles; callers keep those handles for the complete run instead of
    reopening paths after a device has entered raw mode.
    """
    normalized: list[Path] = []
    seen: set[Path] = set()
    for raw_path in paths:
        path = Path(raw_path).expanduser().resolve()
        if path in seen:
            raise ValueError(f"collection outputs must be distinct: {path}")
        seen.add(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized.append(path)

    stack = ReservedOutputFiles()
    created: list[Path] = []
    try:
        for path in normalized:
            if overwrite:
                if path.exists() and path.is_dir():
                    raise IsADirectoryError(str(path))
                fd, temporary_name = tempfile.mkstemp(
                    prefix=f".{path.name}.",
                    suffix=".tmp",
                    dir=str(path.parent),
                )
                temporary = Path(temporary_name)
                handle = os.fdopen(fd, "w+b")
                stack._replacements.append((temporary, path))
            else:
                fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o644)
                created.append(path)
                handle = os.fdopen(fd, "w+b")
            stack.enter_context(handle)
            stack.handles[path] = handle
    except Exception:
        stack.discard()
        if not overwrite:
            for path in created:
                try:
                    if path.stat().st_size == 0:
                        path.unlink()
                except OSError:
                    pass
        raise
    return stack


@dataclass(frozen=True)
class CleanupReport:
    raw_closed: bool = False
    radar_stopped: bool = False
    state_restored: bool = False
    errors: tuple[str, ...] = ()


@dataclass
class CollectionSummary:
    identity: LiveIdentity | None = None
    data_bytes: int = 0
    response_bytes: int = 0
    wire_bytes: int = 0
    dropped_bytes: int = 0
    source_bytes: int = 0
    destination_bytes: int = 0
    queue_high_water: int = 0
    config_source: str = ""
    transport: str = ""
    duration_s: float = 0.0
    warnings: list[str] = field(default_factory=list)
    cleanup: CleanupReport = field(default_factory=CleanupReport)

    def as_dict(self) -> dict[str, Any]:
        return {
            "did": self.identity.did if self.identity else "",
            "board": self.identity.board if self.identity else "",
            "data_bytes": self.data_bytes,
            "response_bytes": self.response_bytes,
            "wire_bytes": self.wire_bytes,
            "dropped_bytes": self.dropped_bytes,
            "source_bytes": self.source_bytes,
            "destination_bytes": self.destination_bytes,
            "queue_high_water": self.queue_high_water,
            "config_source": self.config_source,
            "transport": self.transport,
            "duration_s": self.duration_s,
            "warnings": list(self.warnings),
            "cleanup": {
                "raw_closed": self.cleanup.raw_closed,
                "radar_stopped": self.cleanup.radar_stopped,
                "state_restored": self.cleanup.state_restored,
                "errors": list(self.cleanup.errors),
            },
        }


class LocalWireSession:
    """Parsed-control then byte-oriented raw session for UART or native USB."""

    def __init__(self, plan: CollectionPlan, serial_factory=None):
        plan.validate()
        if plan.transport not in {"uart", "usb"}:
            raise ValueError("LocalWireSession requires uart or usb transport")
        self.plan = plan
        self._serial_factory = serial_factory
        self.serial = None
        self.parsed = True
        self.raw_open = False
        self._saved_mode = "auto"
        self.last_response: dict[str, Any] | None = None
        self._seq = 1

    def _make_serial(self):
        if self._serial_factory is not None:
            try:
                return self._serial_factory(
                    self.plan.port,
                    baudrate=self.plan.baudrate,
                    timeout=0.1,
                )
            except TypeError:
                return self._serial_factory(self.plan.port, self.plan.baudrate, 0.1)
        try:
            import serial
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("pyserial is required for local radar collection") from exc
        if os.name == "posix":
            # Opening a CP210x-backed ESP32 UART with pyserial's default
            # DTR/RTS transition can reset the device.  A local raw session
            # must preserve the parsed-to-wire state across its own open and
            # close, so use the POSIX backend without modem-line updates and
            # keep HUPCL disabled just like the normal UART transport.
            import serial.serialposix as serialposix
            import termios

            class _NoResetSerial(serialposix.Serial):
                def open(self):
                    update_dtr = self._update_dtr_state
                    update_rts = self._update_rts_state
                    try:
                        self._update_dtr_state = lambda: None
                        self._update_rts_state = lambda: None
                        return super().open()
                    finally:
                        self._update_dtr_state = update_dtr
                        self._update_rts_state = update_rts

            serial_obj = _NoResetSerial()
            serial_obj.port = self.plan.port
            serial_obj.baudrate = self.plan.baudrate
            serial_obj.timeout = 0.1
            serial_obj.dtr = False
            serial_obj.rts = False
            serial_obj.open()
            try:
                attrs = termios.tcgetattr(serial_obj.fileno())
                attrs[2] = (attrs[2] | termios.CLOCAL) & ~termios.HUPCL
                termios.tcsetattr(serial_obj.fileno(), termios.TCSANOW, attrs)
            except (OSError, termios.error):
                pass
            return serial_obj
        return serial.Serial(
            self.plan.port,
            baudrate=self.plan.baudrate,
            timeout=0.1,
        )

    def open(self):
        self.serial = self._make_serial()
        return self

    def close(self):
        if self.serial is not None:
            self.serial.close()
            self.serial = None

    def _require_serial(self):
        if self.serial is None:
            raise RuntimeError("local wire session is not open")
        return self.serial

    def _set_baud(self, baud: int):
        serial = self._require_serial()
        if self.plan.transport == "usb":
            raise ValueError("native USB CDC has no physical raw baud")
        serial.baudrate = int(baud)

    def _read_line(self, timeout: float) -> dict[str, Any]:
        serial = self._require_serial()
        deadline = time.monotonic() + max(timeout, 0.1)
        last_line = b""
        while time.monotonic() < deadline:
            buf = bytearray()
            while time.monotonic() < deadline:
                chunk = serial.read(1)
                if chunk:
                    buf.extend(chunk)
                    if chunk == b"\n":
                        break
            if not buf:
                continue

            last_line = bytes(buf)
            try:
                text = last_line.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                # Raw/log bytes can remain in the adapter after an escape.  They
                # are not a parsed response; keep waiting until the deadline.
                continue

            decoder = json.JSONDecoder()
            cursor = 0
            while cursor < len(text):
                start = text.find("{", cursor)
                if start < 0:
                    break
                try:
                    candidate, consumed = decoder.raw_decode(text[start:])
                except json.JSONDecodeError:
                    cursor = start + 1
                    continue
                cursor = start + consumed
                if not isinstance(candidate, dict):
                    continue

                # ESP console logging commonly prefixes the echoed request with
                # text such as ``I (...) ...``.  A request-looking JSON object
                # is not the response to the command we just sent; skip it and
                # continue scanning the same line/stream.
                if candidate.get("type") == "req":
                    continue
                if candidate.get("service") and candidate.get("action") and \
                        "ok" not in candidate and "result" not in candidate:
                    continue
                if (
                    candidate.get("type") in {"res", "event"}
                    or any(key in candidate for key in ("ok", "result", "error", "status"))
                ):
                    return candidate

        detail = f"; last line={last_line!r}" if last_line else ""
        raise TimeoutError(
            f"timed out waiting for parsed control response{detail}"
        )

    def _next_seq(self) -> int:
        seq = self._seq
        self._seq += 1
        return seq

    def _build_control_request(self, command: Mapping[str, Any]) -> dict[str, Any]:
        """Translate the collector's short command form to the CLI wire contract."""
        if not isinstance(command, Mapping):
            raise TypeError("control command must be an object")

        service = command.get("service") or command.get("cmd")
        if not isinstance(service, str) or not service:
            raise ValueError("control command requires a service or cmd")

        supplied_args = command.get("args")
        if supplied_args is None:
            args: dict[str, Any] = {}
        elif isinstance(supplied_args, Mapping):
            args = dict(supplied_args)
        else:
            raise ValueError("control command args must be an object")

        for key, value in command.items():
            if key not in {"type", "seq", "service", "cmd", "action", "args"}:
                args[key] = value

        request: dict[str, Any] = {
            "type": "req",
            "seq": self._next_seq(),
            "service": service,
            "args": args,
        }
        action = command.get("action")
        if isinstance(action, str) and action:
            request["action"] = action
        return request

    def send_control(self, command: Mapping[str, Any], timeout: float = 10.0) -> dict[str, Any]:
        if not self.parsed:
            raise RuntimeError("parsed control is unavailable while wire raw is active")
        serial = self._require_serial()
        request = self._build_control_request(command)
        serial.write((json.dumps(request, separators=(",", ":")) + "\n").encode("utf-8"))
        response = self._read_line(timeout)
        if response.get("ok") is False:
            error = response.get("error")
            if isinstance(error, Mapping):
                message = error.get("message") or error.get("code")
            else:
                message = error
            raise RuntimeError(str(message or "control request failed"))
        self.last_response = response
        return response

    def identify(self, expected_did: str | None = None, timeout: float = 10.0) -> LiveIdentity:
        response = self.send_control({"cmd": "node", "action": "info"}, timeout=timeout)
        payload = response.get("result", response)
        if isinstance(payload, Mapping) and isinstance(payload.get("data"), Mapping):
            payload = payload["data"]
        identity = LiveIdentity.from_payload(payload)
        identity.require_match(expected_did)
        return identity

    def open_raw(self, *, channel: str = "wire", ctrl: str | None = None,
                 data: str | None = None, escape: str | None = None,
                 timeout: float = 10.0) -> dict[str, Any]:
        if self.plan.mode != "host":
            raise ValueError("local wire raw requires host mode")
        command: dict[str, Any] = {
            "cmd": "radar",
            "action": "raw",
            "mode": "runtime",
        }
        if ctrl is None and data is None:
            command["channel"] = channel
        else:
            command["ctrl"] = ctrl or "off"
            command["data"] = data or "off"
        if escape is not None:
            command["escape"] = escape
        if self.plan.raw_baud is not None:
            command["baud"] = self.plan.raw_baud
        response = self.send_control(command, timeout=timeout)
        self.raw_open = True
        self.parsed = False
        if self.plan.raw_baud is not None:
            self._set_baud(self.plan.raw_baud)
            # Firmware acknowledges the parsed request before its wire worker
            # applies the 100 ms UART rate switch. Keep the host quiet for a
            # small margin so cfg/sensorStart cannot straddle that transition.
            time.sleep(RAW_SWITCH_SETTLE_SECONDS)
        return response

    def write_radar_bytes(self, payload: bytes) -> int:
        if not self.raw_open:
            raise RuntimeError("raw route is not active")
        serial = self._require_serial()
        total = 0
        view = memoryview(payload)
        while total < len(view):
            written = int(serial.write(bytes(view[total:])))
            if written <= 0:
                raise RuntimeError("serial write returned no progress")
            total += written
        return total

    def read_raw(self, size: int = 8192) -> bytes:
        if not self.raw_open:
            raise RuntimeError("raw route is not active")
        return bytes(self._require_serial().read(max(1, size)))

    def close_raw(self, escape: bytes | None = None, timeout: float = 3.0) -> dict[str, Any] | None:
        if not self.raw_open:
            return None
        serial = self._require_serial()
        # The firmware only accepts the escape sequence after a full guard
        # interval without radar output.  sensorStop's final response can
        # refresh that interval, so leave a small margin before sending +++.
        time.sleep(RAW_ESCAPE_GUARD_SECONDS)
        self.write_radar_bytes(escape if escape is not None else self.plan.escape.encode("ascii"))
        time.sleep(RAW_ESCAPE_GUARD_SECONDS)
        if self.plan.raw_baud is not None:
            self._set_baud(self.plan.baudrate)
        self.raw_open = False
        self.parsed = True
        try:
            return self._read_line(timeout)
        except TimeoutError:
            return None


class MqttRawSession:
    """Small immutable-plan wrapper used by remote collection entrypoints."""

    def __init__(self, plan: CollectionPlan, collector):
        plan.validate()
        if plan.transport != "mqtt":
            raise ValueError("MqttRawSession requires mqtt transport")
        self.plan = plan
        self.collector = collector

    def raw_request(self) -> dict[str, Any]:
        if self.plan.mode == "auto":
            return {"action": "raw", "mode": "runtime", "channel": "mqtt"}
        return {"action": "raw", "mode": "runtime", "channel": "mqtt"}


class SplitSession:
    """Route command/control and DATA through independent session backends."""

    def __init__(self, control, data):
        self.control = control
        self.data = data

    @property
    def transports(self) -> tuple[str, str]:
        return (
            getattr(self.control, "plan", self.control).transport,
            getattr(self.data, "plan", self.data).transport,
        )


def _mqtt_topics_for_identity(
    identity: LiveIdentity,
    plan: CollectionPlan,
    *,
    data_topic: str | None = None,
    prod: str = "mmwk",
    oid: str = "mmwk",
    cid: str = "",
) -> str:
    """Resolve the raw DATA topic without requiring a control-plane query."""
    if data_topic:
        return data_topic
    from mmwk.mqtt_topics import build_mqtt_topics

    return build_mqtt_topics(
        did=identity.did,
        prod=prod,
        oid=oid,
        cid=cid,
        include_raw_cmd=True,
    )["raw_data"]


def collect_split_wire_mqtt(
    plan: CollectionPlan,
    *,
    broker: str,
    mqtt_port: int = 1883,
    expected_did: str | None = None,
    data_topic: str | None = None,
    prod: str = "mmwk",
    oid: str = "mmwk",
    cid: str = "",
    serial_factory=None,
) -> CollectionSummary:
    """Collect a hybrid host route: parsed/raw control on local wire, DATA on MQTT.

    The local channel remains the command/response plane, while MQTT is subscribed
    before the raw route is opened so the first DATA chunk is not lost.  This is
    the recommended split route for a bandwidth-limited external UART.
    """
    plan.validate()
    if plan.ctrl_transport not in {"uart", "usb"} or plan.data_transport != "mqtt":
        raise ValueError("split collection currently supports local wire control with MQTT DATA")
    if not broker:
        raise ValueError("split wire/MQTT collection requires --broker")

    from mmwk.commands.collect import _MqttRawCaptureSession, _create_mqtt_client, _parse_broker_endpoint

    summary = CollectionSummary()
    summary.transport = "split"
    session = LocalWireSession(plan, serial_factory=serial_factory).open()
    start = time.monotonic()
    raw_open = False
    radar_started = False
    radar_stopped = False
    parsed_restored = False
    cleanup_errors: list[str] = []
    wire_file = None
    data_file = None
    resp_file = None
    client = None
    capture = None
    output_stack = None

    def record_response(response: Mapping[str, Any] | None) -> None:
        if not response or resp_file is None:
            return
        line = (json.dumps(dict(response), separators=(",", ":")) + "\n").encode("utf-8")
        resp_file.write(line)
        resp_file.flush()
        summary.response_bytes += len(line)

    try:
        summary.identity = session.identify(expected_did)
        if summary.identity.board == "wdr" and plan.raw_baud is not None:
            raise ValueError("WDR split DATA uses MQTT; omit --raw-baud")

        output_paths = [Path(plan.data_output), Path(plan.resp_output)]
        if plan.wire_output:
            output_paths.append(Path(plan.wire_output))
        output_stack = reserve_output_files(output_paths, overwrite=plan.overwrite)
        data_file = output_stack.handles[Path(plan.data_output).expanduser().resolve()]
        resp_file = output_stack.handles[Path(plan.resp_output).expanduser().resolve()]
        if plan.wire_output:
            wire_file = output_stack.handles[Path(plan.wire_output).expanduser().resolve()]
        record_response(session.last_response)
        record_response(session.send_control({"cmd": "radar", "action": "start", "mode": "host"}))
        radar_started = True

        topic = _mqtt_topics_for_identity(
            summary.identity,
            plan,
            data_topic=data_topic,
            prod=prod,
            oid=oid,
            cid=cid,
        )
        capture = _MqttRawCaptureSession(topic, "", data_file, resp_file, data_qos=0)
        host, port = _parse_broker_endpoint(broker, mqtt_port)
        client = _create_mqtt_client(client_id=f"mmwk_split_{int(time.time())}")
        capture.bind_client(client)
        client.connect(host, port, 60)
        client.loop_start()
        deadline = time.time() + max(5.0, float(plan.duration) + 5.0)
        while not capture.subscribed.is_set() and time.time() < deadline:
            if capture.connect_error["rc"] is not None or capture.subscribe_error["message"] is not None:
                raise RuntimeError(capture.subscribe_error["message"] or "MQTT connect failed")
            time.sleep(0.05)
        if not capture.subscribed.is_set():
            raise TimeoutError("timed out waiting for MQTT DATA subscription")

        raw_response = session.open_raw(ctrl="wire", data="mqtt", escape=plan.escape)
        record_response(raw_response)
        raw_open = True
        cfg_payload = Path(plan.cfg_path).read_bytes() if plan.cfg_path else None
        summary.config_source = str(Path(plan.cfg_path).expanduser()) if plan.cfg_path else "none"
        if cfg_payload:
            session.write_radar_bytes(cfg_payload)
            if not cfg_payload.endswith(b"\n"):
                session.write_radar_bytes(b"\n")
        session.write_radar_bytes(b"sensorStart\n")

        # Split DATA timing is driven by the first MQTT DATA message. Local
        # wire command responses do not belong to the high-rate DATA window.
        capture_started = None
        capture_deadline = time.monotonic() + plan.duration + 10
        while time.monotonic() < capture_deadline:
            payload = session.read_raw()
            if payload:
                resp_file.write(payload)
                resp_file.flush()
                summary.response_bytes += len(payload)
                summary.wire_bytes += len(payload)
                if wire_file is not None:
                    wire_file.write(payload)
                    wire_file.flush()
                if capture_started is not None and time.monotonic() >= capture_started + plan.duration:
                    break
            if capture.stats["data_messages"] > 0 and capture_started is None:
                capture_started = time.monotonic()
            if capture_started is not None and time.monotonic() >= capture_started + plan.duration:
                break

        summary.data_bytes = int(capture.stats["data_bytes"])
        summary.source_bytes = summary.data_bytes
        summary.destination_bytes = summary.data_bytes
        if capture.stats["data_messages"] <= 0:
            summary.warnings.append("no MQTT DATA arrived before the collection deadline")
        if raw_open:
            session.write_radar_bytes(b"sensorStop\n")
            close_response = session.close_raw(escape=plan.escape.encode("ascii"))
            record_response(close_response)
            raw_open = False
            parsed_restored = True
    except Exception:
        cleanup_errors.append("split collection failed")
        raise
    finally:
        if raw_open:
            try:
                session.close_raw(escape=plan.escape.encode("ascii"))
                raw_open = False
                parsed_restored = True
            except Exception as exc:
                cleanup_errors.append(f"raw close: {exc}")
        if radar_started and session.parsed:
            try:
                session.send_control({"cmd": "radar", "action": "stop"})
                radar_stopped = True
            except Exception as exc:
                cleanup_errors.append(f"radar stop: {exc}")
        if client is not None:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception as exc:
                cleanup_errors.append(f"MQTT close: {exc}")
        if output_stack is not None:
            output_stack.close()
        summary.cleanup = CleanupReport(
            raw_closed=not raw_open,
            radar_stopped=radar_stopped,
            state_restored=parsed_restored,
            errors=tuple(cleanup_errors),
        )
        summary.duration_s = max(0.0, time.monotonic() - start)
        session.close()
    return summary


def write_summary(
    path: str | os.PathLike[str],
    summary: CollectionSummary,
    *,
    overwrite: bool = False,
) -> None:
    target = Path(path)
    with reserve_output_files((target,), overwrite=overwrite) as outputs:
        handle = outputs.handles[target.expanduser().resolve()]
        handle.write((json.dumps(summary.as_dict(), indent=2) + "\n").encode("utf-8"))
        handle.flush()


def collect_local(plan: CollectionPlan, expected_did: str | None = None, serial_factory=None) -> CollectionSummary:
    """Run a conservative local host collection session.

    The function intentionally does not guess radar framing.  It records the
    merged wire bytes and reports counters; callers that own the radar lifecycle
    can segment phases around this primitive.
    """

    plan.validate()
    summary = CollectionSummary()
    summary.transport = plan.transport
    session = LocalWireSession(plan, serial_factory=serial_factory)
    cfg_payload = None
    if plan.cfg_path:
        cfg_payload = Path(plan.cfg_path).read_bytes()
        if not cfg_payload:
            raise ValueError("cfg file is empty")
        summary.config_source = str(Path(plan.cfg_path).expanduser())
    else:
        summary.config_source = "none"
    start = time.monotonic()
    raw_open = False
    radar_started = False
    radar_stopped = False
    parsed_restored = False
    cleanup_errors: list[str] = []
    wire_file = None
    data_file = None
    resp_file = None

    def record_response(resp_file, response: Mapping[str, Any] | None) -> None:
        if not response:
            return
        line = (json.dumps(dict(response), separators=(",", ":")) + "\n").encode("utf-8")
        resp_file.write(line)
        resp_file.flush()
        summary.response_bytes += len(line)

    try:
        session.open()
        summary.identity = session.identify(expected_did)
        if summary.identity.board == "wdr" and plan.transport == "uart" and plan.raw_baud is not None:
            warning = "WDR DATA is 1250000 baud; current 1000000-baud UART adapters are not lossless"
            if not plan.allow_lossy:
                raise ValueError(warning + "; use native USB CDC, MQTT DATA, or --allow-lossy")
            summary.warnings.append("lossy WDR UART capture explicitly allowed")
        elif summary.identity.board in {"mini", "pro"} and plan.raw_baud == MAX_EXTERNAL_UART_BAUD:
            summary.warnings.append(
                "MINI/PRO radar DATA at 921600 baud has little margin at 1000000; verify drops on hardware"
            )
        output_paths = [Path(plan.data_output), Path(plan.resp_output)]
        if plan.wire_output:
            output_paths.append(Path(plan.wire_output))
        with reserve_output_files(output_paths, overwrite=plan.overwrite) as outputs:
            data_file = outputs.handles[Path(plan.data_output).expanduser().resolve()]
            resp_file = outputs.handles[Path(plan.resp_output).expanduser().resolve()]
            if plan.wire_output:
                wire_file = outputs.handles[Path(plan.wire_output).expanduser().resolve()]
            record_response(resp_file, session.last_response)
            start_response = session.send_control({"cmd": "radar", "action": "start", "mode": "host"})
            record_response(resp_file, start_response)
            radar_started = True
            raw_response = session.open_raw(channel="wire", escape=plan.escape)
            record_response(resp_file, raw_response)
            raw_open = True
            if cfg_payload is not None:
                session.write_radar_bytes(cfg_payload)
                if not cfg_payload.endswith(b"\n"):
                    session.write_radar_bytes(b"\n")
            session.write_radar_bytes(b"sensorStart\n")
            # A local host wire is merged, so the collector cannot identify
            # the first radar DATA frame separately from command responses.
            # Start the requested window at sensorStart and retain all bytes.
            capture_started = time.monotonic()
            capture_deadline = time.monotonic() + plan.duration + 10
            data_seen = False
            while time.monotonic() < capture_deadline:
                payload = session.read_raw()
                if payload:
                    data_seen = True
                    data_file.write(payload)
                    data_file.flush()
                    summary.data_bytes += len(payload)
                    summary.source_bytes += len(payload)
                    summary.destination_bytes += len(payload)
                    summary.wire_bytes += len(payload)
                    if wire_file is not None:
                        wire_file.write(payload)
                        wire_file.flush()
                    if time.monotonic() >= capture_started + plan.duration:
                        break
            if raw_open:
                try:
                    session.write_radar_bytes(b"sensorStop\n")
                except Exception as exc:
                    cleanup_errors.append(f"sensorStop: {exc}")
                try:
                    close_response = session.close_raw(escape=plan.escape.encode("ascii"))
                    record_response(resp_file, close_response)
                    raw_open = False
                    parsed_restored = True
                except Exception as exc:
                    cleanup_errors.append(f"raw close: {exc}")
            if not data_seen:
                summary.warnings.append("no raw DATA arrived before the collection deadline")
    except Exception:
        raise
    finally:
        if raw_open:
            try:
                close_response = session.close_raw(escape=plan.escape.encode("ascii"))
                raw_open = False
                parsed_restored = True
                if close_response:
                    if resp_file is not None:
                        record_response(resp_file, close_response)
            except Exception as exc:
                cleanup_errors.append(f"raw close: {exc}")
        if radar_started and session.parsed:
            try:
                session.send_control({"cmd": "radar", "action": "stop"})
                radar_stopped = True
            except Exception as exc:
                cleanup_errors.append(f"radar stop: {exc}")
        summary.cleanup = CleanupReport(
            raw_closed=not raw_open,
            radar_stopped=radar_stopped,
            state_restored=parsed_restored,
            errors=tuple(cleanup_errors),
        )
        summary.duration_s = max(0.0, time.monotonic() - start)
        session.close()
    return summary
