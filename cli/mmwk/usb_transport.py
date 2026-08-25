"""WDR/WSR USB CDC command transport and host-side port selection."""

from dataclasses import dataclass
import json
import os
import re
import threading
import time

from mmwk._logging import logger
from mmwk.transport import RadarTransport


# Windows may bind the native ESP32-S3 CDC interface to its generic serial
# driver and replace the firmware-provided Wavvar board descriptor strings.
_ESP32_NATIVE_USB_VID = 0x303A
_ESP32_NATIVE_USB_CDC_PID = 0x4001
_SUPPORTED_USB_BOARDS = frozenset({"wdr", "wsr"})


@dataclass(frozen=True)
class UsbPortCandidate:
    """A serial-port descriptor returned by the host USB enumerator."""

    device: str
    manufacturer: str = ""
    product: str = ""
    interface: str = ""
    serial_number: str = ""
    vid: int | None = None
    pid: int | None = None


class UsbTransportError(RuntimeError):
    """A USB CDC port could not be selected or passed board identity validation."""


def _default_port_provider():
    try:
        from serial.tools import list_ports
    except ImportError as exc:  # pragma: no cover - dependency is part of the CLI runtime
        raise UsbTransportError("pyserial is required for USB CDC transport") from exc

    return [
        UsbPortCandidate(
            device=str(info.device),
            manufacturer=str(getattr(info, "manufacturer", "") or ""),
            product=str(getattr(info, "product", "") or ""),
            interface=str(getattr(info, "interface", "") or ""),
            serial_number=str(getattr(info, "serial_number", "") or ""),
            vid=getattr(info, "vid", None),
            pid=getattr(info, "pid", None),
        )
        for info in list_ports.comports()
    ]


def _coerce_candidate(value) -> UsbPortCandidate:
    if isinstance(value, UsbPortCandidate):
        return value

    return UsbPortCandidate(
        device=str(getattr(value, "device", "") or ""),
        manufacturer=str(getattr(value, "manufacturer", "") or ""),
        product=str(getattr(value, "product", "") or ""),
        interface=str(getattr(value, "interface", "") or ""),
        serial_number=str(getattr(value, "serial_number", "") or ""),
        vid=getattr(value, "vid", None),
        pid=getattr(value, "pid", None),
    )


def _descriptor_is_supported_board(candidate: UsbPortCandidate) -> bool:
    return (
        candidate.manufacturer.strip().casefold() == "wavvar"
        and candidate.product.strip().casefold() in _SUPPORTED_USB_BOARDS
    )


def _vid_pid_is_native_usb(candidate: UsbPortCandidate) -> bool:
    return (
        candidate.vid == _ESP32_NATIVE_USB_VID
        and candidate.pid == _ESP32_NATIVE_USB_CDC_PID
    )


def _is_explicit_windows_serial_path(path: str) -> bool:
    """Accept a user-supplied COM path even when enumeration omits it briefly."""

    return bool(re.fullmatch(r"(?i)COM\d+", path.strip()))


class UsbPortResolver:
    """Select one WDR/WSR CDC path using a bounded enumeration budget.

    The resolver intentionally delegates final board/DID validation to the
    caller's node-info probe. USB descriptors are only a first-pass filter.
    """

    def __init__(
        self,
        port_provider=None,
        path_exists=None,
        clock=None,
        sleeper=None,
        poll_interval: float = 0.1,
    ):
        self.port_provider = port_provider or _default_port_provider
        self.path_exists = path_exists or os.path.exists
        self.clock = clock or time.monotonic
        self.sleeper = sleeper or time.sleep
        self.poll_interval = max(0.001, float(poll_interval))

    def _snapshot(self):
        try:
            raw_candidates = self.port_provider() or []
        except UsbTransportError:
            raise
        except Exception as exc:
            raise UsbTransportError(f"USB CDC enumeration failed: {exc}") from exc

        candidates = []
        seen = set()
        for raw in raw_candidates:
            candidate = _coerce_candidate(raw)
            device = candidate.device.strip()
            if not device or device in seen:
                continue
            seen.add(device)
            candidates.append(candidate)
        return candidates

    def _candidates_for(self, port: str | None):
        snapshot = self._snapshot()
        if port:
            exact = [candidate for candidate in snapshot if candidate.device == port]
            if exact:
                return exact
            if self.path_exists(port) or _is_explicit_windows_serial_path(port):
                return [UsbPortCandidate(device=port)]
            return []

        return [
            candidate
            for candidate in snapshot
            if _descriptor_is_supported_board(candidate) or _vid_pid_is_native_usb(candidate)
        ]

    @staticmethod
    def _close_quietly(transport):
        try:
            transport.close()
        except Exception:
            pass

    def resolve(
        self,
        *,
        port: str | None,
        wait_ms: int,
        did: str | None,
        probe_timeout: float,
        open_transport,
        probe,
    ):
        if isinstance(wait_ms, bool) or not isinstance(wait_ms, int) or wait_ms < 0:
            raise ValueError("--usb-wait-ms must be a non-negative integer")

        start = self.clock()
        deadline = start + wait_ms / 1000.0
        last_probe_error = None

        while True:
            candidates = self._candidates_for(port)

            if len(candidates) > 1 and not port and not did:
                paths = ", ".join(candidate.device for candidate in candidates)
                raise UsbTransportError(
                    "Multiple WDR/WSR USB CDC candidates found: "
                    f"{paths}; provide --did or --port"
                )

            if candidates:
                remaining = max(0.0, deadline - self.clock())
                candidate_timeout = max(0.0, float(probe_timeout))
                if wait_ms > 0:
                    candidate_timeout = min(candidate_timeout, remaining)

                for candidate in candidates:
                    transport = None
                    success = False
                    try:
                        transport = open_transport(candidate.device)
                        if probe(transport, candidate_timeout):
                            success = True
                            return transport
                        last_probe_error = (
                            f"node info identity mismatch on {candidate.device}"
                        )
                    except Exception as exc:
                        last_probe_error = f"{candidate.device}: {exc}"
                    finally:
                        if transport is not None and not success:
                            # A successful probe returns before this block. Every
                            # failed candidate is closed, including exceptions.
                            self._close_quietly(transport)

                if wait_ms == 0:
                    detail = f" ({last_probe_error})" if last_probe_error else ""
                    raise UsbTransportError(
                        "USB CDC candidate did not pass WDR/WSR node info validation" + detail
                    )

            if wait_ms == 0:
                if port:
                    raise UsbTransportError(
                        f"USB CDC path {port!r} is not currently enumerated"
                    )
                raise UsbTransportError("USB CDC is not currently enumerated")

            remaining = deadline - self.clock()
            if remaining <= 0:
                if candidates and last_probe_error:
                    raise UsbTransportError(
                        "USB CDC candidates did not pass WDR/WSR node info validation "
                        f"before --usb-wait-ms deadline ({last_probe_error})"
                    )
                if port:
                    raise UsbTransportError(
                        f"USB CDC path {port!r} did not appear before --usb-wait-ms deadline"
                    )
                raise UsbTransportError("USB CDC did not appear before --usb-wait-ms deadline")

            self.sleeper(min(self.poll_interval, remaining))


