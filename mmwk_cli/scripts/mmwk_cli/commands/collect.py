"""Host-side MQTT collection command (raw UART bytes -> host files)."""

import json
import os
import threading
import time
from urllib.parse import urlparse

import paho.mqtt.client as mqtt

from mmwk_cli._logging import logger
from mmwk_cli.mqtt_topics import build_mqtt_topics
from mmwk_cli.network_runtime import network_runtime_ip


def _parse_broker_endpoint(raw_broker: str, default_port: int) -> tuple[str, int]:
    """Parse broker URI/host string and return (host, port)."""
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


def _derive_cfg_name(path: str) -> str:
    if not isinstance(path, str) or not path:
        return ""
    base = os.path.basename(path)
    stem, _ = os.path.splitext(base)
    if not stem:
        return ""
    return f"{stem}.cfg"


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
        # Host-side collect should never leave UART raw mirroring enabled.
        "uart_enabled": False,
    }
    for key in ("uri",):
        value = raw.get(key)
        if isinstance(value, str) and value:
            restore[key] = value
    return restore


def _build_raw_restore_args_for_trigger_none(payload: dict | list) -> dict:
    restore = _build_raw_restore_args(payload)
    raw = _unwrap_tool_data(payload)
    if isinstance(raw, dict) and "uart_enabled" in raw:
        restore["uart_enabled"] = bool(raw.get("uart_enabled", False))
    return restore


def _raw_forwarding_is_enabled(payload: dict | list) -> bool:
    raw = _unwrap_tool_data(payload)
    return bool(raw.get("enabled", False))


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


def _append_binary_payload(fout, payload: bytes, stats: dict, prefix: str):
    fout.write(payload)
    fout.flush()

    stats[f"{prefix}_messages"] += 1
    stats[f"{prefix}_bytes"] += len(payload)


class _MqttRawCaptureSession:
    """MQTT subscription and payload routing for host-side raw capture."""

    def __init__(self, data_topic: str, resp_topic: str, data_fout, resp_fout):
        self.data_topic = data_topic
        self.resp_topic = resp_topic
        self.same_topic = data_topic == resp_topic
        self.expected_subscriptions = 1 if self.same_topic else 2
        self.data_fout = data_fout
        self.resp_fout = resp_fout
        self.subscribed = threading.Event()
        self.connect_error = {"rc": None}
        self.subscribe_error = {"message": None}
        self.subscribe_state = {"acks": 0}
        self.stats = {
            "messages": 0,
            "total_bytes": 0,
            "data_messages": 0,
            "data_bytes": 0,
            "resp_messages": 0,
            "resp_bytes": 0,
        }

    def bind_client(self, client):
        client.on_connect = self.on_connect
        client.on_subscribe = self.on_subscribe
        client.on_message = self.on_message

    def _subscribe_topic(self, client, topic: str, label: str) -> bool:
        result, _ = client.subscribe(topic, qos=0)
        if result != mqtt.MQTT_ERR_SUCCESS:
            self.subscribe_error["message"] = f"subscribe failed for {label} topic {topic}: rc={result}"
            return False
        return True

    def on_connect(self, client, userdata, flags, rc):
        if rc != 0:
            self.connect_error["rc"] = rc
            return

        self.subscribe_state["acks"] = 0
        self.subscribe_error["message"] = None

        if not self._subscribe_topic(client, self.data_topic, "data"):
            return

        if not self.same_topic and not self._subscribe_topic(client, self.resp_topic, "resp"):
            return

    def on_subscribe(self, client, userdata, mid, granted_qos):
        self.subscribe_state["acks"] += 1
        if self.subscribe_state["acks"] >= self.expected_subscriptions:
            self.subscribed.set()

    def on_message(self, client, userdata, msg):
        self.stats["messages"] += 1
        self.stats["total_bytes"] += len(msg.payload)

        if msg.topic == self.data_topic:
            _append_binary_payload(self.data_fout, msg.payload, self.stats, "data")
            if self.same_topic:
                _append_binary_payload(self.resp_fout, msg.payload, self.stats, "resp")
            return

        if msg.topic == self.resp_topic:
            _append_binary_payload(self.resp_fout, msg.payload, self.stats, "resp")


