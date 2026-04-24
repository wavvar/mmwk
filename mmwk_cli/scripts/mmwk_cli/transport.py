"""Transport layer for communicating with MMWK bridge/hub devices."""

import abc
import json
import time
import threading
try:
    import termios
except ImportError:  # pragma: no cover - non-POSIX fallback
    termios = None

from mmwk_cli._logging import logger
from mmwk_cli.mqtt_topics import build_mqtt_topics, normalize_topic_id


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


class UartTransport(RadarTransport):
    """UART serial transport using pyserial."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0,
                 reset: bool = False):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._io_lock = threading.Lock()
        self._open_serial()

        if reset:
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

        self._listener = threading.Thread(target=self._listen, daemon=True)
        self._listener.start()

    def _open_serial(self):
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
            try:
                data = json.loads(line_str)
                self.ingest_json(data)
                return
            except json.JSONDecodeError as e:
                logger.warning(f"Corrupt JSON ({e}), len={len(line_str)}: "
                               f"{line_str[:120]}...")
        logger.debug(f"LOG: {line_str}")
        with self.lock:
            self.log_history.append(line_str)


class MqttTransport(RadarTransport):
    """MQTT transport using paho-mqtt."""

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

        self.client = mqtt.Client()
        if username:
            self.client.username_pw_set(username, password)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self._connected = threading.Event()

        logger.info(f"Connecting to MQTT broker {broker}:{port}...")
        self.client.connect(broker, port, 60)
        self.client.loop_start()
        if not self._connected.wait(timeout=10):
            raise ConnectionError("Failed to connect to MQTT broker")

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info(f"MQTT connected, subscribing to {self.resp_topic}")
            client.subscribe(self.resp_topic, qos=self.qos)
            self._connected.set()
        else:
            logger.error(f"MQTT connect failed: rc={rc}")

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
