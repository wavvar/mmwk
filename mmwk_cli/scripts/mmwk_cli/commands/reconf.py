"""Runtime radar reconf command."""

import base64
import json
import os
import time

from mmwk_cli._logging import logger
from mmwk_cli.commands.flash import _extract_radar_state
from mmwk_cli.transport import MqttTransport


class ReconfCommand:
    """Apply runtime-only radar contract updates without flashing firmware."""

    DEFAULT_CHUNK_SIZE = 256
    MQTT_DEFAULT_CHUNK_SIZE = 512

    def __init__(self, mcp):
        self.mcp = mcp

    def _read_status_payload(self, timeout: float = 8.0) -> tuple[dict, str]:
        try:
            result = self.mcp.call_tool("radar", {"action": "status"}, timeout=timeout)
            text = self.mcp.extract_text(result)
        except Exception as exc:
            logger.warning(f"Failed to query radar status during reconf: {exc}")
            return {}, ""

        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                return payload, text
        except Exception:
            pass

        return {}, text

    @staticmethod
    def _status_data(payload: dict) -> dict:
        if not isinstance(payload, dict):
            return {}
        data = payload.get("data")
        return data if isinstance(data, dict) else payload

    def _wait_for_running(self, timeout: float) -> bool:
        deadline = time.time() + max(1.0, timeout)
        last_state = ""

        while time.time() < deadline:
            payload, text = self._read_status_payload(timeout=min(8.0, max(1.0, deadline - time.time())))
            state = _extract_radar_state(payload) or _extract_radar_state(text)

            if state == "running":
                return True

            if state == "error":
                details = self._status_data(payload).get("details")
                if details:
                    logger.error("Radar reconf failed with status details:")
                    logger.error(json.dumps(details, indent=2, ensure_ascii=False))
                else:
                    logger.error(f"Radar reconf failed: {text or payload}")
                return False

            if state and state != last_state:
                logger.info(f"  [reconf] radar state={state!r}")
                last_state = state

            time.sleep(1.0)

        logger.error("Timed out waiting for radar to return to running after reconf")
        return False

    def _send_cfg_chunks(self, cfg_data: bytes, chunk_size: int, mqtt_delay: float) -> bool:
        total = len(cfg_data)
        num_chunks = (total + chunk_size - 1) // chunk_size

        for seq in range(num_chunks):
            chunk = cfg_data[seq * chunk_size:(seq + 1) * chunk_size]
            args = {
                "file": "config",
                "seq": seq,
                "data": base64.b64encode(chunk).decode("ascii"),
            }
            try:
                result = self.mcp.call_tool("uart_data", args, timeout=20)
                text = self.mcp.extract_text(result)
                payload = json.loads(text)
                if payload.get("status") != "success":
                    logger.error(f"Config chunk {seq} failed: {text}")
                    return False
            except Exception as exc:
                logger.error(f"Config chunk {seq} failed: {exc}")
                return False

            if mqtt_delay > 0:
                time.sleep(mqtt_delay)

        return True

    def execute(self,
                cfg_path: str = None,
                clear_cfg: bool = False,
                chunk_size: int = None,
                mqtt_delay: float = 0,
                welcome: bool = None,
                verify: bool = False,
                version: str = None,
                timeout: float = 90.0) -> bool:
        """Send reconf command and wait for the radar service to return to running."""
        cfg_action = "keep"
        cfg_data = None
        is_mqtt = isinstance(self.mcp.transport, MqttTransport)

        if welcome is None:
            logger.error("welcome must be specified for radar reconf")
            return False

        if verify and not version:
            logger.error("verify=true requires --version")
            return False

        if cfg_path and clear_cfg:
            logger.error("--cfg and --clear-cfg are mutually exclusive")
            return False

        if cfg_path:
            if not os.path.exists(cfg_path):
                logger.error(f"Config file not found: {cfg_path}")
                return False
            with open(cfg_path, "rb") as fp:
                cfg_data = fp.read()
            if not cfg_data:
                logger.error("Runtime config file is empty")
                return False
            cfg_action = "replace"
        elif clear_cfg:
            cfg_action = "clear"

        if chunk_size is None:
            chunk_size = self.MQTT_DEFAULT_CHUNK_SIZE if is_mqtt else self.DEFAULT_CHUNK_SIZE
        if is_mqtt and mqtt_delay <= 0:
            mqtt_delay = getattr(self.mcp.transport, "inter_chunk_delay", 0.05)
        elif mqtt_delay <= 0:
            mqtt_delay = 0.05

        reconf_args = {
            "action": "reconf",
            "welcome": welcome,
            "verify": verify,
            "cfg_action": cfg_action,
        }
        if verify:
            reconf_args["version"] = version
        if cfg_data is not None:
            reconf_args["config_size"] = len(cfg_data)
            reconf_args["chunk_size"] = chunk_size

        try:
            result = self.mcp.call_tool("radar", reconf_args, timeout=20)
            logger.info(f"Reconf initiated: {self.mcp.extract_text(result)}")
        except Exception as exc:
            logger.error(f"Failed to initiate radar reconf: {exc}")
            return False

        if cfg_data is not None:
            if not self._send_cfg_chunks(cfg_data, chunk_size, mqtt_delay):
                try:
                    self.mcp.call_tool("uart_data", {"action": "cancel"}, timeout=5)
                except Exception:
                    pass
                return False

            try:
                result = self.mcp.call_tool("uart_data", {"action": "reconf_done"}, timeout=20)
                logger.info(f"Reconf cfg transfer complete: {self.mcp.extract_text(result)}")
            except Exception as exc:
                logger.error(f"Failed to finalize radar reconf: {exc}")
                return False

        return self._wait_for_running(timeout)
