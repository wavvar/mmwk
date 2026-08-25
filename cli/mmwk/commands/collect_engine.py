"""Shared host/remote radar raw collection primitives.

The engine deliberately keeps transport mechanics separate from the public CLI
argument surface. Local wire sessions are byte-oriented after the raw route is
opened; MQTT sessions preserve broker chunks while sharing the same lifecycle,
output, and cleanup model.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading
import time
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Iterable, Mapping
from urllib.parse import unquote, urlparse


MAX_EXTERNAL_UART_BAUD = 1_000_000
DEFAULT_PARSED_BAUD = 115_200
DEFAULT_RAW_BAUD = 1_000_000
RAW_SWITCH_SETTLE_SECONDS = 0.15
# xWRL6432 can emit one final DATA frame after the sensorStop acknowledgement.
# Do not put the next runtime CLI command into that single-UART tail window.
RADAR_SENSOR_STOP_SETTLE_SECONDS = 0.30
RADAR_SENSOR_STOP_RETRY_SECONDS = 0.30
RAW_ESCAPE_GUARD_SECONDS = 1.25
RADAR_DATA_MAGIC = bytes.fromhex("0201040306050807")
MAX_DATA_READY_PREFIX = 1024 * 1024
RADAR_FRAME_HEADER_SIZE = 40
RADAR_FRAME_LENGTH_OFFSET = 12


class _RadarCommandIncompleteResponse(RuntimeError):
    pass


class _RadarCommandRejected(RuntimeError):
    def __init__(self, label: str, response: bytes):
        self.response = response
        super().__init__(f"radar rejected {label}: {response[-240:]!r}")


def _retryable_wdr_sensor_stop_rejection(response: bytes) -> bool:
    """Recognize a transport-truncated sensorStop rejection, not a semantic error."""

    match = re.search(
        rb"['\"]([^'\"]+)['\"] is not recognized as a cli command",
        response.lower(),
    )
    if not match:
        return False
    rejected = match.group(1).strip()
    return bool(rejected) and rejected != b"sensorstop" and b"sensorstop".startswith(rejected)


class _RadarCommandResponseStream:
    """Separate radar CLI text from DATA frames already in flight."""

    def __init__(self) -> None:
        self._pending = bytearray()
        self._line = bytearray()
        self._response = bytearray()
        self.done = False
        self.rejected = False
        self.binary_bytes = 0

    @staticmethod
    def _magic_suffix_length(payload: bytearray) -> int:
        limit = min(len(payload), len(RADAR_DATA_MAGIC) - 1)
        for length in range(limit, 0, -1):
            if payload[-length:] == RADAR_DATA_MAGIC[:length]:
                return length
        return 0

    def _finish_line(self) -> None:
        line = bytes(self._line)
        self._line.clear()
        self._response.extend(line + b"\n")
        lowered = line.strip().lower()
        if lowered == b"done":
            self.done = True
        elif any(token in lowered for token in (b"error", b"failed", b"not recognized")):
            self.rejected = True

    def _consume_unframed(self, payload: bytes) -> None:
        for value in payload:
            if value == 0x0A:
                self._finish_line()
            elif value == 0x0D or value == 0x09 or 0x20 <= value <= 0x7E:
                self._line.append(value)
            else:
                self.binary_bytes += len(self._line) + 1
                self._line.clear()

    def _incomplete_frame_terminal_at(self) -> int:
        """Find a CLI terminal line following a sensorStop-truncated frame.

        WDR shares radar DATA and CLI on one UART.  A final frame may stop
        after its header but before its advertised length, with ``Done``
        following immediately.  Waiting for the impossible remaining frame
        bytes would consume the CLI response as binary and make cleanup time
        out.  Limit recovery to terminal lines and only after a valid frame
        header, leaving ordinary partial frames buffered.
        """
        search_from = min(len(self._pending), RADAR_FRAME_LENGTH_OFFSET + 4)
        lowered = bytes(self._pending).lower()
        positions = [
            position
            for marker in (b"done\n", b"done\r\n", b"error", b"failed")
            if (position := lowered.find(marker, search_from)) >= 0
        ]
        return min(positions) if positions else -1

    def feed(self, payload: bytes) -> None:
        self._pending.extend(payload)
        while self._pending and not (self.done or self.rejected):
            magic_at = self._pending.find(RADAR_DATA_MAGIC)
            if magic_at == 0:
                length_end = RADAR_FRAME_LENGTH_OFFSET + 4
                if len(self._pending) < length_end:
                    return
                frame_length = int.from_bytes(
                    self._pending[RADAR_FRAME_LENGTH_OFFSET:length_end], "little"
                )
                if not RADAR_FRAME_HEADER_SIZE <= frame_length <= MAX_DATA_READY_PREFIX:
                    self._consume_unframed(bytes(self._pending[:1]))
                    del self._pending[:1]
                    continue
                if len(self._pending) < frame_length:
                    terminal_at = self._incomplete_frame_terminal_at()
                    if terminal_at >= 0:
                        self.binary_bytes += terminal_at
                        del self._pending[:terminal_at]
                        continue
                    return
                if self._line:
                    self.binary_bytes += len(self._line)
                    self._line.clear()
                del self._pending[:frame_length]
                self.binary_bytes += frame_length
                continue
            if magic_at > 0:
                prefix = bytes(self._pending[:magic_at])
                del self._pending[:magic_at]
                self._consume_unframed(prefix)
                continue

            keep = self._magic_suffix_length(self._pending)
            consume = len(self._pending) - keep
            if consume:
                prefix = bytes(self._pending[:consume])
                del self._pending[:consume]
                self._consume_unframed(prefix)
            return

    def response(self, *, include_partial: bool = False) -> bytes:
        payload = bytes(self._response)
        if include_partial and self._line:
            payload += bytes(self._line)
        return payload

    @property
    def buffered_bytes(self) -> int:
        return len(self._pending) + len(self._line) + len(self._response)


def _await_radar_command_response(
    read_raw,
    record_response,
    *,
    label: str,
    timeout: float,
) -> bytes:
    """Wait for a terminal radar CLI line while discarding in-flight DATA."""

    stream = _RadarCommandResponseStream()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = read_raw()
        if payload:
            stream.feed(payload)
            if stream.buffered_bytes > MAX_DATA_READY_PREFIX:
                response = stream.response(include_partial=True)
                record_response(response)
                raise RuntimeError(f"{label} response exceeded safety limit")
        if stream.done:
            response = stream.response()
            record_response(response)
            return response
        if stream.rejected:
            response = stream.response()
            record_response(response)
            raise _RadarCommandRejected(label, response)

    response = stream.response(include_partial=True)
    record_response(response)
    if not response:
        raise TimeoutError(f"timed out waiting for radar response to {label}")
    raise _RadarCommandIncompleteResponse(
        f"radar returned an incomplete response to {label}: {response[-240:]!r}"
    )


@dataclass(frozen=True)
class MqttEndpoint:
    """Resolved broker endpoint whose representation never exposes credentials."""

    host: str
    port: int
    tls: bool = False
    username: str = field(default="", repr=False)
    password: str = field(default="", repr=False)


def resolve_mqtt_endpoint(
    broker: str,
    default_port: int = 1883,
    *,
    username: str = "",
    password: str = "",
) -> MqttEndpoint:
    raw = str(broker or "").strip()
    if "://" not in raw:
        if raw.count(":") == 1:
            host, maybe_port = raw.rsplit(":", 1)
            if maybe_port.isdigit():
                return MqttEndpoint(
                    host=host or "localhost",
                    port=int(maybe_port),
                    username=username or "",
                    password=password or "",
                )
        return MqttEndpoint(
            host=raw or "localhost",
            port=int(default_port),
            username=username or "",
            password=password or "",
        )

    parsed = urlparse(raw)
    scheme = (parsed.scheme or "mqtt").lower()
    if scheme not in {"mqtt", "mqtts"}:
        raise ValueError("MQTT broker URI scheme must be mqtt or mqtts")
    use_tls = scheme == "mqtts"
    return MqttEndpoint(
        host=parsed.hostname or "localhost",
        port=int(parsed.port or (8883 if use_tls else default_port)),
        tls=use_tls,
        username=username or unquote(parsed.username or ""),
        password=password or unquote(parsed.password or ""),
    )


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
    data_output: str | None = None
    resp_output: str | None = None
    wire_output: str | None = None
    summary_output: str | None = None
    events_output: str | None = None
    attach: bool = False
    allow_lossy: bool = False
    overwrite: bool = False
    ctrl_transport: str | None = None
    data_transport: str | None = None
    data_ready_timeout: float = 10.0
    control_timeout: float = 10.0

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
        if self.data_ready_timeout <= 0:
            raise ValueError("data-ready timeout must be positive")
        if self.control_timeout <= 0:
            raise ValueError("control timeout must be positive")
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
        if self.attach and self.cfg_path:
            raise ValueError("--attach cannot be combined with --cfg")
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
        if (self.data_output is None) != (self.resp_output is None):
            raise ValueError("data and response outputs must both be explicit or both use defaults")


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


def resolve_output_set(
    plan: CollectionPlan,
    identity: LiveIdentity,
    *,
    timestamp: str | None = None,
    root: str | os.PathLike[str] | None = None,
) -> OutputSet:
    """Resolve explicit outputs or one DID/timestamp-scoped default set."""
    if plan.data_output is not None and plan.resp_output is not None:
        outputs = OutputSet(
            data=Path(plan.data_output),
            response=Path(plan.resp_output),
            wire=Path(plan.wire_output) if plan.wire_output else None,
            summary=Path(plan.summary_output) if plan.summary_output else None,
            events=Path(plan.events_output) if plan.events_output else None,
        )
        outputs.paths()
        return outputs

    stamp = timestamp or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    base = Path(root) if root is not None else Path.cwd() / "collections"
    directory = base / identity.did / stamp
    outputs = OutputSet(
        data=directory / "radar.sraw",
        response=directory / "commands.log",
        wire=Path(plan.wire_output) if plan.wire_output else None,
        summary=(
            Path(plan.summary_output)
            if plan.summary_output
            else directory / "summary.json"
        ),
        events=(
            Path(plan.events_output)
            if plan.events_output
            else directory / "events.jsonl"
        ),
    )
    outputs.paths()
    return outputs


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


def _result_payload(response: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(response, Mapping):
        return {}
    payload: Any = response.get("result", response)
    if isinstance(payload, Mapping) and isinstance(payload.get("data"), Mapping):
        payload = payload["data"]
    return dict(payload) if isinstance(payload, Mapping) else {}


def _control_tool_json(
    control,
    name: str,
    arguments: Mapping[str, Any],
    timeout: float,
) -> dict[str, Any] | list[Any]:
    if control is None:
        raise RuntimeError("collection requires a parsed control transport")
    result = control.call_tool(name, dict(arguments), timeout=timeout)
    if hasattr(control, "extract_text"):
        payload: Any = control.extract_text(result)
    elif isinstance(result, Mapping) and "text" in result:
        payload = result["text"]
    else:
        payload = result
    if isinstance(payload, (bytes, bytearray)):
        payload = bytes(payload).decode("utf-8")
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, (dict, list)):
        raise ValueError(f"{name} returned a non-object response")
    return payload


def _control_payload(
    control,
    name: str,
    arguments: Mapping[str, Any],
    timeout: float,
) -> dict[str, Any]:
    payload = _control_tool_json(control, name, arguments, timeout)
    if not isinstance(payload, Mapping):
        raise ValueError(f"{name} returned a non-object response")
    return _result_payload(payload)


def _route_contains(route: str, requested: str) -> bool:
    return route == requested or route == "both"


@dataclass(frozen=True)
class RawRouteSnapshot:
    radar: str = "auto"
    mode: str = "off"
    ctrl: str = "off"
    data: str = "off"
    baud: int | None = None
    escape: str | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "RawRouteSnapshot":
        radar = str(payload.get("radar") or "auto").strip().lower()
        mode = str(payload.get("mode") or "off").strip().lower()
        ctrl = str(payload.get("ctrl_route", payload.get("ctrl", "off"))).strip().lower()
        data = str(payload.get("data_route", payload.get("data", "off"))).strip().lower()
        valid_routes = {"off", "wire", "mqtt", "both"}
        if radar not in {"auto", "host"}:
            radar = "auto"
        if mode not in {"off", "runtime", "reconnect"}:
            mode = "off"
        if ctrl not in valid_routes:
            ctrl = "off"
        if data not in valid_routes:
            data = "off"
        baud_value = payload.get("current_baud", payload.get("baud"))
        try:
            baud = int(baud_value) if baud_value not in (None, "", 0) else None
        except (TypeError, ValueError):
            baud = None
        escape_value = payload.get("escape")
        escape = str(escape_value) if isinstance(escape_value, str) and escape_value else None
        return cls(radar=radar, mode=mode, ctrl=ctrl, data=data, baud=baud, escape=escape)

    @property
    def live(self) -> bool:
        return self.mode == "runtime" and (self.ctrl != "off" or self.data != "off")

    def data_uses(self, route: str) -> bool:
        return _route_contains(self.data, route)

    def restore_command(self) -> dict[str, Any]:
        command: dict[str, Any] = {"cmd": "radar", "action": "raw", "mode": self.mode}
        if self.mode == "off":
            command["channel"] = "both"
        elif self.mode == "reconnect":
            command["channel"] = "mqtt"
        else:
            command["ctrl"] = self.ctrl
            command["data"] = self.data
            if self.baud and self.data_uses("wire"):
                command["baud"] = self.baud
            if self.escape:
                command["escape"] = self.escape
        return command


@dataclass(frozen=True)
class RadarSnapshot:
    state: str = "unknown"
    mode: str = "auto"
    config: bytes | None = None

    @property
    def running(self) -> bool:
        return self.state == "running"


@dataclass
class MutationLedger:
    """Ordered record of successful device mutations owned by one collection."""

    entries: list[str] = field(default_factory=list)

    def record(self, name: str) -> None:
        if name not in self.entries:
            self.entries.append(name)

    def owns(self, name: str) -> bool:
        return name in self.entries


@dataclass(frozen=True)
class CleanupReport:
    raw_closed: bool = False
    radar_stopped: bool = False
    state_restored: bool = False
    parsed_restored: bool = False
    baud_restored: bool = False
    config_restored: bool = False
    lifecycle_restored: bool = False
    ownership_restored: bool = False
    route_restored: bool = False
    sensor_stopped: bool = False
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
    dropped_chunks: int = 0
    source_crc32: int = 0
    destination_crc32: int = 0
    config_source: str = ""
    transport: str = ""
    duration_s: float = 0.0
    interrupted: bool = False
    borrowed_route: bool = False
    outputs: dict[str, str] = field(default_factory=dict)
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
            "dropped_chunks": self.dropped_chunks,
            "source_crc32": self.source_crc32,
            "destination_crc32": self.destination_crc32,
            "config_source": self.config_source,
            "transport": self.transport,
            "duration_s": self.duration_s,
            "interrupted": self.interrupted,
            "borrowed_route": self.borrowed_route,
            "outputs": dict(self.outputs),
            "warnings": list(self.warnings),
            "cleanup": {
                "raw_closed": self.cleanup.raw_closed,
                "radar_stopped": self.cleanup.radar_stopped,
                "state_restored": self.cleanup.state_restored,
                "parsed_restored": self.cleanup.parsed_restored,
                "baud_restored": self.cleanup.baud_restored,
                "config_restored": self.cleanup.config_restored,
                "lifecycle_restored": self.cleanup.lifecycle_restored,
                "ownership_restored": self.cleanup.ownership_restored,
                "route_restored": self.cleanup.route_restored,
                "sensor_stopped": self.cleanup.sensor_stopped,
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
        self.response_history: list[dict[str, Any]] = []
        self.on_raw_write = None
        self.on_raw_read = None
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
        if self.plan.transport == "uart":
            # Local raw capture must own the physical UART because it changes
            # baud and switches from parsed lines to an unframed byte stream.
            # A proxy left by an earlier short-lived CLI command otherwise
            # keeps a second reader attached to the same adapter.
            from mmwk.transport import shutdown_uart_proxy

            shutdown_uart_proxy(self.plan.port, self.plan.baudrate)
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

    def _read_line(self, timeout: float, expected_seq: int | None = None) -> dict[str, Any]:
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
                    if expected_seq is not None:
                        candidate_seq = candidate.get("seq")
                        if candidate.get("type") == "event" or candidate_seq != expected_seq:
                            continue
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
        response = self._read_line(timeout, expected_seq=request["seq"])
        if response.get("ok") is False:
            error = response.get("error")
            if isinstance(error, Mapping):
                message = error.get("message") or error.get("code")
            else:
                message = error
            raise RuntimeError(str(message or "control request failed"))
        self.last_response = response
        self.response_history.append(response)
        return response

    def identify(self, expected_did: str | None = None, timeout: float = 10.0) -> LiveIdentity:
        response = self.send_control({"cmd": "node", "action": "info"}, timeout=timeout)
        payload = response.get("result", response)
        if isinstance(payload, Mapping) and isinstance(payload.get("data"), Mapping):
            payload = payload["data"]
        identity = LiveIdentity.from_payload(payload)
        identity.require_match(expected_did)
        return identity

    def query_raw(self, timeout: float | None = None) -> tuple[RawRouteSnapshot, dict[str, Any]]:
        response = self.send_control(
            {"cmd": "radar", "action": "raw"},
            timeout=self.plan.control_timeout if timeout is None else timeout,
        )
        return RawRouteSnapshot.from_payload(_result_payload(response)), response

    def query_radar(self, timeout: float | None = None) -> tuple[RadarSnapshot, dict[str, Any]]:
        response = self.send_control(
            {"cmd": "radar", "action": "status"},
            timeout=self.plan.control_timeout if timeout is None else timeout,
        )
        payload = _result_payload(response)
        mode = str(payload.get("mode") or "auto").strip().lower()
        if mode not in {"auto", "host"}:
            mode = "auto"
        state = str(payload.get("state") or "unknown").strip().lower()
        return RadarSnapshot(state=state, mode=mode), response

    def read_config(self, timeout: float | None = None) -> tuple[bytes, dict[str, Any]]:
        response = self.send_control(
            {"cmd": "radar.config", "action": "read"},
            timeout=self.plan.control_timeout if timeout is None else timeout,
        )
        cfg = _result_payload(response).get("cfg")
        if not isinstance(cfg, str):
            raise ValueError("radar.config read did not return cfg text")
        return cfg.encode("utf-8"), response

    def wait_until_running(self, timeout: float | None = None) -> dict[str, Any]:
        wait_timeout = self.plan.control_timeout if timeout is None else timeout
        deadline = time.monotonic() + max(wait_timeout, 0.1)
        last_state = "unknown"
        while time.monotonic() < deadline:
            snapshot, response = self.query_radar(timeout=max(0.1, deadline - time.monotonic()))
            last_state = snapshot.state
            if snapshot.running:
                return response
            if snapshot.state == "error":
                raise RuntimeError("radar entered error state while starting")
            time.sleep(0.1)
        raise TimeoutError(f"timed out waiting for radar status=running (last={last_state})")

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
        if self.on_raw_write is not None:
            self.on_raw_write(bytes(payload))
        return total

    def read_raw(self, size: int = 8192) -> bytes:
        if not self.raw_open:
            raise RuntimeError("raw route is not active")
        payload = bytes(self._require_serial().read(max(1, size)))
        if payload and self.on_raw_read is not None:
            self.on_raw_read(payload)
        return payload

    def _drain_raw_for(self, duration: float) -> None:
        """Keep consuming raw output while an escape guard is in progress."""
        serial = self._require_serial()
        deadline = time.monotonic() + max(0.0, duration)
        while time.monotonic() < deadline:
            payload = bytes(serial.read(8192))
            if payload and self.on_raw_read is not None:
                self.on_raw_read(payload)

    def close_raw(self, escape: bytes | None = None, timeout: float = 3.0) -> dict[str, Any] | None:
        if not self.raw_open:
            return None
        # The firmware only accepts the escape sequence after a full guard
        # interval without host ingress.  Continue reading during both guard
        # windows so a running WDR/WSR lifecycle cannot fill the native USB TX
        # queue and turn a clean route close into a dropped DATA chunk.
        self._drain_raw_for(RAW_ESCAPE_GUARD_SECONDS)
        self.write_radar_bytes(escape if escape is not None else self.plan.escape.encode("ascii"))
        self._drain_raw_for(RAW_ESCAPE_GUARD_SECONDS)
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


class MqttCaptureSession:
    """Thread-safe MQTT DATA/RESP sink with protocol-phase wait primitives."""

    def __init__(
        self,
        data_topic: str,
        resp_topic: str,
        data_fout: BinaryIO,
        resp_fout: BinaryIO,
        *,
        data_qos: int = 0,
        resp_qos: int = 1,
        require_data_magic: bool = False,
        capture_enabled: bool = True,
        wire_fout: BinaryIO | None = None,
    ) -> None:
        self.data_topic = data_topic
        self.resp_topic = resp_topic
        self.data_only = not bool(resp_topic)
        self.same_topic = bool(resp_topic) and data_topic == resp_topic
        self.expected_subscriptions = 1 if self.same_topic or self.data_only else 2
        self.data_fout = data_fout
        self.resp_fout = resp_fout
        self.wire_fout = wire_fout
        self.data_qos = int(data_qos)
        self.resp_qos = int(resp_qos)
        self.require_data_magic = bool(require_data_magic)
        self.capture_enabled = bool(capture_enabled)
        self.store_data = bool(capture_enabled)
        self.subscribed = threading.Event()
        self.data_ready = threading.Event()
        self.data_ready_monotonic: float | None = None
        self.connect_error: dict[str, Any] = {"rc": None}
        self.subscribe_error: dict[str, Any] = {"message": None}
        self.subscribe_state = {"acks": 0}
        self.connection_generation = 0
        self.client = None
        self._condition = threading.Condition()
        self._response_chunks: list[tuple[bytes, bool]] = []
        self._data_prefix = bytearray()
        self.stats = {
            "messages": 0,
            "total_bytes": 0,
            "data_messages": 0,
            "data_bytes": 0,
            "resp_messages": 0,
            "resp_bytes": 0,
            "duplicate_resp_messages": 0,
            "ignored_retained_messages": 0,
            "pre_ready_bytes": 0,
            "wire_bytes": 0,
        }

    def bind_client(self, client) -> None:
        self.client = client
        client.on_connect = self.on_connect
        client.on_subscribe = self.on_subscribe
        client.on_message = self.on_message
        if hasattr(client, "on_disconnect"):
            client.on_disconnect = self.on_disconnect

    def _subscribe_topic(self, client, topic: str, label: str, qos: int) -> bool:
        result, _ = client.subscribe(topic, qos=qos)
        if result != 0:
            self.subscribe_error["message"] = (
                f"subscribe failed for {label} topic {topic}: rc={result}"
            )
            return False
        return True

    def on_connect(self, client, userdata, flags, rc, *extra) -> None:
        if rc != 0:
            self.connect_error["rc"] = rc
            return
        with self._condition:
            self.connection_generation += 1
            self.subscribe_state["acks"] = 0
            self.subscribe_error["message"] = None
            self.subscribed.clear()
        if not self._subscribe_topic(client, self.data_topic, "data", self.data_qos):
            return
        if (
            not self.same_topic
            and not self.data_only
            and not self._subscribe_topic(client, self.resp_topic, "resp", self.resp_qos)
        ):
            return

    def on_disconnect(self, client, userdata, rc, *extra) -> None:
        self.subscribed.clear()

    def on_subscribe(self, client, userdata, mid, granted_qos, *extra) -> None:
        with self._condition:
            self.subscribe_state["acks"] += 1
            if self.subscribe_state["acks"] >= self.expected_subscriptions:
                self.subscribed.set()
                self._condition.notify_all()

    def _append_data(self, payload: bytes) -> None:
        if not self.store_data:
            return
        self.data_fout.write(payload)
        self.data_fout.flush()
        self.stats["data_messages"] += 1
        self.stats["data_bytes"] += len(payload)

    def _append_wire_unlocked(self, payload: bytes) -> None:
        """Append one observed raw-transport payload to the merged audit."""
        if self.wire_fout is not None:
            self.wire_fout.write(payload)
            self.wire_fout.flush()
        self.stats["wire_bytes"] += len(payload)

    def audit_wire(self, payload: bytes) -> None:
        """Record outgoing or non-MQTT bytes in the same serialized audit."""
        with self._condition:
            self._append_wire_unlocked(bytes(payload))

    def _handle_data(self, payload: bytes) -> None:
        if not self.capture_enabled:
            return
        if self.data_ready.is_set():
            self._append_data(payload)
            return
        if not self.require_data_magic:
            self._append_data(payload)
            self.data_ready_monotonic = time.monotonic()
            self.data_ready.set()
            return

        self._data_prefix.extend(payload)
        magic_at = self._data_prefix.find(RADAR_DATA_MAGIC)
        if magic_at < 0:
            if len(self._data_prefix) > MAX_DATA_READY_PREFIX:
                self.subscribe_error["message"] = (
                    "MQTT DATA-ready prefix exceeded safety limit without radar magic"
                )
                self._data_prefix.clear()
            return
        self.stats["pre_ready_bytes"] += magic_at
        framed = bytes(self._data_prefix[magic_at:])
        self._data_prefix.clear()
        self._append_data(framed)
        self.data_ready_monotonic = time.monotonic()
        self.data_ready.set()

    def on_message(self, client, userdata, msg) -> None:
        payload = bytes(msg.payload)
        retained = bool(getattr(msg, "retain", False))
        with self._condition:
            if retained:
                self.stats["ignored_retained_messages"] += 1
                return
            self._append_wire_unlocked(payload)
            self.stats["messages"] += 1
            self.stats["total_bytes"] += len(payload)
            if msg.topic == self.data_topic:
                self._handle_data(payload)
                if self.same_topic:
                    self.resp_fout.write(payload)
                    self.resp_fout.flush()
                    self.stats["resp_messages"] += 1
                    self.stats["resp_bytes"] += len(payload)
                    self._response_chunks.append(
                        (payload, bool(getattr(msg, "dup", False)))
                    )
            elif not self.data_only and msg.topic == self.resp_topic:
                self.resp_fout.write(payload)
                self.resp_fout.flush()
                duplicated = bool(getattr(msg, "dup", False))
                self.stats["resp_messages"] += 1
                self.stats["resp_bytes"] += len(payload)
                if duplicated:
                    self.stats["duplicate_resp_messages"] += 1
                self._response_chunks.append((payload, duplicated))
            self._condition.notify_all()

    def start_capture(self) -> None:
        with self._condition:
            self.capture_enabled = True
            self.store_data = True
            self.data_ready.clear()
            self.data_ready_monotonic = None
            self._data_prefix.clear()

    def start_probe(self) -> None:
        with self._condition:
            self.capture_enabled = True
            self.store_data = False
            self.data_ready.clear()
            self.data_ready_monotonic = None
            self._data_prefix.clear()

    def stop_capture(self) -> None:
        with self._condition:
            self.capture_enabled = False
            self.store_data = False
            self._data_prefix.clear()

    def response_checkpoint(self) -> int:
        with self._condition:
            return len(self._response_chunks)

    def wait_for_command_done(self, checkpoint: int, timeout: float) -> bool:
        deadline = time.monotonic() + max(0.0, timeout)
        assembled = bytearray()
        cursor = max(0, int(checkpoint))
        with self._condition:
            while True:
                while cursor < len(self._response_chunks):
                    payload, duplicated = self._response_chunks[cursor]
                    cursor += 1
                    if duplicated:
                        continue
                    assembled.extend(payload)
                    lowered = bytes(assembled).lower()
                    if any(token in lowered for token in (b"error", b"failed", b"not recognized")):
                        return False
                    if b"done" in lowered:
                        return True
                    if len(assembled) > MAX_DATA_READY_PREFIX:
                        return False
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)

    def wait_for_data_ready(self, timeout: float) -> bool:
        return self.data_ready.wait(max(0.0, timeout))


def _new_mqtt_client(client_id: str):
    import paho.mqtt.client as mqtt

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


def _configure_mqtt_client(client, endpoint: MqttEndpoint, ca_cert: str | None) -> None:
    if endpoint.username:
        client.username_pw_set(endpoint.username, endpoint.password or None)
    if endpoint.tls:
        if ca_cert:
            client.tls_set(ca_certs=ca_cert)
        else:
            client.tls_set()


def _publish_mqtt_command(
    client,
    capture: MqttCaptureSession,
    topic: str,
    payload: bytes,
    *,
    label: str,
    timeout: float,
    published_callback=None,
) -> None:
    checkpoint = capture.response_checkpoint()
    capture.audit_wire(payload)
    info = client.publish(topic, bytes(payload), qos=1, retain=False)
    result_code = getattr(info, "rc", None)
    if result_code is None and isinstance(info, tuple) and info:
        result_code = info[0]
    if result_code not in (None, 0):
        raise RuntimeError(f"MQTT publish failed for {label}: rc={result_code}")
    wait_for_publish = getattr(info, "wait_for_publish", None)
    if callable(wait_for_publish):
        published = wait_for_publish(timeout=max(timeout, 0.1))
        if published is False:
            raise TimeoutError(f"timed out publishing MQTT command for {label}")
    if published_callback is not None:
        published_callback()
    if not capture.wait_for_command_done(checkpoint, timeout):
        raise TimeoutError(f"timed out waiting for MQTT raw response to {label}")


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


def _mqtt_topic_set(
    identity: LiveIdentity,
    node_info: Mapping[str, Any],
    *,
    data_topic: str | None,
    resp_topic: str | None,
    cmd_topic: str | None,
    prod: str,
    oid: str,
    cid: str,
) -> dict[str, str]:
    from mmwk.mqtt_topics import build_mqtt_topics

    resolved_prod = str(node_info.get("prod") or prod or "mmwk")
    resolved_oid = str(node_info.get("oid") or oid or "mmwk")
    resolved_cid = str(node_info.get("cid") or cid or "")
    defaults = build_mqtt_topics(
        did=identity.did,
        prod=resolved_prod,
        oid=resolved_oid,
        cid=resolved_cid,
        include_raw_cmd=True,
    )
    return {
        "data": str(data_topic or node_info.get("raw_data") or defaults["raw_data"]),
        "resp": str(resp_topic or node_info.get("raw_resp") or defaults["raw_resp"]),
        "cmd": str(cmd_topic or node_info.get("raw_cmd") or defaults["raw_cmd"]),
    }


def _require_mqtt_topic_identity(
    topic: str,
    identity: LiveIdentity,
    node_info: Mapping[str, Any],
    *,
    cid: str = "",
) -> None:
    """Reject a topic routed to neither the live DID nor its claimed id."""
    segments = {
        segment.strip().lower()
        for segment in str(topic).split("/")
        if segment.strip()
    }
    accepted = {identity.did}
    for value in (node_info.get("cid"), cid):
        if isinstance(value, str) and value.strip():
            accepted.add(value.strip().lower())
    if segments.isdisjoint(accepted):
        raise ValueError(
            "MQTT raw topic identity does not agree with the live device DID or claimed id"
        )


def collect_mqtt(
    plan: CollectionPlan,
    *,
    control,
    broker: str = "",
    mqtt_port: int = 1883,
    expected_did: str | None = None,
    data_topic: str | None = None,
    resp_topic: str | None = None,
    cmd_topic: str | None = None,
    prod: str = "mmwk",
    oid: str = "mmwk",
    cid: str = "",
    mqtt_username: str = "",
    mqtt_password: str = "",
    mqtt_ca: str | None = None,
    client_factory=None,
    stop_event: threading.Event | None = None,
    progress_callback=None,
) -> CollectionSummary:
    """Collect host or borrowed DATA over MQTT with snapshot-driven cleanup."""

    plan.validate()
    if plan.transport != "mqtt" or plan.ctrl_transport is not None:
        raise ValueError("collect_mqtt requires a non-split MQTT plan")
    if control is None:
        raise ValueError("MQTT collection requires parsed control for identity and route safety")
    if plan.mode == "auto" and not plan.attach:
        raise ValueError("auto collection requires --attach to an existing MQTT DATA route")

    explicit_cfg: bytes | None = None
    explicit_source = ""
    explicit_sensor_stop = b"sensorStop\n"
    explicit_sensor_start = b"sensorStart\n"
    if plan.cfg_path:
        cfg_path = Path(plan.cfg_path).expanduser()
        explicit_source = str(cfg_path)
        explicit_payload = cfg_path.read_bytes()
        explicit_sensor_stop, explicit_sensor_start = _radar_lifecycle_commands(
            explicit_payload, explicit_source
        )
        explicit_cfg = _prepare_config(explicit_payload, explicit_source)

    summary = CollectionSummary(transport="mqtt", borrowed_route=plan.attach)
    ledger = MutationLedger()
    primary_error: BaseException | None = None
    cleanup_errors: list[str] = []
    capture_elapsed = 0.0
    client = None
    capture: MqttCaptureSession | None = None

    node_info = _control_payload(
        control, "node", {"action": "info"}, plan.control_timeout
    )
    summary.identity = LiveIdentity.from_payload(node_info)
    summary.identity.require_match(expected_did)
    raw_payload = _control_payload(
        control, "radar", {"action": "raw"}, plan.control_timeout
    )
    raw_before = RawRouteSnapshot.from_payload(raw_payload)
    radar_payload = _control_payload(
        control, "radar", {"action": "status"}, plan.control_timeout
    )
    radar_before = RadarSnapshot(
        state=str(radar_payload.get("state") or "unknown").strip().lower(),
        mode=str(radar_payload.get("mode") or raw_before.radar).strip().lower(),
    )
    if radar_before.mode not in {"auto", "host"}:
        raise ValueError(f"invalid radar ownership snapshot: {radar_before.mode}")
    if radar_before.mode != raw_before.radar:
        raise ValueError(
            "incomplete ownership snapshot: radar status and raw status disagree "
            f"({radar_before.mode} != {raw_before.radar})"
        )

    prior_sensor_stop = b"sensorStop\n"
    prior_sensor_start = b"sensorStart\n"
    collection_sensor_stop = b"sensorStop\n"
    collection_sensor_start = b"sensorStart\n"
    if plan.attach:
        if not raw_before.live or not raw_before.data_uses("mqtt"):
            raise ValueError(
                "--attach requires an already-active MQTT DATA route; it will not create one"
            )
        if plan.mode != raw_before.radar:
            raise ValueError(
                f"--attach ownership mismatch: requested {plan.mode}, active {raw_before.radar}"
            )
        prior_cfg = None
        collection_cfg = None
        summary.config_source = "borrowed:unchanged"
    else:
        if raw_before.live:
            raise ValueError(
                "a host raw route is already active; close it first or use --attach "
                "for a borrowed MQTT DATA route"
            )
        cfg_payload = _control_payload(
            control, "radar.config", {"action": "read"}, plan.control_timeout
        )
        cfg_text = cfg_payload.get("cfg")
        if not isinstance(cfg_text, str):
            if explicit_cfg is None or (raw_before.radar == "host" and radar_before.running):
                raise ValueError(
                    "a complete restorable radar config snapshot is unavailable; "
                    "provide --cfg or use --attach"
                )
            prior_cfg = None
        else:
            prior_sensor_stop, prior_sensor_start = _radar_lifecycle_commands(
                cfg_text.encode("utf-8"), "device:radar.config"
            )
            prior_cfg = _prepare_config(
                cfg_text.encode("utf-8"), "device:radar.config"
            )
        if explicit_cfg is not None:
            explicit_cfg = _prepare_runtime_config(
                explicit_cfg, explicit_source, summary.identity.board
            )
        if prior_cfg is not None:
            prior_cfg = _prepare_runtime_config(
                prior_cfg, "device:radar.config", summary.identity.board
            )
        collection_cfg = explicit_cfg if explicit_cfg is not None else prior_cfg
        if explicit_cfg is not None:
            collection_sensor_stop = explicit_sensor_stop
            collection_sensor_start = explicit_sensor_start
        else:
            collection_sensor_stop = prior_sensor_stop
            collection_sensor_start = prior_sensor_start
        summary.config_source = (
            explicit_source if explicit_cfg is not None else "device:radar.config"
        )
        if collection_cfg is None:
            raise ValueError("no validated radar cfg is available for host MQTT collection")

    network_info: dict[str, Any] = {}
    try:
        network_info = _control_payload(
            control, "network", {"action": "mqtt"}, plan.control_timeout
        )
    except Exception:
        network_info = {}
    broker_value = str(
        broker
        or network_info.get("uri")
        or network_info.get("mqtt_uri")
        or node_info.get("uri")
        or "localhost"
    )
    endpoint = resolve_mqtt_endpoint(
        broker_value,
        mqtt_port,
        username=mqtt_username or str(network_info.get("user") or ""),
        password=mqtt_password or str(network_info.get("pass") or ""),
    )
    topics = _mqtt_topic_set(
        summary.identity,
        node_info,
        data_topic=data_topic,
        resp_topic=resp_topic,
        cmd_topic=cmd_topic,
        prod=prod,
        oid=oid,
        cid=cid,
    )
    _require_mqtt_topic_identity(topics["data"], summary.identity, node_info, cid=cid)
    if plan.mode != "auto":
        _require_mqtt_topic_identity(topics["resp"], summary.identity, node_info, cid=cid)
        _require_mqtt_topic_identity(topics["cmd"], summary.identity, node_info, cid=cid)
    outputs_set = resolve_output_set(plan, summary.identity)
    summary.outputs = {
        "data": str(outputs_set.data),
        "response": str(outputs_set.response),
        **({"wire": str(outputs_set.wire)} if outputs_set.wire is not None else {}),
        **({"summary": str(outputs_set.summary)} if outputs_set.summary is not None else {}),
        **({"events": str(outputs_set.events)} if outputs_set.events is not None else {}),
    }

    raw_closed = True
    sensor_stopped = True
    parsed_restored = True
    baud_restored = True
    config_restored = True
    lifecycle_restored = True
    ownership_restored = True
    route_restored = True

    with reserve_output_files(outputs_set.paths(), overwrite=plan.overwrite) as output_stack:
        data_file = output_stack.handles[outputs_set.data.expanduser().resolve()]
        resp_file = output_stack.handles[outputs_set.response.expanduser().resolve()]
        wire_file = (
            output_stack.handles[outputs_set.wire.expanduser().resolve()]
            if outputs_set.wire is not None
            else None
        )
        summary_file = (
            output_stack.handles[outputs_set.summary.expanduser().resolve()]
            if outputs_set.summary is not None
            else None
        )
        events_file = (
            output_stack.handles[outputs_set.events.expanduser().resolve()]
            if outputs_set.events is not None
            else None
        )
        event_lock = threading.Lock()

        def record_event(phase: str, **details: Any) -> None:
            if progress_callback is not None:
                progress_callback(phase, dict(details))
            if events_file is None:
                return
            payload = {"ts": time.time(), "phase": phase, **details}
            encoded = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
            with event_lock:
                events_file.write(encoded)
                events_file.flush()

        def control_call(name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
            result = _control_payload(control, name, arguments, plan.control_timeout)
            record_event("control", service=name, action=arguments.get("action", ""))
            return result

        def cleanup_action(label: str, action) -> bool:
            try:
                action()
                record_event("cleanup", item=label, ok=True)
                return True
            except Exception as exc:
                cleanup_errors.append(f"{label}: {exc}")
                record_event("cleanup", item=label, ok=False, error=str(exc))
                return False

        def wait_control_running() -> None:
            deadline = time.monotonic() + plan.control_timeout
            last_state = "unknown"
            while time.monotonic() < deadline:
                payload = control_call("radar", {"action": "status"})
                last_state = str(payload.get("state") or "unknown").strip().lower()
                if last_state == "running":
                    return
                if last_state == "error":
                    raise RuntimeError("radar entered error state while starting")
                time.sleep(0.1)
            raise TimeoutError(
                f"timed out waiting for radar status=running (last={last_state})"
            )

        def send_command(command: bytes, label: str, *, published_callback=None) -> None:
            if capture is None or client is None:
                raise RuntimeError("MQTT raw command route is unavailable")
            payload = command if command.endswith(b"\n") else command + b"\n"
            _publish_mqtt_command(
                client,
                capture,
                topics["cmd"],
                payload,
                label=label,
                timeout=plan.control_timeout,
                published_callback=published_callback,
            )
            record_event("raw_cmd", label=label, bytes=len(payload), qos=1)
            settle_seconds = _radar_command_settle_seconds(
                summary.identity.board, payload
            )
            if settle_seconds > 0.0:
                time.sleep(settle_seconds)

        def send_config(config: bytes, label: str) -> None:
            for raw_line in config.splitlines():
                line = raw_line.strip()
                if not line or line.startswith((b"%", b"#")):
                    continue
                send_command(line + b"\n", label)

        try:
            factory = client_factory or _new_mqtt_client
            client_id = f"mmwk_collect_{summary.identity.did}_{int(time.time())}"
            try:
                client = factory(client_id)
            except TypeError:
                client = factory()
            _configure_mqtt_client(client, endpoint, mqtt_ca)
            capture = MqttCaptureSession(
                topics["data"],
                "" if plan.mode == "auto" else topics["resp"],
                data_file,
                resp_file,
                data_qos=0,
                resp_qos=1,
                require_data_magic=True,
                capture_enabled=False,
                wire_fout=wire_file,
            )
            capture.bind_client(client)
            client.connect(endpoint.host, endpoint.port, 60)
            client.loop_start()
            if not capture.subscribed.wait(max(plan.control_timeout, 0.1)):
                message = capture.subscribe_error.get("message")
                if message:
                    raise RuntimeError(str(message))
                rc = capture.connect_error.get("rc")
                if rc is not None:
                    raise ConnectionError(f"MQTT connect failed: rc={rc}")
                raise TimeoutError("timed out waiting for MQTT subscription acknowledgement")
            record_event(
                "mqtt_ready",
                generation=capture.connection_generation,
                data_qos=0,
                resp_qos=None if plan.mode == "auto" else 1,
            )

            if plan.attach:
                capture.start_capture()
                if not capture.wait_for_data_ready(plan.data_ready_timeout):
                    raise TimeoutError("timed out waiting for attached MQTT DATA-ready frame magic")
                capture_started = capture.data_ready_monotonic or time.monotonic()
                record_event("data_ready", borrowed=True)
                deadline = capture_started + plan.duration
                while time.monotonic() < deadline and not (
                    stop_event is not None and stop_event.is_set()
                ):
                    time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
                capture_elapsed = max(0.0, time.monotonic() - capture_started)
                capture.stop_capture()
            else:
                if raw_before.mode == "reconnect":
                    control_call(
                        "radar", {"action": "raw", "mode": "off", "channel": "mqtt"}
                    )
                    ledger.record("route_displaced")
                    route_restored = False

                if raw_before.radar != "host" or not radar_before.running:
                    control_call("radar", {"action": "start", "mode": "host"})
                    ledger.record("radar_started")
                    lifecycle_restored = False
                    if raw_before.radar != "host":
                        ledger.record("ownership_changed")
                        ownership_restored = False
                    wait_control_running()

                control_call(
                    "radar", {"action": "raw", "mode": "runtime", "channel": "mqtt"}
                )
                ledger.record("raw_open")
                raw_closed = False

                send_command(collection_sensor_stop, "collection sensorStop")
                ledger.record("sensor_stopped_for_collection")
                if radar_before.running:
                    lifecycle_restored = False
                if raw_before.radar == "host" and radar_before.running:
                    ledger.record("config_displaced")
                    config_restored = False
                send_config(collection_cfg, "collection cfg")
                capture.start_capture()

                def mark_sensor_started() -> None:
                    nonlocal sensor_stopped
                    ledger.record("sensor_started")
                    sensor_stopped = False

                send_command(
                    collection_sensor_start,
                    "collection sensorStart",
                    published_callback=mark_sensor_started,
                )
                if not capture.wait_for_data_ready(plan.data_ready_timeout):
                    raise TimeoutError("timed out waiting for MQTT DATA-ready frame magic")
                capture_started = capture.data_ready_monotonic or time.monotonic()
                record_event("data_ready", borrowed=False)
                deadline = capture_started + plan.duration
                while time.monotonic() < deadline and not (
                    stop_event is not None and stop_event.is_set()
                ):
                    time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
                capture_elapsed = max(0.0, time.monotonic() - capture_started)
                capture.stop_capture()
        except KeyboardInterrupt as exc:
            summary.interrupted = True
            primary_error = exc
            if capture is not None:
                capture.stop_capture()
            record_event("interrupt", count=1)
        except BaseException as exc:
            primary_error = exc
            if capture is not None:
                capture.stop_capture()
            summary.warnings.append(f"collection failed: {type(exc).__name__}: {exc}")
            record_event("failure", error_type=type(exc).__name__, error=str(exc))
        finally:
            if not plan.attach and capture is not None and client is not None:
                if ledger.owns("sensor_started"):
                    sensor_stopped = cleanup_action(
                        "sensorStop",
                        lambda: send_command(
                            collection_sensor_stop, "cleanup sensorStop"
                        ),
                    )

                if ledger.owns("config_displaced"):
                    def restore_config() -> None:
                        if prior_cfg is None:
                            raise RuntimeError("prior config snapshot is missing")
                        send_config(prior_cfg, "restore cfg")

                    config_restored = cleanup_action("config restore", restore_config)
                    if config_restored:
                        def restore_running() -> None:
                            capture.start_probe()
                            send_command(prior_sensor_start, "restore sensorStart")
                            if not capture.wait_for_data_ready(plan.data_ready_timeout):
                                raise TimeoutError(
                                    "timed out proving restored MQTT radar lifecycle"
                                )
                            capture.stop_capture()

                        lifecycle_restored = cleanup_action(
                            "running lifecycle restore", restore_running
                        )

                if ledger.owns("raw_open"):
                    raw_closed = cleanup_action(
                        "raw close",
                        lambda: control_call(
                            "radar",
                            {"action": "raw", "mode": "off", "channel": "mqtt"},
                        ),
                    )

                if raw_closed:
                    def verify_raw_closed() -> None:
                        payload = control_call("radar", {"action": "raw"})
                        snapshot = RawRouteSnapshot.from_payload(payload)
                        if snapshot.live:
                            raise RuntimeError("collector-owned MQTT raw route is still active")
                        _apply_raw_metrics(summary, payload)

                    verified_closed = cleanup_action(
                        "raw close verification", verify_raw_closed
                    )
                    raw_closed = raw_closed and verified_closed

                if ledger.owns("radar_started"):
                    if raw_before.radar != "host":
                        def restore_ownership() -> None:
                            control_call(
                                "radar", {"action": "start", "mode": raw_before.radar}
                            )
                            wait_control_running()

                        ownership_restored = cleanup_action(
                            "ownership restore", restore_ownership
                        )
                        if ownership_restored and radar_before.running:
                            lifecycle_restored = True
                    if not radar_before.running and ownership_restored:
                        lifecycle_restored = cleanup_action(
                            "stopped lifecycle restore",
                            lambda: control_call("radar", {"action": "stop"}),
                        )

                if ledger.owns("route_displaced"):
                    restore = raw_before.restore_command()
                    restore.pop("cmd", None)
                    route_restored = cleanup_action(
                        "raw route restore",
                        lambda: control_call("radar", restore),
                    )
            elif plan.attach:
                try:
                    final_raw = _control_payload(
                        control, "radar", {"action": "raw"}, plan.control_timeout
                    )
                    _apply_raw_metrics(summary, final_raw)
                    if not RawRouteSnapshot.from_payload(final_raw).data_uses("mqtt"):
                        route_restored = False
                        cleanup_errors.append("borrowed MQTT DATA route disappeared during capture")
                except Exception as exc:
                    route_restored = False
                    cleanup_errors.append(f"borrowed route verification: {exc}")

            if client is not None:
                try:
                    client.loop_stop()
                except Exception:
                    pass
                try:
                    client.disconnect()
                except Exception:
                    pass

            if capture is not None:
                summary.data_bytes = int(capture.stats["data_bytes"])
                summary.response_bytes = int(capture.stats["resp_bytes"])
                summary.wire_bytes = int(capture.stats["wire_bytes"])
                summary.destination_bytes = summary.destination_bytes or summary.data_bytes
                summary.source_bytes = summary.source_bytes or summary.data_bytes
                if capture.stats["duplicate_resp_messages"]:
                    summary.warnings.append(
                        "duplicate QoS 1 response chunks were preserved without advancing phases"
                    )
            summary.duration_s = capture_elapsed
            state_restored = all((
                raw_closed,
                parsed_restored,
                baud_restored,
                config_restored,
                lifecycle_restored,
                ownership_restored,
                route_restored,
                sensor_stopped,
            ))
            summary.cleanup = CleanupReport(
                raw_closed=raw_closed,
                radar_stopped=sensor_stopped,
                state_restored=state_restored,
                parsed_restored=parsed_restored,
                baud_restored=baud_restored,
                config_restored=config_restored,
                lifecycle_restored=lifecycle_restored,
                ownership_restored=ownership_restored,
                route_restored=route_restored,
                sensor_stopped=sensor_stopped,
                errors=tuple(cleanup_errors),
            )
            record_event(
                "complete" if primary_error is None else "cleanup_complete",
                cleanup=summary.as_dict()["cleanup"],
            )
            if summary_file is not None:
                summary_file.write(
                    (json.dumps(summary.as_dict(), indent=2) + "\n").encode("utf-8")
                )
                summary_file.flush()

    if primary_error is not None:
        raise primary_error
    return summary


def collect_reconnect_mqtt(
    plan: CollectionPlan,
    *,
    control,
    broker: str = "",
    mqtt_port: int = 1883,
    expected_did: str | None = None,
    data_topic: str | None = None,
    prod: str = "mmwk",
    oid: str = "mmwk",
    cid: str = "",
    mqtt_username: str = "",
    mqtt_password: str = "",
    mqtt_ca: str | None = None,
    client_factory=None,
    stop_event: threading.Event | None = None,
    progress_callback=None,
) -> CollectionSummary:
    """Arm one reconnect generation, reboot, and capture its MQTT DATA session."""

    plan.validate()
    if plan.transport != "mqtt" or plan.mode != "auto" or plan.attach:
        raise ValueError("reconnect collection requires a non-attach auto MQTT plan")
    if control is None:
        raise ValueError("reconnect collection requires parsed MQTT control")

    node_before = _control_payload(
        control, "node", {"action": "info"}, plan.control_timeout
    )
    identity = LiveIdentity.from_payload(node_before)
    identity.require_match(expected_did)
    raw_before_payload = _control_payload(
        control, "radar", {"action": "raw"}, plan.control_timeout
    )
    raw_before = RawRouteSnapshot.from_payload(raw_before_payload)
    if raw_before.radar != "auto":
        raise ValueError("reconnect collection requires auto radar ownership")
    if raw_before.live or raw_before.mode == "reconnect":
        raise ValueError("reconnect collection requires raw mode=off before arming")

    network_info: dict[str, Any] = {}
    try:
        network_info = _control_payload(
            control, "network", {"action": "mqtt"}, plan.control_timeout
        )
    except Exception:
        network_info = {}
    endpoint = resolve_mqtt_endpoint(
        str(
            broker
            or network_info.get("uri")
            or network_info.get("mqtt_uri")
            or node_before.get("uri")
            or "localhost"
        ),
        mqtt_port,
        username=mqtt_username or str(network_info.get("user") or ""),
        password=mqtt_password or str(network_info.get("pass") or ""),
    )
    topics = _mqtt_topic_set(
        identity,
        node_before,
        data_topic=data_topic,
        resp_topic=None,
        cmd_topic=None,
        prod=prod,
        oid=oid,
        cid=cid,
    )
    _require_mqtt_topic_identity(topics["data"], identity, node_before, cid=cid)
    outputs_set = resolve_output_set(plan, identity)
    summary = CollectionSummary(
        identity=identity,
        transport="mqtt-reconnect",
        config_source="reconnect:auto",
        outputs={
            "data": str(outputs_set.data),
            "response": str(outputs_set.response),
            **({"wire": str(outputs_set.wire)} if outputs_set.wire is not None else {}),
            **({"summary": str(outputs_set.summary)} if outputs_set.summary is not None else {}),
            **({"events": str(outputs_set.events)} if outputs_set.events is not None else {}),
        },
    )
    client = None
    capture: MqttCaptureSession | None = None
    armed = False
    primary_error: BaseException | None = None
    cleanup_errors: list[str] = []
    capture_elapsed = 0.0
    raw_closed = True

    with reserve_output_files(outputs_set.paths(), overwrite=plan.overwrite) as output_stack:
        data_file = output_stack.handles[outputs_set.data.expanduser().resolve()]
        resp_file = output_stack.handles[outputs_set.response.expanduser().resolve()]
        wire_file = (
            output_stack.handles[outputs_set.wire.expanduser().resolve()]
            if outputs_set.wire is not None
            else None
        )
        summary_file = (
            output_stack.handles[outputs_set.summary.expanduser().resolve()]
            if outputs_set.summary is not None
            else None
        )
        events_file = (
            output_stack.handles[outputs_set.events.expanduser().resolve()]
            if outputs_set.events is not None
            else None
        )

        def record_event(phase: str, **details: Any) -> None:
            if progress_callback is not None:
                progress_callback(phase, dict(details))
            if events_file is None:
                return
            events_file.write(
                (json.dumps({"ts": time.time(), "phase": phase, **details}, separators=(",", ":")) + "\n").encode("utf-8")
            )
            events_file.flush()

        try:
            factory = client_factory or _new_mqtt_client
            try:
                client = factory(f"mmwk_reconnect_{identity.did}_{int(time.time())}")
            except TypeError:
                client = factory()
            _configure_mqtt_client(client, endpoint, mqtt_ca)
            capture = MqttCaptureSession(
                topics["data"],
                "",
                data_file,
                resp_file,
                data_qos=0,
                require_data_magic=True,
                capture_enabled=False,
                wire_fout=wire_file,
            )
            capture.bind_client(client)
            client.connect(endpoint.host, endpoint.port, 60)
            client.loop_start()
            if not capture.subscribed.wait(plan.control_timeout):
                raise TimeoutError("timed out waiting for reconnect MQTT DATA subscription")
            subscribed_generation = capture.connection_generation
            record_event("mqtt_ready", generation=subscribed_generation, data_qos=0)

            capture.start_capture()
            arm_payload = _control_payload(
                control,
                "radar",
                {"action": "raw", "mode": "reconnect", "channel": "mqtt"},
                plan.control_timeout,
            )
            armed_snapshot = RawRouteSnapshot.from_payload(arm_payload)
            if armed_snapshot.mode != "reconnect" or not armed_snapshot.data_uses("mqtt"):
                raise RuntimeError("device did not acknowledge the MQTT reconnect arm")
            armed = True
            raw_closed = False
            record_event("reconnect_armed")

            _control_payload(
                control, "node", {"action": "reboot"}, max(plan.control_timeout, 15.0)
            )
            record_event("reboot_acknowledged")

            baseline_uptime = node_before.get("uptime_sec")
            generation_seen = False
            deadline = time.monotonic() + max(plan.control_timeout, plan.data_ready_timeout)
            last_mode = "unknown"
            while time.monotonic() < deadline:
                try:
                    node_after = _control_payload(
                        control, "node", {"action": "info"}, plan.control_timeout
                    )
                    LiveIdentity.from_payload(node_after).require_match(identity.did)
                    after_uptime = node_after.get("uptime_sec")
                    if baseline_uptime is None or after_uptime != baseline_uptime:
                        generation_seen = True
                    raw_after_payload = _control_payload(
                        control, "radar", {"action": "raw"}, plan.control_timeout
                    )
                    raw_after = RawRouteSnapshot.from_payload(raw_after_payload)
                    last_mode = raw_after.mode
                    if raw_after.mode == "runtime" and raw_after.data_uses("mqtt"):
                        generation_seen = True
                        _apply_raw_metrics(summary, raw_after_payload)
                        break
                except Exception:
                    pass
                time.sleep(0.1)
            if not generation_seen or last_mode != "runtime":
                raise TimeoutError(
                    "reconnect arm was not consumed by a new MQTT generation "
                    f"(last mode={last_mode})"
                )
            record_event("reconnect_consumed", mode=last_mode)

            if not capture.wait_for_data_ready(plan.data_ready_timeout):
                raise TimeoutError("timed out waiting for post-reboot MQTT DATA-ready frame magic")
            capture_started = capture.data_ready_monotonic or time.monotonic()
            record_event("data_ready", generation=capture.connection_generation)
            capture_deadline = capture_started + plan.duration
            while time.monotonic() < capture_deadline and not (
                stop_event is not None and stop_event.is_set()
            ):
                time.sleep(min(0.1, max(0.0, capture_deadline - time.monotonic())))
            capture_elapsed = max(0.0, time.monotonic() - capture_started)
            capture.stop_capture()
        except KeyboardInterrupt as exc:
            summary.interrupted = True
            primary_error = exc
            if capture is not None:
                capture.stop_capture()
        except BaseException as exc:
            primary_error = exc
            if capture is not None:
                capture.stop_capture()
            summary.warnings.append(f"collection failed: {type(exc).__name__}: {exc}")
            record_event("failure", error_type=type(exc).__name__, error=str(exc))
        finally:
            if armed:
                try:
                    _control_payload(
                        control,
                        "radar",
                        {"action": "raw", "mode": "off", "channel": "mqtt"},
                        plan.control_timeout,
                    )
                    final_raw = _control_payload(
                        control, "radar", {"action": "raw"}, plan.control_timeout
                    )
                    final_snapshot = RawRouteSnapshot.from_payload(final_raw)
                    raw_closed = not final_snapshot.live and final_snapshot.mode == "off"
                    _apply_raw_metrics(summary, final_raw)
                    if not raw_closed:
                        raise RuntimeError("reconnect-owned MQTT DATA route is still active")
                    record_event("cleanup", item="raw close", ok=True)
                except Exception as exc:
                    raw_closed = False
                    cleanup_errors.append(f"raw close: {exc}")
                    record_event("cleanup", item="raw close", ok=False, error=str(exc))
            if client is not None:
                try:
                    client.loop_stop()
                except Exception:
                    pass
                try:
                    client.disconnect()
                except Exception:
                    pass
            if capture is not None:
                summary.data_bytes = int(capture.stats["data_bytes"])
                summary.wire_bytes = int(capture.stats["wire_bytes"])
            summary.source_bytes = summary.source_bytes or summary.data_bytes
            summary.destination_bytes = summary.destination_bytes or summary.data_bytes
            summary.duration_s = capture_elapsed
            summary.cleanup = CleanupReport(
                raw_closed=raw_closed,
                radar_stopped=True,
                state_restored=raw_closed,
                parsed_restored=True,
                baud_restored=True,
                config_restored=True,
                lifecycle_restored=True,
                ownership_restored=True,
                route_restored=raw_closed,
                sensor_stopped=True,
                errors=tuple(cleanup_errors),
            )
            record_event(
                "complete" if primary_error is None else "cleanup_complete",
                cleanup=summary.as_dict()["cleanup"],
            )
            if summary_file is not None:
                summary_file.write(
                    (json.dumps(summary.as_dict(), indent=2) + "\n").encode("utf-8")
                )
                summary_file.flush()

    if primary_error is not None:
        raise primary_error
    return summary


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
    mqtt_username: str = "",
    mqtt_password: str = "",
    mqtt_ca: str | None = None,
    client_factory=None,
) -> CollectionSummary:
    """Collect with CMD/RESP on a local wire and DATA on MQTT."""
    plan.validate()
    if plan.ctrl_transport not in {"uart", "usb"} or plan.data_transport != "mqtt":
        raise ValueError("split collection currently supports local wire control with MQTT DATA")

    explicit_cfg: bytes | None = None
    explicit_source = ""
    explicit_sensor_stop = b"sensorStop\n"
    explicit_sensor_start = b"sensorStart\n"
    if plan.cfg_path:
        cfg_path = Path(plan.cfg_path).expanduser()
        explicit_source = str(cfg_path)
        explicit_payload = cfg_path.read_bytes()
        explicit_sensor_stop, explicit_sensor_start = _radar_lifecycle_commands(
            explicit_payload, explicit_source
        )
        explicit_cfg = _prepare_config(explicit_payload, explicit_source)

    summary = CollectionSummary(transport="split")
    session = LocalWireSession(plan, serial_factory=serial_factory)
    ledger = MutationLedger()
    primary_error: BaseException | None = None
    cleanup_errors: list[str] = []
    capture_elapsed = 0.0
    client = None
    capture: MqttCaptureSession | None = None
    raw_before = RawRouteSnapshot()
    radar_before = RadarSnapshot()
    prior_cfg: bytes | None = None
    prior_sensor_stop = b"sensorStop\n"
    prior_sensor_start = b"sensorStart\n"
    collection_cfg: bytes | None = None
    collection_sensor_stop = b"sensorStop\n"
    collection_sensor_start = b"sensorStart\n"

    raw_closed = True
    sensor_stopped = True
    parsed_restored = True
    baud_restored = True
    config_restored = True
    lifecycle_restored = True
    ownership_restored = True
    route_restored = True

    session.open()
    try:
        summary.identity = session.identify(expected_did, timeout=plan.control_timeout)
        node_info = _result_payload(session.last_response)
        if summary.identity.board == "wdr" and plan.raw_baud is not None:
            raise ValueError("WDR split DATA uses MQTT; omit --raw-baud")
        raw_before, _ = session.query_raw()
        radar_before, _ = session.query_radar()
        if radar_before.mode != raw_before.radar:
            raise ValueError(
                "incomplete ownership snapshot: radar status and raw status disagree "
                f"({radar_before.mode} != {raw_before.radar})"
            )
        if raw_before.live:
            raise ValueError(
                "a host raw route is already active; close it first or use MQTT --attach"
            )
        try:
            prior_cfg_raw, _ = session.read_config()
            prior_sensor_stop, prior_sensor_start = _radar_lifecycle_commands(
                prior_cfg_raw, "device:radar.config"
            )
            prior_cfg = _prepare_config(prior_cfg_raw, "device:radar.config")
        except Exception:
            if explicit_cfg is None or (raw_before.radar == "host" and radar_before.running):
                raise ValueError(
                    "a complete restorable radar config snapshot is unavailable; "
                    "provide --cfg or use --attach"
                )
        if explicit_cfg is not None:
            explicit_cfg = _prepare_runtime_config(
                explicit_cfg, explicit_source, summary.identity.board
            )
        if prior_cfg is not None:
            prior_cfg = _prepare_runtime_config(
                prior_cfg, "device:radar.config", summary.identity.board
            )
        collection_cfg = explicit_cfg if explicit_cfg is not None else prior_cfg
        if explicit_cfg is not None:
            collection_sensor_stop = explicit_sensor_stop
            collection_sensor_start = explicit_sensor_start
        else:
            collection_sensor_stop = prior_sensor_stop
            collection_sensor_start = prior_sensor_start
        if collection_cfg is None:
            raise ValueError("no validated radar cfg is available for split collection")
        summary.config_source = (
            explicit_source if explicit_cfg is not None else "device:radar.config"
        )

        network_info: dict[str, Any] = {}
        try:
            response = session.send_control({"cmd": "network", "action": "mqtt"})
            network_info = _result_payload(response)
        except Exception:
            network_info = {}
        broker_value = str(
            broker
            or network_info.get("uri")
            or network_info.get("mqtt_uri")
            or node_info.get("uri")
            or ""
        )
        if not broker_value:
            raise ValueError("split wire/MQTT collection requires --broker or a device MQTT URI")
        endpoint = resolve_mqtt_endpoint(
            broker_value,
            mqtt_port,
            username=mqtt_username or str(network_info.get("user") or ""),
            password=mqtt_password or str(network_info.get("pass") or ""),
        )
        topic = _mqtt_topics_for_identity(
            summary.identity,
            plan,
            data_topic=data_topic,
            prod=prod,
            oid=oid,
            cid=cid,
        )
        _require_mqtt_topic_identity(topic, summary.identity, node_info, cid=cid)
        outputs_set = resolve_output_set(plan, summary.identity)
        summary.outputs = {
            "data": str(outputs_set.data),
            "response": str(outputs_set.response),
            **({"wire": str(outputs_set.wire)} if outputs_set.wire is not None else {}),
            **({"summary": str(outputs_set.summary)} if outputs_set.summary is not None else {}),
            **({"events": str(outputs_set.events)} if outputs_set.events is not None else {}),
        }

        with reserve_output_files(outputs_set.paths(), overwrite=plan.overwrite) as output_stack:
            data_file = output_stack.handles[outputs_set.data.expanduser().resolve()]
            resp_file = output_stack.handles[outputs_set.response.expanduser().resolve()]
            wire_file = (
                output_stack.handles[outputs_set.wire.expanduser().resolve()]
                if outputs_set.wire is not None
                else None
            )
            summary_file = (
                output_stack.handles[outputs_set.summary.expanduser().resolve()]
                if outputs_set.summary is not None
                else None
            )
            events_file = (
                output_stack.handles[outputs_set.events.expanduser().resolve()]
                if outputs_set.events is not None
                else None
            )
            recorded_responses = 0

            def record_event(phase: str, **details: Any) -> None:
                if events_file is None:
                    return
                events_file.write(
                    (json.dumps({"ts": time.time(), "phase": phase, **details}, separators=(",", ":")) + "\n").encode("utf-8")
                )
                events_file.flush()

            def flush_responses() -> None:
                nonlocal recorded_responses
                while recorded_responses < len(session.response_history):
                    response = session.response_history[recorded_responses]
                    line = (json.dumps(response, separators=(",", ":")) + "\n").encode("utf-8")
                    resp_file.write(line)
                    resp_file.flush()
                    summary.response_bytes += len(line)
                    recorded_responses += 1

            def audit(direction: str, payload: bytes) -> None:
                if capture is None:
                    raise RuntimeError("split raw audit started before MQTT capture setup")
                capture.audit_wire(payload)
                record_event("wire", direction=direction, bytes=len(payload))

            def read_command_response(label: str) -> bytes:
                def record_response(payload: bytes) -> None:
                    if not payload:
                        return
                    resp_file.write(payload)
                    resp_file.flush()
                    summary.response_bytes += len(payload)

                return _await_radar_command_response(
                    session.read_raw,
                    record_response,
                    label=label,
                    timeout=plan.control_timeout,
                )

            def send_command(command: bytes, label: str) -> None:
                payload = command if command.endswith(b"\n") else command + b"\n"
                session.write_radar_bytes(payload)
                read_command_response(label)
                settle_seconds = _radar_command_settle_seconds(
                    summary.identity.board, payload
                )
                if settle_seconds > 0.0:
                    time.sleep(settle_seconds)

            def send_config(config: bytes, label: str) -> None:
                for raw_line in config.splitlines():
                    line = raw_line.strip()
                    if not line or line.startswith((b"%", b"#")):
                        continue
                    send_command(line + b"\n", label)

            def cleanup_action(label: str, action) -> bool:
                try:
                    action()
                    record_event("cleanup", item=label, ok=True)
                    return True
                except Exception as exc:
                    cleanup_errors.append(f"{label}: {exc}")
                    record_event("cleanup", item=label, ok=False, error=str(exc))
                    return False

            flush_responses()
            session.on_raw_write = lambda payload: audit("host_to_device", payload)
            session.on_raw_read = lambda payload: audit("device_to_host", payload)

            try:
                factory = client_factory or _new_mqtt_client
                try:
                    client = factory(f"mmwk_split_{summary.identity.did}_{int(time.time())}")
                except TypeError:
                    client = factory()
                _configure_mqtt_client(client, endpoint, mqtt_ca)
                capture = MqttCaptureSession(
                    topic,
                    "",
                    data_file,
                    resp_file,
                    data_qos=0,
                    require_data_magic=True,
                    capture_enabled=False,
                    wire_fout=wire_file,
                )
                capture.bind_client(client)
                client.connect(endpoint.host, endpoint.port, 60)
                client.loop_start()
                if not capture.subscribed.wait(plan.control_timeout):
                    raise TimeoutError("timed out waiting for MQTT DATA subscription")
                record_event("mqtt_ready", generation=capture.connection_generation, data_qos=0)

                if raw_before.mode == "reconnect":
                    session.send_control({
                        "cmd": "radar", "action": "raw", "mode": "off", "channel": "mqtt"
                    })
                    ledger.record("route_displaced")
                    route_restored = False
                    flush_responses()

                if raw_before.radar != "host" or not radar_before.running:
                    session.send_control({"cmd": "radar", "action": "start", "mode": "host"})
                    ledger.record("radar_started")
                    lifecycle_restored = False
                    if raw_before.radar != "host":
                        ledger.record("ownership_changed")
                        ownership_restored = False
                    session.wait_until_running()
                    flush_responses()

                session.open_raw(ctrl="wire", data="mqtt", escape=plan.escape)
                ledger.record("raw_open")
                raw_closed = False
                parsed_restored = False
                flush_responses()

                send_command(collection_sensor_stop, "collection sensorStop")
                ledger.record("sensor_stopped_for_collection")
                if radar_before.running:
                    lifecycle_restored = False
                if raw_before.radar == "host" and radar_before.running:
                    ledger.record("config_displaced")
                    config_restored = False
                send_config(collection_cfg, "collection cfg")
                capture.start_capture()
                session.write_radar_bytes(collection_sensor_start)
                ledger.record("sensor_started")
                sensor_stopped = False
                read_command_response("collection sensorStart")
                if not capture.wait_for_data_ready(plan.data_ready_timeout):
                    raise TimeoutError("timed out waiting for split MQTT DATA-ready frame magic")
                capture_started = capture.data_ready_monotonic or time.monotonic()
                record_event("data_ready")
                deadline = capture_started + plan.duration
                while time.monotonic() < deadline:
                    time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
                capture_elapsed = max(0.0, time.monotonic() - capture_started)
                capture.stop_capture()
            except KeyboardInterrupt as exc:
                summary.interrupted = True
                primary_error = exc
                if capture is not None:
                    capture.stop_capture()
            except BaseException as exc:
                primary_error = exc
                if capture is not None:
                    capture.stop_capture()
                summary.warnings.append(f"collection failed: {type(exc).__name__}: {exc}")
                record_event("failure", error_type=type(exc).__name__, error=str(exc))
            finally:
                if ledger.owns("sensor_started") and session.raw_open:
                    sensor_stopped = cleanup_action(
                        "sensorStop",
                        lambda: send_command(
                            collection_sensor_stop, "cleanup sensorStop"
                        ),
                    )

                if ledger.owns("config_displaced") and session.raw_open:
                    def restore_config() -> None:
                        if prior_cfg is None:
                            raise RuntimeError("prior config snapshot is missing")
                        send_config(prior_cfg, "restore cfg")

                    config_restored = cleanup_action("config restore", restore_config)
                    if config_restored and capture is not None:
                        def restore_running() -> None:
                            capture.start_probe()
                            session.write_radar_bytes(prior_sensor_start)
                            read_command_response("restore sensorStart")
                            if not capture.wait_for_data_ready(plan.data_ready_timeout):
                                raise TimeoutError("timed out proving restored split lifecycle")
                            capture.stop_capture()

                        lifecycle_restored = cleanup_action(
                            "running lifecycle restore", restore_running
                        )

                if session.raw_open:
                    raw_closed = cleanup_action(
                        "wire raw close",
                        lambda: session.close_raw(escape=plan.escape.encode("ascii")),
                    )
                    parsed_restored = raw_closed and session.parsed
                    baud_restored = plan.ctrl_transport == "usb" or parsed_restored
                    flush_responses()

                if session.parsed and ledger.owns("raw_open"):
                    def close_mqtt_data_route() -> None:
                        snapshot, _ = session.query_raw()
                        if snapshot.data_uses("mqtt"):
                            session.send_control({
                                "cmd": "radar", "action": "raw", "mode": "off", "channel": "mqtt"
                            })
                        final_snapshot, response = session.query_raw()
                        if final_snapshot.live:
                            raise RuntimeError("collector-owned split raw route is still active")
                        _apply_raw_metrics(summary, _result_payload(response))

                    raw_closed = cleanup_action("MQTT DATA route close", close_mqtt_data_route)
                    parsed_restored = raw_closed
                    flush_responses()

                if ledger.owns("radar_started") and session.parsed:
                    if raw_before.radar != "host":
                        def restore_ownership() -> None:
                            session.send_control({
                                "cmd": "radar", "action": "start", "mode": raw_before.radar
                            })
                            session.wait_until_running()

                        ownership_restored = cleanup_action("ownership restore", restore_ownership)
                        if ownership_restored and radar_before.running:
                            lifecycle_restored = True
                        flush_responses()
                    if not radar_before.running and ownership_restored:
                        lifecycle_restored = cleanup_action(
                            "stopped lifecycle restore",
                            lambda: session.send_control({"cmd": "radar", "action": "stop"}),
                        )
                        flush_responses()

                if ledger.owns("route_displaced") and session.parsed:
                    restore = raw_before.restore_command()
                    route_restored = cleanup_action(
                        "raw route restore", lambda: session.send_control(restore)
                    )
                    flush_responses()

                if client is not None:
                    try:
                        client.loop_stop()
                    except Exception:
                        pass
                    try:
                        client.disconnect()
                    except Exception:
                        pass

                if capture is not None:
                    summary.data_bytes = int(capture.stats["data_bytes"])
                    summary.wire_bytes = int(capture.stats["wire_bytes"])
                summary.source_bytes = summary.source_bytes or summary.data_bytes
                summary.destination_bytes = summary.destination_bytes or summary.data_bytes
                summary.duration_s = capture_elapsed
                state_restored = all((
                    raw_closed,
                    parsed_restored,
                    baud_restored,
                    config_restored,
                    lifecycle_restored,
                    ownership_restored,
                    route_restored,
                    sensor_stopped,
                ))
                summary.cleanup = CleanupReport(
                    raw_closed=raw_closed,
                    radar_stopped=sensor_stopped,
                    state_restored=state_restored,
                    parsed_restored=parsed_restored,
                    baud_restored=baud_restored,
                    config_restored=config_restored,
                    lifecycle_restored=lifecycle_restored,
                    ownership_restored=ownership_restored,
                    route_restored=route_restored,
                    sensor_stopped=sensor_stopped,
                    errors=tuple(cleanup_errors),
                )
                record_event(
                    "complete" if primary_error is None else "cleanup_complete",
                    cleanup=summary.as_dict()["cleanup"],
                )
                if summary_file is not None:
                    summary_file.write(
                        (json.dumps(summary.as_dict(), indent=2) + "\n").encode("utf-8")
                    )
                    summary_file.flush()
    finally:
        session.close()

    if primary_error is not None:
        raise primary_error
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


def _decode_config_text(payload: bytes, source: str) -> str:
    """Validate a radar cfg payload and return normalized text."""
    if not payload:
        raise ValueError(f"radar cfg is empty: {source}")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"radar cfg is not UTF-8 text: {source}") from exc
    if "\x00" in text:
        raise ValueError(f"radar cfg contains NUL bytes: {source}")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _radar_lifecycle_commands(payload: bytes, source: str) -> tuple[bytes, bytes]:
    """Return the cfg-owned sensorStop/sensorStart commands.

    Older radar profiles use bare lifecycle commands, while the L6432 WDR
    profiles require their arguments.  The collector owns the lifecycle
    window, so it must preserve those arguments instead of reconstructing
    generic commands after stripping the lines from the config body.
    """
    text = _decode_config_text(payload, source)
    sensor_stop = b"sensorStop\n"
    sensor_start = b"sensorStart\n"
    for raw_line in text.split("\n"):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith(("%", "#")):
            continue
        token = stripped.split(None, 1)[0].lower()
        if token == "sensorstop" and sensor_stop == b"sensorStop\n":
            sensor_stop = stripped.encode("utf-8") + b"\n"
        elif token == "sensorstart" and sensor_start == b"sensorStart\n":
            sensor_start = stripped.encode("utf-8") + b"\n"
    return sensor_stop, sensor_start


def _prepare_config(payload: bytes, source: str) -> bytes:
    """Validate cfg text and remove lifecycle lines owned by the collector."""
    text = _decode_config_text(payload, source)

    retained: list[str] = []
    commands = 0
    for raw_line in text.split("\n"):
        stripped = raw_line.strip()
        token = stripped.split(None, 1)[0].lower() if stripped else ""
        if token in {"sensorstart", "sensorstop"}:
            continue
        retained.append(raw_line.rstrip())
        if stripped and not stripped.startswith(("%", "#")):
            commands += 1
    if commands == 0:
        raise ValueError(f"radar cfg has no configuration commands: {source}")
    while retained and retained[-1] == "":
        retained.pop()
    return ("\n".join(retained) + "\n").encode("utf-8")


def _prepare_runtime_config(config: bytes, source: str, board: str) -> bytes:
    """Remove commands that are valid only during radar boot.

    ``baudRate`` is interpreted by the bridge driver while applying boot
    configuration.  Replaying it through the runtime CLI changes the radar's
    UART clock without retuning the bridge-side UART, which corrupts the
    following response and leaves the raw handoff out of sync.  WDR profiles
    are already booted at their required 1.25 Mbit/s rate, so omit this one
    boot-only command from a collection window.  Other boards retain their
    existing runtime configuration behavior.
    """
    if board.strip().lower() != "wdr":
        return config
    retained: list[bytes] = []
    for raw_line in config.splitlines():
        stripped = raw_line.strip()
        token = stripped.split(None, 1)[0].lower() if stripped else b""
        if token == b"baudrate":
            continue
        retained.append(raw_line.rstrip())
    while retained and retained[-1] == b"":
        retained.pop()
    if not retained:
        raise ValueError(f"radar cfg has no runtime commands after filtering: {source}")
    return b"\n".join(retained) + b"\n"


def _radar_command_settle_seconds(board: str, command: bytes) -> float:
    """Return the board-specific quiet time after a runtime radar command."""
    command_name = command.lstrip().split(None, 1)[0].lower() if command.strip() else b""
    if board.strip().lower() == "wdr" and command_name == b"sensorstop":
        return RADAR_SENSOR_STOP_SETTLE_SECONDS
    return 0.0


def _integer(payload: Mapping[str, Any], key: str, default: int = 0) -> int:
    try:
        return int(payload.get(key, default))
    except (TypeError, ValueError):
        return default


def _apply_raw_metrics(summary: CollectionSummary, payload: Mapping[str, Any]) -> None:
    summary.source_bytes = _integer(payload, "source_bytes", summary.source_bytes)
    summary.destination_bytes = _integer(
        payload,
        "completed_bytes",
        _integer(payload, "submitted_bytes", summary.destination_bytes),
    )
    summary.dropped_bytes = _integer(payload, "dropped_bytes", summary.dropped_bytes)
    summary.source_crc32 = _integer(payload, "source_crc32", summary.source_crc32)
    summary.destination_crc32 = _integer(
        payload,
        "completed_crc32",
        _integer(payload, "submitted_crc32", summary.destination_crc32),
    )
    observed_dropped_chunks = _integer(payload, "open_drop")
    adapters = payload.get("adapters")
    if isinstance(adapters, Mapping):
        for adapter in adapters.values():
            if not isinstance(adapter, Mapping):
                continue
            observed_dropped_chunks += _integer(adapter, "dropped_chunks")
            summary.queue_high_water = max(
                summary.queue_high_water,
                _integer(adapter, "queue_high_water"),
                _integer(adapter, "queued_chunks"),
            )
    summary.dropped_chunks = max(summary.dropped_chunks, observed_dropped_chunks)


def _manual_escape_recovery(escape: str) -> str:
    return (
        "Forced exit: keep the wire silent for one second, send "
        f"{escape!r} with no newline, keep it silent for one second, "
        "then reopen parsed control at 115200."
    )


def collect_local(plan: CollectionPlan, expected_did: str | None = None, serial_factory=None) -> CollectionSummary:
    """Collect one local host session with snapshot-driven restoration."""

    plan.validate()
    summary = CollectionSummary(transport=plan.transport, borrowed_route=plan.attach)
    session = LocalWireSession(plan, serial_factory=serial_factory)
    ledger = MutationLedger()
    total_started = time.monotonic()
    explicit_cfg: bytes | None = None
    explicit_source = ""
    explicit_sensor_stop = b"sensorStop\n"
    explicit_sensor_start = b"sensorStart\n"
    if plan.cfg_path:
        cfg_path = Path(plan.cfg_path).expanduser()
        explicit_source = str(cfg_path)
        explicit_payload = cfg_path.read_bytes()
        explicit_sensor_stop, explicit_sensor_start = _radar_lifecycle_commands(
            explicit_payload, explicit_source
        )
        explicit_cfg = _prepare_config(explicit_payload, explicit_source)

    raw_before = RawRouteSnapshot()
    radar_before = RadarSnapshot()
    prior_cfg: bytes | None = None
    prior_sensor_stop = b"sensorStop\n"
    prior_sensor_start = b"sensorStart\n"
    collection_cfg: bytes | None = None
    collection_sensor_stop = b"sensorStop\n"
    collection_sensor_start = b"sensorStart\n"
    outputs_set: OutputSet | None = None
    primary_error: BaseException | None = None
    cleanup_errors: list[str] = []
    recorded_responses = 0
    data_file = None
    resp_file = None
    wire_file = None
    summary_file = None
    events_file = None
    capture_started: float | None = None
    capture_elapsed = 0.0

    sensor_stopped = True
    config_restored = True
    lifecycle_restored = True
    raw_closed = True
    parsed_restored = True
    baud_restored = plan.transport == "usb"
    ownership_restored = True
    route_restored = True

    def record_event(phase: str, **details: Any) -> None:
        if events_file is None:
            return
        payload = {"ts": time.time(), "phase": phase, **details}
        events_file.write((json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8"))
        events_file.flush()

    def flush_responses() -> None:
        nonlocal recorded_responses
        if resp_file is None:
            return
        while recorded_responses < len(session.response_history):
            response = session.response_history[recorded_responses]
            line = (json.dumps(response, separators=(",", ":")) + "\n").encode("utf-8")
            resp_file.write(line)
            resp_file.flush()
            summary.response_bytes += len(line)
            recorded_responses += 1

    def write_raw_wire(direction: str, payload: bytes) -> None:
        if wire_file is not None:
            wire_file.write(payload)
            wire_file.flush()
        summary.wire_bytes += len(payload)
        record_event("wire", direction=direction, bytes=len(payload))

    def record_raw_response(payload: bytes) -> None:
        if not payload or resp_file is None:
            return
        resp_file.write(payload)
        resp_file.flush()
        summary.response_bytes += len(payload)

    def read_radar_command_response(label: str) -> bytes:
        return _await_radar_command_response(
            session.read_raw,
            record_raw_response,
            label=label,
            timeout=plan.control_timeout,
        )

    def send_radar_command(command: bytes, label: str) -> bytes:
        if not command.endswith(b"\n"):
            command += b"\n"
        board = summary.identity.board if summary.identity else ""
        command_name = command.lstrip().split(None, 1)[0].lower()
        retry_stop = board.strip().lower() == "wdr" and command_name == b"sensorstop"
        attempts = 2 if retry_stop else 1

        for attempt in range(1, attempts + 1):
            session.write_radar_bytes(command)
            try:
                response = read_radar_command_response(label)
            except (TimeoutError, _RadarCommandIncompleteResponse, _RadarCommandRejected) as exc:
                fragmented_stop = (
                    isinstance(exc, _RadarCommandRejected)
                    and _retryable_wdr_sensor_stop_rejection(exc.response)
                )
                if attempt >= attempts or (
                    isinstance(exc, _RadarCommandRejected) and not fragmented_stop
                ):
                    raise
                record_event(
                    "radar_command_retry",
                    label=label,
                    command="sensorStop",
                    attempt=attempt + 1,
                    reason=str(exc),
                )
                time.sleep(RADAR_SENSOR_STOP_RETRY_SECONDS)
                continue

            settle_seconds = _radar_command_settle_seconds(board, command)
            if settle_seconds > 0.0:
                # The WDR single-UART radar may still deliver one final DATA
                # frame after its CLI ACK.  Waiting for that tail to drain keeps
                # the following cfg command from being consumed as stale output.
                time.sleep(settle_seconds)
            return response

        raise AssertionError("unreachable radar command retry state")

    def send_radar_config(config: bytes, label: str) -> None:
        for raw_line in config.splitlines():
            line = raw_line.strip()
            if not line or line.startswith((b"%", b"#")):
                continue
            send_radar_command(line + b"\n", f"{label}: {line[:64].decode('utf-8', 'replace')}")

    def wait_for_data_magic(label: str, *, capture: bool) -> float:
        prefix = bytearray()
        deadline = time.monotonic() + plan.data_ready_timeout
        while time.monotonic() < deadline:
            payload = session.read_raw()
            if not payload:
                continue
            prefix.extend(payload)
            magic_at = prefix.find(RADAR_DATA_MAGIC)
            if magic_at < 0:
                if len(prefix) > MAX_DATA_READY_PREFIX:
                    raise RuntimeError(
                        f"{label} prefix exceeded safety limit without radar magic"
                    )
                continue
            response_prefix = bytes(prefix[:magic_at])
            first_data = bytes(prefix[magic_at:])
            if response_prefix:
                record_raw_response(response_prefix)
            ready_at = time.monotonic()
            if capture:
                data_file.write(first_data)
                data_file.flush()
                summary.data_bytes += len(first_data)
                record_event("data_ready", prefix_bytes=len(response_prefix))
            else:
                record_event(
                    "lifecycle_restored",
                    prefix_bytes=len(response_prefix),
                    proof="radar_data_magic",
                )
            return ready_at
        if prefix:
            record_raw_response(bytes(prefix))
        raise TimeoutError(f"timed out waiting for {label} radar frame magic")

    def cleanup_action(label: str, action) -> bool:
        try:
            action()
            record_event("cleanup", item=label, ok=True)
            return True
        except KeyboardInterrupt:
            print(_manual_escape_recovery(plan.escape), file=sys.stderr, flush=True)
            raise
        except Exception as exc:
            cleanup_errors.append(f"{label}: {exc}")
            record_event("cleanup", item=label, ok=False, error=str(exc))
            return False

    try:
        session.open()
        summary.identity = session.identify(expected_did, timeout=plan.control_timeout)
        raw_before, _ = session.query_raw()
        radar_before, _ = session.query_radar()
        if radar_before.mode != raw_before.radar:
            raise ValueError(
                "incomplete ownership snapshot: radar status and raw status disagree "
                f"({radar_before.mode} != {raw_before.radar})"
            )
        if raw_before.live:
            if plan.attach:
                raise ValueError(
                    "local --attach requires a separate parsed control channel; "
                    "use MQTT attach for an already-active route"
                )
            raise ValueError(
                "a host raw route is already active; close it first or use --attach "
                "on a supported borrowed MQTT DATA route"
            )

        if plan.attach and (raw_before.radar != "host" or not radar_before.running):
            raise ValueError(
                "local host --attach requires an already-running host radar lifecycle"
            )

        if plan.attach:
            summary.config_source = "borrowed:running-host"
        else:
            try:
                prior_cfg_raw, _ = session.read_config()
                prior_sensor_stop, prior_sensor_start = _radar_lifecycle_commands(
                    prior_cfg_raw, "device:radar.config"
                )
                prior_cfg = _prepare_config(prior_cfg_raw, "device:radar.config")
            except Exception:
                if explicit_cfg is None or (raw_before.radar == "host" and radar_before.running):
                    raise ValueError(
                        "a complete restorable radar config snapshot is unavailable; "
                        "provide --cfg or use --attach without replacing the running host"
                    )
                prior_cfg = None

        if not plan.attach:
            if explicit_cfg is not None:
                explicit_cfg = _prepare_runtime_config(
                    explicit_cfg, explicit_source, summary.identity.board
                )
            if prior_cfg is not None:
                prior_cfg = _prepare_runtime_config(
                    prior_cfg, "device:radar.config", summary.identity.board
                )
            if explicit_cfg is not None:
                collection_cfg = explicit_cfg
                collection_sensor_stop = explicit_sensor_stop
                collection_sensor_start = explicit_sensor_start
                summary.config_source = explicit_source
            else:
                collection_cfg = prior_cfg
                collection_sensor_stop = prior_sensor_stop
                collection_sensor_start = prior_sensor_start
                summary.config_source = "device:radar.config"

        if summary.identity.board == "wdr" and plan.transport == "uart" and plan.raw_baud is not None:
            warning = "WDR DATA is 1250000 baud; current 1000000-baud UART adapters are not lossless"
            if not plan.allow_lossy:
                raise ValueError(warning + "; use native USB CDC, MQTT DATA, or --allow-lossy")
            summary.warnings.append(
                "lossy WDR UART capture explicitly allowed; disqualified from "
                "lossless hardware acceptance"
            )
        elif summary.identity.board in {"mini", "pro", "wsr"} and plan.raw_baud == MAX_EXTERNAL_UART_BAUD:
            summary.warnings.append(
                "MINI/PRO/WSR radar DATA at 921600 baud has only an 8.5% adapter margin at "
                "1000000; drop counters are mandatory for acceptance"
            )

        outputs_set = resolve_output_set(plan, summary.identity)
        summary.outputs = {
            "data": str(outputs_set.data),
            "response": str(outputs_set.response),
            **({"wire": str(outputs_set.wire)} if outputs_set.wire is not None else {}),
            **({"summary": str(outputs_set.summary)} if outputs_set.summary is not None else {}),
            **({"events": str(outputs_set.events)} if outputs_set.events is not None else {}),
        }
        with reserve_output_files(outputs_set.paths(), overwrite=plan.overwrite) as output_stack:
            data_file = output_stack.handles[outputs_set.data.expanduser().resolve()]
            resp_file = output_stack.handles[outputs_set.response.expanduser().resolve()]
            if outputs_set.wire is not None:
                wire_file = output_stack.handles[outputs_set.wire.expanduser().resolve()]
            if outputs_set.summary is not None:
                summary_file = output_stack.handles[outputs_set.summary.expanduser().resolve()]
            if outputs_set.events is not None:
                events_file = output_stack.handles[outputs_set.events.expanduser().resolve()]
            flush_responses()
            record_event(
                "preflight",
                did=summary.identity.did,
                board=summary.identity.board,
                ownership=raw_before.radar,
                raw_mode=raw_before.mode,
                radar_state=radar_before.state,
                config_source=summary.config_source,
            )

            session.on_raw_write = lambda payload: write_raw_wire("host_to_device", payload)
            session.on_raw_read = lambda payload: write_raw_wire("device_to_host", payload)

            try:
                if raw_before.mode == "reconnect":
                    session.send_control(
                        {"cmd": "radar", "action": "raw", "mode": "off", "channel": "both"}
                    )
                    ledger.record("route_displaced")
                    route_restored = False
                    flush_responses()

                if raw_before.radar != "host" or not radar_before.running:
                    session.send_control(
                        {"cmd": "radar", "action": "start", "mode": "host"}
                    )
                    ledger.record("radar_started")
                    lifecycle_restored = False
                    if raw_before.radar != "host":
                        ledger.record("ownership_changed")
                        ownership_restored = False
                    session.wait_until_running()
                    flush_responses()

                session.open_raw(channel="wire", escape=plan.escape)
                ledger.record("raw_open")
                raw_closed = False
                parsed_restored = False
                baud_restored = plan.transport == "usb"
                flush_responses()

                if plan.attach:
                    record_event("radar", operation="borrow_running_host")
                else:
                    if collection_cfg is None:
                        raise ValueError("no validated radar cfg is available for host collection")
                    # ``radar status=running`` proves the host service is live, but
                    # does not prove that a sensorStart command is currently
                    # producing DATA. Own the lifecycle explicitly for this
                    # window, while preserving the prior cfg/running snapshot.
                    send_radar_command(collection_sensor_stop, "collection sensorStop")
                    ledger.record("sensor_stopped_for_collection")
                    if radar_before.running:
                        lifecycle_restored = False
                    if raw_before.radar == "host" and radar_before.running:
                        ledger.record("config_displaced")
                        config_restored = False
                    send_radar_config(collection_cfg, "collection cfg")
                    session.write_radar_bytes(collection_sensor_start)
                    ledger.record("sensor_started")
                    sensor_stopped = False
                    record_event("radar", operation="sensorStop_cfg_sensorStart")
                capture_started = wait_for_data_magic("DATA-ready", capture=True)

                capture_deadline = capture_started + plan.duration
                while time.monotonic() < capture_deadline:
                    payload = session.read_raw()
                    if not payload:
                        continue
                    data_file.write(payload)
                    data_file.flush()
                    summary.data_bytes += len(payload)
                capture_elapsed = max(0.0, time.monotonic() - capture_started)
            except KeyboardInterrupt as exc:
                summary.interrupted = True
                primary_error = exc
                record_event("interrupt", count=1)
            except BaseException as exc:
                primary_error = exc
                summary.warnings.append(f"collection failed: {type(exc).__name__}: {exc}")
                record_event("failure", error_type=type(exc).__name__, error=str(exc))
            finally:
                if ledger.owns("sensor_started") and session.raw_open:
                    sensor_stopped = cleanup_action(
                        "sensorStop",
                        lambda: send_radar_command(
                            collection_sensor_stop, "cleanup sensorStop"
                        ),
                    )

                if ledger.owns("config_displaced") and session.raw_open:
                    def restore_config() -> None:
                        if prior_cfg is None:
                            raise RuntimeError("prior config snapshot is missing")
                        send_radar_config(prior_cfg, "restore cfg")

                    config_restored = cleanup_action("config restore", restore_config)
                    if config_restored:
                        def restore_running_lifecycle() -> None:
                            session.write_radar_bytes(prior_sensor_start)
                            wait_for_data_magic("restored lifecycle", capture=False)

                        lifecycle_restored = cleanup_action(
                            "running lifecycle restore",
                            restore_running_lifecycle,
                        )

                if session.raw_open:
                    close_response: dict[str, Any] | None = None

                    def close_route() -> None:
                        nonlocal close_response
                        close_response = session.close_raw(escape=plan.escape.encode("ascii"))

                    raw_closed = cleanup_action("raw close", close_route)
                    if raw_closed:
                        baud_restored = plan.transport == "usb" or session.parsed
                    flush_responses()

                raw_after: RawRouteSnapshot | None = None
                if session.parsed:
                    def verify_parsed() -> None:
                        nonlocal raw_after, raw_closed
                        raw_after, response = session.query_raw()
                        if raw_after.live:
                            raw_closed = False
                            raise RuntimeError(
                                "collector-owned raw route is still active after escape"
                            )
                        raw_closed = True
                        _apply_raw_metrics(summary, _result_payload(response))

                    parsed_restored = cleanup_action("parsed verification", verify_parsed)
                    flush_responses()
                else:
                    parsed_restored = False

                if plan.attach and session.parsed:
                    def verify_borrowed_lifecycle() -> None:
                        snapshot, _ = session.query_radar()
                        if snapshot.mode != radar_before.mode or snapshot.running != radar_before.running:
                            raise RuntimeError(
                                "borrowed radar lifecycle changed during collection: "
                                f"expected {radar_before.mode}/{radar_before.state}, got "
                                f"{snapshot.mode}/{snapshot.state}"
                            )

                    lifecycle_restored = cleanup_action(
                        "borrowed lifecycle verification",
                        verify_borrowed_lifecycle,
                    )
                    ownership_restored = lifecycle_restored
                    flush_responses()

                if ledger.owns("radar_started") and session.parsed:
                    if raw_before.radar != "host":
                        def restore_ownership() -> None:
                            session.send_control({
                                "cmd": "radar", "action": "start", "mode": raw_before.radar
                            })
                            session.wait_until_running()

                        ownership_restored = cleanup_action(
                            "ownership restore",
                            restore_ownership,
                        )
                        flush_responses()
                        if ownership_restored and radar_before.running:
                            lifecycle_restored = True

                    if not radar_before.running and ownership_restored:
                        lifecycle_restored = cleanup_action(
                            "stopped lifecycle restore",
                            lambda: session.send_control({"cmd": "radar", "action": "stop"}),
                        )
                        flush_responses()

                if ledger.owns("route_displaced") and session.parsed:
                    route_restored = cleanup_action(
                        "raw route restore",
                        lambda: session.send_control(raw_before.restore_command()),
                    )
                    flush_responses()

                summary.source_bytes = summary.source_bytes or summary.data_bytes
                summary.destination_bytes = summary.destination_bytes or summary.data_bytes
                summary.duration_s = capture_elapsed
                state_restored = all((
                    raw_closed,
                    parsed_restored,
                    baud_restored,
                    config_restored,
                    lifecycle_restored,
                    ownership_restored,
                    route_restored,
                    sensor_stopped,
                ))
                summary.cleanup = CleanupReport(
                    raw_closed=raw_closed,
                    radar_stopped=sensor_stopped,
                    state_restored=state_restored,
                    parsed_restored=parsed_restored,
                    baud_restored=baud_restored,
                    config_restored=config_restored,
                    lifecycle_restored=lifecycle_restored,
                    ownership_restored=ownership_restored,
                    route_restored=route_restored,
                    sensor_stopped=sensor_stopped,
                    errors=tuple(cleanup_errors),
                )
                record_event(
                    "complete" if primary_error is None else "cleanup_complete",
                    cleanup=summary.as_dict()["cleanup"],
                )
                if summary_file is not None:
                    summary_file.write(
                        (json.dumps(summary.as_dict(), indent=2) + "\n").encode("utf-8")
                    )
                    summary_file.flush()
    finally:
        session.close()

    if primary_error is not None:
        raise primary_error
    summary.duration_s = max(summary.duration_s, 0.0)
    return summary
