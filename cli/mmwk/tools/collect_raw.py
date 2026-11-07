"""Pure-MQTT raw capture helper contract surface."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Mapping, Sequence

from mmwk._logging import logger
from mmwk.commands.collect import (
    CollectCommand,
    _create_mqtt_client,
    _parse_broker_endpoint,
)
from mmwk.commands.collect_engine import (
    CollectionPlan,
    collect_reconnect_mqtt,
)
from mmwk.mcp_client import McpClient
from mmwk.mqtt_topics import build_mqtt_topics
from mmwk.transport import create_transport


TRIGGERS = ("none", "radar-restart", "device-reboot")
DEFAULT_DURATION = 10
DEFAULT_TIMEOUT = 10.0
DEFAULT_DATA_OUTPUT = "data_resp.sraw"
DEFAULT_RESP_OUTPUT = "cmd_resp.log"

ENV_BROKER = "MMWK_SERVER_MQTT_URI"
ENV_DID = "MMWK_DID"
ENV_PROD = "MMWK_PROD"
ENV_OID = "MMWK_OID"
ENV_CID = "MMWK_CID"
ENV_RAW_DATA = "MMWK_RAW_DATA"
ENV_RAW_RESP = "MMWK_RAW_RESP"


@dataclass(frozen=True)
class CollectRawConfig:
    trigger: str
    duration: int
    timeout: float
    broker: str
    did: str
    prod: str
    oid: str
    cid: str
    cmd: str
    resp: str
    raw_data: str
    raw_resp: str
    data_output: str
    resp_output: str
    resp_optional: bool
    overwrite: bool = False


def _topic_defaults(*, did: str, prod: str, oid: str, cid: str) -> dict[str, str]:
    return build_mqtt_topics(
        did=did,
        prod=prod or "mmwk",
        oid=oid or "mmwk",
        cid=cid or "",
        include_raw_cmd=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="collect.sh --trigger",
        description="Pure-MQTT raw capture helper",
        epilog=(
            "Environment fallback variables:\n"
            f"  {ENV_BROKER}\n"
            f"  {ENV_DID}\n"
            f"  {ENV_PROD}\n"
            f"  {ENV_OID}\n"
            f"  {ENV_CID}\n"
            f"  {ENV_RAW_DATA}\n"
            f"  {ENV_RAW_RESP}\n\n"
            "The collect.sh direct mode can auto-load MMWK_SERVER_MQTT_URI from server.sh state.\n"
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
    parser.add_argument("--did", help=f"DID used for default topics (env: {ENV_DID})")
    parser.add_argument("--prod", default="", help=f"Product route segment (default/env: mmwk/{ENV_PROD})")
    parser.add_argument("--oid", default="", help=f"Organization route segment (default/env: mmwk/{ENV_OID})")
    parser.add_argument("--cid", default="", help=f"Claimed route id; takes precedence over --did (env: {ENV_CID})")
    parser.add_argument(
        "--raw-data",
        help=f"Raw data topic override (env: {ENV_RAW_DATA})",
    )
    parser.add_argument(
        "--raw-resp",
        help=f"Raw response topic override (env: {ENV_RAW_RESP})",
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
        help=(
            "Deprecated and rejected; use run.sh collect --mode auto --attach "
            "for a borrowed DATA-only route"
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing capture outputs instead of rejecting collisions",
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
    did = _choose(getattr(args, "did", ""), _env_value(env, ENV_DID))
    prod = _choose(getattr(args, "prod", ""), _env_value(env, ENV_PROD), "mmwk")
    oid = _choose(getattr(args, "oid", ""), _env_value(env, ENV_OID), "mmwk")
    cid = _choose(getattr(args, "cid", ""), _env_value(env, ENV_CID))
    if not broker:
        raise ValueError(f"Missing MQTT broker; set --broker or {ENV_BROKER}")
    if not (did or cid):
        raise ValueError(f"Missing MQTT route id; set --did, --cid, {ENV_DID}, or {ENV_CID}")

    defaults = _topic_defaults(did=did, prod=prod, oid=oid, cid=cid)
    cmd = defaults["cmd"]
    resp = defaults["resp"]
    raw_data = _choose(
        getattr(args, "raw_data", ""),
        _env_value(env, ENV_RAW_DATA),
        defaults["raw_data"],
    )
    raw_resp = _choose(
        getattr(args, "raw_resp", ""),
        _env_value(env, ENV_RAW_RESP),
        defaults["raw_resp"],
    )

    data_output = str(getattr(args, "data_output", DEFAULT_DATA_OUTPUT)).strip() or DEFAULT_DATA_OUTPUT
    resp_output = str(getattr(args, "resp_output", DEFAULT_RESP_OUTPUT)).strip() or DEFAULT_RESP_OUTPUT
    if os.path.abspath(data_output) == os.path.abspath(resp_output):
        raise ValueError("data-output and resp-output must be different paths")

    if getattr(args, "resp_optional", False):
        raise ValueError(
            "--resp-optional is not supported by --trigger; use "
            "run.sh collect --mode auto --attach"
        )

    return CollectRawConfig(
        trigger=args.trigger,
        duration=int(args.duration),
        timeout=float(args.timeout),
        broker=broker,
        did=did,
        prod=prod,
        oid=oid,
        cid=cid,
        cmd=cmd,
        resp=resp,
        raw_data=raw_data,
        raw_resp=raw_resp,
        data_output=data_output,
        resp_output=resp_output,
        resp_optional=bool(getattr(args, "resp_optional", False)),
        overwrite=bool(getattr(args, "overwrite", False)),
    )


def _flag_present(argv: Sequence[str], flag: str) -> bool:
    return any(arg == flag or arg.startswith(f"{flag}=") for arg in argv)


def resolve_collect_raw_runtime_topics(
    argv: Sequence[str],
    environ: Mapping[str, str],
    config: CollectRawConfig,
) -> tuple[str, str]:
    raw_data_explicit = _flag_present(argv, "--raw-data") or bool(_env_value(environ, ENV_RAW_DATA))
    raw_resp_explicit = _flag_present(argv, "--raw-resp") or bool(_env_value(environ, ENV_RAW_RESP))

    return (
        config.raw_data if raw_data_explicit else "",
        config.raw_resp if raw_resp_explicit else "",
    )


def _build_transport_args(config: CollectRawConfig) -> SimpleNamespace:
    _, port = _parse_broker_endpoint(config.broker, 1883)
    return SimpleNamespace(
        transport="mqtt",
        # Preserve the URI so MqttTransport can reuse mqtts, URI credentials,
        # and its explicit port for the parsed control connection.
        broker=config.broker,
        mqtt_port=port,
        did=config.did,
        prod=config.prod,
        oid=config.oid,
        cid=config.cid,
        timeout=config.timeout,
    )


def _resolve_startup_trigger_topics(
    argv: Sequence[str],
    environ: Mapping[str, str],
    config: CollectRawConfig,
    raw_state: Mapping[str, object],
    hi: Mapping[str, object],
) -> tuple[str, str]:
    defaults = _topic_defaults(did=config.did, prod=config.prod, oid=config.oid, cid=config.cid)
    raw_data_explicit = _flag_present(argv, "--raw-data") or bool(_env_value(environ, ENV_RAW_DATA))
    raw_resp_explicit = _flag_present(argv, "--raw-resp") or bool(_env_value(environ, ENV_RAW_RESP))

    raw_data = _choose(
        config.raw_data if raw_data_explicit else "",
        raw_state.get("raw_data", ""),
        _value_from_hi(hi, "raw_data"),
        defaults["raw_data"],
    )
    raw_resp = _choose(
        config.raw_resp if raw_resp_explicit else "",
        raw_state.get("raw_resp", ""),
        _value_from_hi(hi, "raw_resp"),
        defaults["raw_resp"],
    )
    return raw_data, raw_resp


def _execute_trigger_radar_restart(
    config: CollectRawConfig,
    mcp: McpClient,
    argv: Sequence[str],
    environ: Mapping[str, str],
) -> bool:
    """Map the legacy restart trigger to the shared host lifecycle engine."""
    data_topic, resp_topic = _resolve_startup_trigger_topics(
        argv=argv,
        environ=environ,
        config=config,
        raw_state={},
        hi={},
    )
    return CollectCommand(mcp).execute(
        duration=config.duration,
        data_output=config.data_output,
        resp_output=config.resp_output,
        broker=config.broker,
        mqtt_port=_parse_broker_endpoint(config.broker, 1883)[1],
        did=config.did,
        prod=config.prod,
        oid=config.oid,
        cid=config.cid,
        data_topic=data_topic,
        resp_topic=resp_topic,
        mode="host",
        attach=False,
        overwrite=config.overwrite,
        timeout=config.timeout,
    )


def _execute_trigger_device_reboot(
    config: CollectRawConfig,
    mcp: McpClient,
    argv: Sequence[str],
    environ: Mapping[str, str],
) -> bool:
    """Compatibility wrapper for the shared reconnect collection backend."""
    try:
        data_topic, _ = _resolve_startup_trigger_topics(
            argv=argv,
            environ=environ,
            config=config,
            raw_state={},
            hi={},
        )
        collect_reconnect_mqtt(
            CollectionPlan(
                transport="mqtt",
                mode="auto",
                duration=config.duration,
                data_output=config.data_output,
                resp_output=config.resp_output,
                overwrite=config.overwrite,
                data_ready_timeout=config.timeout,
                control_timeout=config.timeout,
            ),
            control=mcp,
            broker=config.broker,
            # CID selects the MQTT topic route; it is not the hardware DID
            # returned by node info.
            expected_did=config.did or None,
            data_topic=data_topic or None,
            prod=config.prod,
            oid=config.oid,
            cid=config.cid,
            client_factory=_create_mqtt_client,
        )
        return True
    except Exception as exc:
        logger.error("Reconnect collection failed: %s", exc)
        return False


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
                did=config.did,
                prod=config.prod,
                oid=config.oid,
                cid=config.cid,
                data_topic=data_topic,
                resp_topic=resp_topic,
                resp_optional=config.resp_optional,
                overwrite=config.overwrite,
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
