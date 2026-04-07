"""OTA command: HTTP-based firmware update."""

import os
import json
import time
import shutil
import threading
import tempfile
from urllib.parse import urlparse

import paho.mqtt.client as mqtt

from mmwk_cli._logging import logger
from mmwk_cli.http_server import FirmwareHttpServer
from mmwk_cli.commands._radar_meta import resolve_radar_update_request
from mmwk_cli.mqtt_topics import build_mqtt_topics
from mmwk_cli.network_runtime import (
    network_ready,
    network_runtime_ip,
    network_runtime_summary,
    terminal_network_failure,
)


def _parse_broker_endpoint(raw_broker: str, default_port: int) -> tuple[str, int]:
    broker = (raw_broker or "").strip()
    if not broker:
        return "localhost", default_port

    if "://" in broker:
        parsed = urlparse(broker)
        host = parsed.hostname or "localhost"
        port = parsed.port or default_port
        return host, int(port)

    if broker.count(":") == 1:
        host, maybe_port = broker.rsplit(":", 1)
        if maybe_port.isdigit():
            return host, int(maybe_port)

    return broker, default_port


def _create_mqtt_client(client_id: str) -> mqtt.Client:
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


def _unwrap_tool_data(payload: dict | list) -> dict:
    if isinstance(payload, dict):
        data = payload.get("data", payload)
        if isinstance(data, dict):
            return data
    return {}


def _build_raw_restore_args(payload: dict | list) -> dict:
    raw = _unwrap_tool_data(payload)
    restore = {
        "action": "raw",
        "enabled": bool(raw.get("enabled", False)),
        "uart_enabled": False,
    }
    for key in ("uri",):
        value = raw.get(key)
        if isinstance(value, str) and value:
            restore[key] = value
    return restore


class _OtaRawRespCaptureSession:
    def __init__(
        self,
        host: str,
        port: int,
        resp_topic: str,
        raw_output: str,
        subscribe_timeout: float,
    ):
        self.host = host
        self.port = port
        self.resp_topic = resp_topic
        self.raw_output = raw_output
        self.subscribe_timeout = subscribe_timeout
        self.messages = 0
        self.bytes = 0
        self._client = None
        self._raw_file = None
        self._subscribed = threading.Event()
        self._connect_rc = None
        self._subscribe_error = None

    def _on_connect(self, client, userdata, flags, rc):
        if rc != 0:
            self._connect_rc = rc
            return
        result, _ = client.subscribe(self.resp_topic, qos=0)
        if result != mqtt.MQTT_ERR_SUCCESS:
            self._subscribe_error = f"subscribe failed for {self.resp_topic}: rc={result}"

    def _on_subscribe(self, client, userdata, mid, granted_qos):
        self._subscribed.set()

    def _on_message(self, client, userdata, msg):
        payload = msg.payload or b""
        self._raw_file.write(payload)
        self._raw_file.flush()
        self.messages += 1
        self.bytes += len(payload)

    def start(self):
        out_dir = os.path.dirname(os.path.abspath(self.raw_output))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        self._raw_file = open(self.raw_output, "wb")
        self._client = _create_mqtt_client(client_id=f"mmwk_ota_capture_{int(time.time())}")
        self._client.on_connect = self._on_connect
        self._client.on_subscribe = self._on_subscribe
        self._client.on_message = self._on_message
        self._client.connect(self.host, self.port, 60)
        self._client.loop_start()

        deadline = time.time() + max(1.0, float(self.subscribe_timeout))
        while not self._subscribed.is_set() and time.time() < deadline:
            if self._connect_rc is not None:
                break
            if self._subscribe_error is not None:
                break
            time.sleep(0.05)

        if not self._subscribed.is_set():
            connect_error = (
                f"connect failed rc={self._connect_rc}"
                if self._connect_rc is not None
                else "subscribe-ready timeout"
            )
            if self._subscribe_error is not None:
                connect_error = self._subscribe_error
            self.stop()
            raise RuntimeError(f"Failed to start OTA raw_resp capture: {connect_error}")

    def stop(self):
        if self._client is not None:
            try:
                self._client.loop_stop()
            except Exception:
                pass
            try:
                self._client.disconnect()
            except Exception:
                pass
            self._client = None

        if self._raw_file is not None:
            try:
                self._raw_file.close()
            except Exception:
                pass
            self._raw_file = None


