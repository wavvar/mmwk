"""Runtime implementation for local server helper.

This module preserves the original shell-based behavior in `cli/server.sh` while
making the control plane available to Python entry points and platform-neutral
wrappers.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import shlex
import signal
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse

from mmwk.http_server import get_local_ip



def timestamp_now() -> str:
    """Return a compact log timestamp."""
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def is_pid_running(pid_text: str | None) -> bool:
    if not pid_text:
        return False
    try:
        pid = int(str(pid_text).strip())
    except ValueError:
        return False

    if pid <= 0:
        return False

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.OpenProcess(
            process_query_limited_information,
            False,
            pid,
        )
        if not handle:
            return False

        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
    except OSError:
        return False

    return True


def _read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_pid_file(path: pathlib.Path) -> str:
    if not path.is_file():
        return ""
    return _read_text(path).strip()


def _is_private_ipv4(value: str) -> bool:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)\.(\d+)$", value)
    if not match:
        return False
    first, second, _, _ = map(int, match.groups())
    if first == 0:
        return False
    if first == 10:
        return True
    if first == 192 and second == 168:
        return True
    if first == 172 and 16 <= second <= 31:
        return True
    return False


def parse_url_port(raw_url: str, default_port: int) -> int:
    raw = (raw_url or "").strip()
    if not raw:
        return default_port
    value = raw
    if "://" not in value:
        value = f"tcp://{value}"

    parsed = urlparse(value)
    if not parsed.scheme:
        return default_port
    return parsed.port or default_port


def parse_http_host_port(raw_url: str, default_port: int) -> tuple[str, int]:
    raw = (raw_url or "").strip()
    if not raw:
        return "", default_port

    value = raw
    if "://" not in value:
        value = f"http://{value}"
    parsed = urlparse(value)
    host = parsed.hostname or ""
    return host, parsed.port or default_port


def split_mqtt_uri(raw_uri: str, fallback_port: str | int) -> tuple[str, str]:
    port = parse_url_port(raw_uri, int(fallback_port))
    host = raw_uri.strip()
    if "://" in host:
        parsed = urlparse(host)
        host = parsed.hostname or ""
    host = (host.split(":", 1)[0] if ":" in host else host)
    return host, str(port)


def split_http_base_url(raw_url: str, fallback_port: str | int) -> tuple[str, str]:
    host, port = parse_http_host_port(raw_url, int(fallback_port))
    return host, str(port)


def mqtt_uri_from_host_port(host: str, port: str | int) -> str:
    return f"mqtt://{host}:{int(port)}"


def http_base_url_from_host_port(host: str, port: str | int) -> str:
    return f"http://{host}:{int(port)}/"


def parse_env_file_value(path: pathlib.Path, key: str) -> str:
    if not path.is_file():
        return ""
    pattern = re.compile(rf"^{re.escape(key)}=(.*)$")

    for line in _read_text(path).splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        return match.group(1)

    return ""


def _safe_relpath(target: pathlib.Path, root: pathlib.Path) -> str:
    try:
        rel = target.relative_to(root)
        return str(rel.as_posix())
    except ValueError:
        return str(target.resolve())


def _read_lines(path: pathlib.Path) -> list[str]:
    if not path.is_file():
        return []
    return _read_text(path).splitlines()


def _find_git_toplevel() -> pathlib.Path | None:
    import subprocess

    try:
        value = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None

    if not value:
        return None

    toplevel = pathlib.Path(value)
    if toplevel.is_dir():
        return toplevel

    return None


def resolve_public_package_root(start_dir: pathlib.Path | None = None) -> pathlib.Path:
    base = (start_dir or pathlib.Path(__file__).resolve()).parent.parent
    candidates = [
        base,
        base.parent,
        base.parent.parent,
    ]

    if _find_git_toplevel() is not None:
        git_root = _find_git_toplevel()
        if git_root is not None:
            candidates.insert(0, git_root)

    for candidate in candidates:
        if candidate.is_dir() and (candidate / "firmwares").is_dir():
            return candidate

    # Fallback: always return the nearest candidate even when firmwares is absent
    # so callers can preserve existing failure behavior.
    return base


def _to_bool(raw: str | None) -> bool:
    if raw is None:
        return False
    value = str(raw).strip().lower()
    return value in {"1", "true", "yes", "on"}


class ServerRuntime:
    """Shared runtime and state for local MQTT+HTTP helper."""

    def __init__(
        self,
        *,
        state_dir: str,
        serve_dir: str | None,
        upload_dir: str | None,
        device_ota: bool,
        device_ota_board: str,
        host_ip: str,
        target_ip: str,
        mqtt_port: int,
        http_port: int,
        invoke_pwd: str | None = None,
    ) -> None:
        self.base_dir = pathlib.Path(invoke_pwd or os.getcwd()).resolve()
        self.state_dir = self._abspath(state_dir or str(self.base_dir / "build_output/local_server"))
        self.serve_dir_input = serve_dir
        self.upload_dir_input = upload_dir
        self.device_ota = bool(device_ota)
        self.device_ota_board = (device_ota_board or "").strip()
        self.host_ip = (host_ip or "").strip()
        self.target_ip = (target_ip or "").strip()
        self.mqtt_port = int(mqtt_port)
        self.http_port = int(http_port)

        if self.device_ota:
            self.configure_device_ota_mode()

        if self.device_ota:
            if not self.device_ota_dir:
                self.device_ota_dir = self.resolve_device_ota_dir()
            if not self.device_ota_path:
                # Keep fallback behavior from legacy script: keep unresolved path and
                # fail during server preparation, matching the previous error path.
                self.device_ota_path = str(pathlib.Path(self.device_ota_dir) / "mmwk_sensor_bridge_full.bin")
        else:
            self.device_ota_dir = ""
            self.device_ota_path = ""

        self.device_ota_url = ""
        self.device_ota_version = ""

        if self.device_ota:
            self.device_ota_board = self.device_ota_board

        if self.serve_dir_input:
            self.serve_dir = self._abspath(self.serve_dir_input)
        elif self.device_ota:
            self.serve_dir = self._abspath(self.device_ota_dir)
        else:
            self.serve_dir = self._abspath(str(self.base_dir))

        if self.upload_dir_input:
            self.upload_dir = self._abspath(self.upload_dir_input)
        else:
            self.upload_dir = self._abspath(f"{self.state_dir}/uploads")

        self.stop_file = pathlib.Path(self.state_dir) / "stop.request"
        self.mqtt_pid_file = pathlib.Path(self.state_dir) / "mosquitto.pid"
        self.http_pid_file = pathlib.Path(self.state_dir) / "http.pid"
        self.server_pid_file = pathlib.Path(self.state_dir) / "server.pid"
        self.env_file = pathlib.Path(self.state_dir) / "server.env"
        self.server_log = pathlib.Path(self.state_dir) / "server.log"
        self.mqtt_log = pathlib.Path(self.state_dir) / "mosquitto.log"
        self.http_log = pathlib.Path(self.state_dir) / "http.log"
        self.mosq_conf = pathlib.Path(self.state_dir) / "mosquitto.conf"

        self.prepared_host_ip: str = ""
        self.mosquitto_command: str = ""
        self.mqtt_process = None
        self.http_process = None

    def _abspath(self, value: str) -> str:
        path = pathlib.Path(value)
        if path.is_absolute():
            return str(path.resolve())
        return str((self.base_dir / path).resolve())

    # ----------------------------- logging -----------------------------

    def log_info(self, text: str) -> None:
        print(f"[{timestamp_now()}] [server] {text}", flush=True)

    def log_warn(self, text: str) -> None:
        print(f"[{timestamp_now()}] [server] {text}", file=sys.stderr, flush=True)

    # ---------------------------- helpers -----------------------------

    def detect_public_package_root(self) -> pathlib.Path:
        return resolve_public_package_root(pathlib.Path(__file__).resolve().parent)

    def resolve_device_ota_dir(self) -> str:
        if not self.device_ota_board:
            return self._abspath(self.base_dir)

        return str((self.detect_public_package_root() / "firmwares" / "esp" / self.device_ota_board).resolve())

    def latest_version_dir(self, board_root: str) -> pathlib.Path | None:
        artifact_root = pathlib.Path(board_root) / "mmwk_sensor_bridge"
        if not artifact_root.is_dir():
            return None

        version_dirs = [
            p for p in artifact_root.glob("v*")
            if p.is_dir() and re.match(r"^v\d+", p.name)
        ]
        if not version_dirs:
            return None

        version_dirs.sort(key=lambda item: item.name)
        return version_dirs[-1]

    def extract_device_ota_zip(self, ota_zip: str, extract_root: str) -> None:
        import zipfile

        target = pathlib.Path(extract_root)
        target.mkdir(parents=True, exist_ok=True)
        for child in target.glob("*"):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                import shutil

                shutil.rmtree(child)

        with zipfile.ZipFile(ota_zip, "r") as handle:
            handle.extractall(str(target))

    def select_versioned_device_ota(self, board_root: str) -> bool:
        version_dir = self.latest_version_dir(board_root)
        if version_dir is None:
            return False

        ota_zip = version_dir / "ota.zip"
        if not ota_zip.is_file():
            return False

        version_name = version_dir.name
        extract_root = f"{self.state_dir}/device_ota/{self.device_ota_board}/{version_name}"
        self.extract_device_ota_zip(str(ota_zip), extract_root)

        bins = sorted(pathlib.Path(extract_root).rglob("*.bin"))
        if not bins:
            raise RuntimeError(f"device OTA artifact has no .bin payload: {ota_zip}")

        self.device_ota_dir = str(pathlib.Path(extract_root).resolve())
        self.device_ota_path = str(bins[0].resolve())
        self.device_ota_version = version_name.lstrip("v")
        return True

    def configure_device_ota_mode(self) -> None:
        if not self.device_ota:
            return

        if not self.device_ota_board:
            raise RuntimeError("--device-ota requires --device-ota-board")

        board_root = self.resolve_device_ota_dir()
        full_bin = pathlib.Path(board_root) / "mmwk_sensor_bridge_full.bin"
        self.device_ota_dir = str(pathlib.Path(board_root).resolve())
        self.device_ota_path = str(full_bin.resolve())
        self.device_ota_version = ""

        if full_bin.is_file():
            version_file = pathlib.Path(board_root) / "mmwk_sensor_bridge.version"
            if version_file.is_file():
                self.device_ota_version = version_file.read_text(encoding="utf-8").strip()
            return

        self.select_versioned_device_ota(board_root)

    def _windows_service_image_path(self, service_name: str) -> str:
        if os.name != "nt":
            return ""

        query = (
            f"(Get-CimInstance -ClassName Win32_Service "
            f"-Filter \"Name='{service_name}'\" -ErrorAction SilentlyContinue).PathName"
        )
        try:
            return subprocess.check_output(
                ["powershell.exe", "-NoProfile", "-Command", query],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).strip()
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return ""

    def _extract_windows_exe_path(self, raw_command: str) -> str:
        raw = (raw_command or "").strip()
        if not raw:
            return ""

        candidate = ""
        if raw.startswith('"'):
            end_quote = raw.find('"', 1)
            if end_quote > 1:
                candidate = raw[1:end_quote]
        else:
            exe_match = re.search(r"\.exe\b", raw, flags=re.IGNORECASE)
            if exe_match:
                candidate = raw[: exe_match.end()]
            else:
                try:
                    parts = shlex.split(raw, posix=False)
                except ValueError:
                    parts = []
                if parts:
                    candidate = parts[0].strip('"')

        candidate = os.path.expandvars(candidate.strip().strip('"'))
        if not candidate:
            return ""

        path = pathlib.Path(candidate)
        if path.name.lower() != "mosquitto.exe":
            return ""
        if not path.is_file():
            return ""
        return str(path)

    def resolve_mosquitto_command(self) -> str:
        from shutil import which

        for name in ("mosquitto", "mosquitto.exe"):
            found = which(name)
            if found:
                return found

        if os.name != "nt":
            return ""

        service_path = self._extract_windows_exe_path(
            self._windows_service_image_path("mosquitto")
        )
        if service_path:
            return service_path

        candidate_roots = [
            os.environ.get("ProgramFiles", ""),
            os.environ.get("ProgramFiles(x86)", ""),
            r"C:\Program Files",
            r"C:\Program Files (x86)",
        ]
        for root in candidate_roots:
            if not root:
                continue
            candidate = pathlib.Path(root) / "mosquitto" / "mosquitto.exe"
            if candidate.is_file():
                return str(candidate)

        return ""

    def load_state_runtime(self) -> None:
        if not self.env_file.is_file():
            return

        mqtt_uri = parse_env_file_value(self.env_file, "MMWK_SERVER_MQTT_URI")
        http_base_url = parse_env_file_value(self.env_file, "MMWK_SERVER_HTTP_BASE_URL")

        if mqtt_uri:
            self.mqtt_port = parse_url_port(mqtt_uri, self.mqtt_port)
        if http_base_url:
            _, self.http_port = parse_http_host_port(http_base_url, self.http_port)

        board = parse_env_file_value(self.env_file, "MMWK_SERVER_DEVICE_OTA_BOARD")
        ota_dir = parse_env_file_value(self.env_file, "MMWK_SERVER_DEVICE_OTA_DIR")
        ota_path = parse_env_file_value(self.env_file, "MMWK_SERVER_DEVICE_OTA_PATH")
        ota_url = parse_env_file_value(self.env_file, "MMWK_SERVER_DEVICE_OTA_URL")
        ota_version = parse_env_file_value(self.env_file, "MMWK_SERVER_DEVICE_OTA_VERSION")

        self.device_ota_board = board or self.device_ota_board
        self.device_ota_dir = ota_dir or self.device_ota_dir
        self.device_ota_path = ota_path or self.device_ota_path
        self.device_ota_url = ota_url or self.device_ota_url
        self.device_ota_version = ota_version or self.device_ota_version
        self.device_ota = bool(self.device_ota_board or self.device_ota_path or self.device_ota_url)

    def _ping_tcp(self, host: str, port: int, timeout: float = 1.0) -> bool:
        try:
            with socket.create_connection((host, int(port)), timeout=timeout):
                return True
        except OSError:
            return False

    def _port_available(self, port: int) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("0.0.0.0", int(port)))
            return True
        except OSError:
            return False
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def pick_available_port(self, requested_port: int) -> int:
        for port in (requested_port + offset for offset in range(0, 10)):
            if self._port_available(port):
                return int(port)
        raise RuntimeError(f"could not find a free port near {requested_port}")

    def detect_host_ip(self) -> str:
        if self.host_ip:
            return self.host_ip

        return get_local_ip(target_ip=self.target_ip).strip()

    def device_ota_url_for_host(self, host: str) -> str:
        if not self.device_ota or not self.device_ota_path:
            return ""

        resolved_path = pathlib.Path(self.device_ota_path).resolve()
        serve_root = pathlib.Path(self.serve_dir).resolve()

        if not str(resolved_path).startswith(str(serve_root)):
            rel_path = _safe_relpath(resolved_path, serve_root)
            if rel_path.startswith("..") or rel_path.startswith(("/", "\\")):
                raise RuntimeError(
                    f"device OTA artifact must live under the served HTTP directory ({serve_root})"
                )
        else:
            rel_path = os.path.relpath(resolved_path, str(serve_root)).replace(os.sep, "/")

        return f"http://{host}:{self.http_port}/{rel_path}"

    def write_env_file(self, resolved_host_ip: str) -> None:
        self.device_ota_url = self.device_ota_url_for_host(resolved_host_ip)
        lines = [
            f"MMWK_SERVER_HOST_IP={resolved_host_ip}",
            f"MMWK_SERVER_MQTT_URI={mqtt_uri_from_host_port(resolved_host_ip, self.mqtt_port)}",
            f"MMWK_SERVER_HTTP_BASE_URL={http_base_url_from_host_port(resolved_host_ip, self.http_port)}",
            f"MMWK_SERVER_STATE_DIR={self.state_dir}",
            f"MMWK_SERVER_SERVE_DIR={self.serve_dir}",
            f"MMWK_SERVER_UPLOAD_DIR={self.upload_dir}",
            f"MMWK_SERVER_DEVICE_OTA_BOARD={self.device_ota_board}",
            f"MMWK_SERVER_DEVICE_OTA_DIR={self.device_ota_dir}",
            f"MMWK_SERVER_DEVICE_OTA_PATH={self.device_ota_path}",
            f"MMWK_SERVER_DEVICE_OTA_URL={self.device_ota_url}",
            f"MMWK_SERVER_DEVICE_OTA_VERSION={self.device_ota_version}",
        ]

        self.state_dir_obj.mkdir(parents=True, exist_ok=True)
        self.env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.log_info(f"Env File   : {self.env_file}")

    @property
    def state_dir_obj(self) -> pathlib.Path:
        return pathlib.Path(self.state_dir)

    @property
    def serve_dir_obj(self) -> pathlib.Path:
        return pathlib.Path(self.serve_dir)

    @property
    def upload_dir_obj(self) -> pathlib.Path:
        return pathlib.Path(self.upload_dir)

    @property
    def prepared(self) -> bool:
        return bool(self.prepared_host_ip)

    # ---------------------------- lifecycle ----------------------------

    def ensure_not_running(self) -> None:
        mqtt_pid = _read_pid_file(self.mqtt_pid_file)
        http_pid = _read_pid_file(self.http_pid_file)
        server_pid = _read_pid_file(self.server_pid_file)

        if any(is_pid_running(value) for value in (mqtt_pid, http_pid, server_pid)):
            raise RuntimeError(f"server already running in {self.state_dir}")

    def prepare_start_state(self) -> None:
        self.state_dir_obj.mkdir(parents=True, exist_ok=True)
        self.upload_dir_obj.mkdir(parents=True, exist_ok=True)
        self.stop_file.unlink(missing_ok=True)
        self.ensure_not_running()
        self.env_file.unlink(missing_ok=True)
        self.server_log.write_text("", encoding="utf-8")

    def prepare_server(self) -> None:
        if self.device_ota and not self.device_ota_path:
            raise RuntimeError("device OTA mode requires --device-ota-board and valid artifact")

        if self.device_ota and not pathlib.Path(self.device_ota_path).is_file():
            raise RuntimeError(
                f"device OTA artifact not found under {self.resolve_device_ota_dir()}"
            )

        self.mosquitto_command = self.resolve_mosquitto_command()
        if not self.mosquitto_command:
            raise RuntimeError(
                "required command not found: mosquitto "
                "(add mosquitto.exe to PATH, or install the Windows mosquitto service)"
            )

        self.state_dir_obj.mkdir(parents=True, exist_ok=True)
        self.upload_dir_obj.mkdir(parents=True, exist_ok=True)
        self.stop_file.unlink(missing_ok=True)

        self.ensure_not_running()
        self.env_file.unlink(missing_ok=True)

        self.log_info("Preparing local server")
        self.log_info(f"State Dir   : {self.state_dir}")
        self.log_info(f"Serve Dir   : {self.serve_dir}")
        self.log_info(f"Upload Dir  : {self.upload_dir}")
        self.log_info(f"Mosquitto   : {self.mosquitto_command}")
        self.log_info(f"Requested MQTT Port: {self.mqtt_port}")
        self.log_info(f"Requested HTTP Port: {self.http_port}")

        self.prepared_host_ip = self.detect_host_ip().strip()
        if not self.prepared_host_ip or self.prepared_host_ip == "0.0.0.0":
            raise RuntimeError("could not determine a usable host IP. Pass --host-ip explicitly.")

        self.mqtt_port = self.pick_available_port(self.mqtt_port)
        self.http_port = self.pick_available_port(self.http_port)

        self.mosq_conf.write_text(
            "\n".join(
                [
                    "allow_anonymous true",
                    "persistence false",
                    f"listener {self.mqtt_port} 0.0.0.0",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self.mqtt_log.write_text("", encoding="utf-8")
        self.http_log.write_text("", encoding="utf-8")
        self.log_info(f"Resolved Host IP : {self.prepared_host_ip}")
        self.log_info(f"Resolved MQTT Port: {self.mqtt_port}")
        self.log_info(f"Resolved HTTP Port: {self.http_port}")

    def cleanup_server(self) -> None:
        for pid_file in (self.mqtt_pid_file, self.http_pid_file, self.server_pid_file):
            pid = _read_pid_file(pid_file)
            self.terminate_pid(pid, skip_current=True)

        # Wait briefly for children. When called by the supervisor itself, the
        # server pid file points at the current process and must not keep cleanup
        # waiting forever or make the process terminate itself on Windows.
        for _ in range(20):
            pending = [
                _read_pid_file(self.mqtt_pid_file),
                _read_pid_file(self.http_pid_file),
                self.other_process_pid(_read_pid_file(self.server_pid_file)),
            ]
            if not any(is_pid_running(p) for p in pending):
                break
            time.sleep(0.2)

        for p in (self.mqtt_pid_file, self.http_pid_file, self.server_pid_file):
            if not p.is_file():
                continue
            p.unlink(missing_ok=True)

        self.stop_file.unlink(missing_ok=True)

    def cleanup_children_only(self) -> None:
        for pid_file in (self.mqtt_pid_file, self.http_pid_file):
            pid = _read_pid_file(pid_file)
            self.terminate_pid(pid, skip_current=True)

        for _ in range(20):
            if (
                is_pid_running(_read_pid_file(self.mqtt_pid_file))
                or is_pid_running(_read_pid_file(self.http_pid_file))
            ):
                time.sleep(0.2)
            else:
                break

        for p in (self.mqtt_pid_file, self.http_pid_file):
            p.unlink(missing_ok=True)

    def wait_for_tcp(self, host: str, port: int, timeout_sec: int = 15) -> bool:
        start = time.time()
        while True:
            if self._ping_tcp(host, port, timeout=1.0):
                return True
            if time.time() - start >= timeout_sec:
                return False
            time.sleep(1)

    def tcp_connects(self, host: str, port: int) -> bool:
        return self._ping_tcp(host, port, timeout=1.0)

    def pid_is_current_process(self, pid_text: str | None) -> bool:
        try:
            return int(str(pid_text or "").strip()) == os.getpid()
        except ValueError:
            return False

    def other_process_pid(self, pid_text: str | None) -> str:
        return "" if self.pid_is_current_process(pid_text) else (pid_text or "")

    def terminate_pid(self, pid_text: str | None, *, skip_current: bool) -> None:
        if not pid_text:
            return
        if skip_current and self.pid_is_current_process(pid_text):
            return
        if not is_pid_running(pid_text):
            return
        try:
            os.kill(int(str(pid_text).strip()), signal.SIGTERM)
        except (OSError, ValueError):
            pass

    def terminate_process(self, process) -> None:
        if process is None:
            return
        if process.poll() is not None:
            return
        try:
            process.terminate()
        except OSError:
            return

        for _ in range(10):
            if process.poll() is not None:
                return
            time.sleep(0.1)

        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                return
        try:
            process.wait(timeout=2)
        except Exception:
            pass

    def write_stop_request(self, reason: str) -> None:
        lines = [
            "stop",
            f"reason={reason}",
            f"pid={os.getpid()}",
            f"time={timestamp_now()}",
        ]
        self.stop_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def read_stop_request_summary(self) -> str:
        if not self.stop_file.is_file():
            return ""
        try:
            content = self.stop_file.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
        return content.replace("\r", "").replace("\n", "; ")

    def print_server_summary(self, resolved_host_ip: str) -> None:
        device_ota_url = self.device_ota_url_for_host(resolved_host_ip)
        self.log_info(f"Local server started")
        self.log_info(f"  Host IP   : {resolved_host_ip}")
        self.log_info(f"  MQTT URI  : mqtt://{resolved_host_ip}:{self.mqtt_port}")
        self.log_info(f"  HTTP Base : http://{resolved_host_ip}:{self.http_port}/")
        self.log_info(f"  Serve Dir : {self.serve_dir}")
        self.log_info(f"  Upload Dir: {self.upload_dir}")
        self.log_info(f"  State Dir : {self.state_dir}")
        self.log_info(f"  MQTT Log  : {self.mqtt_log}")
        self.log_info(f"  HTTP Log  : {self.http_log}")
        if self.device_ota:
            self.log_info(f"  Device OTA Board  : {self.device_ota_board}")
            self.log_info(f"  Device OTA Dir    : {self.device_ota_dir}")
            self.log_info(f"  Device OTA Path   : {self.device_ota_path}")
            self.log_info(f"  Device OTA URL    : {device_ota_url}")
            if self.device_ota_version:
                self.log_info(f"  Device OTA Version: {self.device_ota_version}")

    def start_children(self) -> None:
        self.mqtt_log.write_text("", encoding="utf-8")
        self.http_log.write_text("", encoding="utf-8")

        self.log_info(f"MQTT Log   : {self.mqtt_log}")
        self.log_info(f"HTTP Log   : {self.http_log}")

        mqtt_log_handle = self.mqtt_log.open("a", encoding="utf-8")
        http_log_handle = self.http_log.open("a", encoding="utf-8")

        mqtt_proc = subprocess.Popen(
            [self.mosquitto_command or "mosquitto", "-c", str(self.mosq_conf), "-v"],
            stdin=subprocess.DEVNULL,
            stdout=mqtt_log_handle,
            stderr=subprocess.STDOUT,
        )
        self.mqtt_process = mqtt_proc
        self.mqtt_pid_file.write_text(f"{mqtt_proc.pid}\n", encoding="utf-8")
        self.log_info(f"Starting mosquitto (pid={mqtt_proc.pid})")

        if not self.wait_for_tcp("127.0.0.1", self.mqtt_port, timeout_sec=15):
            raise RuntimeError(f"mosquitto failed to start. See {self.mqtt_log}")

        env = os.environ.copy()
        cli_dir = pathlib.Path(__file__).resolve().parents[1]
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{cli_dir}{os.pathsep}{existing_pythonpath}"
            if existing_pythonpath
            else str(cli_dir)
        )

        http_attempts = [
            (
                "local_http_server",
                [
                    sys.executable,
                    "-m",
                    "mmwk.local_http_server",
                    "--serve-dir",
                    self.serve_dir,
                    "--bind",
                    "0.0.0.0",
                    "--port",
                    str(self.http_port),
                    "--upload-dir",
                    self.upload_dir,
                ],
            ),
            (
                "static http.server fallback",
                [
                    sys.executable,
                    "-m",
                    "http.server",
                    str(self.http_port),
                    "--bind",
                    "0.0.0.0",
                    "--directory",
                    self.serve_dir,
                ],
            ),
        ]

        for index, (label, cmd) in enumerate(http_attempts):
            if index > 0:
                self.log_warn(
                    "Falling back to static HTTP file serving; upload endpoints are unavailable"
                )
            http_proc = self.start_http_server_attempt(label, cmd, http_log_handle, env=env)
            if http_proc is not None:
                self.http_process = http_proc
                return

        raise RuntimeError(f"HTTP server failed to start. See {self.http_log}")

    def start_http_server_attempt(self, label: str, cmd: list[str], log_handle, *, env=None):
        self.http_pid_file.unlink(missing_ok=True)
        self.log_info(f"Starting HTTP server command ({label}): {' '.join(cmd)}")
        http_proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=env,
        )
        self.http_process = http_proc
        self.http_pid_file.write_text(f"{http_proc.pid}\n", encoding="utf-8")
        self.log_info(f"Starting HTTP server (pid={http_proc.pid})")

        if self.wait_for_tcp("127.0.0.1", self.http_port, timeout_sec=15):
            return http_proc

        self.log_warn(f"HTTP server attempt failed ({label}). See {self.http_log}")
        self.terminate_process(http_proc)
        self.http_pid_file.unlink(missing_ok=True)
        return None

    def owned_child_running(self, process, pid_file: pathlib.Path) -> bool:
        if process is not None:
            return process.poll() is None
        return is_pid_running(_read_pid_file(pid_file))

    def run_server(self, stop_requested: bool = False) -> int:
        self.prepare_server()
        resolved_host_ip = self.prepared_host_ip

        with self.server_pid_file.open("w", encoding="utf-8") as handle:
            handle.write(f"{os.getpid()}\n")

        self.log_info(f"Supervisor PID: {os.getpid()}")

        try:
            self.start_children()
        except Exception:
            self.cleanup_server()
            raise

        self.write_env_file(resolved_host_ip)
        self.print_server_summary(resolved_host_ip)
        self.log_info(f"Env file written: {self.env_file}")

        def _on_signal(_signum, _frame):
            self.write_stop_request(f"signal:{_signum}")

        if hasattr(signal, "SIGINT"):
            signal.signal(signal.SIGINT, _on_signal)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _on_signal)

        if stop_requested:
            self.write_stop_request("run_server:stop_requested")

        exit_code = 0
        while True:
            if self.stop_file.is_file():
                summary = self.read_stop_request_summary()
                if summary:
                    self.log_info(f"Stop request detected ({summary})")
                else:
                    self.log_info("Stop request detected")
                break

            if not self.owned_child_running(self.mqtt_process, self.mqtt_pid_file):
                self.log_warn("MQTT process exited unexpectedly")
                exit_code = 1
                break
            if not self.owned_child_running(self.http_process, self.http_pid_file):
                self.log_warn("HTTP process exited unexpectedly")
                exit_code = 1
                break
            if not self.tcp_connects("127.0.0.1", self.mqtt_port):
                self.log_warn(f"MQTT is no longer listening on port {self.mqtt_port}")
                exit_code = 1
                break
            if not self.tcp_connects("127.0.0.1", self.http_port):
                self.log_warn(f"HTTP is no longer listening on port {self.http_port}")
                exit_code = 1
                break

            time.sleep(1)

        self.cleanup_server()
        return exit_code

    def start(self) -> int:
        self.prepare_start_state()
        self.log_info(f"Server Log : {self.server_log}")

        run_cmd = [
            sys.executable,
            "-m",
            "mmwk.server",
            "run",
            "--state-dir",
            self.state_dir,
            "--serve-dir",
            self.serve_dir,
            "--upload-dir",
            self.upload_dir,
            "--mqtt-port",
            str(self.mqtt_port),
            "--http-port",
            str(self.http_port),
        ]

        if self.device_ota:
            run_cmd.extend(["--device-ota", "--device-ota-board", self.device_ota_board])
        if self.host_ip:
            run_cmd.extend(["--host-ip", self.host_ip])
        if self.target_ip:
            run_cmd.extend(["--target-ip", self.target_ip])

        with self.server_log.open("a", encoding="utf-8") as handle:
            proc = subprocess.Popen(
                run_cmd,
                stdin=subprocess.DEVNULL,
                stdout=handle,
                stderr=subprocess.STDOUT,
                cwd=pathlib.Path(__file__).resolve().parents[1],
            )

        timeout = int(os.environ.get("MMWK_SERVER_START_TIMEOUT_SEC", "90"))
        for _ in range(timeout):
            if self.env_file.is_file():
                self.load_state_runtime()
                if self.tcp_connects("127.0.0.1", self.mqtt_port) and self.tcp_connects("127.0.0.1", self.http_port):
                    output = _read_text(self.server_log)
                    if output:
                        print(output, end="")
                    return 0

            if not is_pid_running(str(proc.pid)):
                print(_read_text(self.server_log), file=sys.stderr)
                raise RuntimeError(f"detached server supervisor exited. See {self.server_log}")
            time.sleep(1)

        if proc.poll() is None:
            proc.terminate()
        raise RuntimeError(
            f"timed out waiting for detached server to become ready. See {self.server_log}"
        )

    def stop(self) -> int:
        self.write_stop_request("command:stop")

        for _ in range(20):
            server_pid = _read_pid_file(self.server_pid_file)
            mqtt_pid = _read_pid_file(self.mqtt_pid_file)
            http_pid = _read_pid_file(self.http_pid_file)
            if not (
                is_pid_running(server_pid)
                or is_pid_running(mqtt_pid)
                or is_pid_running(http_pid)
            ):
                break
            time.sleep(0.2)

        server_pid = _read_pid_file(self.server_pid_file)
        if is_pid_running(server_pid):
            self.terminate_pid(server_pid, skip_current=True)
            for _ in range(20):
                if not is_pid_running(_read_pid_file(self.server_pid_file)):
                    break
                time.sleep(0.2)

        if not is_pid_running(_read_pid_file(self.server_pid_file)):
            self.cleanup_children_only()

        for p in (self.server_pid_file, self.mqtt_pid_file, self.http_pid_file, self.stop_file):
            p.unlink(missing_ok=True)

        self.log_info(f"State Dir : {self.state_dir}")
        print("Local server stopped")
        return 0

    def status(self) -> int:
        self.load_state_runtime()

        mqtt_pid = _read_pid_file(self.mqtt_pid_file)
        http_pid = _read_pid_file(self.http_pid_file)
        server_pid = _read_pid_file(self.server_pid_file)

        mqtt_running = "yes" if is_pid_running(mqtt_pid) else "no"
        http_running = "yes" if is_pid_running(http_pid) else "no"
        server_running = "yes" if is_pid_running(server_pid) else "no"

        mqtt_listening = "yes" if self.tcp_connects("127.0.0.1", self.mqtt_port) else "no"
        http_listening = "yes" if self.tcp_connects("127.0.0.1", self.http_port) else "no"

        print(f"State Dir : {self.state_dir}")
        print(f"Server Log: {self.server_log}")
        print(f"MQTT Log  : {self.mqtt_log}")
        print(f"HTTP Log  : {self.http_log}")
        print(f"Server PID: {server_pid}")
        print(f"MQTT PID  : {mqtt_pid}")
        print(f"HTTP PID  : {http_pid}")
        print(f"Server Up : {server_running}")
        print(f"MQTT Port : {self.mqtt_port}")
        print(f"HTTP Port : {self.http_port}")
        print(f"Device OTA Mode : {_to_bool(str(self.device_ota))}")
        print(f"Device OTA Board: {self.device_ota_board}")
        print(f"Device OTA Dir  : {self.device_ota_dir}")
        print(f"Device OTA Path : {self.device_ota_path}")
        print(f"Device OTA URL  : {self.device_ota_url}")
        print(f"Device OTA Ver  : {self.device_ota_version}")
        print(f"MQTT Listen: {mqtt_listening}")
        print(f"HTTP Listen: {http_listening}")
        print(f"MQTT Up   : {'yes' if mqtt_running == 'yes' and mqtt_listening == 'yes' else 'no'}")
        print(f"HTTP Up   : {'yes' if http_running == 'yes' and http_listening == 'yes' else 'no'}")

        if self.env_file.is_file():
            print(f"Env File  : {self.env_file}")
            print(_read_text(self.env_file).rstrip("\n"))

        return 0

    def env(self) -> int:
        if not self.env_file.is_file():
            raise RuntimeError(f"env file not found: {self.env_file}")

        print(_read_text(self.env_file).rstrip("\n"))
        return 0


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state-dir", default="", help="State/log/pid directory (default: ./build_output/local_server)")
    parser.add_argument("--serve-dir", default="", help="Directory exposed by HTTP server")
    parser.add_argument("--upload-dir", default="", help="Directory for HTTP POST upload dumps")
    parser.add_argument("--device-ota", action="store_true", help="Publish bridge OTA artifact")
    parser.add_argument("--device-ota-board", default="", help="Board name for bridge OTA artifact lookup")
    parser.add_argument("--host-ip", default="", help="Advertised host IP for device access")
    parser.add_argument("--target-ip", default="", help="Device/runtime IP used to auto-pick host IP")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT listen port (default: 1883)")
    parser.add_argument("--http-port", type=int, default=8380, help="HTTP listen port (default: 8380)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="server.py",
        description="local MQTT + HTTP helper for radar OTA and collect",
    )

    parser.add_argument("--invoke-pwd", default="", help=argparse.SUPPRESS)

    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Start detached supervisor")
    _add_common_options(start)

    run = sub.add_parser("run", help="Start foreground supervisor")
    _add_common_options(run)

    stop = sub.add_parser("stop", help="Stop local server")
    stop.add_argument("--state-dir", default="", help="State/log/pid directory (default: ./build_output/local_server)")

    status = sub.add_parser("status", help="Show local server status")
    status.add_argument("--state-dir", default="", help="State/log/pid directory (default: ./build_output/local_server)")

    env = sub.add_parser("env", help="Print env variables")
    env.add_argument("--state-dir", default="", help="State/log/pid directory (default: ./build_output/local_server)")

    return parser


def _resolve_runtime_for_parsed_args(args: argparse.Namespace) -> ServerRuntime:
    if not args.state_dir:
        state_dir = ""
    else:
        state_dir = args.state_dir

    return ServerRuntime(
        state_dir=state_dir,
        serve_dir=getattr(args, "serve_dir", "") ,
        upload_dir=getattr(args, "upload_dir", ""),
        device_ota=getattr(args, "device_ota", False),
        device_ota_board=getattr(args, "device_ota_board", ""),
        host_ip=getattr(args, "host_ip", ""),
        target_ip=getattr(args, "target_ip", ""),
        mqtt_port=getattr(args, "mqtt_port", 1883),
        http_port=getattr(args, "http_port", 8380),
        invoke_pwd=getattr(args, "invoke_pwd", ""),
    )


def run_cli(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Command-level options normalize
    runtime = _resolve_runtime_for_parsed_args(args)

    try:
        if args.command == "run":
            return runtime.run_server()
        if args.command == "start":
            return runtime.start()
        if args.command == "stop":
            return runtime.stop()
        if args.command == "status":
            return runtime.status()
        if args.command == "env":
            return runtime.env()
        parser.error(f"unknown command: {args.command}")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
