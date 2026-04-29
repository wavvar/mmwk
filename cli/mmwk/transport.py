"""Transport layer for communicating with MMWK bridge/hub devices."""

import abc
import json
import os
import socket
import time
import threading
from urllib.parse import urlparse
try:
    import termios
except ImportError:  # pragma: no cover - non-POSIX fallback
    termios = None

from mmwk._logging import logger
from mmwk.mqtt_topics import build_mqtt_topics, normalize_topic_id


def _control_cli_error_code_to_jsonrpc(code: str) -> int:
    mapping = {
        "invalid.json": -32700,
        "invalid.req": -32600,
        "not.found": -32601,
        "invalid.arg": -32602,
        "unauthorized": -32001,
    }
    return mapping.get(code, -32000)


def _normalize_control_cli_message(data: dict) -> dict:
    if not isinstance(data, dict):
        return data

    msg_type = data.get("type")
    if msg_type == "res":
        seq = data.get("seq")
        if not isinstance(seq, int):
            return data

        if data.get("ok") is True:
            payload = data.get("result", {})
            return {
                "jsonrpc": "2.0",
                "id": seq,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(payload, separators=(",", ":")),
                        }
                    ]
                },
            }

        error = data.get("error", {})
        if not isinstance(error, dict):
            error = {}
        return {
            "jsonrpc": "2.0",
            "id": seq,
            "error": {
                "code": _control_cli_error_code_to_jsonrpc(str(error.get("code", ""))),
                "message": str(error.get("message", "CLI request failed")),
                "data": error,
            },
        }

    if msg_type == "evt":
        return {
            "jsonrpc": "2.0",
            "method": "notifications/event",
            "params": {
                "service": data.get("service"),
                "event": data.get("event"),
                "ts": data.get("ts"),
                "data": data.get("data", {}),
            },
        }

    return data


class RadarTransport(abc.ABC):
    """Abstract transport for communicating with MMWK bridge/hub devices."""

    def __init__(self):
        self.responses = []
        self.notifications = []
        self.log_history = []
        self.lock = threading.Lock()
        self.running = True
        self._msg_id = 0

    def next_msg_id(self):
        self._msg_id += 1
        return self._msg_id

    @abc.abstractmethod
    def send_raw(self, data: str):
        """Send raw string over the transport."""
        pass

    def send_json(self, obj: dict):
        """Send a JSON-RPC message."""
        msg = json.dumps(obj, separators=(',', ':'))
        logger.debug(f"TX: {msg}")
        self.send_raw(msg)

    @abc.abstractmethod
    def close(self):
        pass

    def add_response(self, data: dict):
        with self.lock:
            self.responses.append(data)

    def add_notification(self, data: dict):
        with self.lock:
            self.notifications.append(data)

    def ingest_json(self, data: dict):
        normalized = _normalize_control_cli_message(data)
        logger.debug(
            "RX JSON: id=%s seq=%s type=%s method=%s",
            normalized.get("id"),
            data.get("seq"),
            data.get("type", "-"),
            normalized.get("method", "-"),
        )
        if "id" in normalized:
            self.add_response(normalized)
        elif normalized.get("method", "").startswith("notifications/"):
            self.add_notification(normalized)
        else:
            self.add_response(normalized)

    def wait_for_response(self, msg_id: int, timeout: float = 10.0) -> dict:
        """Wait for a JSON-RPC response with the given id."""
        start = time.time()
        while time.time() - start < timeout:
            with self.lock:
                for i, resp in enumerate(self.responses):
                    if resp.get("id") == msg_id:
                        self.responses.pop(i)
                        return resp
            time.sleep(0.05)
        elapsed = time.time() - start
        logger.debug(f"Timeout waiting for msg_id={msg_id} after {elapsed:.1f}s "
                     f"(pending responses: {len(self.responses)})")
        return None

    def drain_notifications(self) -> list:
        with self.lock:
            items = list(self.notifications)
            self.notifications.clear()
            return items

    def clear_pending(self):
        with self.lock:
            self.responses.clear()
            self.notifications.clear()


