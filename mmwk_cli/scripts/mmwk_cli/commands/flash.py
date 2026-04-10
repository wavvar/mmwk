"""Flash command: chunk-based firmware transfer over UART or MQTT."""

import os
import json
import time
import base64

from mmwk_cli._logging import logger
from mmwk_cli.transport import MqttTransport
from mmwk_cli.commands._radar_meta import resolve_radar_update_request


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
        if "error" in lower:
            return "error"

    return ""


class FlashCommand:
    """Orchestrates firmware flash over UART or MQTT using MCP protocol."""

    DEFAULT_CHUNK_SIZE = 256
    MQTT_DEFAULT_CHUNK_SIZE = 512

    def __init__(self, mcp):
        self.mcp = mcp

    @staticmethod
    def _coerce_int01(value):
        if isinstance(value, bool):
            return 1 if value else 0
        if isinstance(value, (int, float)):
            return 1 if int(value) != 0 else 0
        if isinstance(value, str):
            text = value.strip().lower()
            if text in ("1", "true", "on", "yes"):
                return 1
            if text in ("0", "false", "off", "no"):
                return 0
            if text.isdigit():
                return 1 if int(text) != 0 else 0
        return None

    def _read_radar_state(self, timeout: float = 8.0) -> str:
        """Best-effort radar state read that tolerates bridge/hub payload differences."""
        try:
            resp = self.mcp.call_tool("radar", {"action": "status"}, timeout=timeout)
            text = self.mcp.extract_text(resp)
            try:
                return _extract_radar_state(json.loads(text))
            except Exception:
                return _extract_radar_state(text)
        except Exception:
            return ""

    def _ensure_mcp_ready(self, wait_sec: int = 30) -> bool:
        """Re-handshake MCP after reboot/reset so subsequent calls are less racy."""
        deadline = time.time() + max(5, wait_sec)
        while time.time() < deadline:
            try:
                self.mcp.initialize(timeout=5)
                return True
            except Exception:
                time.sleep(1.0)
        return False

    def _pulse_radar_start(self) -> None:
        """Try a stop/start pulse to recover stale STARTING/ERROR states."""
        try:
            self.mcp.call_tool("radar", {"action": "stop"}, timeout=10)
        except Exception:
            pass
        time.sleep(1.0)
        try:
            self.mcp.call_tool("radar", {"action": "start", "mode": "auto"}, timeout=10)
        except Exception:
            pass

    def _wait_radar_running(self, wait_sec: int = 90, recover_starting: bool = True) -> bool:
        """Wait until radar reaches running; optionally recover stuck starting."""
        deadline = time.time() + max(10, wait_sec)
        last_state = ""
        starting_streak = 0
        recovery_issued = False

        while time.time() < deadline:
            state = self._read_radar_state(timeout=8)
            if state == "running":
                return True

            if state and state != last_state:
                logger.info(f"  [wait-running] radar state={state!r}")
                last_state = state

            if state == "starting":
                starting_streak += 1
            else:
                starting_streak = 0

            if state == "stopped":
                try:
                    self.mcp.call_tool("radar", {"action": "start", "mode": "auto"}, timeout=10)
                except Exception:
                    pass

            if state == "error" and not recovery_issued:
                self._pulse_radar_start()
                recovery_issued = True

            if recover_starting and starting_streak >= 6 and not recovery_issued:
                logger.warning("Radar stuck in starting; issuing stop/start recovery")
                self._pulse_radar_start()
                recovery_issued = True

            time.sleep(3)

        return False

    def _read_agent_state(self) -> dict:
        """Read device agent flags; tolerant to bridge/hub response envelopes."""
        try:
            resp = self.mcp.call_tool("device", {"action": "agent"}, timeout=8)
            text = self.mcp.extract_text(resp)
            payload = json.loads(text)
            if isinstance(payload, dict):
                data = payload.get("data")
                if isinstance(data, dict):
                    payload = data
            if not isinstance(payload, dict):
                return {}
            out = {}
            for key in ("mqtt_en", "raw_auto", "uart_en"):
                val = self._coerce_int01(payload.get(key))
                if val is not None:
                    out[key] = val
            return out
        except Exception:
            return {}

    def _set_agent_state(self, **kwargs) -> bool:
        args = {"action": "agent"}
        for key, value in kwargs.items():
            if value is None:
                continue
            coerced = self._coerce_int01(value)
            if coerced is not None:
                args[key] = coerced
        if len(args) == 1:
            return True
        try:
            self.mcp.call_tool("device", args, timeout=10)
            return True
        except Exception as e:
            logger.warning(f"Failed to set device agent state {args}: {e}")
            return False

    def _enter_uart_low_load_mode(self) -> dict:
        """
        Best-effort reduction of runtime load during UART flash.
        Returns original flags for later restoration.
        """
        original = self._read_agent_state()
        if not original:
            return {}
        desired = {}
        if original.get("mqtt_en") == 1:
            desired["mqtt_en"] = 0
        if original.get("raw_auto") == 1:
            desired["raw_auto"] = 0
        if not desired:
            return original
        if self._set_agent_state(**desired):
            logger.info("Enabled low-load agent mode for UART flash")
        return original

    def _restore_agent_state(self, original: dict) -> None:
        if not original:
            return
        restore = {}
        for key in ("mqtt_en", "raw_auto", "uart_en"):
            if key in original:
                restore[key] = original[key]
        if restore and self._set_agent_state(**restore):
            logger.info("Restored agent mode after UART flash")

    def _best_effort_reboot_recover(
        self,
        reason: str,
        wait_sec: int = 120,
    ) -> bool:
        """
        Reboot device and wait for radar to return to running.
        Used only as a recovery path when update session is stuck.
        """
        logger.warning(f"{reason}; attempting device reboot recovery...")
        try:
            self.mcp.call_tool("device", {"action": "reboot"}, timeout=15)
        except Exception as e:
            logger.warning(f"Device reboot command failed during recovery: {e}")
            return False

        self._ensure_mcp_ready(wait_sec=min(45, wait_sec))
        return self._wait_radar_running(wait_sec=wait_sec, recover_starting=True)

    def _recover_stale_updating_before_flash(self):
        """
        If previous attempts left the device in updating state, clear it before
        starting a new session to reduce chunk 0/early chunk timeouts.
        """
        state = self._read_radar_state(timeout=5)
        if state != "updating":
            return
        self._best_effort_reboot_recover(
            "Detected stale radar updating state before new flash session",
            wait_sec=90,
        )

    def _allow_recovery_flash_from_error_state(self, context: str) -> bool:
        """
        A radar in error can still accept a new update session. Allow retrying
        flash from that state instead of treating it as unrecoverable.
        """
        state = self._read_radar_state(timeout=8)
        if state != "error":
            return False
        logger.warning(f"{context}; radar remains reachable in error state, attempting recovery flash")
        return True

    def execute(self, fw_path: str, cfg_path: str = None,
                chunk_size: int = None, mqtt_delay: float = 0,
                progress_interval: int = 5, reboot_delay: int = 0,
                version: str = None, welcome: bool = None,
                verify: bool = None, _retry_left: int = 2) -> bool:
        """Flash firmware (and optionally config) to the radar."""
        show_progress = os.isatty(1)

        def retry_session(reason: str) -> bool:
            if _retry_left <= 0:
                logger.error(reason)
                return False
            logger.warning(f"{reason}, retrying full flash session once...")
            retry_chunk_size = chunk_size
            if (not is_mqtt) and isinstance(retry_chunk_size, int) and retry_chunk_size > 256:
                retry_chunk_size = max(256, retry_chunk_size // 2)
                logger.warning(f"Reducing UART chunk size to {retry_chunk_size} for retry session")
            if not is_mqtt:
                recovered = self._best_effort_reboot_recover(
                    "Preparing clean state before flash retry",
                    wait_sec=90,
                )
                if not recovered:
                    logger.warning("Reboot recovery did not reach running; trying direct start recovery")
                    self._ensure_mcp_ready(wait_sec=20)
                    if not self._wait_radar_running(wait_sec=70, recover_starting=True):
                        if not self._allow_recovery_flash_from_error_state(
                            "Radar recovery failed before retry session"
                        ):
                            logger.error("Radar recovery failed before retry session")
                            return False
            time.sleep(2.0)
            return self.execute(
                fw_path=fw_path,
                cfg_path=cfg_path,
                chunk_size=retry_chunk_size,
                mqtt_delay=mqtt_delay,
                progress_interval=progress_interval,
                reboot_delay=reboot_delay,
                version=version,
                welcome=welcome,
                verify=verify,
                _retry_left=_retry_left - 1,
            )

        is_mqtt = isinstance(self.mcp.transport, MqttTransport)
        if chunk_size is None:
            chunk_size = self.MQTT_DEFAULT_CHUNK_SIZE if is_mqtt else self.DEFAULT_CHUNK_SIZE
        if is_mqtt and mqtt_delay <= 0:
            mqtt_delay = self.mcp.transport.inter_chunk_delay
        if not is_mqtt and mqtt_delay <= 0:
            mqtt_delay = 0.12

        original_agent_state = {}
        if not is_mqtt:
            self._ensure_mcp_ready(wait_sec=10)
            original_agent_state = self._enter_uart_low_load_mode()
            self._recover_stale_updating_before_flash()
            self._ensure_mcp_ready(wait_sec=20)
            if not self._wait_radar_running(wait_sec=70, recover_starting=True):
                if not self._allow_recovery_flash_from_error_state(
                    "Radar is not ready for flash (failed to reach running state)"
                ):
                    return retry_session("Radar is not ready for flash (failed to reach running state)")

        try:
            # Clear any previous half-open UART transfer session before a new flash.
            if not is_mqtt:
                try:
                    self.mcp.call_tool("uart_data", {"action": "cancel"}, timeout=3)
                except Exception:
                    pass

            # Read firmware file
            if not os.path.exists(fw_path):
                logger.error(f"Firmware file not found: {fw_path}")
                return False
            with open(fw_path, "rb") as f:
                fw_data = f.read()
            fw_size = len(fw_data)
            logger.info(f"Firmware: {os.path.basename(fw_path)} ({fw_size} bytes)")
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

            # Read config file if provided
            cfg_data = None
            cfg_size = 0
            if cfg_path:
                if not os.path.exists(cfg_path):
                    logger.error(f"Config file not found: {cfg_path}")
                    return False
                with open(cfg_path, "rb") as f:
                    cfg_data = f.read()
                cfg_size = len(cfg_data)
                logger.info(f"Config: {os.path.basename(cfg_path)} ({cfg_size} bytes)")

            # Step 1: Initiate flash
            logger.info("Step 1/3: Initiating flash...")
            start_time = time.time()
            flash_args = {
                "action": "flash",
                "base": "uart://",
                "firmware_size": fw_size,
                "chunk_size": chunk_size
            }
            if cfg_size > 0:
                flash_args["config_size"] = cfg_size
            if progress_interval >= 0:
                flash_args["prog_intvl"] = progress_interval
            if reboot_delay > 0:
                flash_args["reboot_delay"] = reboot_delay
            flash_args["welcome"] = update_request.welcome
            flash_args["verify"] = update_request.verify
            if update_request.version:
                flash_args["version"] = update_request.version

            try:
                result = self.mcp.call_tool("radar", flash_args, timeout=20)
                logger.info(f"Flash initiated: {self.mcp.extract_text(result)}")
            except Exception as e:
                return retry_session(f"Flash initiation failed: {e}")

            # Wait for device to fully teardown radar driver and enter active update state
            logger.info("Waiting for device to enter update mode...")
            deadline = time.time() + 20.0
            entered = False
            saw_stopped = False
            while time.time() < deadline:
                try:
                    resp = self.mcp.call_tool("radar", {"action": "status"}, timeout=3.0)
                    text = self.mcp.extract_text(resp)
                    try:
                        st = _extract_radar_state(json.loads(text))
                    except Exception:
                        st = _extract_radar_state(text)
                    if "updating" in st:
                        entered = True
                        break
                    if "stopped" in st:
                        saw_stopped = True
                except Exception:
                    pass
                time.sleep(0.5)

            # Some firmware builds expose a brief stopped window before the UART
            # update worker becomes active. If we only saw "stopped", do a short
            # re-check window and require a real "updating" before sending chunks.
            if not entered and saw_stopped:
                logger.info("Device reached stopped state; waiting extra time for update worker...")
                settle_deadline = time.time() + 8.0
                while time.time() < settle_deadline:
                    try:
                        resp = self.mcp.call_tool("radar", {"action": "status"}, timeout=3.0)
                        text = self.mcp.extract_text(resp)
                        try:
                            st = _extract_radar_state(json.loads(text))
                        except Exception:
                            st = _extract_radar_state(text)
                        if st == "updating":
                            entered = True
                            break
                    except Exception:
                        pass
                    time.sleep(0.5)

            if not entered:
                return retry_session("Device failed to enter updating state")

            # Give the device task loop time to fully initialize UART update
            # state (open temp files, set active=true) after state transitions
            time.sleep(5.0)

            # Step 2: Send firmware chunks
            logger.info("Step 2/3: Sending firmware data...")
            if not self._send_file_chunks(fw_data, "firmware", chunk_size, mqtt_delay, show_progress=show_progress):
                return retry_session("Firmware chunk transfer failed")

            # Send config chunks if provided
            if cfg_data:
                logger.info("Sending config data...")
                if not self._send_file_chunks(cfg_data, "config", chunk_size, mqtt_delay, show_progress=show_progress):
                    return retry_session("Config chunk transfer failed")

            # Step 3: Complete
            logger.info("Step 3/3: Completing flash (this can take up to 2 minutes)...")
            try:
                result = self.mcp.call_tool("uart_data", {"action": "complete"}, timeout=180)
                logger.info(f"Flash trigger response: {self.mcp.extract_text(result)}")

                # For UART, poll for flash_progress notifications from device
                logger.info("Waiting for ESP32 background radar flash (up to 120s)...")
                deadline = time.time() + 120
                last_pct = -1
                while time.time() < deadline:
                    for n in self.mcp.transport.drain_notifications():
                        if not isinstance(n, dict):
                            continue
                        params = n.get("params", {})
                        data = params.get("data", {}) if isinstance(params, dict) else {}
                        if isinstance(data, str):
                            try:
                                data = json.loads(data)
                            except Exception:
                                data = {}
                        if not isinstance(data, dict):
                            continue
                        st = data.get("status", "")
                        pct = data.get("progress", -1)
                        if st in ("flash_progress", "progress") and pct >= 0:
                            if show_progress and pct != last_pct:
                                bar_len = 30
                                filled = bar_len * pct // 100
                                bar = '\u2588' * filled + '\u2591' * (bar_len - filled)
                                print(f"\r  [{bar}] {pct}% flashing...", end='', flush=True)
                                last_pct = pct
                        elif st in ("flash_done", "complete", "done", "flash_success"):
                            if show_progress and last_pct >= 0:
                                print()  # newline after progress bar
                            logger.info("Flash completed (device notification)!")
                            elapsed = time.time() - start_time
                            logger.info(f"\u23f1\ufe0f  Update took {elapsed:.1f} seconds.")
                            return True
                        elif st in ("flash_error", "error", "failed"):
                            if show_progress and last_pct >= 0:
                                print()
                            logger.error(f"Flash error from device: {data}")
                            return False
                    time.sleep(1)
                if show_progress and last_pct >= 0:
                    print()
                logger.info("Flash wait window ended without completion notification; polling radar state...")

                status_deadline = time.time() + 240
                last_state = ""
                while time.time() < status_deadline:
                    try:
                        state = self._read_radar_state(timeout=8)
                    except Exception:
                        state = ""

                    if state == "running":
                        logger.info("Radar returned to running state after flash.")
                        elapsed = time.time() - start_time
                        logger.info(f"\u23f1\ufe0f  Update took {elapsed:.1f} seconds.")
                        return True

                    if state and state != last_state:
                        logger.info(f"  [flash-settle] radar state={state!r}")
                        last_state = state

                    if state == "stopped":
                        try:
                            self.mcp.call_tool("radar", {"action": "start", "mode": "auto"}, timeout=10)
                        except Exception:
                            pass

                    time.sleep(3)

                if not is_mqtt and self._best_effort_reboot_recover(
                    "Radar did not return to running after flash settle window",
                    wait_sec=120,
                ):
                    logger.info("Recovered to operable radar state after reboot fallback.")
                    elapsed = time.time() - start_time
                    logger.info(f"\u23f1\ufe0f  Update took {elapsed:.1f} seconds.")
                    return True

                return retry_session("Radar did not return to running state after flash completion window")
            except Exception as e:
                return retry_session(f"Flash completion failed: {e}")

            logger.info("\u2705 Firmware flash successful!")
            elapsed = time.time() - start_time
            logger.info(f"\u23f1\ufe0f  Update took {elapsed:.1f} seconds.")
            return True
        finally:
            if not is_mqtt:
                self._restore_agent_state(original_agent_state)

    def _send_file_chunks(self, data: bytes, file_type: str,
                          chunk_size: int, mqtt_delay: float = 0,
                          show_progress: bool = True) -> bool:
        """Send file data in base64-encoded chunks."""
        total = len(data)
        num_chunks = (total + chunk_size - 1) // chunk_size
        is_mqtt = isinstance(self.mcp.transport, MqttTransport)

        for i in range(num_chunks):
            chunk = data[i * chunk_size: (i + 1) * chunk_size]
            b64 = base64.b64encode(chunk).decode('ascii').replace('\n', '').replace('\r', '')

            if is_mqtt:
                chunk_retries = 15 if i == 0 else 3
                chunk_timeout = 20
            else:
                chunk_retries = 24 if i == 0 else 10
                chunk_timeout = 25 if i == 0 else 18
            args = {
                "file": file_type,
                "seq": i,
                "data": b64
            }

            for try_idx in range(chunk_retries):
                try:
                    res = self.mcp.call_tool("uart_data", args, timeout=chunk_timeout)
                    st = "unknown"
                    if res:
                        try:
                            # The response is embedded as JSON inside the content text
                            text_resp = self.mcp.extract_text(res)
                            res_json = json.loads(text_resp)
                            st = res_json.get("status", "unknown")
                        except Exception:
                            st = text_resp if text_resp else "unknown"
                    if st == "success":
                        if try_idx > 0:
                            logger.info(f"Chunk {i} succeeded on attempt {try_idx+1}")
                        break  # success, break from retry loop
                    else:
                        if try_idx < chunk_retries - 1:
                            logger.warning(f"Chunk {i} attempt {try_idx+1} failed (status: {st}), retrying in 1s...")
                            time.sleep(1.0)
                            continue
                        else:
                            logger.error(f"Chunk {i} failed after {chunk_retries} attempts (status: {st}).")
                            # Try to cancel
                            try:
                                self.mcp.call_tool("uart_data", {"action": "cancel"}, timeout=5)
                            except:
                                pass
                            return False
                except Exception as e:
                    err_text = str(e)
                    if (
                        ("err=-2" in err_text) or ("No UART update in progress" in err_text)
                    ) and try_idx >= (1 if i == 0 else 2):
                        logger.error(
                            f"Chunk {i} keeps reporting not-active update session; restarting flash session"
                        )
                        return False
                    if "Timeout waiting for tool 'uart_data' response" in err_text and try_idx >= (3 if i == 0 else 4):
                        logger.error(
                            f"Chunk {i} timed out repeatedly; restarting flash session"
                        )
                        return False
                    if try_idx < chunk_retries - 1:
                        logger.warning(f"Chunk {i} attempt {try_idx+1} failed with error: {e}, retrying in 1s...")
                        time.sleep(1.0)
                        continue
                    else:
                        logger.error(f"Chunk {i} failed with exception: {e}")
                        # Try to cancel
                        try:
                            self.mcp.call_tool("uart_data", {"action": "cancel"}, timeout=5)
                        except:
                            pass
                        return False
            else:  # This else block executes if the for loop completes without a 'break'
                # This means all retries failed
                return False

            # Progress display
            pct = ((i + 1) * 100) // num_chunks
            if show_progress:
                bar_len = 30
                filled = bar_len * (i + 1) // num_chunks
                bar = '\u2588' * filled + '\u2591' * (bar_len - filled)
                sent = min((i + 1) * chunk_size, total)
                print(f"\r  [{bar}] {pct}% ({sent}/{total} bytes)", end='', flush=True)

            # Important: Add explicit delay allowing the ESP32 to decode and dump base64 without buffer overrun
            if mqtt_delay > 0:
                time.sleep(mqtt_delay)
            else:
                time.sleep(0.05)

        if show_progress:
            print()  # newline after progress bar
        return True