def _extract_radar_state(payload) -> str:
    """Extract radar state from MCP payload text/object for bridge/hub compatibility."""
    if isinstance(payload, dict):
        state = payload.get("state")
        if not isinstance(state, str):
            nested = payload.get("data")
            if isinstance(nested, dict):
                state = nested.get("state")
        return state.lower() if isinstance(state, str) else ""

    if isinstance(payload, str):
        lower = payload.lower()
        if "updating" in lower:
            return "updating"
        if "stopped" in lower:
            return "stopped"
        if "starting" in lower:
            return "starting"
        if "running" in lower:
            return "running"

    return ""


def _is_transient_http_connect_error(data: dict) -> bool:
    if not isinstance(data, dict):
        return False

    message = str(data.get("msg", "")).strip().lower()
    error_code = data.get("error_code")
    progress = data.get("progress")
    transferred = data.get("bytes")

    if "failed to open http connection" not in message and error_code != 28674:
        return False

    if isinstance(progress, (int, float)) and progress > 0:
        return False
    if isinstance(transferred, (int, float)) and transferred > 0:
        return False

    return True


class OtaCommand:
    """Orchestrates firmware OTA via HTTP: starts local server, tells device to download."""

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

    def _device_runtime_ip(self) -> str:
        for attempt in range(3):
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

            if attempt < 2:
                time.sleep(1.0)

        return ""

    def _runtime_ready(self) -> tuple[bool, bool, str]:
        hi_data = {}
        status_data = {}
        diag_data = {}
        radar_data = {}
        device_ip = ""

        try:
            hi_resp = self.mcp.call_tool("device", {"action": "hi"}, timeout=8)
            hi_data = self._parse_json_dict(self.mcp.extract_text(hi_resp))
            device_ip = network_runtime_ip(hi_data)
        except Exception as exc:
            return False, False, f"device.hi_error={exc}"

        try:
            status_resp = self.mcp.call_tool("network", {"action": "status"}, timeout=8)
            status_data = self._parse_json_dict(self.mcp.extract_text(status_resp))
        except Exception as exc:
            return False, False, f"network.status_error={exc}"

        try:
            diag_resp = self.mcp.call_tool("network", {"action": "diag"}, timeout=8)
            diag_data = self._parse_json_dict(self.mcp.extract_text(diag_resp))
        except Exception:
            diag_data = {}

        try:
            radar_resp = self.mcp.call_tool("radar", {"action": "status"}, timeout=8)
            radar_payload = self._parse_json_dict(self.mcp.extract_text(radar_resp))
            radar_data = radar_payload if isinstance(radar_payload, dict) else {}
        except Exception as exc:
            return False, False, f"radar.status_error={exc}"

        detail = network_runtime_summary(status_data, diag_payload=diag_data, device_ip=device_ip)
        radar_state = _extract_radar_state(radar_data)
        detail = f"{detail}, radar_state={radar_state or '<none>'}"

        if terminal_network_failure(status_data, diag_data):
            return False, True, detail

        ready = network_ready(status_data) and radar_state == "running"
        return ready, False, detail

    def _wait_for_runtime_ready(
        self,
        timeout_sec: float,
        interval_sec: float = 2.0,
    ) -> bool:
        deadline = time.time() + max(0.0, timeout_sec)
        last_detail = "runtime state unavailable"

        while time.time() < deadline:
            ready, terminal_failure, detail = self._runtime_ready()
            last_detail = detail
            if ready:
                logger.info("Radar OTA preflight ready: %s", detail)
                return True
            if terminal_failure:
                logger.error("Radar OTA preflight hit terminal network failure: %s", detail)
                return False
            time.sleep(interval_sec)

        logger.error("Radar OTA preflight timed out within %.0fs: %s", timeout_sec, last_detail)
        return False

    def _tool_json(self, tool_name: str, arguments: dict, timeout: float) -> dict:
        try:
            result = self.mcp.call_tool(tool_name, arguments, timeout=timeout)
            text = self.mcp.extract_text(result)
            payload = json.loads(text)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _prepare_local_http_directory(
        self,
        fw_path: str,
        cfg_path: str | None,
    ) -> tuple[str, tempfile.TemporaryDirectory | None]:
        fw_abs = os.path.abspath(fw_path)
        fw_dir = os.path.dirname(fw_abs)
        if not cfg_path:
            return fw_dir, None

        cfg_abs = os.path.abspath(cfg_path)
        cfg_dir = os.path.dirname(cfg_abs)
        if cfg_dir == fw_dir:
            return fw_dir, None

        staging = tempfile.TemporaryDirectory(prefix="mmwk_ota_http_")
        shutil.copy2(fw_abs, os.path.join(staging.name, os.path.basename(fw_abs)))
        shutil.copy2(cfg_abs, os.path.join(staging.name, os.path.basename(cfg_abs)))
        logger.info(
            "Config file not in same directory as firmware; staging local OTA payload in %s",
            staging.name,
        )
        return staging.name, staging

    def execute(self, fw_path: str, cfg_path: str = None,
                 http_port: int = 8380, base_url: str = None,
                 version: str = None, welcome: bool = None,
                 verify: bool = None, timeout: float = 120.0,
                 force: bool = False,
                 progress_interval: int = 5,
                 raw_resp_output: str = None,
                 raw_capture_broker: str = None,
                 raw_resp_topic: str = None,
                 raw_capture_timeout: float = 10.0) -> bool:
        """Start HTTP server and tell device to OTA from it."""

        if not os.path.exists(fw_path):
            logger.error(f"Firmware file not found: {fw_path}")
            return False

        fw_name = os.path.basename(fw_path)
        fw_dir = os.path.dirname(os.path.abspath(fw_path))
        fw_size = os.path.getsize(fw_path)
        logger.info(f"Firmware: {fw_name} ({fw_size} bytes)")
        try:
            update_request = resolve_radar_update_request(
                fw_path,
                welcome=welcome,
                verify=verify,
                version=version,
            )
        except ValueError as exc:
            logger.error(str(exc))
            return False
        if update_request.version:
            logger.info(f"Expected version: {update_request.version}")
        logger.info(
            "Radar update contract: welcome=%s verify=%s",
            update_request.welcome,
            update_request.verify,
        )

        cfg_name = None
        if cfg_path:
            if not os.path.exists(cfg_path):
                logger.error(f"Config file not found: {cfg_path}")
                return False
            cfg_name = os.path.basename(cfg_path)
            cfg_dir = os.path.dirname(os.path.abspath(cfg_path))
            if cfg_dir != fw_dir:
                if base_url:
                    logger.warning(
                        "Config file not in same directory as firmware; external OTA base URL must serve %s alongside %s",
                        cfg_name,
                        fw_name,
                    )
                else:
                    logger.warning(
                        "Config file not in same directory as firmware; staging both files for local OTA server",
                    )

        capture_session = None
        restore_raw_args = None
        staged_http_dir = None

        if not self._wait_for_runtime_ready(timeout_sec=min(max(timeout / 2.0, 30.0), 90.0)):
            return False

        # Start local HTTP server if no external URL provided
        server = None
        if not base_url:
            device_ip = self._device_runtime_ip()
            http_directory, staged_http_dir = self._prepare_local_http_directory(fw_path, cfg_path)
            server = FirmwareHttpServer(directory=http_directory, port=http_port)
            server.start(target_ip=device_ip)
            base_url = server.get_base_url(target_ip=device_ip)
            if device_ip:
                logger.info(f"Advertising OTA server for device IP {device_ip}: {base_url}")
            time.sleep(0.2)

        try:
            if raw_resp_output:
                raw_state = self._tool_json("radar", {"action": "raw"}, timeout=min(timeout, 10.0))
                restore_raw_args = _build_raw_restore_args(raw_state)
                raw_cfg = _unwrap_tool_data(raw_state)
                hi_cfg = self._tool_json("device", {"action": "hi"}, timeout=min(timeout, 10.0))
                hi_data = _unwrap_tool_data(hi_cfg)
                client_id = hi_data.get("client_id") or hi_data.get("id") or "mmwk_ota_capture"
                default_topics = build_mqtt_topics(client_id, include_raw_cmd=True)
                resolved_resp_topic = (
                    raw_resp_topic
                    or raw_cfg.get("resp_topic")
                    or hi_data.get("raw_resp_topic")
                    or default_topics["raw_resp_topic"]
                )
                resolved_broker = (
                    raw_capture_broker
                    or raw_cfg.get("uri")
                    or hi_data.get("mqtt_uri")
                    or "localhost"
                )
                host, mqtt_port = _parse_broker_endpoint(resolved_broker, 1883)

                capture_session = _OtaRawRespCaptureSession(
                    host=host,
                    port=mqtt_port,
                    resp_topic=resolved_resp_topic,
                    raw_output=raw_resp_output,
                    subscribe_timeout=raw_capture_timeout,
                )
                capture_session.start()

                raw_enable_args = {
                    "action": "raw",
                    "enabled": True,
                    "uart_enabled": False,
                }
                if raw_cfg.get("uri"):
                    raw_enable_args["uri"] = raw_cfg.get("uri")
                elif hi_data.get("mqtt_uri"):
                    raw_enable_args["uri"] = hi_data.get("mqtt_uri")

                self.mcp.call_tool("radar", raw_enable_args, timeout=min(timeout, 10.0))
                logger.info(
                    "OTA raw_resp capture armed: broker=%s:%s topic=%s output=%s",
                    host,
                    mqtt_port,
                    resolved_resp_topic,
                    raw_resp_output,
                )

            start_time = time.time()
            # Send OTA command.  Device acks immediately; download+flash is async.
            logger.info(f"Sending OTA command: base={base_url}, firmware={fw_name}")
            ota_args = {
                "action": "ota",
                "base": base_url,
                "firmware": fw_name,
            }
            if cfg_name:
                ota_args["config"] = cfg_name
            ota_args["welcome"] = update_request.welcome
            ota_args["verify"] = update_request.verify
            if update_request.version:
                ota_args["version"] = update_request.version
            if force:
                ota_args["force"] = True
            if progress_interval >= 0:
                ota_args["prog_intvl"] = progress_interval

            def send_ota_request(log_prefix: str) -> bool:
                try:
                    result = self.mcp.call_tool("radar", ota_args, timeout=30)
                except Exception as ota_err:
                    logger.error(f"{log_prefix} failed: {ota_err}")
                    return False
                text = self.mcp.extract_text(result)
                logger.info(f"{log_prefix}: {text}")
                return True

            if not send_ota_request("OTA initiated"):
                return False

            # -- 3-Phase OTA completion detection --
            #
            # Phase 1 - Wait for device to download the firmware file from
            #           our HTTP server.  The tracker records when the full
            #           file body has been sent.  Timeout = timeout/2.
            #
            # Phase 2 - Wait for radar state to leave "running".  This means
            #           the radar driver was stopped and UART flashing started
            #           (state -> "updating").  Timeout = timeout/2.
            #
            # Phase 3 - Wait for radar to come back to "running".  This
            #           confirms flashing completed and radar rebooted.
            #           Timeout = up to REBOOT_TIMEOUT extra seconds.
            #
            # At each phase we also drain any push notifications so we can
            # react to an explicit ota_complete/ota_error immediately.
            POLL_SEC      = progress_interval if progress_interval > 0 else 3
            REBOOT_TIMEOUT = 120  # max extra seconds for post-flash boot
            TRANSITION_GRACE_TIMEOUT = 30  # hub OTA may linger in updating briefly before running

            # Track OTA progress reported by device
            _ota_last_pct = [-1]  # list for mutation in closure
            _download_success_seen = [False]
            _download_progress_seen = [False]
            _flash_start_seen = [False]
            _flash_progress_seen = [False]

            def _print_progress(pct: int):
                """Render an in-place ASCII progress bar."""
                bar_len = 30
                filled = bar_len * pct // 100
                bar = '\u2588' * filled + '\u2591' * (bar_len - filled)
                print(f"\r  [{bar}] {pct}% (OTA flashing...)", end='', flush=True)

            def drain_notifs() -> str:
                """Drain notifications; return terminal hint immediately."""
                result = ""
                for n in self.mcp.transport.drain_notifications():
                    if not isinstance(n, dict):
                        continue
                    params = n.get("params", {})
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
                    st = data.get("status", "")
                    # Handle progress updates - show progress bar, suppress other logs
                    if st in ("flash_progress", "ota_progress", "progress"):
                        pct = data.get("progress", -1)
                        if st in ("ota_progress", "progress") and data.get("bytes", 0):
                            _download_progress_seen[0] = True
                        if st == "flash_progress":
                            _flash_progress_seen[0] = True
                        if isinstance(pct, (int, float)) and 0 <= pct <= 100:
                            pct = int(pct)
                            if pct != _ota_last_pct[0]:
                                _print_progress(pct)
                                _ota_last_pct[0] = pct
                        continue
                    if st:
                        if _ota_last_pct[0] >= 0:
                            print()  # finish progress line before logging
                            _ota_last_pct[0] = -1
                        logger.info(f"  [notif] device status={st} data={data}")
                    if st == "download_success":
                        _download_success_seen[0] = True
                    elif st == "flash_start":
                        _flash_start_seen[0] = True
                    if st in ("ota_complete", "ota_done", "complete", "done", "success", "flash_success"):
                        result = "done"
                    elif st == "download_success":
                        result = "download_success"
                    elif st in ("ota_error", "ota_failed", "error", "failed"):
                        if _is_transient_http_connect_error(data):
                            logger.warning(
                                "Transient OTA HTTP-open failure before download start: %s",
                                data.get("msg", "Unknown error"),
                            )
                            result = "retry_http_connect"
                            continue
                        msg = data.get("msg", "Unknown error")
                        logger.error(f"OTA error from device: {msg} (Data: {data})")
                        result = "error"
                return result

            def poll_radar_state() -> str:
                """Call radar/status; return state string or '' on timeout."""
                try:
                    resp = self.mcp.call_tool("radar", {"action": "status"}, timeout=8)
                    text = self.mcp.extract_text(resp)
                    try:
                        return _extract_radar_state(json.loads(text))
                    except Exception:
                        return _extract_radar_state(text.strip())
                except Exception:
                    return ""  # device offline or timed-out

            # -- Phase 1: wait for HTTP download to complete --
            phase1_dl = timeout / 2
            logger.info(f"Phase 1/3: waiting up to {phase1_dl:.0f}s for device to "
                        f"download {fw_name} ({fw_size} bytes)...")
            p1_deadline = time.time() + phase1_dl
            downloaded = server.tracker.is_complete(fw_name) if server else True
            phase1_retry_used = False

            while not downloaded and time.time() < p1_deadline:
                hint = drain_notifs()
                if hint == "done":
                    logger.info("\u2705 OTA complete (notification, phase 1)")
                    elapsed = time.time() - start_time
                    logger.info(f"\u23f1\ufe0f  Update took {elapsed:.1f} seconds.")
                    return True
                if hint == "retry_http_connect":
                    if phase1_retry_used:
                        logger.error("OTA retry budget exhausted after repeated HTTP-open failures")
                        return False
                    logger.warning(
                        "Retrying OTA once after pre-download HTTP-open failure"
                    )
                    phase1_retry_used = True
                    if not send_ota_request("OTA retry initiated"):
                        return False
                    p1_deadline = time.time() + phase1_dl
                    time.sleep(1.0)
                    continue
                if hint == "error":
                    return False
                if hint == "download_success":
                    downloaded = True
                downloaded = server.tracker.is_complete(fw_name) if server else True
                if not downloaded:
                    elapsed = time.time() - (p1_deadline - phase1_dl)
                    logger.info(f"  [phase1] waiting for download... {elapsed:.0f}s elapsed")
                time.sleep(2)

            downloaded = downloaded or _download_success_seen[0]
            if downloaded:
                logger.info("  [phase1] Firmware downloaded \u2713 \u2014 device will now apply update")
            else:
                logger.warning("  [phase1] download not confirmed via HTTP; proceeding anyway")

            # -- Phase 2: wait for radar to go offline / into updating --
            phase2_timeout = timeout / 2
            logger.info(f"Phase 2/3: waiting up to {phase2_timeout:.0f}s for radar to "
                        f"enter update mode...")
            p2_deadline = time.time() + phase2_timeout
            last_poll = 0.0
            radar_was_running = False
            radar_left_running = False
            seen_update_state = False

            while time.time() < p2_deadline:
                hint = drain_notifs()
                if hint == "done":
                    logger.info("\u2705 OTA complete (notification, phase 2)")
                    return True
                if hint == "retry_http_connect":
                    logger.error("OTA error from device: retryable HTTP-open failure arrived after phase 1")
                    return False
                if hint == "error":
                    return False

                if time.time() - last_poll >= POLL_SEC:
                    last_poll = time.time()
                    state = poll_radar_state()
                    if state:
                        logger.info(f"  [phase2] radar state={state!r}")
                        if state == "running":
                            radar_was_running = True
                        elif state in ("updating", "stopped", "starting", "error"):
                            seen_update_state = True
                            if radar_was_running:
                                logger.info(f"  [phase2] state changed to {state!r} \u2014 update in progress")
                            else:
                                logger.info(f"  [phase2] observed {state!r} before running \u2014 update already in progress")
                            radar_left_running = True
                            break
                        elif radar_was_running and state != "running":
                            logger.info(f"  [phase2] state changed to {state!r} \u2014 update in progress")
                            radar_left_running = True
                            break
                    else:
                        # Device stopped responding -> also means update is underway
                        logger.info("  [phase2] device unresponsive \u2014 update underway")
                        radar_left_running = True
                        break

                time.sleep(1)

            if not radar_left_running:
                if seen_update_state:
                    logger.warning("  [phase2] update state observed, but transition tracking did not converge cleanly")
                else:
                    logger.warning("  [phase2] radar never showed an update transition within timeout")
                if not (
                    downloaded
                    or _download_success_seen[0]
                    or _download_progress_seen[0]
                    or _flash_start_seen[0]
                    or _flash_progress_seen[0]
                ):
                    logger.error(
                        "OTA failed: no download or flashing evidence was observed before radar remained in 'running'"
                    )
                    return False

            last_poll = 0.0
            stalled_state = ""
            stalled_count = 0
            start_recovery_sent = False
            phase3_transition_seen = radar_left_running
            phase3_reboot_window_started = _flash_start_seen[0] or _flash_progress_seen[0]

            def wait_for_phase3(deadline: float, phase_label: str) -> bool | None:
                nonlocal last_poll, stalled_state, stalled_count, start_recovery_sent
                nonlocal phase3_transition_seen, phase3_reboot_window_started

                while time.time() < deadline:
                    hint = drain_notifs()
                    if hint == "done":
                        logger.info(f"\u2705 OTA complete (notification, {phase_label})")
                        elapsed = time.time() - start_time
                        logger.info(f"\u23f1\ufe0f  Update took {elapsed:.1f} seconds.")
                        return True
                    if hint == "retry_http_connect":
                        logger.error("OTA error from device: retryable HTTP-open failure arrived after phase 1")
                        return False
                    if hint == "error":
                        return False

                    if not phase3_reboot_window_started and (
                        _flash_start_seen[0] or _flash_progress_seen[0]
                    ):
                        phase3_reboot_window_started = True
                        extended_deadline = time.time() + REBOOT_TIMEOUT
                        if extended_deadline > deadline:
                            trigger = "flash_start" if _flash_start_seen[0] else "flash_progress"
                            deadline = extended_deadline
                            logger.info(
                                "  [%s] observed %s; resetting reboot wait to %ss from now",
                                phase_label,
                                trigger,
                                REBOOT_TIMEOUT,
                            )

                    if time.time() - last_poll >= POLL_SEC:
                        last_poll = time.time()
                        state = poll_radar_state()
                        if state:
                            logger.info(f"  [{phase_label}] radar state={state!r}")
                            if state == "running":
                                if not phase3_transition_seen:
                                    logger.warning(
                                        "  [%s] radar is still 'running' without any observed update transition; waiting for stronger OTA evidence",
                                        phase_label,
                                    )
                                    time.sleep(1)
                                    continue
                                logger.info("\u2705 Radar back to 'running' \u2014 OTA complete!")
                                elapsed = time.time() - start_time
                                logger.info(f"\u23f1\ufe0f  Update took {elapsed:.1f} seconds.")
                                return True
                            phase3_transition_seen = True
                            if state == stalled_state:
                                stalled_count += 1
                            else:
                                stalled_state = state
                                stalled_count = 1

                            if (
                                not start_recovery_sent
                                and state in ("error", "stopped")
                                and stalled_count >= 3
                            ):
                                logger.warning(
                                    "  [%s] radar stuck in %r for %s polls; issuing start recovery",
                                    phase_label, state, stalled_count,
                                )
                                try:
                                    self.mcp.call_tool(
                                        "radar",
                                        {"action": "status", "set": "start", "mode": "auto"},
                                        timeout=10,
                                    )
                                    start_recovery_sent = True
                                    logger.info(f"  [{phase_label}] issued radar start recovery")
                                except Exception as recover_err:
                                    logger.warning(f"  [{phase_label}] failed to issue radar start recovery: {recover_err}")
                        else:
                            phase3_transition_seen = True
                            stalled_state = ""
                            stalled_count = 0
                            remaining = deadline - time.time()
                            logger.info(f"  [{phase_label}] radar still offline, {remaining:.0f}s remaining")

                    time.sleep(1)

                return None

            # -- Phase 3: wait for radar to come back to 'running' --
            logger.info(f"Phase 3/3: waiting up to {REBOOT_TIMEOUT}s for radar to "
                        f"finish flashing and reboot...")
            phase3_result = wait_for_phase3(time.time() + REBOOT_TIMEOUT, "phase3")
            if phase3_result is not None:
                return phase3_result

            if stalled_state in ("updating", "starting"):
                logger.warning(
                    "Radar still in %r after %ss; extending phase 3 grace by %ss",
                    stalled_state,
                    REBOOT_TIMEOUT,
                    TRANSITION_GRACE_TIMEOUT,
                )
                phase3_result = wait_for_phase3(
                    time.time() + TRANSITION_GRACE_TIMEOUT,
                    "phase3-grace",
                )
                if phase3_result is not None:
                    return phase3_result

            logger.error("OTA timeout \u2014 radar did not come back within expected time.")
            return False

        except Exception as e:
            logger.error(f"OTA failed: {e}")
            return False
        finally:
            if capture_session is not None:
                capture_session.stop()
                logger.info(
                    "OTA raw_resp capture complete: messages=%s bytes=%s",
                    capture_session.messages,
                    capture_session.bytes,
                )
            if restore_raw_args:
                try:
                    self.mcp.call_tool("radar", restore_raw_args, timeout=min(timeout, 10.0))
                except Exception as restore_err:
                    logger.warning(f"Failed to restore radar raw config after OTA capture: {restore_err}")
            if server:
                time.sleep(3)  # brief buffer for any trailing requests
                server.stop()
            if staged_http_dir is not None:
                staged_http_dir.cleanup()