class CollectCommand:
    """Subscribe MQTT topics and persist raw UART byte streams."""

    def __init__(self, mcp_client=None):
        self.mcp = mcp_client

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

    def _load_hi(self, timeout: float) -> dict:
        if not self.mcp:
            return {}

        try:
            result = self.mcp.call_tool("device", {"action": "hi"}, timeout=timeout)
            text = self.mcp.extract_text(result)
            data = json.loads(text)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning(f"Unable to read device hi for auto-discovery: {e}")
            return {}

    def _tool_json(self, tool_name: str, arguments: dict, timeout: float) -> dict | list:
        if not self.mcp:
            return {}
        try:
            result = self.mcp.call_tool(tool_name, arguments, timeout=timeout)
            text = self.mcp.extract_text(result)
            return json.loads(text)
        except Exception:
            return {}

    def _required_tool_json(self, tool_name: str, arguments: dict, timeout: float) -> dict | list:
        if not self.mcp:
            raise RuntimeError(f"{tool_name} call requires MCP control transport")

        result = self.mcp.call_tool(tool_name, arguments, timeout=timeout)
        text = self.mcp.extract_text(result)
        payload = json.loads(text)
        if not isinstance(payload, (dict, list)):
            raise ValueError(f"{tool_name} returned non-object JSON payload")
        return payload

    def _device_runtime_ip(self, timeout: float) -> str:
        if not self.mcp:
            return ""

        for tool_name, tool_args in (
            ("device", {"action": "hi"}),
            ("network", {"action": "status"}),
        ):
            try:
                result = self.mcp.call_tool(tool_name, tool_args, timeout=timeout)
                payload = self._parse_json_dict(self.mcp.extract_text(result))
            except Exception:
                continue

            runtime_ip = network_runtime_ip(payload)
            if runtime_ip:
                return runtime_ip

        return ""

    def _wait_for_device_network_ready(self, timeout: float) -> bool:
        if not self.mcp:
            return False

        wait_budget_sec = max(5, min(20, int(float(timeout) + 5)))
        ip_timeout = min(8.0, max(1.0, float(timeout)))
        waiting_logged = False

        for attempt in range(wait_budget_sec):
            ip_addr = self._device_runtime_ip(timeout=ip_timeout)
            if ip_addr:
                if waiting_logged:
                    logger.info("Device network ready for raw capture: ip=%s", ip_addr)
                # Give the device MQTT client a brief chance to reconnect after Wi-Fi recovery.
                time.sleep(1.0)
                return True

            if not waiting_logged:
                logger.info(
                    "Device network not ready for MQTT raw capture yet; waiting up to %ss",
                    wait_budget_sec,
                )
                waiting_logged = True

            if attempt < wait_budget_sec - 1:
                time.sleep(1.0)

        logger.warning("Device network did not become ready before raw capture; continuing anyway")
        return False

    def _hydrate_hi(self, hi: dict, timeout: float) -> dict:
        """Backfill hi fields from network/agent/fw tools for older firmware."""
        data = dict(hi or {})
        if not self.mcp:
            return data

        net = self._tool_json("network", {"action": "mqtt"}, timeout)
        net_data = net.get("data", net) if isinstance(net, dict) else {}
        if isinstance(net_data, dict):
            cid = net_data.get("cid") or net_data.get("client_id") or data.get("client_id")
            if cid and not data.get("client_id"):
                data["client_id"] = cid
            if net_data.get("mqtt_uri") and not data.get("mqtt_uri"):
                data["mqtt_uri"] = net_data.get("mqtt_uri")
            if net_data.get("cmd_topic") and not data.get("cmd_topic"):
                data["cmd_topic"] = net_data.get("cmd_topic")
            if net_data.get("resp_topic") and not data.get("resp_topic"):
                data["resp_topic"] = net_data.get("resp_topic")

        agent = self._tool_json("device", {"action": "agent"}, timeout)
        agent_data = agent.get("data", agent) if isinstance(agent, dict) else {}
        if isinstance(agent_data, dict):
            for key in ("mqtt_en", "uart_en", "raw_auto"):
                if key in agent_data and key not in data:
                    data[key] = agent_data[key]

        fw_list = self._tool_json("fw", {"action": "list"}, timeout)
        entries = fw_list if isinstance(fw_list, list) else fw_list.get("firmwares", [])
        if isinstance(entries, list) and entries:
            first = entries[0] if isinstance(entries[0], dict) else {}
            if first.get("name") and not data.get("radar_fw"):
                data["radar_fw"] = first.get("name")
            if first.get("version") and not data.get("radar_fw_version"):
                data["radar_fw_version"] = first.get("version")
            cfg_name = first.get("config_name") or _derive_cfg_name(first.get("path", ""))
            if not cfg_name and first.get("name"):
                cfg_name = "factory_default.cfg"
            if cfg_name and not data.get("radar_cfg"):
                data["radar_cfg"] = cfg_name

        client_id = data.get("client_id") or data.get("id")
        if client_id:
            topics = build_mqtt_topics(client_id, include_raw_cmd=True)
            data.setdefault("raw_data_topic", topics["raw_data_topic"])
            data.setdefault("raw_resp_topic", topics["raw_resp_topic"])
        return data

    def _resolve_trigger_none_raw_topics(
        self,
        device_id: str,
        data_topic: str,
        resp_topic: str,
        raw_cfg: dict,
        hi: dict,
    ) -> tuple[str, str]:
        default_id = device_id or hi.get("client_id") or hi.get("id") or "mmwk_collector"
        default_topics = build_mqtt_topics(default_id, include_raw_cmd=True)
        resolved_data_topic = (
            data_topic
            or raw_cfg.get("data_topic")
            or hi.get("raw_data_topic")
            or default_topics["raw_data_topic"]
        )
        resolved_resp_topic = (
            resp_topic
            or raw_cfg.get("resp_topic")
            or hi.get("raw_resp_topic")
            or default_topics["raw_resp_topic"]
        )
        return resolved_data_topic, resolved_resp_topic

    def _append_binary_payload(self, fout, payload: bytes, stats: dict, prefix: str):
        _append_binary_payload(fout, payload, stats, prefix)

    def _wait_for_resp_activity(self, stats: dict, wait_sec: float):
        deadline = time.time() + max(0.0, wait_sec)
        while stats["resp_messages"] <= 0 and time.time() < deadline:
            time.sleep(0.1)

    def _wait_for_data_activity(self, stats: dict, wait_sec: float, min_messages: int = 1) -> bool:
        deadline = time.time() + max(0.0, wait_sec)
        target_messages = max(int(min_messages), 1)
        while stats["data_messages"] < target_messages and time.time() < deadline:
            time.sleep(0.1)
        return stats["data_messages"] >= target_messages

    def _restart_radar_for_resp_probe(self, timeout: float):
        if not self.mcp:
            return

        control_timeout = max(float(timeout), 10.0)
        logger.info(
            "No raw_resp traffic observed after bootstrap; restarting radar service to elicit command-port traffic"
        )

        try:
            self.mcp.call_tool("radar", {"action": "stop"}, timeout=control_timeout)
        except Exception as e:
            logger.warning(f"Failed to stop radar service for raw_resp probe: {e}")

        time.sleep(1.0)

        try:
            self.mcp.call_tool(
                "radar",
                {"action": "start", "mode": "auto"},
                timeout=control_timeout,
            )
        except Exception as e:
            logger.warning(f"Failed to restart radar service for raw_resp probe: {e}")

    def _print_summary(self, stats: dict, data_output: str, resp_output: str):
        print(f"Collected frames: {stats['messages']}")
        print(f"Collected bytes: {stats['total_bytes']}")
        print(f"Data topic frames (DATA UART / binary): {stats['data_messages']}")
        print(f"Data topic bytes (DATA UART / binary): {stats['data_bytes']}")
        print(f"Resp topic frames (CMD UART / startup-trimmed command-port text): {stats['resp_messages']}")
        print(f"Resp topic bytes (CMD UART / startup-trimmed command-port text): {stats['resp_bytes']}")
        print(f"Data output (.sraw recommended): {data_output}")
        print(f"Resp output (.log recommended): {resp_output}")

    def _log_raw_forwarding_snapshot(self, label: str, timeout: float):
        if not self.mcp:
            return

        try:
            result = self.mcp.call_tool("radar", {"action": "raw"}, timeout=timeout)
            payload = self.mcp.extract_text(result)
        except Exception as e:
            logger.warning("Failed to query radar raw forwarding snapshot (%s): %s", label, e)
            return

        if payload and payload.strip():
            logger.info("Radar raw forwarding %s: %s", label, payload)

    def _disable_preexisting_raw_forwarding(self, raw_state: dict | list, timeout: float):
        if not self.mcp or not _raw_forwarding_is_enabled(raw_state):
            return

        try:
            # WDR single-UART capture can inherit a previous raw session whose
            # MQTT outbox is already backed up. Stop that session before we arm
            # a new collect window so startup bytes do not get hidden behind
            # stale queued traffic from raw_auto or an earlier collect run.
            self.mcp.call_tool(
                "radar",
                {"action": "raw", "enabled": False, "uart_enabled": False},
                timeout=timeout,
            )
            logger.info("Temporarily disabled pre-existing radar raw forwarding before collect bootstrap")
        except Exception as e:
            logger.warning("Failed to disable pre-existing radar raw forwarding before collect bootstrap: %s", e)

    def execute(
        self,
        duration: int,
        data_output: str,
        resp_output: str,
        broker: str,
        mqtt_port: int,
        device_id: str,
        data_topic: str,
        resp_topic: str,
        resp_optional: bool = False,
        timeout: float = 10.0,
    ) -> bool:
        output_paths = {
            os.path.abspath(data_output),
            os.path.abspath(resp_output),
        }
        if len(output_paths) != 2:
            logger.error("data-output and resp-output must be different files")
            return False

        hi = self._hydrate_hi(self._load_hi(timeout=timeout), timeout=timeout)
        if self.mcp:
            self._wait_for_device_network_ready(timeout=timeout)

        resolved_broker = broker or hi.get("mqtt_uri") or "localhost"
        host, port = _parse_broker_endpoint(resolved_broker, mqtt_port)
        client_id = device_id or hi.get("client_id") or hi.get("id") or "mmwk_collector"
        default_topics = build_mqtt_topics(client_id, include_raw_cmd=True)
        resolved_data_topic = data_topic or hi.get("raw_data_topic") or default_topics["raw_data_topic"]
        resolved_resp_topic = resp_topic or hi.get("raw_resp_topic") or default_topics["raw_resp_topic"]

        for out_path in (data_output, resp_output):
            out_dir = os.path.dirname(os.path.abspath(out_path))
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)

        logger.info(
            "Collect config: broker=%s:%s, data_topic=%s, resp_topic=%s, duration=%ss, "
            "data_output=%s, resp_output=%s",
            host,
            port,
            resolved_data_topic,
            resolved_resp_topic,
            duration,
            data_output,
            resp_output,
        )

        restore_raw_args = None
        raw_args = None
        raw_state = {}
        if self.mcp:
            raw_state = self._tool_json("radar", {"action": "raw"}, timeout=timeout)
            restore_raw_args = _build_raw_restore_args(raw_state)
            # Bootstrap raw forwarding after MQTT subscriptions are live so the
            # first raw_resp frames are not lost during collect startup.
            raw_args = {"action": "raw", "enabled": True, "uart_enabled": False}
            if hi.get("mqtt_uri"):
                raw_args["uri"] = hi.get("mqtt_uri")

        result_ok = False
        client = None
        capture_session = None

        with open(data_output, "wb") as data_fout, open(resp_output, "wb") as resp_fout:
            try:
                self._disable_preexisting_raw_forwarding(raw_state, timeout=timeout)
                capture_session = _MqttRawCaptureSession(
                    resolved_data_topic,
                    resolved_resp_topic,
                    data_fout,
                    resp_fout,
                )
                mqtt_ready = False
                wait_timeout = max(float(timeout), 20.0)
                for attempt in range(3):
                    capture_session.subscribed.clear()
                    capture_session.connect_error["rc"] = None
                    capture_session.subscribe_error["message"] = None
                    capture_session.subscribe_state["acks"] = 0
                    client = _create_mqtt_client(client_id=f"mmwk_collect_{int(time.time())}_{attempt}")
                    capture_session.bind_client(client)

                    try:
                        client.connect(host, port, 60)
                    except Exception as e:
                        logger.warning(
                            "Failed to connect MQTT broker %s:%s on attempt %s/3: %s",
                            host,
                            port,
                            attempt + 1,
                            e,
                        )
                        client = None
                    else:
                        client.loop_start()
                        wait_deadline = time.time() + wait_timeout
                        while not capture_session.subscribed.is_set() and time.time() < wait_deadline:
                            if (
                                capture_session.connect_error["rc"] is not None
                                or capture_session.subscribe_error["message"] is not None
                            ):
                                break
                            time.sleep(0.1)
                        if capture_session.subscribed.is_set():
                            mqtt_ready = True
                            break

                        if capture_session.connect_error["rc"] is not None:
                            logger.warning(
                                "MQTT connect failed with rc=%s on attempt %s/3",
                                capture_session.connect_error["rc"],
                                attempt + 1,
                            )
                        elif capture_session.subscribe_error["message"] is not None:
                            logger.warning(
                                "MQTT subscribe failed on attempt %s/3: %s",
                                attempt + 1,
                                capture_session.subscribe_error["message"],
                            )
                        else:
                            logger.warning(
                                "MQTT subscribe-ready timeout on attempt %s/3",
                                attempt + 1,
                            )

                        client.loop_stop()
                        client.disconnect()
                        client = None

                    if attempt < 2:
                        time.sleep(2.0)

                if not mqtt_ready:
                    logger.error("MQTT connect timeout while waiting for subscribe-ready state")
                    self._print_summary(capture_session.stats, data_output, resp_output)
                    result_ok = False
                else:
                    if self.mcp and raw_args:
                        try:
                            raw_result = self.mcp.call_tool("radar", raw_args, timeout=timeout)
                            bootstrap_resp_payload = self.mcp.extract_text(raw_result)
                            if bootstrap_resp_payload and bootstrap_resp_payload.strip():
                                logger.info(
                                    "Radar raw forwarding bootstrap acknowledged: %s",
                                    bootstrap_resp_payload,
                                )
                        except Exception as e:
                            logger.warning(f"Failed to pre-enable radar raw forwarding: {e}")

                        self._wait_for_resp_activity(
                            capture_session.stats,
                            wait_sec=min(2.0, max(1.0, float(timeout))),
                        )
                        if capture_session.stats["resp_messages"] <= 0:
                            if resp_optional:
                                logger.info(
                                    "No raw_resp traffic observed after bootstrap; skipping radar restart because "
                                    "resp_optional is for late-attach steady-state collection only"
                                )
                            else:
                                data_messages_before_restart = capture_session.stats["data_messages"]
                                self._restart_radar_for_resp_probe(timeout=timeout)
                                self._wait_for_resp_activity(capture_session.stats, wait_sec=3.0)
                                if capture_session.stats["data_messages"] <= data_messages_before_restart:
                                    logger.info(
                                        "Waiting briefly for post-restart raw data before starting capture window"
                                    )
                                    self._wait_for_data_activity(
                                        capture_session.stats,
                                        wait_sec=max(2.0, min(5.0, float(timeout) + 2.0)),
                                        min_messages=data_messages_before_restart + 1,
                                    )

                    try:
                        end_ts = time.time() + max(1, duration)
                        while time.time() < end_ts:
                            time.sleep(0.2)
                    except KeyboardInterrupt:
                        logger.info("Collection interrupted by user")

                    self._print_summary(capture_session.stats, data_output, resp_output)
                    self._log_raw_forwarding_snapshot("final snapshot before restore", timeout=timeout)

                    if capture_session.stats["resp_messages"] <= 0:
                        if resp_optional:
                            logger.warning(
                                "No raw command-port payload captured on resp topic; continuing because "
                                "resp_optional=true in a late-attach steady-state window"
                            )
                            result_ok = True
                        else:
                            logger.error("No raw command-port payload captured on resp topic")
                            result_ok = False
                    else:
                        result_ok = True
            finally:
                if client is not None:
                    try:
                        client.loop_stop()
                    except Exception:
                        pass
                    try:
                        client.disconnect()
                    except Exception:
                        pass
                if self.mcp and restore_raw_args:
                    try:
                        self.mcp.call_tool("radar", restore_raw_args, timeout=timeout)
                    except Exception as e:
                        logger.error(f"Failed to restore radar raw config after collect: {e}")
                        result_ok = False
        return result_ok

    def execute_trigger_none(
        self,
        duration: int,
        data_output: str,
        resp_output: str,
        broker: str,
        mqtt_port: int,
        device_id: str,
        data_topic: str,
        resp_topic: str,
        resp_optional: bool = False,
        timeout: float = 10.0,
    ) -> bool:
        output_paths = {
            os.path.abspath(data_output),
            os.path.abspath(resp_output),
        }
        if len(output_paths) != 2:
            logger.error("data-output and resp-output must be different files")
            return False

        if not self.mcp:
            logger.error("trigger=none requires MQTT control transport")
            return False

        try:
            raw_state = _unwrap_tool_data(self._required_tool_json("radar", {"action": "raw"}, timeout=timeout))
        except Exception as e:
            logger.error(f"Failed to query radar raw config for trigger=none: {e}")
            return False
        restore_raw_args = _build_raw_restore_args_for_trigger_none(raw_state)
        hi = self._hydrate_hi(self._load_hi(timeout=timeout), timeout=timeout)
        resolved_data_topic, resolved_resp_topic = self._resolve_trigger_none_raw_topics(
            device_id=device_id,
            data_topic=data_topic,
            resp_topic=resp_topic,
            raw_cfg=raw_state,
            hi=hi,
        )

        resolved_broker = broker or raw_state.get("uri") or hi.get("mqtt_uri") or "localhost"
        host, port = _parse_broker_endpoint(resolved_broker, mqtt_port)

        for out_path in (data_output, resp_output):
            out_dir = os.path.dirname(os.path.abspath(out_path))
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)

        logger.info(
            "Collect config: broker=%s:%s, data_topic=%s, resp_topic=%s, duration=%ss, "
            "data_output=%s, resp_output=%s",
            host,
            port,
            resolved_data_topic,
            resolved_resp_topic,
            duration,
            data_output,
            resp_output,
        )

        raw_args = {
            "action": "raw",
            "enabled": True,
            "uart_enabled": False,
        }
        if broker:
            raw_args["uri"] = broker
        elif raw_state.get("uri"):
            raw_args["uri"] = raw_state.get("uri")
        elif hi.get("mqtt_uri"):
            raw_args["uri"] = hi.get("mqtt_uri")

        result_ok = False
        client = None
        capture_session = None
        restore_failed = False
        raw_enable_failed = False

        with open(data_output, "wb") as data_fout, open(resp_output, "wb") as resp_fout:
            try:
                self._disable_preexisting_raw_forwarding(raw_state, timeout=timeout)
                capture_session = _MqttRawCaptureSession(
                    resolved_data_topic,
                    resolved_resp_topic,
                    data_fout,
                    resp_fout,
                )
                mqtt_ready = False
                wait_timeout = max(float(timeout), 20.0)
                for attempt in range(3):
                    capture_session.subscribed.clear()
                    capture_session.connect_error["rc"] = None
                    capture_session.subscribe_error["message"] = None
                    capture_session.subscribe_state["acks"] = 0
                    client = _create_mqtt_client(client_id=f"mmwk_collect_{int(time.time())}_{attempt}")
                    capture_session.bind_client(client)

                    try:
                        client.connect(host, port, 60)
                    except Exception as e:
                        logger.warning(
                            "Failed to connect MQTT broker %s:%s on attempt %s/3: %s",
                            host,
                            port,
                            attempt + 1,
                            e,
                        )
                        client = None
                    else:
                        client.loop_start()
                        wait_deadline = time.time() + wait_timeout
                        while not capture_session.subscribed.is_set() and time.time() < wait_deadline:
                            if (
                                capture_session.connect_error["rc"] is not None
                                or capture_session.subscribe_error["message"] is not None
                            ):
                                break
                            time.sleep(0.1)
                        if capture_session.subscribed.is_set():
                            mqtt_ready = True
                            break

                        if capture_session.connect_error["rc"] is not None:
                            logger.warning(
                                "MQTT connect failed with rc=%s on attempt %s/3",
                                capture_session.connect_error["rc"],
                                attempt + 1,
                            )
                        elif capture_session.subscribe_error["message"] is not None:
                            logger.warning(
                                "MQTT subscribe failed on attempt %s/3: %s",
                                attempt + 1,
                                capture_session.subscribe_error["message"],
                            )
                        else:
                            logger.warning(
                                "MQTT subscribe-ready timeout on attempt %s/3",
                                attempt + 1,
                            )

                        client.loop_stop()
                        client.disconnect()
                        client = None

                    if attempt < 2:
                        time.sleep(2.0)

                if not mqtt_ready:
                    logger.error("MQTT connect timeout while waiting for subscribe-ready state")
                    self._print_summary(capture_session.stats, data_output, resp_output)
                    result_ok = False
                else:
                    try:
                        raw_result = self.mcp.call_tool("radar", raw_args, timeout=timeout)
                        raw_payload = self.mcp.extract_text(raw_result)
                        if raw_payload and raw_payload.strip():
                            logger.info("Radar raw forwarding armed: %s", raw_payload)
                    except Exception as e:
                        raw_enable_failed = True
                        logger.error(f"Failed to enable radar raw forwarding for trigger=none: {e}")

                    try:
                        end_ts = time.time() + max(1, duration)
                        while time.time() < end_ts:
                            time.sleep(0.2)
                    except KeyboardInterrupt:
                        logger.info("Collection interrupted by user")

                    self._print_summary(capture_session.stats, data_output, resp_output)
                    self._log_raw_forwarding_snapshot("final snapshot before restore", timeout=timeout)

                    if raw_enable_failed:
                        result_ok = False
                    elif capture_session.stats["resp_messages"] <= 0:
                        if resp_optional:
                            logger.info(
                                "No raw command-port payload captured on resp topic; continuing because "
                                "resp_optional=true in a pure late-attach window"
                            )
                            result_ok = True
                        else:
                            logger.error("No raw command-port payload captured on resp topic")
                            result_ok = False
                    else:
                        result_ok = True
            finally:
                if client is not None:
                    try:
                        client.loop_stop()
                    except Exception:
                        pass
                    try:
                        client.disconnect()
                    except Exception:
                        pass
                if restore_raw_args:
                    try:
                        self.mcp.call_tool("radar", restore_raw_args, timeout=timeout)
                    except Exception as e:
                        logger.error(f"Failed to restore radar raw config after collect: {e}")
                        restore_failed = True
                if restore_failed:
                    result_ok = False
        return result_ok