class UsbTransport(RadarTransport):
    """Direct 115200-baud USB CDC line transport.

    This class deliberately has no UART proxy, modem-control reset, or
    binary framing API. It carries the existing newline-delimited JSON text
    protocol only.
    """

    def __init__(self, port: str, timeout: float = 1.0):
        super().__init__()
        self.port = port
        self.baudrate = 115200
        self.timeout = timeout
        self._io_lock = threading.Lock()

        import serial

        ser = serial.Serial()
        ser.port = port
        ser.baudrate = self.baudrate
        ser.timeout = timeout
        # Keep native USB CDC modem-control lines idle.  They are not needed
        # for readiness and must not be used as a UART-style reset signal.
        ser.dtr = False
        ser.rts = False
        ser.open()
        self.ser = ser
        self._disable_hupcl(ser)
        self._start_listener()

    def _start_listener(self):
        self._listener = threading.Thread(target=self._listen, daemon=True)
        self._listener.start()

    def _stop_listener(self):
        self.running = False
        with self._io_lock:
            try:
                if getattr(self, "ser", None) and self.ser.is_open:
                    self.ser.close()
            except Exception:
                pass
        listener = getattr(self, "_listener", None)
        if listener and listener.is_alive() and listener is not threading.current_thread():
            listener.join(timeout=1.0)

    @staticmethod
    def _disable_hupcl(ser):
        try:
            import termios

            fd = ser.fileno()
            attrs = termios.tcgetattr(fd)
            attrs[2] = (attrs[2] | termios.CLOCAL) & ~termios.HUPCL
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
        except Exception:
            # CDC devices and Windows serial handles may not expose POSIX
            # termios; no modem-control change is needed in that case.
            return

    def send_raw(self, data: str):
        payload = (data + "\n").encode("utf-8")
        chunk_size = 256
        with self._io_lock:
            for i in range(0, len(payload), chunk_size):
                self.ser.write(payload[i:i + chunk_size])
                self.ser.flush()
                time.sleep(0.01)

    def close(self):
        self._stop_listener()

    def _listen(self):
        while self.running:
            try:
                line = self.ser.readline()
                if not line:
                    continue
                line_str = line.decode("utf-8", errors="ignore").strip()
                if line_str:
                    self._process_line(line_str)
            except Exception as exc:
                if self.running:
                    logger.error("USB CDC read error: %s", exc)
                break

    def _process_line(self, line_str: str):
        decoder = json.JSONDecoder()
        cursor = 0
        parsed_count = 0

        while cursor < len(line_str):
            first_brace = line_str.find("{", cursor)
            first_type = line_str.find('"type"', cursor)
            use_type = False

            if first_type != -1 and first_brace == -1:
                start = first_type
                use_type = True
            elif first_type != -1 and first_brace != -1:
                if first_type < first_brace:
                    start = first_type
                    use_type = True
                else:
                    start = first_brace
            elif first_brace != -1:
                start = first_brace
            else:
                break

            payload = line_str[start:]
            if use_type:
                payload = "{" + payload
            try:
                data, consumed = decoder.raw_decode(payload)
            except json.JSONDecodeError:
                if parsed_count > 0:
                    return
                cursor = max(cursor + 1, start + 1)
                continue

            if not isinstance(data, dict):
                return
            self.ingest_json(data)
            parsed_count += 1
            cursor = start + consumed

        if parsed_count == 0:
            with self.lock:
                self.log_history.append(line_str)
