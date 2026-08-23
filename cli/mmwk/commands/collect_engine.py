"""Shared host/remote radar raw collection primitives.

The engine deliberately keeps transport mechanics separate from the public CLI
argument surface.  Local wire sessions are byte-oriented after the raw route is
opened; MQTT sessions remain chunk-oriented and are implemented by the existing
MQTT collector entrypoints.
"""

from __future__ import annotations

import json
import os
import sys
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
RADAR_DATA_MAGIC = bytes.fromhex("0201040306050807")
MAX_DATA_READY_PREFIX = 1024 * 1024


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


def _prepare_config(payload: bytes, source: str) -> bytes:
    """Validate cfg text and remove lifecycle lines owned by the collector."""
    if not payload:
        raise ValueError(f"radar cfg is empty: {source}")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"radar cfg is not UTF-8 text: {source}") from exc
    if "\x00" in text:
        raise ValueError(f"radar cfg contains NUL bytes: {source}")

    retained: list[str] = []
    commands = 0
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
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
    adapters = payload.get("adapters")
    if isinstance(adapters, Mapping):
        for adapter in adapters.values():
            if not isinstance(adapter, Mapping):
                continue
            summary.dropped_chunks += _integer(adapter, "dropped_chunks")
            summary.queue_high_water = max(
                summary.queue_high_water,
                _integer(adapter, "queue_high_water"),
                _integer(adapter, "queued_chunks"),
            )


def _manual_escape_recovery(escape: str) -> str:
    return (
        "Forced exit: keep the wire silent for one second, send "
        f"{escape!r} with no newline, keep it silent for one second, "
        "then reopen parsed control at 115200."
    )


def collect_local(plan: CollectionPlan, expected_did: str | None = None, serial_factory=None) -> CollectionSummary:
    """Collect one local host session with snapshot-driven restoration."""

    plan.validate()
    summary = CollectionSummary(transport=plan.transport)
    session = LocalWireSession(plan, serial_factory=serial_factory)
    ledger = MutationLedger()
    total_started = time.monotonic()
    explicit_cfg: bytes | None = None
    explicit_source = ""
    if plan.cfg_path:
        cfg_path = Path(plan.cfg_path).expanduser()
        explicit_source = str(cfg_path)
        explicit_cfg = _prepare_config(cfg_path.read_bytes(), explicit_source)

    raw_before = RawRouteSnapshot()
    radar_before = RadarSnapshot()
    prior_cfg: bytes | None = None
    collection_cfg: bytes | None = None
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
        response = bytearray()
        deadline = time.monotonic() + plan.control_timeout
        quiet_deadline: float | None = None
        while time.monotonic() < deadline:
            payload = session.read_raw()
            now = time.monotonic()
            if payload:
                response.extend(payload)
                if len(response) > MAX_DATA_READY_PREFIX:
                    raise RuntimeError(f"{label} response exceeded safety limit")
                quiet_deadline = now + 0.15
                continue
            if response and quiet_deadline is not None and now >= quiet_deadline:
                break
        if not response:
            raise TimeoutError(f"timed out waiting for radar response to {label}")
        payload = bytes(response)
        record_raw_response(payload)
        lowered = payload.lower()
        if b"error" in lowered or b"not recognized" in lowered or b"failed" in lowered:
            raise RuntimeError(f"radar rejected {label}: {payload[-240:]!r}")
        if b"done" not in lowered:
            raise RuntimeError(f"radar returned an incomplete response to {label}: {payload[-240:]!r}")
        return payload

    def send_radar_command(command: bytes, label: str) -> bytes:
        if not command.endswith(b"\n"):
            command += b"\n"
        session.write_radar_bytes(command)
        return read_radar_command_response(label)

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

        try:
            prior_cfg_raw, _ = session.read_config()
            prior_cfg = _prepare_config(prior_cfg_raw, "device:radar.config")
        except Exception:
            if explicit_cfg is None or (raw_before.radar == "host" and radar_before.running):
                raise ValueError(
                    "a complete restorable radar config snapshot is unavailable; "
                    "provide --cfg or use --attach without replacing the running host"
                )
            prior_cfg = None

        if explicit_cfg is not None:
            collection_cfg = explicit_cfg
            summary.config_source = explicit_source
        else:
            collection_cfg = prior_cfg
            summary.config_source = "device:radar.config"

        if summary.identity.board == "wdr" and plan.transport == "uart" and plan.raw_baud is not None:
            warning = "WDR DATA is 1250000 baud; current 1000000-baud UART adapters are not lossless"
            if not plan.allow_lossy:
                raise ValueError(warning + "; use native USB CDC, MQTT DATA, or --allow-lossy")
            summary.warnings.append("lossy WDR UART capture explicitly allowed")
        elif summary.identity.board in {"mini", "pro"} and plan.raw_baud == MAX_EXTERNAL_UART_BAUD:
            summary.warnings.append(
                "MINI/PRO radar DATA at 921600 baud has little margin at 1000000; verify drops on hardware"
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

                if collection_cfg is None:
                    raise ValueError("no validated radar cfg is available for host collection")
                # ``radar status=running`` proves the host service is live, but
                # does not prove that a sensorStart command is currently
                # producing DATA. Own the lifecycle explicitly for this
                # window, while preserving the prior cfg/running snapshot.
                send_radar_command(b"sensorStop\n", "collection sensorStop")
                ledger.record("sensor_stopped_for_collection")
                if radar_before.running:
                    lifecycle_restored = False
                if raw_before.radar == "host" and radar_before.running:
                    ledger.record("config_displaced")
                    config_restored = False
                send_radar_config(collection_cfg, "collection cfg")
                session.write_radar_bytes(b"sensorStart\n")
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
                        lambda: send_radar_command(b"sensorStop\n", "cleanup sensorStop"),
                    )

                if ledger.owns("config_displaced") and session.raw_open:
                    def restore_config() -> None:
                        if prior_cfg is None:
                            raise RuntimeError("prior config snapshot is missing")
                        send_radar_config(prior_cfg, "restore cfg")

                    config_restored = cleanup_action("config restore", restore_config)
                    if config_restored:
                        def restore_running_lifecycle() -> None:
                            session.write_radar_bytes(b"sensorStart\n")
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
