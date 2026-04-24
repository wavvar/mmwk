"""Pure-MQTT raw capture helper contract surface."""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Mapping, Sequence

from mmwk_cli._logging import logger
from mmwk_cli.commands.collect import (
    CollectCommand,
    _MqttRawCaptureSession,
    _build_raw_restore_args_for_trigger_none,
    _create_mqtt_client,
    _parse_broker_endpoint,
    _unwrap_tool_data,
)
from mmwk_cli.mcp_client import McpClient
from mmwk_cli.mqtt_topics import build_mqtt_topics
from mmwk_cli.transport import create_transport


TRIGGERS = ("none", "radar-restart", "device-reboot")
DEFAULT_DURATION = 10
DEFAULT_TIMEOUT = 10.0
DEFAULT_DATA_OUTPUT = "data_resp.sraw"
DEFAULT_RESP_OUTPUT = "cmd_resp.log"

ENV_BROKER = "MMWK_SERVER_MQTT_URI"
ENV_DEVICE_ID = "MMWK_DEVICE_ID"
ENV_CMD_TOPIC = "MMWK_CMD_TOPIC"
ENV_RESP_TOPIC = "MMWK_RESP_TOPIC"
ENV_RAW_DATA_TOPIC = "MMWK_RAW_DATA_TOPIC"
ENV_RAW_RESP_TOPIC = "MMWK_RAW_RESP_TOPIC"


@dataclass(frozen=True)
class CollectRawConfig:
    trigger: str
    duration: int
    timeout: float
    broker: str
    device_id: str
    cmd_topic: str
    resp_topic: str
    raw_data_topic: str
    raw_resp_topic: str
    data_output: str
    resp_output: str
    resp_optional: bool


