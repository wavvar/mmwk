"""Device OTA command: HTTP-based ESP OTA update."""

import json
import os
import time

from mmwk_cli._logging import logger
from mmwk_cli.http_server import FirmwareHttpServer
from mmwk_cli.network_runtime import (
    network_ready,
    network_runtime_ip,
    network_runtime_summary,
    terminal_network_failure,
)


class DeviceOtaCommand:
    """Serve a local .bin bundle or pass through a remote URL for device self-OTA."""

    def __init__(self, mcp):
        self.mcp = mcp

    @staticmethod
    def _parse_json_dict(text: str) -> dict:
        try:
            payload = json.loads(text)
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}
        nested = payload.get("data")
        return nested if isinstance(nested, dict) else payload

    def _network_runtime_ready(self) -> tuple[bool, str]:
        hi_data = {}
        status_data = {}
        diag_data = {}
        device_ip = ""
        try:
            hi_resp = self.mcp.call_tool("device", {"action": "hi"}, timeout=8)
            hi_text = self.mcp.extract_text(hi_resp)
            hi_data = self._parse_json_dict(hi_text)
            device_ip = network_runtime_ip(hi_data)
        except Exception as exc:
            return False, f"device.hi_error={exc}"

        try:
            status_resp = self.mcp.call_tool("network", {"action": "status"}, timeout=8)
            status_text = self.mcp.extract_text(status_resp)
            status_data = self._parse_json_dict(status_text)
        except Exception as exc:
            return False, f"network.status_error={exc}"

        try:
            diag_resp = self.mcp.call_tool("network", {"action": "diag"}, timeout=8)
            diag_text = self.mcp.extract_text(diag_resp)
            diag_data = self._parse_json_dict(diag_text)
        except Exception:
            diag_data = {}

        detail = network_runtime_summary(status_data, diag_payload=diag_data, device_ip=device_ip)
        if terminal_network_failure(status_data, diag_data):
            return False, detail

        ready = network_ready(status_data)
        return ready, detail

    def _wait_for_network_runtime_ready(
        self,
        timeout_sec: float,
        interval_sec: float = 2.0,
    ) -> bool:
        deadline = time.time() + max(0.0, timeout_sec)
        last_detail = "network status unavailable"
        while time.time() < deadline:
            ready, detail = self._network_runtime_ready()
            last_detail = detail
            if ready:
                logger.info("Device network ready for OTA: %s", detail)
                return True
            time.sleep(interval_sec)
        logger.error("Device network not ready for OTA within %.0fs: %s", timeout_sec, last_detail)
        return False

    @staticmethod
    def _is_retriable_http_connect(msg: str) -> bool:
        if not isinstance(msg, str):
            return False
        upper = msg.upper()
        return "ESP_ERR_HTTP_CONNECT" in upper or "HTTP_CONNECT" in upper

    @staticmethod
    def _is_retriable_start_error(msg: str) -> bool:
        if not isinstance(msg, str):
            return False
        lower = msg.lower()
        if "timeout waiting for tool 'device' response" in lower:
            return True
        if "timed out" in lower and "device" in lower:
            return True
        return False

    def _device_runtime_ip(self) -> str:
        for tool_name, tool_args in (
            ("device", {"action": "hi"}),
            ("network", {"action": "status"}),
        ):
            try:
                resp = self.mcp.call_tool(tool_name, tool_args, timeout=8)
                payload = self._parse_json_dict(self.mcp.extract_text(resp))
            except Exception:
                continue

            runtime_ip = network_runtime_ip(payload)
            if runtime_ip:
                return runtime_ip

        return ""

    def _execute_once(self, url: str, served_name: str, server, timeout: float) -> tuple[bool, bool]:
        try:
            # Drop stale OTA notifications from previous runs/retries.
            self.mcp.transport.drain_notifications()
        except Exception:
            pass

        try:
            result = self.mcp.call_tool("device", {"action": "ota", "url": url}, timeout=45)
            result_text = self.mcp.extract_text(result)
            logger.info(f"Device OTA initiated: {result_text}")
            payload = self._parse_json_dict(result_text)
            if isinstance(payload, dict) and payload.get("status") not in ("started", "success", "ok", None):
                logger.error(f"Device OTA rejected: {payload}")
                return False, False
        except Exception as exc:
            err = str(exc)
            logger.error(f"Device OTA command failed before download start: {err}")
            return False, self._is_retriable_start_error(err)

        start_time = time.time()
        downloaded = False if served_name else True
        success_seen = False
        rebooting_seen = False
        last_pct = -1
        retriable_http_error = False

        while time.time() - start_time < timeout:
            for notif in self.mcp.transport.drain_notifications():
                if not isinstance(notif, dict):
                    continue
                params = notif.get("params", {})
                if not isinstance(params, dict):
                    continue
                data = params.get("data", {})
                if isinstance(data, str):
                    try:
                        data = json.loads(data)
                    except Exception:
                        data = {}
                if not isinstance(data, dict):
                    continue

                status = data.get("status", "")
                if status == "device_ota_progress":
                    pct = data.get("progress", -1)
                    if isinstance(pct, (int, float)):
                        pct = int(pct)
                        if pct != last_pct:
                            logger.info(f"  [device ota] progress={pct}%")
                            last_pct = pct
                    continue

                if status == "device_ota_success":
                    logger.info("  [device ota] image written, waiting for reboot")
                    success_seen = True
                elif status == "device_ota_rebooting":
                    logger.info("  [device ota] rebooting")
                    rebooting_seen = True
                elif status == "device_ota_error":
                    msg = str(data.get("msg", "unknown error"))
                    logger.error(f"Device OTA failed: {msg}")
                    retriable_http_error = self._is_retriable_http_connect(msg)
                    return False, retriable_http_error
                elif status:
                    logger.info(f"  [device ota] status={status} data={data}")

            if server and not downloaded and server.tracker.is_complete(served_name):
                logger.info(f"  [device ota] download complete: {served_name}")
                downloaded = True

            if rebooting_seen or (success_seen and downloaded):
                break

            time.sleep(1)

        logger.info("Waiting for device to come back after OTA reboot...")
        reconnect_deadline = time.time() + max(45.0, timeout / 2)
        last_error = None
        while time.time() < reconnect_deadline:
            try:
                self.mcp.initialize(timeout=5)
                self.mcp.call_tool("device", {"action": "hi"}, timeout=10)
                elapsed = time.time() - start_time
                logger.info(f"Device OTA complete in {elapsed:.1f}s")
                return True, False
            except Exception as exc:
                last_error = exc
                time.sleep(2)

        logger.error(f"Device did not return after OTA: {last_error}")
        return False, retriable_http_error

    def execute(self,
                fw_path: str = None,
                url: str = None,
                http_port: int = 8380,
                use_https: bool = False,
                https_cert: str = None,
                https_key: str = None,
                timeout: float = 300.0) -> bool:
        if not fw_path and not url:
            logger.error("Either fw_path or url is required for device OTA")
            return False

        server = None
        served_name = None

        if fw_path:
            if not os.path.exists(fw_path):
                logger.error(f"Firmware file not found: {fw_path}")
                return False
            if not fw_path.lower().endswith(".bin"):
                logger.error(f"Device OTA only supports .bin artifacts: {fw_path}")
                return False

            served_name = os.path.basename(fw_path)
            fw_dir = os.path.dirname(os.path.abspath(fw_path))
            fw_size = os.path.getsize(fw_path)
            logger.info(f"ESP OTA artifact: {served_name} ({fw_size} bytes)")

            server = FirmwareHttpServer(
                directory=fw_dir,
                port=http_port,
                scheme="https" if use_https else "http",
                certfile=https_cert,
                keyfile=https_key,
            )
            device_ip = self._device_runtime_ip()
            server.start(target_ip=device_ip)
            url = f"{server.get_base_url(target_ip=device_ip)}{served_name}"
            if device_ip:
                logger.info("Advertising device OTA server for device IP %s: %s", device_ip, url)
            # Give the HTTP(S) server thread a brief window to accept connections.
            time.sleep(1.5 if use_https else 0.2)
        else:
            logger.info(f"ESP OTA URL: {url}")

        try:
            attempts = 3 if use_https else 1
            for attempt in range(1, attempts + 1):
                preflight_timeout = 150.0 if use_https else 90.0
                if not self._wait_for_network_runtime_ready(preflight_timeout):
                    return False

                ok, retriable_http_connect = self._execute_once(
                    url=url,
                    served_name=served_name,
                    server=server,
                    timeout=timeout,
                )
                if ok:
                    return True

                if use_https and retriable_http_connect and attempt < attempts:
                    logger.warning("Retrying HTTPS device OTA after HTTP connect failure (%d/%d)...", attempt, attempts)
                    time.sleep(5)
                    continue

                return False

            return False
        finally:
            if server:
                server.stop()