def _parse_uart_proxy_endpoint(raw: str):
    value = (raw or "").strip()
    if not value:
        return None

    if value.startswith("tcp://"):
        value = value[len("tcp://"):]

    host, sep, port_text = value.rpartition(":")
    if sep != ":" or not host or not port_text:
        raise ValueError(f"Invalid UART proxy endpoint: {raw!r}")

    try:
        port = int(port_text, 10)
    except ValueError as exc:
        raise ValueError(f"Invalid UART proxy port in endpoint: {raw!r}") from exc

    if port <= 0 or port > 65535:
        raise ValueError(f"UART proxy port out of range in endpoint: {raw!r}")

    return host, port


def _recv_socket_line(sock, timeout: float) -> bytes:
    deadline = time.time() + max(timeout, 0.1)
    chunks = bytearray()

    while time.time() < deadline:
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            continue

        if not chunk:
            break

        chunks.extend(chunk)
        newline_idx = chunks.find(b"\n")
        if newline_idx != -1:
            return bytes(chunks[:newline_idx + 1])

    if chunks:
        return bytes(chunks)
    raise TimeoutError("Timed out waiting for UART proxy response")


class _SocketSerialAdapter:
    """Socket-backed serial-like client used by the UART proxy."""

    def __init__(self, endpoint, timeout: float):
        host, port = endpoint
        self._sock = socket.create_connection((host, port), timeout=timeout)
        self._sock.settimeout(timeout)
        self._buffer = bytearray()
        self.is_open = True

    def readline(self):
        while self.is_open:
            newline_idx = self._buffer.find(b"\n")
            if newline_idx != -1:
                line = bytes(self._buffer[:newline_idx + 1])
                del self._buffer[:newline_idx + 1]
                return line

            try:
                chunk = self._sock.recv(4096)
            except socket.timeout:
                return b""

            if not chunk:
                if self._buffer:
                    line = bytes(self._buffer)
                    self._buffer.clear()
                    return line
                self.is_open = False
                raise ConnectionError("UART proxy socket closed")

            self._buffer.extend(chunk)

        return b""

    def write(self, data):
        if not self.is_open:
            raise ConnectionError("UART proxy socket is closed")
        self._sock.sendall(data)
        return len(data)

    def flush(self):
        return None

    def close(self):
        self.is_open = False
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        self._sock.close()


def _get_noreset_posix_serial_class():
    import serial.serialposix as serialposix

    class _NoResetPosixSerial(serialposix.Serial):
        """POSIX serial backend that skips DTR/RTS updates during open()."""

        def open(self):
            original_update_dtr = self._update_dtr_state
            original_update_rts = self._update_rts_state
            try:
                self._update_dtr_state = lambda: None
                self._update_rts_state = lambda: None
                return super().open()
            finally:
                self._update_dtr_state = original_update_dtr
                self._update_rts_state = original_update_rts

    return _NoResetPosixSerial