def _topic_defaults(device_id: str) -> dict[str, str]:
    return build_mqtt_topics(device_id, include_raw_cmd=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mmwk_raw",
        description="Pure-MQTT raw capture helper",
        epilog=(
            "Environment fallback variables:\n"
            f"  {ENV_BROKER}\n"
            f"  {ENV_DEVICE_ID}\n"
            f"  {ENV_CMD_TOPIC}\n"
            f"  {ENV_RESP_TOPIC}\n"
            f"  {ENV_RAW_DATA_TOPIC}\n"
            f"  {ENV_RAW_RESP_TOPIC}\n\n"
            "The mmwk_raw.sh wrapper can auto-load MMWK_SERVER_MQTT_URI from server.sh state.\n"
            "This helper itself remains pure MQTT only."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--trigger",
        required=True,
        choices=TRIGGERS,
        metavar="none|radar-restart|device-reboot",
        help="Required trigger mode for the capture flow",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=DEFAULT_DURATION,
        help=f"Capture duration in seconds (default: {DEFAULT_DURATION})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"MQTT setup timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument("--broker", help=f"MQTT broker URI/host (env: {ENV_BROKER})")
    parser.add_argument("--device-id", help=f"Device id used for default topics (env: {ENV_DEVICE_ID})")
    parser.add_argument("--cmd-topic", help=f"Command topic override (env: {ENV_CMD_TOPIC})")
    parser.add_argument("--resp-topic", help=f"Response topic override (env: {ENV_RESP_TOPIC})")
    parser.add_argument(
        "--raw-data-topic",
        help=f"Raw data topic override (env: {ENV_RAW_DATA_TOPIC})",
    )
    parser.add_argument(
        "--raw-resp-topic",
        help=f"Raw response topic override (env: {ENV_RAW_RESP_TOPIC})",
    )
    parser.add_argument(
        "--data-output",
        default=DEFAULT_DATA_OUTPUT,
        help=f"Output file for raw data capture (default: {DEFAULT_DATA_OUTPUT})",
    )
    parser.add_argument(
        "--resp-output",
        default=DEFAULT_RESP_OUTPUT,
        help=f"Output file for raw response capture (default: {DEFAULT_RESP_OUTPUT})",
    )
    parser.add_argument(
        "--resp-optional",
        action="store_true",
        help="Allow resp capture to be optional for trigger=none only",
    )
    return parser


def _env_value(environ: Mapping[str, str], name: str) -> str:
    return str(environ.get(name, "")).strip()


def _choose(*values: str) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _value_from_hi(hi: Mapping[str, object], key: str) -> str:
    for container in (hi, hi.get("device_hi")):
        if isinstance(container, Mapping):
            value = container.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def resolve_collect_raw_config(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> CollectRawConfig:
    env = environ if environ is not None else os.environ
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    broker = _choose(getattr(args, "broker", ""), _env_value(env, ENV_BROKER))
    device_id = _choose(getattr(args, "device_id", ""), _env_value(env, ENV_DEVICE_ID))
    if not broker:
        raise ValueError(f"Missing MQTT broker; set --broker or {ENV_BROKER}")
    if not device_id:
        raise ValueError(f"Missing device id; set --device-id or {ENV_DEVICE_ID}")

    defaults = _topic_defaults(device_id)
    cmd_topic = _choose(getattr(args, "cmd_topic", ""), _env_value(env, ENV_CMD_TOPIC), defaults["cmd_topic"])
    resp_topic = _choose(getattr(args, "resp_topic", ""), _env_value(env, ENV_RESP_TOPIC), defaults["resp_topic"])
    raw_data_topic = _choose(
        getattr(args, "raw_data_topic", ""),
        _env_value(env, ENV_RAW_DATA_TOPIC),
        defaults["raw_data_topic"],
    )
    raw_resp_topic = _choose(
        getattr(args, "raw_resp_topic", ""),
        _env_value(env, ENV_RAW_RESP_TOPIC),
        defaults["raw_resp_topic"],
    )

    data_output = str(getattr(args, "data_output", DEFAULT_DATA_OUTPUT)).strip() or DEFAULT_DATA_OUTPUT
    resp_output = str(getattr(args, "resp_output", DEFAULT_RESP_OUTPUT)).strip() or DEFAULT_RESP_OUTPUT
    if os.path.abspath(data_output) == os.path.abspath(resp_output):
        raise ValueError("data-output and resp-output must be different paths")

    if getattr(args, "resp_optional", False) and getattr(args, "trigger", "") != "none":
        raise ValueError("--resp-optional is only valid with --trigger none")

    return CollectRawConfig(
        trigger=args.trigger,
        duration=int(args.duration),
        timeout=float(args.timeout),
        broker=broker,
        device_id=device_id,
        cmd_topic=cmd_topic,
        resp_topic=resp_topic,
        raw_data_topic=raw_data_topic,
        raw_resp_topic=raw_resp_topic,
        data_output=data_output,
        resp_output=resp_output,
        resp_optional=bool(getattr(args, "resp_optional", False)),
    )


def _flag_present(argv: Sequence[str], flag: str) -> bool:
    return any(arg == flag or arg.startswith(f"{flag}=") for arg in argv)


def resolve_collect_raw_runtime_topics(
    argv: Sequence[str],
    environ: Mapping[str, str],
    config: CollectRawConfig,
) -> tuple[str, str]:
    raw_data_explicit = _flag_present(argv, "--raw-data-topic") or bool(_env_value(environ, ENV_RAW_DATA_TOPIC))
    raw_resp_explicit = _flag_present(argv, "--raw-resp-topic") or bool(_env_value(environ, ENV_RAW_RESP_TOPIC))

    return (
        config.raw_data_topic if raw_data_explicit else "",
        config.raw_resp_topic if raw_resp_explicit else "",
    )


def _build_transport_args(config: CollectRawConfig) -> SimpleNamespace:
    host, port = _parse_broker_endpoint(config.broker, 1883)
    return SimpleNamespace(
        transport="mqtt",
        broker=host,
        mqtt_port=port,
        device_id=config.device_id,
        cmd_topic=config.cmd_topic,
        resp_topic=config.resp_topic,
        timeout=config.timeout,
    )


def _resolve_startup_trigger_topics(
    argv: Sequence[str],
    environ: Mapping[str, str],
    config: CollectRawConfig,
    raw_state: Mapping[str, object],
    hi: Mapping[str, object],
) -> tuple[str, str]:
    defaults = _topic_defaults(config.device_id)
    raw_data_explicit = _flag_present(argv, "--raw-data-topic") or bool(_env_value(environ, ENV_RAW_DATA_TOPIC))
    raw_resp_explicit = _flag_present(argv, "--raw-resp-topic") or bool(_env_value(environ, ENV_RAW_RESP_TOPIC))

    raw_data_topic = _choose(
        config.raw_data_topic if raw_data_explicit else "",
        raw_state.get("data_topic", ""),
        _value_from_hi(hi, "raw_data_topic"),
        defaults["raw_data_topic"],
    )
    raw_resp_topic = _choose(
        config.raw_resp_topic if raw_resp_explicit else "",
        raw_state.get("resp_topic", ""),
        _value_from_hi(hi, "raw_resp_topic"),
        defaults["raw_resp_topic"],
    )
    return raw_data_topic, raw_resp_topic


def _control_topics_explicit(argv: Sequence[str], environ: Mapping[str, str]) -> tuple[bool, bool]:
    return (
        _flag_present(argv, "--cmd-topic") or bool(_env_value(environ, ENV_CMD_TOPIC)),
        _flag_present(argv, "--resp-topic") or bool(_env_value(environ, ENV_RESP_TOPIC)),
    )


def _connect_capture_client(
    capture_session: _MqttRawCaptureSession,
    host: str,
    port: int,
    timeout: float,
) -> object | None:
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
        except Exception as exc:
            logger.warning(
                "Failed to connect MQTT broker %s:%s on attempt %s/3: %s",
                host,
                port,
                attempt + 1,
                exc,
            )
            client = None
        else:
            client.loop_start()
            wait_deadline = time.time() + wait_timeout
            while not capture_session.subscribed.is_set() and time.time() < wait_deadline:
                if capture_session.connect_error["rc"] is not None or capture_session.subscribe_error["message"] is not None:
                    break
                time.sleep(0.1)

            if capture_session.subscribed.is_set():
                return client

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
                logger.warning("MQTT subscribe-ready timeout on attempt %s/3", attempt + 1)

            try:
                client.loop_stop()
            except Exception:
                pass
            try:
                client.disconnect()
            except Exception:
                pass
            client = None

        if attempt < 2:
            time.sleep(2.0)

    return None


def _execute_trigger_radar_restart(
    config: CollectRawConfig,
    mcp: McpClient,
    argv: Sequence[str],
    environ: Mapping[str, str],
) -> bool:
    collector = CollectCommand(mcp)

    try:
        raw_state = _unwrap_tool_data(
            collector._required_tool_json("radar", {"action": "raw"}, timeout=config.timeout)
        )
    except Exception as exc:
        logger.error(f"Failed to query radar raw config for trigger=radar-restart: {exc}")
        return False

    hi = collector._load_hi(timeout=config.timeout)
    restore_raw_args = _build_raw_restore_args_for_trigger_none(raw_state)
    data_topic, resp_topic = _resolve_startup_trigger_topics(
        argv=argv,
        environ=environ,
        config=config,
        raw_state=raw_state,
        hi=hi,
    )
    host, port = _parse_broker_endpoint(config.broker, 1883)

    for out_path in (config.data_output, config.resp_output):
        out_dir = os.path.dirname(os.path.abspath(out_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

    logger.info(
        "Collect config: broker=%s:%s, data_topic=%s, resp_topic=%s, duration=%ss, "
        "data_output=%s, resp_output=%s",
        host,
        port,
        data_topic,
        resp_topic,
        config.duration,
        config.data_output,
        config.resp_output,
    )

    raw_args = {
        "action": "raw",
        "enabled": True,
        "uart_enabled": False,
        "uri": config.broker,
    }

    result_ok = False
    client = None
    raw_enable_ok = False
    status_stop_ok = False
    status_start_ok = False

    with open(config.data_output, "wb") as data_fout, open(config.resp_output, "wb") as resp_fout:
        capture_session = _MqttRawCaptureSession(
            data_topic,
            resp_topic,
            data_fout,
            resp_fout,
        )
        try:
            client = _connect_capture_client(capture_session, host=host, port=port, timeout=config.timeout)

            if client is None:
                logger.error("MQTT connect timeout while waiting for subscribe-ready state")
            else:
                try:
                    raw_result = mcp.call_tool("radar", raw_args, timeout=config.timeout)
                    raw_payload = mcp.extract_text(raw_result)
                    if raw_payload and raw_payload.strip():
                        logger.info("Radar raw forwarding armed: %s", raw_payload)
                    raw_enable_ok = True
                except Exception as exc:
                    logger.error(f"Failed to enable radar raw forwarding for trigger=radar-restart: {exc}")

                if raw_enable_ok:
                    try:
                        mcp.call_tool("radar", {"action": "stop"}, timeout=config.timeout)
                        status_stop_ok = True
                    except Exception as exc:
                        logger.error(f"Failed to stop radar service for trigger=radar-restart: {exc}")

                    time.sleep(1.0)

                    try:
                        mcp.call_tool(
                            "radar",
                            {"action": "start", "mode": "auto"},
                            timeout=config.timeout,
                        )
                        status_start_ok = True
                    except Exception as exc:
                        logger.error(f"Failed to restart radar service for trigger=radar-restart: {exc}")

                    if status_stop_ok and status_start_ok:
                        try:
                            time.sleep(max(0.0, float(config.duration)))
                        except KeyboardInterrupt:
                            logger.info("Collection interrupted by user")

                        collector._print_summary(capture_session.stats, config.data_output, config.resp_output)
                        if capture_session.stats["resp_messages"] <= 0:
                            logger.error("No raw command-port payload captured on resp topic after radar restart")
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
            try:
                mcp.call_tool("radar", restore_raw_args, timeout=config.timeout)
            except Exception as exc:
                logger.error(f"Failed to restore radar raw config after collect: {exc}")
                result_ok = False

    return result_ok and raw_enable_ok and status_stop_ok and status_start_ok


def _execute_trigger_device_reboot(
    config: CollectRawConfig,
    mcp: McpClient,
    argv: Sequence[str],
    environ: Mapping[str, str],
) -> bool:
    collector = CollectCommand(mcp)

    try:
        raw_state = _unwrap_tool_data(
            collector._required_tool_json("radar", {"action": "raw"}, timeout=config.timeout)
        )
    except Exception as exc:
        logger.error(f"Failed to query radar raw config for trigger=device-reboot: {exc}")
        return False

    try:
        hi_payload = collector._required_tool_json("device", {"action": "hi"}, timeout=config.timeout)
    except Exception as exc:
        logger.error(f"Failed to query device hi for trigger=device-reboot: {exc}")
        return False

    hi = _unwrap_tool_data(hi_payload)
    if not isinstance(hi, dict):
        logger.error("device-reboot requires device hi to return an object payload")
        return False

    hi_client_id = _choose(_value_from_hi(hi, "client_id"), _value_from_hi(hi, "id"))
    if not hi_client_id:
        logger.error("device-reboot requires device hi to confirm client_id")
        return False
    if hi_client_id != config.device_id:
        logger.error(
            "device-reboot device hi client_id mismatch: expected %s, got %s",
            config.device_id,
            hi_client_id,
        )
        return False

    cmd_explicit, resp_explicit = _control_topics_explicit(argv, environ)
    hi_cmd_topic = _value_from_hi(hi, "cmd_topic")
    hi_resp_topic = _value_from_hi(hi, "resp_topic")
    if hi_cmd_topic and hi_cmd_topic != config.cmd_topic and not cmd_explicit:
        logger.error(
            "device-reboot requires explicit cmd_topic when device hi reports non-default control topic %s",
            hi_cmd_topic,
        )
        return False
    if hi_resp_topic and hi_resp_topic != config.resp_topic and not resp_explicit:
        logger.error(
            "device-reboot requires explicit resp_topic when device hi reports non-default control topic %s",
            hi_resp_topic,
        )
        return False

    try:
        agent_state = _unwrap_tool_data(
            collector._required_tool_json("device", {"action": "agent"}, timeout=config.timeout)
        )
    except Exception as exc:
        logger.error(f"Failed to query device agent state for trigger=device-reboot: {exc}")
        return False

    if not bool(agent_state.get("raw_auto")):
        logger.error("device-reboot requires raw_auto=1")
        return False

    data_topic, resp_topic = _resolve_startup_trigger_topics(
        argv=argv,
        environ=environ,
        config=config,
        raw_state=raw_state,
        hi=hi,
    )
    host, port = _parse_broker_endpoint(config.broker, 1883)

    for out_path in (config.data_output, config.resp_output):
        out_dir = os.path.dirname(os.path.abspath(out_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

    logger.info(
        "Collect config: broker=%s:%s, data_topic=%s, resp_topic=%s, duration=%ss, "
        "data_output=%s, resp_output=%s",
        host,
        port,
        data_topic,
        resp_topic,
        config.duration,
        config.data_output,
        config.resp_output,
    )

    raw_args = {
        "action": "raw",
        "enabled": True,
        "uart_enabled": False,
        "uri": config.broker,
    }

    result_ok = False
    client = None
    raw_enable_ok = False
    reboot_ok = False
    post_reboot_seen = False

    with open(config.data_output, "wb") as data_fout, open(config.resp_output, "wb") as resp_fout:
        capture_session = _MqttRawCaptureSession(
            data_topic,
            resp_topic,
            data_fout,
            resp_fout,
        )
        try:
            client = _connect_capture_client(capture_session, host=host, port=port, timeout=config.timeout)

            if client is None:
                logger.error("MQTT connect timeout while waiting for subscribe-ready state")
            else:
                try:
                    raw_result = mcp.call_tool("radar", raw_args, timeout=config.timeout)
                    raw_payload = mcp.extract_text(raw_result)
                    if raw_payload and raw_payload.strip():
                        logger.info("Radar raw forwarding armed for reboot capture: %s", raw_payload)
                    raw_enable_ok = True
                except Exception as exc:
                    logger.error(f"Failed to enable radar raw forwarding for trigger=device-reboot: {exc}")

                if raw_enable_ok:
                    baseline_messages = int(capture_session.stats["messages"])
                    baseline_resp_messages = int(capture_session.stats["resp_messages"])
                    try:
                        reboot_result = mcp.call_tool("device", {"action": "reboot"}, timeout=max(config.timeout, 15.0))
                        reboot_payload = mcp.extract_text(reboot_result)
                        if reboot_payload and reboot_payload.strip():
                            logger.info("Device reboot requested: %s", reboot_payload)
                        reboot_ok = True
                    except Exception as exc:
                        logger.error(f"Failed to request device reboot for trigger=device-reboot: {exc}")

                    if reboot_ok:
                        wait_deadline = time.time() + max(0.1, float(config.timeout))
                        while capture_session.stats["messages"] <= baseline_messages and time.time() < wait_deadline:
                            time.sleep(0.1)

                        if capture_session.stats["messages"] <= baseline_messages:
                            logger.error("No post-reboot raw payload captured before timeout")
                        else:
                            post_reboot_seen = True
                            try:
                                time.sleep(max(0.0, float(config.duration)))
                            except KeyboardInterrupt:
                                logger.info("Collection interrupted by user")

                            collector._print_summary(capture_session.stats, config.data_output, config.resp_output)
                            if capture_session.stats["resp_messages"] <= baseline_resp_messages:
                                logger.error("No raw command-port payload captured on resp topic after device reboot")
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

    return result_ok and raw_enable_ok and reboot_ok and post_reboot_seen


def execute_collect_raw(
    config: CollectRawConfig,
    argv: Sequence[str],
    environ: Mapping[str, str],
) -> bool:
    transport_args = _build_transport_args(config)
    transport = create_transport(transport_args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=config.timeout)
        collector = CollectCommand(mcp)
        if config.trigger == "none":
            data_topic, resp_topic = resolve_collect_raw_runtime_topics(argv, environ, config)
            return collector.execute_trigger_none(
                duration=config.duration,
                data_output=config.data_output,
                resp_output=config.resp_output,
                broker=config.broker,
                mqtt_port=transport_args.mqtt_port,
                device_id=config.device_id,
                data_topic=data_topic,
                resp_topic=resp_topic,
                resp_optional=config.resp_optional,
                timeout=config.timeout,
            )
        if config.trigger == "radar-restart":
            return _execute_trigger_radar_restart(config, mcp, argv, environ)
        if config.trigger == "device-reboot":
            return _execute_trigger_device_reboot(config, mcp, argv, environ)
        raise ValueError(f"trigger={config.trigger} is not implemented yet")
    finally:
        transport.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]

    if any(arg in ("-h", "--help") for arg in argv):
        parser.parse_args(list(argv))
        return 0

    try:
        config = resolve_collect_raw_config(argv)
        ok = execute_collect_raw(config, argv, os.environ)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
