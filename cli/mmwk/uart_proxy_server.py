"""Persistent UART proxy for short-lived CLI commands."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import threading
import time
from pathlib import Path

import serial

try:
    import termios
except ImportError:  # pragma: no cover
    termios = None


MAX_PROXY_LINE_BUFFER = 16384


def _disable_hupcl(ser) -> None:
    if termios is None or not hasattr(ser, "fileno"):
        return

    try:
        fd = ser.fileno()
        attrs = termios.tcgetattr(fd)
        attrs[2] = (attrs[2] | termios.CLOCAL) & ~termios.HUPCL
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
    except Exception:
        return


def _get_noreset_posix_serial_class():
    import serial.serialposix as serialposix

    class _NoResetPosixSerial(serialposix.Serial):
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


def _create_noreset_serial():
    if termios is not None and os.name == "posix":
        return _get_noreset_posix_serial_class()()
    return serial.Serial()


def _recv_json_line(conn: socket.socket, timeout: float) -> dict:
    conn.settimeout(timeout)
    data = bytearray()

    while True:
        chunk = conn.recv(4096)
        if not chunk:
            break
        data.extend(chunk)
        if b"\n" in data:
            break

    text = data.decode("utf-8", errors="ignore").strip()
    if not text:
        return {}
    payload = json.loads(text)
    return payload if isinstance(payload, dict) else {}


class SerialProxy:
    def __init__(self, port: str, baudrate: int, timeout: float, serial_log: str | None = None):
        self.running = True
        self.serial_lock = threading.Lock()
        self.client_lock = threading.Lock()
        self.trace_lock = threading.Lock()
        self.active_conn: socket.socket | None = None
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.trace_file = open(serial_log, "ab", buffering=0) if serial_log else None
        self.ser = None
        self._open_serial()

    def _open_serial(self, reset_backend: bool = False) -> None:
        self.ser = serial.Serial() if reset_backend else _create_noreset_serial()
        self.ser.port = self.port
        self.ser.baudrate = self.baudrate
        self.ser.timeout = self.timeout
        self.ser.dtr = False
        self.ser.rts = False
        self.ser.open()
        _disable_hupcl(self.ser)

    def close(self) -> None:
        self.running = False
        with self.serial_lock:
            if self.ser and self.ser.is_open:
                self.ser.close()
        with self.trace_lock:
            if self.trace_file is not None:
                self.trace_file.close()
                self.trace_file = None

    def _set_active_conn(self, conn: socket.socket | None) -> None:
        with self.client_lock:
            self.active_conn = conn

    def _get_active_conn(self) -> socket.socket | None:
        with self.client_lock:
            return self.active_conn

    def _trace_serial_output(self, chunk: bytes) -> None:
        if not chunk:
            return
        with self.trace_lock:
            if self.trace_file is None:
                return
            try:
                self.trace_file.write(chunk)
                self.trace_file.flush()
            except Exception:
                self.trace_file = None

    def pump_serial_output(self) -> None:
        pending = bytearray()
        pending_conn: socket.socket | None = None

        while self.running:
            try:
                chunk = self.ser.readline()
            except Exception as exc:
                if not self.running:
                    break
                print(f"serial read error: {exc}", flush=True)
                time.sleep(0.05)
                continue

            if not chunk:
                continue

            self._trace_serial_output(chunk)
            conn = self._get_active_conn()
            if conn is None:
                pending.clear()
                pending_conn = None
                continue

            if conn is not pending_conn:
                pending.clear()
                pending_conn = conn

            pending.extend(chunk)
            if len(pending) > MAX_PROXY_LINE_BUFFER:
                pending.clear()
                continue

            try:
                while True:
                    newline_at = pending.find(b"\n")
                    if newline_at < 0:
                        break
                    line = bytes(pending[:newline_at + 1])
                    del pending[:newline_at + 1]
                    conn.sendall(line)
            except Exception:
                self._set_active_conn(None)
                pending.clear()
                pending_conn = None

    def reset_device(self) -> None:
        with self.serial_lock:
            try:
                if self.ser and self.ser.is_open:
                    self.ser.close()
            except Exception:
                pass
            self._open_serial(reset_backend=True)
            self.ser.dtr = False
            self.ser.rts = False
            time.sleep(0.1)
            self.ser.dtr = True
            self.ser.rts = True
            time.sleep(0.1)
            self.ser.rts = False
            self.ser.dtr = False
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
        time.sleep(2)

    def handle_client(self, conn: socket.socket) -> None:
        conn.settimeout(0.2)
        self._set_active_conn(conn)

        try:
            while self.running:
                try:
                    data = conn.recv(4096)
                except socket.timeout:
                    continue

                if not data:
                    break

                with self.serial_lock:
                    for start in range(0, len(data), 256):
                        self.ser.write(data[start:start + 256])
                        self.ser.flush()
                        time.sleep(0.01)
        finally:
            if self._get_active_conn() is conn:
                self._set_active_conn(None)
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            conn.close()


def _write_env_file(path: Path, data_host: str, data_port: int, ctrl_host: str, ctrl_port: int) -> None:
    path.write_text(
        "\n".join(
            [
                f"MMWK_CLI_UART_PROXY_DATA=tcp://{data_host}:{data_port}",
                f"MMWK_CLI_UART_PROXY_CTRL=tcp://{ctrl_host}:{ctrl_port}",
            ]
        ) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=0.2)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--pid-file")
    parser.add_argument("--serial-log")
    args = parser.parse_args()

    proxy = SerialProxy(args.port, args.baudrate, args.timeout, args.serial_log)
    data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ctrl_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    for sock in (data_sock, ctrl_sock):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        sock.settimeout(0.2)

    data_host, data_port = data_sock.getsockname()
    ctrl_host, ctrl_port = ctrl_sock.getsockname()
    _write_env_file(Path(args.env_file), data_host, data_port, ctrl_host, ctrl_port)
    if args.pid_file:
        Path(args.pid_file).write_text(str(os.getpid()) + "\n", encoding="utf-8")

    stop_event = threading.Event()

    def request_stop(*_args) -> None:
        proxy.running = False
        stop_event.set()
        for sock in (data_sock, ctrl_sock):
            try:
                sock.close()
            except Exception:
                pass

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    def control_loop() -> None:
        while not stop_event.is_set():
            try:
                conn, _ = ctrl_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            try:
                request = _recv_json_line(conn, timeout=1.0)
                command = request.get("command")
                if command == "reset":
                    proxy.reset_device()
                    response = {"ok": True}
                elif command == "ping":
                    response = {"ok": True, "port": args.port}
                elif command == "shutdown":
                    response = {"ok": True}
                    request_stop()
                else:
                    response = {"ok": False, "error": f"unsupported command: {command}"}
                conn.sendall((json.dumps(response, separators=(",", ":")) + "\n").encode("utf-8"))
            except Exception as exc:
                try:
                    conn.sendall(
                        (json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")) + "\n").encode("utf-8")
                    )
                except Exception:
                    pass
            finally:
                try:
                    conn.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                conn.close()

    ctrl_thread = threading.Thread(target=control_loop, daemon=True)
    serial_thread = threading.Thread(target=proxy.pump_serial_output, daemon=True)
    serial_thread.start()
    ctrl_thread.start()

    try:
        while not stop_event.is_set():
            try:
                conn, _ = data_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            proxy.handle_client(conn)
    finally:
        request_stop()
        ctrl_thread.join(timeout=1.0)
        serial_thread.join(timeout=1.0)
        proxy.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