class UartTransport(RadarTransport):
    """UART serial transport using pyserial."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0,
                 reset: bool = False):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._reset_requested = reset
        self._serial_backend = ""
        self._io_lock = threading.Lock()
        self._proxy_data_endpoint = _parse_uart_proxy_endpoint(
            os.getenv("MMWK_CLI_UART_PROXY_DATA", "")
        )
        self._proxy_ctrl_endpoint = _parse_uart_proxy_endpoint(
            os.getenv("MMWK_CLI_UART_PROXY_CTRL", "")
        )

        if self._should_use_uart_proxy() and reset:
            self._proxy_reset()

        self._open_serial()

        if reset and not self._should_use_uart_proxy():
            # Reset ESP32 via DTR/RTS
            self.ser.dtr = False
            self.ser.rts = False
            time.sleep(0.1)
            self.ser.dtr = True
            self.ser.rts = True
            time.sleep(0.1)
            self.ser.rts = False
            self.ser.dtr = False
            time.sleep(2)  # Wait for boot

        self._start_listener()

    def _start_listener(self):
        self._listener = threading.Thread(target=self._listen, daemon=True)
        self._listener.start()

    def _ensure_listener_running(self):
        listener = getattr(self, "_listener", None)
        if self.running and (listener is None or not listener.is_alive()):
            self._start_listener()

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

    def _open_serial(self):
        if self._should_use_uart_proxy():
            self._open_serial_proxy()
            return
        if self._should_use_posix_noreset_backend():
            self._open_serial_posix_noreset()
            return
        self._open_serial_pyserial()

    def _should_use_uart_proxy(self) -> bool:
        return self._proxy_data_endpoint is not None

    def _should_use_posix_noreset_backend(self) -> bool:
        backend_hint = os.getenv("MMWK_CLI_UART_NORESET_BACKEND", "").strip().lower()

        if backend_hint == "pyserial":
            return False

        return (
            not self._should_use_uart_proxy() and
            not self._reset_requested and
            termios is not None and
            os.name == "posix"
        )

    def _proxy_reset(self):
        if not self._proxy_ctrl_endpoint:
            raise RuntimeError(
                "MMWK_CLI_UART_PROXY_CTRL is required when --reset is used with UART proxy"
            )

        host, port = self._proxy_ctrl_endpoint
        reset_timeout = max(self.timeout, 5.0)
        sock = socket.create_connection((host, port), timeout=reset_timeout)
        try:
            sock.settimeout(reset_timeout)
            request = json.dumps(
                {"command": "reset", "port": self.port},
                separators=(",", ":"),
            ).encode("utf-8") + b"\n"
            sock.sendall(request)
            response_raw = _recv_socket_line(sock, reset_timeout)
            try:
                response = json.loads(response_raw.decode("utf-8", errors="ignore").strip() or "{}")
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Invalid UART proxy control response: {response_raw!r}"
                ) from exc
            if not isinstance(response, dict) or response.get("ok") is not True:
                raise RuntimeError(
                    f"UART proxy reset rejected: {response.get('error', response)}"
                )
        finally:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            sock.close()
        time.sleep(2)

    def _open_serial_proxy(self):
        self.ser = _SocketSerialAdapter(self._proxy_data_endpoint, self.timeout)
        self._serial_backend = "proxy"

    def _open_serial_posix_noreset(self):
        NoResetSerial = _get_noreset_posix_serial_class()
        ser = NoResetSerial()
        ser.port = self.port
        ser.baudrate = self.baudrate
        ser.timeout = self.timeout
        ser.dtr = False
        ser.rts = False
        ser.open()
        self._disable_hupcl(ser)
        self.ser = ser
        self._serial_backend = "posix"

    def _open_serial_pyserial(self):
        import serial
        ser = serial.Serial()
        ser.port = self.port
        ser.baudrate = self.baudrate
        ser.timeout = self.timeout
        # Keep ESP auto-reset lines idle until we intentionally toggle them.
        ser.dtr = False
        ser.rts = False
        ser.open()
        self._disable_hupcl(ser)
        self.ser = ser
        self._serial_backend = "pyserial"

    @staticmethod
    def _disable_hupcl(ser):
        """Keep Linux from dropping modem control lines on close/open cycles."""
        if termios is None or not hasattr(ser, "fileno"):
            return

        try:
            fd = ser.fileno()
            attrs = termios.tcgetattr(fd)
            attrs[2] = (attrs[2] | termios.CLOCAL) & ~termios.HUPCL
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
        except Exception as e:
            logger.debug(f"Failed to disable HUPCL on {getattr(ser, 'port', '?')}: {e}")

    @staticmethod
    def _is_reconnectable_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        markers = (
            "device disconnected",
            "device not configured",
            "returned no data",
            "resource busy",
            "no such file",
            "input/output",
            "ioerror",
            "filenotfounderror",
            "broken pipe",
            "connection reset",
            "connection refused",
        )
        return any(marker in msg for marker in markers)

    def _reconnect(self, wait_sec: float = 20.0) -> bool:
        deadline = time.time() + max(1.0, wait_sec)
        last_err = None
        while self.running and time.time() < deadline:
            try:
                with self._io_lock:
                    try:
                        if getattr(self, "ser", None) and self.ser.is_open:
                            self.ser.close()
                    except Exception:
                        pass
                    self._open_serial()
                logger.warning(f"UART reconnected on {self.port}")
                return True
            except Exception as e:
                last_err = e
                time.sleep(0.5)
        if last_err:
            logger.error(f"UART reconnect failed on {self.port}: {last_err}")
        return False

    def recover_after_reboot(self, settle_sec: float = 5.0, reconnect_wait_sec: float = 20.0) -> bool:
        self.clear_pending()
        time.sleep(max(0.0, settle_sec))
        self._stop_listener()
        self.running = True
        ok = self._reconnect(wait_sec=reconnect_wait_sec)
        if ok:
            self._start_listener()
        self.clear_pending()
        return ok

    def reset_device(self, settle_sec: float = 2.0, reconnect_wait_sec: float = 20.0) -> bool:
        self.clear_pending()
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

        self.running = True
        if self._should_use_uart_proxy():
            self._proxy_reset()
            with self._io_lock:
                self._open_serial()
            time.sleep(max(0.0, settle_sec))
        else:
            with self._io_lock:
                self._open_serial()
                self.ser.dtr = False
                self.ser.rts = False
                time.sleep(0.1)
                self.ser.dtr = True
                self.ser.rts = True
                time.sleep(0.1)
                self.ser.rts = False
                self.ser.dtr = False
            time.sleep(max(0.0, settle_sec))

        self._start_listener()
        self.clear_pending()
        return True

    def send_raw(self, data: str):
        payload = (data + "\n").encode('utf-8')
        for attempt in range(2):
            try:
                # To avoid overrunning ESP32 UART RX FIFO (which may be 256-1024 bytes),
                # write the data in small chunks and sleep in between
                chunk_size = 256
                with self._io_lock:
                    for i in range(0, len(payload), chunk_size):
                        self.ser.write(payload[i:i+chunk_size])
                        self.ser.flush()
                        time.sleep(0.01)
                return
            except Exception as e:
                if attempt == 0 and self._is_reconnectable_error(e) and self._reconnect(wait_sec=20.0):
                    logger.warning(f"UART write error recovered by reconnect: {e}")
                    continue
                raise

    def close(self):
        self.running = False
        with self._io_lock:
            if getattr(self, "ser", None) and self.ser.is_open:
                self.ser.close()

    def _listen(self):
        while self.running:
            try:
                line = self.ser.readline()
                if not line:
                    continue
                line_str = line.decode('utf-8', errors='ignore').strip()
                if not line_str:
                    continue
                self._process_line(line_str)
            except Exception as e:
                if not self.running:
                    break

                msg = str(e)
                # USB-UART on ESP32 can bounce during reset/flash and pyserial
                # may temporarily fail reads/writes. Reconnect in-place.
                if self._is_reconnectable_error(e):
                    logger.warning(f"Transient serial read error: {e}")
                    if not self._reconnect(wait_sec=20.0):
                        break
                    continue

                logger.error(f"Serial read error: {e}")
                break

    def _process_line(self, line_str: str):
        """Process a single newline-delimited line from UART."""
        if line_str.startswith('{'):
            decoder = json.JSONDecoder()
            offset = 0
            parsed_count = 0
            try:
                while offset < len(line_str):
                    while offset < len(line_str) and line_str[offset].isspace():
                        offset += 1
                    if offset >= len(line_str):
                        break

                    data, offset = decoder.raw_decode(line_str, offset)
                    if not isinstance(data, dict):
                        raise json.JSONDecodeError("JSON value is not an object", line_str, offset)
                    self.ingest_json(data)
                    parsed_count += 1

                if parsed_count > 0:
                    return
            except json.JSONDecodeError as e:
                if parsed_count > 0:
                    logger.warning(f"Corrupt JSON tail ({e}), len={len(line_str)}: "
                                   f"{line_str[:120]}...")
                    return
                logger.warning(f"Corrupt JSON ({e}), len={len(line_str)}: "
                               f"{line_str[:120]}...")
        logger.debug(f"LOG: {line_str}")
        with self.lock:
            self.log_history.append(line_str)


class MqttTransport(RadarTransport):
    """MQTT transport using paho-mqtt."""

    @staticmethod
    def _resolve_broker_endpoint(broker: str, port: int) -> tuple[str, int, bool]:
        raw = str(broker or "").strip()
        if "://" not in raw:
            return raw or "localhost", int(port), False

        parsed = urlparse(raw)
        scheme = (parsed.scheme or "").lower()
        host = parsed.hostname or "localhost"
        use_tls = scheme == "mqtts"
        default_port = 8883 if use_tls else int(port)
        return host, int(parsed.port or default_port), use_tls

    def __init__(self, broker: str, port: int = 1883, device_id: str = None,
                 cmd_topic: str = None, resp_topic: str = None,
                 username: str = None, password: str = None,
                 qos: int = 1, inter_chunk_delay: float = 0.05):
        super().__init__()
        import paho.mqtt.client as mqtt

        topics = build_mqtt_topics(device_id, include_raw_cmd=True)

        self.device_id = normalize_topic_id(device_id)
        self.cmd_topic = cmd_topic or topics["cmd_topic"]
        self.resp_topic = resp_topic or topics["resp_topic"]
        self.qos = qos
        self.inter_chunk_delay = inter_chunk_delay
        broker_host, broker_port, use_tls = self._resolve_broker_endpoint(broker, port)

        self.client = mqtt.Client()
        if username:
            self.client.username_pw_set(username, password)
        if use_tls:
            self.client.tls_set()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_subscribe = self._on_subscribe
        self._connected = threading.Event()
        self._subscribed = threading.Event()
        self._connect_error = None
        self._subscribe_error = None

        logger.info(f"Connecting to MQTT broker {broker_host}:{broker_port}...")
        self.client.connect(broker_host, broker_port, 60)
        self.client.loop_start()
        try:
            if not self._connected.wait(timeout=10):
                raise ConnectionError("Failed to connect to MQTT broker")
            if self._connect_error is not None:
                raise ConnectionError(f"Failed to connect to MQTT broker: {self._connect_error}")
            if self._subscribe_error is not None:
                raise ConnectionError(f"Failed to subscribe to MQTT response topic: {self._subscribe_error}")
            if not self._subscribed.wait(timeout=10):
                raise ConnectionError("Failed to subscribe to MQTT response topic: subscribe-ready timeout")
            if self._subscribe_error is not None:
                raise ConnectionError(f"Failed to subscribe to MQTT response topic: {self._subscribe_error}")
        except Exception:
            self.close()
            raise

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info(f"MQTT connected, subscribing to {self.resp_topic}")
            try:
                result, _mid = client.subscribe(self.resp_topic, qos=self.qos)
            except Exception as exc:
                self._subscribe_error = str(exc)
                self._subscribed.set()
            else:
                if result != 0:
                    self._subscribe_error = f"rc={result}"
                    self._subscribed.set()
            self._connected.set()
        else:
            self._connect_error = f"rc={rc}"
            logger.error(f"MQTT connect failed: rc={rc}")
            self._connected.set()

    def _on_subscribe(self, client, userdata, mid, granted_qos, properties=None):
        self._subscribed.set()

    def _on_message(self, client, userdata, msg):
        payload = msg.payload.decode('utf-8', errors='ignore')
        try:
            data = json.loads(payload)
            self.ingest_json(data)
        except json.JSONDecodeError:
            logger.debug(f"Non-JSON MQTT: {payload}")

    def send_raw(self, data: str):
        info = self.client.publish(self.cmd_topic, data, qos=self.qos)
        if self.qos > 0:
            info.wait_for_publish(timeout=5)

    def close(self):
        self.running = False
        self.client.loop_stop()
        self.client.disconnect()


def create_transport(args, retries: int = 1, retry_delay: float = 2.0) -> RadarTransport:
    """Create transport from parsed arguments.

    Args:
        args: Namespace with transport configuration attributes.
        retries: Number of connection attempts (default: 1 for CLI, use 3 for tests).
        retry_delay: Seconds between retries.

    Returns:
        A connected RadarTransport instance.

    Raises:
        ValueError: If required arguments are missing.
        Exception: If connection fails after all retries.
    """
    transport_type = getattr(args, 'transport', 'uart')

    for attempt in range(retries):
        try:
            if transport_type == "mqtt":
                device_id = getattr(args, 'device_id', None)
                if not device_id:
                    raise ValueError("--device-id required for MQTT transport")
                return MqttTransport(
                    broker=getattr(args, 'broker', 'localhost'),
                    port=getattr(args, 'mqtt_port', 1883),
                    device_id=device_id,
                    cmd_topic=getattr(args, 'cmd_topic', None),
                    resp_topic=getattr(args, 'resp_topic', None),
                    qos=getattr(args, 'mqtt_qos', 1),
                    inter_chunk_delay=getattr(args, 'mqtt_delay', 0.05),
                )
            else:
                port = getattr(args, 'port', None)
                if not port:
                    raise ValueError("--port required for UART transport")
                return UartTransport(
                    port=port,
                    baudrate=getattr(args, 'baudrate', 115200),
                    reset=getattr(args, 'reset', False),
                )
        except ValueError:
            raise  # Don't retry on missing args
        except Exception as e:
            if attempt < retries - 1:
                logger.warning(f"Transport connect attempt {attempt+1}/{retries} failed: {e}")
                import time as _time
                _time.sleep(retry_delay)
            else:
                raise
