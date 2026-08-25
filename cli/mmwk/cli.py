"""CLI entry point for mmwk."""

import sys
import json
import logging
import argparse
import os
from pathlib import Path

from mmwk._logging import logger
from mmwk.transport import create_transport
from mmwk.protocol_client import create_protocol_client
from mmwk.usb_transport import UsbTransportError
from mmwk.commands.flash import FlashCommand
from mmwk.commands.ota import OtaCommand
from mmwk.commands.reconf import ReconfCommand
from mmwk.commands.device_ota import DeviceOtaCommand
from mmwk.commands.collect import CollectCommand
from mmwk.commands.collect_engine import (
    CollectionPlan,
    collect_local,
    collect_split_wire_mqtt,
)
from mmwk.commands.cfg import CfgCommand

_ACTIVE_PROTOCOL = "cli"
_ACTIVE_KEY = ""
_ACTIVE_REQUEST_RETRIES = 1
_ACTIVE_REQUEST_RETRY_DELAY = 1.0


def McpClient(transport):
    return create_protocol_client(
        _ACTIVE_PROTOCOL,
        transport,
        key=_ACTIVE_KEY,
        request_retries=_ACTIVE_REQUEST_RETRIES,
        request_retry_delay=_ACTIVE_REQUEST_RETRY_DELAY,
    )


def _cli_create_transport(args):
    """Thin wrapper: catch ValueError from create_transport and exit."""
    if hasattr(args, "protocol"):
        _set_active_protocol(getattr(args, "protocol", None) or "cli")
    try:
        _set_active_key(args)
        _set_active_request_retry_args(args)
        retries, retry_delay = _resolve_transport_retry_args(args)
        if getattr(args, "transport", "uart") == "usb":
            return create_transport(
                args,
                retries=retries,
                retry_delay=retry_delay,
                usb_probe=_build_usb_probe(args),
            )
        return create_transport(
            args,
            retries=retries,
            retry_delay=retry_delay,
        )
    except (ValueError, UsbTransportError) as e:
        print(f"Error: {e}")
        sys.exit(1)


def _identity_values(payload):
    """Return flattened node identity views from old and new response shapes."""
    if not isinstance(payload, dict):
        return []

    views = [payload]
    for key in ("data", "result"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            views.append(nested)
            data = nested.get("data")
            if isinstance(data, dict):
                views.append(data)
    return views


def _usb_node_info_matches(text, expected_did=None):
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        logger.debug("USB node info probe returned non-JSON text: %r", text)
        return False

    views = _identity_values(payload)
    board = next(
        (view.get("board") for view in views if view.get("board") is not None),
        None,
    )
    reported_did = None
    for view in views:
        for key in ("did", "id", "client_id"):
            if view.get(key) is not None:
                reported_did = view.get(key)
                break
        if reported_did is not None:
            break

    if str(board or "").strip().casefold() not in {"wdr", "wsr"}:
        logger.debug("USB node info probe rejected board=%r", board)
        return False
    if expected_did and str(reported_did or "").strip().casefold() != expected_did:
        logger.debug(
            "USB node info probe rejected DID=%r expected=%r",
            reported_did,
            expected_did,
        )
        return False
    return True


def _build_usb_probe(args):
    expected_did = str(getattr(args, "did", "") or "").strip().casefold() or None
    protocol = getattr(args, "protocol", None) or _ACTIVE_PROTOCOL
    key = _ACTIVE_KEY

    def probe(transport, timeout):
        probe_timeout = max(0.1, float(timeout))
        client = create_protocol_client(
            protocol,
            transport,
            key=key,
            request_retries=1,
            request_retry_delay=0.0,
        )
        client.initialize(timeout=probe_timeout)
        result = client.call_tool("node", {"action": "info"}, timeout=probe_timeout)
        return _usb_node_info_matches(client.extract_text(result), expected_did)

    return probe


def _resolve_transport_retry_args(args):
    transport = getattr(args, "transport", "uart") or "uart"
    retries = getattr(args, "transport_retries", None)
    retry_delay = getattr(args, "transport_retry_delay", 2.0)

    if retries is None:
        retries = 3 if transport == "mqtt" else 1
    if retry_delay is None:
        retry_delay = 2.0

    retries = int(retries)
    retry_delay = float(retry_delay)
    if retries < 1:
        raise ValueError("--transport-retries must be >= 1")
    if retry_delay < 0:
        raise ValueError("--transport-retry-delay must be >= 0")
    return retries, retry_delay


def _resolve_request_retry_args(args):
    retries = getattr(args, "request_retries", None)
    retry_delay = getattr(args, "request_retry_delay", 1.0)

    if retries is None:
        retries = 1
    if retry_delay is None:
        retry_delay = 1.0

    retries = int(retries)
    retry_delay = float(retry_delay)
    if retries < 1:
        raise ValueError("--request-retries must be >= 1")
    if retry_delay < 0:
        raise ValueError("--request-retry-delay must be >= 0")
    return retries, retry_delay


def _print_json_payload(text):
    try:
        data = json.loads(text)
        print(json.dumps(data, indent=2))
    except Exception:
        print(text)


def _load_json_object_arg(raw_value):
    if raw_value is None:
        return {}

    text = raw_value
    if raw_value.startswith("@"):
        with open(raw_value[1:], "r", encoding="utf-8") as fp:
            text = fp.read()
    elif os.path.exists(raw_value):
        with open(raw_value, "r", encoding="utf-8") as fp:
            text = fp.read()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON payload ({exc})")
        sys.exit(1)

    if not isinstance(data, dict):
        print("Error: JSON payload must be an object")
        sys.exit(1)

    return data


def _usb_ms_arg(value):
    try:
        parsed = int(value, 10)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(
            "usb_ms must be an integer from 0 to 60000"
        ) from exc

    if parsed < 0 or parsed > 60000:
        raise argparse.ArgumentTypeError(
            "usb_ms must be an integer from 0 to 60000"
        )
    return parsed


def _usb_wait_ms_arg(value):
    try:
        parsed = int(value, 10)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(
            "usb-wait-ms must be a non-negative integer"
        ) from exc

    if parsed < 0:
        raise argparse.ArgumentTypeError(
            "usb-wait-ms must be a non-negative integer"
        )
    return parsed

def _set_active_protocol(protocol):
    global _ACTIVE_PROTOCOL
    _ACTIVE_PROTOCOL = protocol


def _set_active_key(args):
    global _ACTIVE_KEY
    cli_key = getattr(args, "key", None)
    env_key = os.environ.get("MMWK_CLI_KEY", "")
    _ACTIVE_KEY = cli_key or env_key or ""


def _set_active_request_retry_args(args):
    global _ACTIVE_REQUEST_RETRIES, _ACTIVE_REQUEST_RETRY_DELAY
    _ACTIVE_REQUEST_RETRIES, _ACTIVE_REQUEST_RETRY_DELAY = _resolve_request_retry_args(args)


def _finalize_protocol_args(args):
    if not hasattr(args, "protocol"):
        return

    _set_active_key(args)

    if args.protocol is None:
        args.protocol = "cli"
        print(
            "Warning: default control protocol is now cli. Upgrade callers to pass "
            "--protocol cli; if needed, retry with --protocol mcp.",
            file=sys.stderr,
        )

    _set_active_protocol(args.protocol)


def _call_tool_and_print_json(args, tool, payload):
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)
        result = mcp.call_tool(tool, payload, timeout=args.timeout)
        _print_json_payload(mcp.extract_text(result))
    finally:
        transport.close()


def _endpoint_id_arg(args):
    endpoint_id = getattr(args, "id", None)
    if endpoint_id is not None:
        return endpoint_id
    return getattr(args, "endpoint", None)


def add_transport_args(parser, include_route_args=True):
    """Add common transport arguments to a parser."""
    group = parser.add_argument_group("Transport")
    group.add_argument("--protocol", choices=["mcp", "cli"],
                       help="Control protocol (default: cli; use mcp as fallback)")
    group.add_argument("--transport", "-t", default="uart",
                       choices=["uart", "usb", "mqtt"],
                       help="Transport layer (default: uart; USB is WDR/WSR CDC only)")
    group.add_argument("--port", "-p", help="Serial port (UART or exact USB CDC path)")
    group.add_argument("--baudrate", "-b", type=int, default=115200,
                       help="UART baudrate (USB CDC always uses 115200; default: 115200)")
    group.add_argument(
        "--usb-wait-ms",
        type=_usb_wait_ms_arg,
        default=0,
        help=(
            "Host-side USB CDC enumeration wait budget in milliseconds "
            "(default: 0; does not read or set the device usb_ms window)"
        ),
    )
    group.add_argument("--reset", action="store_true",
                       help="Reset UART device via DTR/RTS before connecting (not valid for USB)")
    group.add_argument("--uart-proxy", choices=["auto", "off"], default=None,
                       help="Use persistent local UART proxy (UART only; default: auto)")
    group.add_argument("--broker", default="localhost",
                       help="MQTT broker address (default: localhost)")
    group.add_argument("--mqtt-port", type=int, default=1883,
                       help="MQTT broker port (default: 1883)")
    if include_route_args:
        group.add_argument("--did", help="DID for MQTT route fallback")
        group.add_argument("--prod", default="mmwk",
                           help="MQTT product route segment (default: mmwk)")
        group.add_argument("--oid", default="mmwk",
                           help="MQTT organization route segment (default: mmwk)")
        group.add_argument("--cid", default="",
                           help="MQTT claimed route id; when set it takes precedence over --did")
    group.add_argument("--transport-retries", type=int, default=None,
                       help="Transport connection attempts (default: 3 for MQTT, 1 for UART)")
    group.add_argument("--transport-retry-delay", type=float, default=2.0,
                       help="Seconds between transport connection attempts (default: 2)")
    group.add_argument("--request-retries", type=int, default=None,
                       help="Tool request attempts after transport is connected (default: 1)")
    group.add_argument("--request-retry-delay", type=float, default=1.0,
                       help="Seconds between tool request attempts (default: 1)")
    group.add_argument("--timeout", type=float, default=10.0,
                       help="Response timeout in seconds (default: 10)")
    group.add_argument("--key", help="CLI protection key for protected commands")
    group.add_argument("-v", "--verbose", action="store_true",
                       help="Enable debug logging")


def add_ota_transport_arg(parser):
    parser.add_argument(
        "--ota-transport",
        choices=["http", "mqtt"],
        default="http",
        help="OTA data plane: http or mqtt binary stream (default: http)",
    )


def require_mqtt_control_for_mqtt_ota(args) -> None:
    if getattr(args, "ota_transport", "http") == "mqtt" and getattr(args, "transport", "uart") != "mqtt":
        print("Error: --ota-transport mqtt requires --transport mqtt")
        sys.exit(1)


def reject_usb_binary_command(args, command: str) -> None:
    if getattr(args, "transport", "uart") == "usb":
        print(f"Error: {command} is not supported over USB CDC")
        sys.exit(1)


def reject_radar_only_node_ota_args_for_esp(args) -> None:
    if getattr(args, "version", None):
        print("Error: --version is only supported with --target radar")
        sys.exit(1)
    if getattr(args, "verify", None) is not None:
        print("Error: --verify/--no-verify is only supported with --target radar")
        sys.exit(1)
    if getattr(args, "welcome", None) is not None:
        print("Error: --welcome/--no-welcome is only supported with --target radar")
        sys.exit(1)
    if getattr(args, "force", False):
        print("Error: --force is only supported with --target radar")
        sys.exit(1)
    if getattr(args, "progress_interval", None) is not None:
        print("Error: --progress-interval is only supported with --target radar")
        sys.exit(1)


def cmd_radar_flash(args):
    """Handle: mmwk radar flash ..."""
    reject_usb_binary_command(args, "radar fw flash")
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        flash = FlashCommand(mcp)
        mqtt_delay = getattr(args, 'mqtt_delay', 0)
        ok = flash.execute(
            fw_path=args.fw,
            cfg_path=args.cfg,
            chunk_size=args.chunk_size,
            mqtt_delay=mqtt_delay,
            progress_interval=getattr(args, 'progress_interval', 5),
            reboot_delay=getattr(args, 'reboot_delay', 0),
            version=args.version,
            welcome=args.welcome,
            verify=args.verify,
        )
        sys.exit(0 if ok else 1)
    finally:
        transport.close()


def cmd_radar_ota(args):
    """Handle: mmwk radar ota ..."""
    reject_usb_binary_command(args, "radar fw ota")
    require_mqtt_control_for_mqtt_ota(args)
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        ota = OtaCommand(mcp)
        ok = ota.execute(
            fw_path=args.fw,
            cfg_path=args.cfg,
            http_port=args.http_port,
            base_url=args.base_url,
            version=args.version,
            welcome=args.welcome,
            verify=args.verify,
            timeout=args.ota_timeout,
            force=getattr(args, "force", False),
            progress_interval=getattr(args, 'progress_interval', 5),
            raw_resp_output=getattr(args, "raw_resp_output", None),
            raw_broker=getattr(args, "raw_broker", None),
            raw_resp=getattr(args, "raw_resp", None),
            raw_timeout=getattr(args, "raw_timeout", 10.0),
            transport=getattr(args, "transport", "uart"),
            ota_transport=getattr(args, "ota_transport", "http"),
        )
        sys.exit(0 if ok else 1)
    finally:
        transport.close()


def cmd_radar_reconf(args):
    """Handle: mmwk radar reconf ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        reconf = ReconfCommand(mcp)
        ok = reconf.execute(
            cfg_path=args.cfg,
            clear_cfg=args.clear_cfg,
            chunk_size=args.chunk_size,
            mqtt_delay=args.mqtt_delay,
            version=args.version,
            welcome=args.welcome,
            verify=args.verify,
            timeout=args.reconf_timeout,
        )
        sys.exit(0 if ok else 1)
    finally:
        transport.close()


def cmd_radar_cfg(args):
    """Handle: mmwk radar config read ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        cfg = CfgCommand(mcp)
        try:
            output = cfg.execute(gen=getattr(args, "gen", False), timeout=args.timeout)
        except Exception as exc:
            print(f"Error: {exc}")
            sys.exit(1)

        sys.stdout.write(output)
        sys.exit(0)
    finally:
        transport.close()


def cmd_radar_version(args):
    """Handle: mmwk radar version ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        result = mcp.call_tool("radar.fw", {"action": "version"}, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            data = json.loads(text)
            print(json.dumps(data, indent=2))
        except:
            print(text)
    finally:
        transport.close()


def cmd_radar_status(args):
    """Handle: mmwk radar status ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        radar_args = {"action": "status"}

        result = mcp.call_tool("radar", radar_args, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            data = json.loads(text)
            print(json.dumps(data, indent=2))
        except:
            print(text)
    finally:
        transport.close()


def cmd_radar_start(args):
    """Handle: mmwk radar start ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        radar_args = {"action": "start"}
        if getattr(args, "mode", None):
            radar_args["mode"] = args.mode

        result = mcp.call_tool("radar", radar_args, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            data = json.loads(text)
            print(json.dumps(data, indent=2))
        except Exception:
            print(text)
    finally:
        transport.close()


def cmd_radar_stop(args):
    """Handle: mmwk radar stop ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        result = mcp.call_tool("radar", {"action": "stop"}, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            data = json.loads(text)
            print(json.dumps(data, indent=2))
        except Exception:
            print(text)
    finally:
        transport.close()


def cmd_radar_debug(args):
    """Handle: mmwk radar debug ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        radar_args = {"action": "debug", "op": args.op}
        if args.op == "set":
            if args.packets is None or args.frames is None:
                print("Error: radar debug set requires --packets and --frames (on/off)")
                sys.exit(1)
            radar_args["packets"] = args.packets == "on"
            radar_args["frames"] = args.frames == "on"
        elif args.packets is not None or args.frames is not None:
            print("Error: --packets/--frames are only valid for radar debug set")
            sys.exit(1)

        result = mcp.call_tool("radar.diag", radar_args, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            data = json.loads(text)
            print(json.dumps(data, indent=2))
        except Exception:
            print(text)
    finally:
        transport.close()


def cmd_node_info(args):
    """Handle: mmwk node info ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        result = mcp.call_tool("node", {"action": "info"}, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            data = json.loads(text)
            print(json.dumps(data, indent=2))
        except:
            print(text)
    finally:
        transport.close()


def cmd_node_reboot(args):
    """Handle: mmwk node reboot ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=15)
        resp = mcp.call_tool("node", {"action": "reboot"}, timeout=10)
        text = mcp.extract_text(resp)
        print(text)
    finally:
        transport.close()


def cmd_node_factory_reset(args):
    """Handle: mmwk node factory-reset ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)
        mcp.call_tool("node", {"action": "factory_reset"}, timeout=args.timeout)
        print("已触发重置")
    finally:
        transport.close()


def cmd_node_claim(args):
    """Handle: mmwk node claim ..."""
    if getattr(args, "transport", "uart") not in ("uart", "usb"):
        print("Error: node claim is only supported over UART or USB/local transport")
        sys.exit(1)

    payload = {"action": "claim"}
    if getattr(args, "endpoint", None):
        payload["endpoint"] = args.endpoint
    if getattr(args, "token", None):
        payload["token"] = args.token
    if getattr(args, "prod", None):
        payload["prod"] = args.prod
    if getattr(args, "oid", None):
        payload["oid"] = args.oid
    if getattr(args, "cid", None):
        payload["cid"] = args.cid
    _call_tool_and_print_json(args, "node", payload)


def cmd_device_ota(args):
    """Handle: mmwk device ota ..."""
    reject_usb_binary_command(args, "node ota")
    target = getattr(args, "target", "esp") or "esp"
    if target == "radar" and args.url:
        print("Error: node ota --target radar requires --fw and does not support --url")
        sys.exit(1)
    if target == "esp" and getattr(args, "cfg", None):
        print("Error: --cfg is only supported with --target radar")
        sys.exit(1)
    if target == "esp":
        reject_radar_only_node_ota_args_for_esp(args)
    if target == "radar" and args.https:
        print("Error: --https is only supported with --target esp")
        sys.exit(1)
    if getattr(args, "ota_transport", "http") == "mqtt" and args.url:
        print("Error: --ota-transport mqtt requires local --fw and does not support --url")
        sys.exit(1)
    if getattr(args, "ota_transport", "http") == "mqtt" and args.https:
        print("Error: --https is only supported with --ota-transport http")
        sys.exit(1)
    require_mqtt_control_for_mqtt_ota(args)
    if args.https and not args.fw:
        print("Error: --https is only supported with local --fw source")
        sys.exit(1)
    if args.https and (not args.https_cert or not args.https_key):
        print("Error: --https requires both --https-cert and --https-key")
        sys.exit(1)

    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        if target == "radar":
            ota = OtaCommand(mcp)
            ok = ota.execute(
                fw_path=args.fw,
                cfg_path=args.cfg,
                http_port=args.http_port,
                base_url=None,
                version=args.version,
                welcome=args.welcome,
                verify=args.verify,
                timeout=args.ota_timeout,
                force=getattr(args, "force", False),
                progress_interval=args.progress_interval if args.progress_interval is not None else 5,
                transport=getattr(args, "transport", "uart"),
                ota_transport=getattr(args, "ota_transport", "http"),
            )
        else:
            ota = DeviceOtaCommand(mcp)
            ok = ota.execute(
                fw_path=args.fw,
                url=args.url,
                http_port=args.http_port,
                use_https=args.https,
                https_cert=args.https_cert,
                https_key=args.https_key,
                timeout=args.ota_timeout,
                transport=getattr(args, "transport", "uart"),
                ota_transport=getattr(args, "ota_transport", "http"),
                post_reboot_check=os.environ.get("MMWK_DEVICE_OTA_POST_REBOOT_CHECK", "sdk-node"),
            )
        sys.exit(0 if ok else 1)
    finally:
        transport.close()


def cmd_device_agent(args):
    """Handle: mmwk device agent ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        dev_args = {"action": "agent"}
        if args.mqtt is not None:
            dev_args["mqtt"] = args.mqtt
        if args.uart is not None:
            dev_args["uart"] = args.uart
        if getattr(args, "uart_split", None) is not None:
            dev_args["uart_split"] = args.uart_split
        if getattr(args, "led", None) is not None:
            dev_args["led"] = args.led
        if getattr(args, "reboot_ms", None) is not None:
            dev_args["reboot_ms"] = args.reboot_ms
        if getattr(args, "usb_ms", None) is not None:
            dev_args["usb_ms"] = args.usb_ms

        result = mcp.call_tool("node", dev_args, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            data = json.loads(text)
            print(json.dumps(data, indent=2))
        except Exception:
            print(text)
    finally:
        transport.close()


def cmd_node_key(args):
    """Handle: mmwk node key ..."""
    payload = {"action": "key", "op": args.key_action}
    if getattr(args, "new_key", None) is not None:
        payload["new_key"] = args.new_key
    _call_tool_and_print_json(args, "node", payload)


def cmd_device_heartbeat(args):
    """Handle: mmwk device heartbeat ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        dev_args = {"action": "heartbeat", "interval": args.interval}
        if args.fields:
            dev_args["fields"] = args.fields

        result = mcp.call_tool("node", dev_args, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            data = json.loads(text)
            print(json.dumps(data, indent=2))
        except Exception:
            print(text)
    finally:
        transport.close()


def cmd_fw_list(args):
    """Handle: mmwk fw list ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        result = mcp.call_tool("radar.fw", {"action": "list"}, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            data = json.loads(text)
            print(json.dumps(data, indent=2))
        except Exception:
            print(text)
    finally:
        transport.close()


def cmd_fw_set(args):
    """Handle: mmwk fw set ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        result = mcp.call_tool("radar.fw", {"action": "set", "index": args.index}, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            data = json.loads(text)
            print(json.dumps(data, indent=2))
        except Exception:
            print(text)
    finally:
        transport.close()


def cmd_radar_fw_switch(args):
    """Handle: mmwk radar fw switch ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        payload = {"action": "switch", "index": args.index}
        if getattr(args, "persist", False):
            payload["persist"] = True

        result = mcp.call_tool("radar.fw", payload, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            data = json.loads(text)
            print(json.dumps(data, indent=2))
        except Exception:
            print(text)
    finally:
        transport.close()


def cmd_fw_del(args):
    """Handle: mmwk fw del ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        result = mcp.call_tool("radar.fw", {"action": "del", "index": args.index}, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            data = json.loads(text)
            print(json.dumps(data, indent=2))
        except Exception:
            print(text)
    finally:
        transport.close()


def cmd_fw_download(args):
    """Handle: mmwk fw download ..."""
    reject_usb_binary_command(args, "radar fw download")
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        fw_args = {
            "action": "download",
            "source": args.source,
            "name": args.name,
            "version": args.fw_version,
            "size": args.size,
        }
        result = mcp.call_tool("radar.fw", fw_args, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            data = json.loads(text)
            print(json.dumps(data, indent=2))
        except Exception:
            print(text)
    finally:
        transport.close()


def cmd_radar_raw(args):
    """Handle: mmwk radar raw ..."""
    payload = {"action": "raw"}
    action = args.raw_action
    if action == "status":
        _call_tool_and_print_json(args, "radar", payload)
        return

    channel = getattr(args, "channel", None)
    ctrl = getattr(args, "ctrl", None)
    data = getattr(args, "data", None)
    baud = getattr(args, "baud", None)
    escape = getattr(args, "escape", None)
    if channel is not None and (ctrl is not None or data is not None):
        print("Error: --channel cannot be combined with --ctrl/--data")
        raise SystemExit(2)
    if (ctrl is None) != (data is None):
        print("Error: --ctrl and --data must be supplied together")
        raise SystemExit(2)
    if channel is None and ctrl is None and action != "off":
        print("Error: state-changing raw commands require --channel or --ctrl/--data")
        raise SystemExit(2)
    if action == "reconnect":
        if channel != "mqtt" or ctrl is not None or data is not None:
            print("Error: reconnect requires --channel mqtt and no explicit ctrl/data")
            raise SystemExit(2)
        if baud is not None or escape is not None:
            print("Error: reconnect does not accept --baud or --escape")
            raise SystemExit(2)
    if action == "off" and baud is not None:
        print("Error: --baud is only valid for raw runtime")
        raise SystemExit(2)
    if action != "runtime" and escape is not None:
        print("Error: --escape is only valid for raw runtime")
        raise SystemExit(2)
    data_route = data or channel
    if baud is not None and data_route not in {"wire", "both"}:
        print("Error: --baud requires a wire DATA route")
        raise SystemExit(2)

    payload["mode"] = action
    for name in ("channel", "ctrl", "data", "baud", "escape"):
        value = getattr(args, name, None)
        if value is not None:
            payload[name] = value
    _call_tool_and_print_json(args, "radar", payload)


def cmd_radar_record(args):
    """Handle: mmwk radar record start|stop|trigger ..."""
    payload = {"action": "record", "op": args.record_action}
    if args.record_action == "config_set":
        payload["config"] = _load_json_object_arg(args.json)
    elif args.record_action == "start":
        if not getattr(args, "uri", None):
            print("Error: radar record start requires --uri")
            raise SystemExit(2)
        payload["uri"] = args.uri
    elif args.record_action == "trigger":
        if getattr(args, "event", None):
            payload["event"] = args.event
        if getattr(args, "duration_s", None) is not None:
            payload["duration_s"] = args.duration_s
    _call_tool_and_print_json(args, "radar", payload)


def cmd_collect(args):
    """Handle: mmwk collect ..."""
    summary_output = getattr(args, "summary_output", None)
    explicit_output_values = [
        value for value in (
            getattr(args, "data_output", None),
            getattr(args, "resp_output", None),
            getattr(args, "wire_output", None),
            summary_output,
            getattr(args, "events_output", None),
        ) if value
    ]
    resolved_outputs = [Path(value).expanduser().resolve() for value in explicit_output_values]
    if len(set(resolved_outputs)) != len(resolved_outputs):
        print("Error: collection output paths must be distinct")
        sys.exit(1)
    transport_name = getattr(args, "transport", None)
    ctrl_transport = getattr(args, "ctrl_transport", None)
    data_transport = getattr(args, "data_transport", None)
    if (ctrl_transport is None) != (data_transport is None):
        print("Error: --ctrl-transport and --data-transport must be supplied together")
        sys.exit(1)
    if ctrl_transport is not None:
        if transport_name is not None:
            print("Error: --transport cannot be combined with --ctrl-transport/--data-transport")
            sys.exit(1)
        if not (ctrl_transport in {"uart", "usb"} and data_transport == "mqtt"):
            print("Error: split collection currently supports local wire control with MQTT DATA")
            sys.exit(1)
        transport_name = ctrl_transport
    else:
        transport_name = transport_name or ("uart" if args.port else "mqtt")
    mode = getattr(args, "mode", "host")
    if transport_name in {"uart", "usb"}:
        try:
            raw_baud = args.raw_baud
            if raw_baud is None and transport_name == "uart" and data_transport is None:
                raw_baud = 1_000_000
            plan = CollectionPlan(
                transport=transport_name,
                port=args.port,
                baudrate=args.baudrate,
                raw_baud=raw_baud,
                escape=getattr(args, "escape", "+++"),
                mode=mode,
                duration=args.duration,
                cfg_path=getattr(args, "cfg", None),
                data_output=args.data_output,
                resp_output=args.resp_output,
                wire_output=getattr(args, "wire_output", None),
                summary_output=summary_output,
                events_output=getattr(args, "events_output", None),
                overwrite=getattr(args, "overwrite", False),
                attach=getattr(args, "attach", False),
                allow_lossy=getattr(args, "allow_lossy", False),
                ctrl_transport=ctrl_transport,
                data_transport=data_transport,
                data_ready_timeout=getattr(args, "data_ready_timeout", 10.0),
                control_timeout=args.timeout,
            )
            if ctrl_transport is not None:
                summary = collect_split_wire_mqtt(
                    plan,
                    broker=args.broker,
                    mqtt_port=args.mqtt_port,
                    expected_did=args.did,
                    data_topic=args.data_topic,
                    prod=args.prod,
                    oid=args.oid,
                    cid=args.cid,
                    mqtt_username=getattr(args, "mqtt_user", "") or "",
                    mqtt_password=getattr(args, "mqtt_password", "") or "",
                    mqtt_ca=getattr(args, "mqtt_ca", None),
                )
            else:
                summary = collect_local(plan, expected_did=args.did)
            print(json.dumps(summary.as_dict(), indent=2))
            return
        except Exception as exc:
            print(f"Error: {exc}")
            sys.exit(1)

    transport = None
    mcp = None

    try:
        args.transport = "mqtt"
        transport = _cli_create_transport(args)
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        collector = CollectCommand(mcp)
        ok = collector.execute(
            duration=args.duration,
            data_output=args.data_output,
            resp_output=args.resp_output,
            broker=args.broker,
            mqtt_port=args.mqtt_port,
            did=args.did,
            prod=args.prod,
            oid=args.oid,
            cid=args.cid,
            data_topic=args.data_topic,
            resp_topic=args.resp_topic,
            resp_optional=getattr(args, "resp_optional", False),
            mode=mode,
            attach=getattr(args, "attach", False),
            overwrite=getattr(args, "overwrite", False),
            timeout=args.timeout,
            cfg_path=getattr(args, "cfg", None),
            summary_output=summary_output,
            events_output=getattr(args, "events_output", None),
            wire_output=getattr(args, "wire_output", None),
            mqtt_username=getattr(args, "mqtt_user", "") or "",
            mqtt_password=getattr(args, "mqtt_password", "") or "",
            mqtt_ca=getattr(args, "mqtt_ca", None),
        )
        sys.exit(0 if ok else 1)
    finally:
        if transport:
            transport.close()


def cmd_help(args):
    """Handle: mmwk help ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        result = mcp.call_tool("help", {}, timeout=args.timeout)
        _print_json_payload(mcp.extract_text(result))
    finally:
        transport.close()


def cmd_network(args):
    """Handle: mmwk network ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        net_args = {"action": args.action}
        if args.action == "wifi":
            net_args["ssid"] = args.ssid
            net_args["pass"] = args.passphrase
        elif args.action == "prov":
            net_args["enable"] = 1 if args.enable else 0
        elif args.action == "mqtt":
            if args.uri is not None:
                net_args["uri"] = args.uri
            if args.user is not None:
                net_args["user"] = args.user
            if args.passphrase is not None:
                net_args["pass"] = args.passphrase
        elif args.action == "4g":
            if args.apn is not None:
                net_args["apn"] = args.apn
            if args.user is not None:
                net_args["user"] = args.user
            if args.passphrase is not None:
                net_args["pass"] = args.passphrase
        elif args.action == "priority":
            if args.pref is not None:
                net_args["pref"] = args.pref
        elif args.action == "ntp":
            if getattr(args, 'server', None): net_args["server"] = args.server
            if getattr(args, 'tz_offset', None) is not None: net_args["tz_offset"] = args.tz_offset
            if getattr(args, 'ntp_interval', None) is not None: net_args["interval"] = args.ntp_interval

        result = mcp.call_tool("network", net_args, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            data = json.loads(text)
            print(json.dumps(data, indent=2))
        except:
            print(text)
    finally:
        transport.close()


def cmd_tools_list(args):
    """Handle: mmwk tools ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        tools = mcp.tools_list(timeout=args.timeout)
        for tool in tools:
            print(f"  {tool.get('name', '?'):14s} — {tool.get('description', '')}")
    finally:
        transport.close()


def cmd_endpoint_catalog(args):
    """Handle: mmwk endpoint list ..."""
    _call_tool_and_print_json(args, "endpoint", {"action": "list"})


def cmd_endpoint_list(args):
    """Handle: mmwk endpoint list ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        result = mcp.call_tool("endpoint", {"action": "list"}, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            payload = json.loads(text)
        except Exception:
            print(text)
            return
        if args.json:
            print(json.dumps(payload, indent=2))
            return

        endpoints = payload.get("endpoints", []) if isinstance(payload, dict) else []
        for endpoint in endpoints:
            if isinstance(endpoint, dict):
                endpoint_id = endpoint.get("id")
                if isinstance(endpoint_id, str) and endpoint_id:
                    print(endpoint_id)
    finally:
        transport.close()


def cmd_endpoint_describe(args):
    """Handle: mmwk endpoint describe ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        result = mcp.call_tool(
            "endpoint",
            {"action": "describe", "id": _endpoint_id_arg(args)},
            timeout=args.timeout,
        )
        _print_json_payload(mcp.extract_text(result))
    finally:
        transport.close()


def cmd_endpoint_read(args):
    """Handle: mmwk endpoint read ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        result = mcp.call_tool(
            "endpoint",
            {"action": "read", "id": _endpoint_id_arg(args)},
            timeout=args.timeout,
        )
        _print_json_payload(mcp.extract_text(result))
    finally:
        transport.close()


def cmd_endpoint_config_get(args):
    """Handle: mmwk endpoint config get ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        result = mcp.call_tool(
            "endpoint",
            {"action": "config_get", "id": _endpoint_id_arg(args)},
            timeout=args.timeout,
        )
        _print_json_payload(mcp.extract_text(result))
    finally:
        transport.close()


def cmd_endpoint_config_set(args):
    """Handle: mmwk endpoint config set ..."""
    payload = {
        "action": "config_set",
        "id": _endpoint_id_arg(args),
        "config": _load_json_object_arg(args.config_json),
    }
    _call_tool_and_print_json(args, "endpoint", payload)


def cmd_device_proto(args):
    """Handle: mmwk device proto ..."""
    payload = {"action": args.proto_action}
    if getattr(args, "name", None):
        payload["name"] = args.name
    _call_tool_and_print_json(args, "proto", payload)


def cmd_scene_show(args):
    """Handle: mmwk scene show ..."""
    _call_tool_and_print_json(args, "scene", {"action": "read"})


def cmd_scene_set(args):
    """Handle: mmwk scene set ..."""
    payload = {"action": "set", "config": _load_json_object_arg(args.config_json)}
    _call_tool_and_print_json(args, "scene", payload)


def cmd_scene_apply(args):
    """Handle: mmwk scene apply ..."""
    _call_tool_and_print_json(args, "scene", {"action": "apply"})


def cmd_scene_wait_ready(args):
    """Handle: mmwk scene wait-ready ..."""
    payload = {
        "action": "wait",
        "timeout_ms": args.timeout_ms,
        "interval_ms": args.interval_ms,
    }
    _call_tool_and_print_json(args, "scene", payload)


def main():
    parser = argparse.ArgumentParser(
        prog="mmwk",
        description="MMWK Sensor CLI — Control mmwk devices via canonical CLI JSON or MCP/JSON-RPC 2.0"
    )
    subparsers = parser.add_subparsers(dest="tool", help="Control service namespace")

    # -- radar --
    radar_parser = subparsers.add_parser("radar", help="Radar capability surface")
    radar_sub = radar_parser.add_subparsers(dest="radar_domain", required=True)

    radar_status_parser = radar_sub.add_parser("status", help="Query radar status")
    add_transport_args(radar_status_parser)
    radar_status_parser.set_defaults(func=cmd_radar_status)

    radar_start_parser = radar_sub.add_parser("start", help="Start or restart radar service")
    radar_start_parser.add_argument("--mode", choices=["auto", "host"], default=None,
                                    help="Persist start mode, then start/restart radar service in that mode")
    add_transport_args(radar_start_parser)
    radar_start_parser.set_defaults(func=cmd_radar_start)

    radar_stop_parser = radar_sub.add_parser("stop", help="Stop radar service")
    add_transport_args(radar_stop_parser)
    radar_stop_parser.set_defaults(func=cmd_radar_stop)

    radar_config_parser = radar_sub.add_parser("config", help="Read or apply radar runtime configuration")
    radar_config_sub = radar_config_parser.add_subparsers(dest="radar_config_action", required=True)

    cfg_parser = radar_config_sub.add_parser("read", help="Read current radar cfg text")
    cfg_parser.add_argument("--gen", action="store_true",
                            help="Read runtime-generated cfg text instead of file cfg")
    add_transport_args(cfg_parser)
    cfg_parser.set_defaults(func=cmd_radar_cfg)

    reconf_parser = radar_config_sub.add_parser("apply", help="Apply runtime radar configuration without flashing firmware")
    reconf_cfg_group = reconf_parser.add_mutually_exclusive_group()
    reconf_cfg_group.add_argument("--cfg", help="Runtime config file path to stage and apply")
    reconf_cfg_group.add_argument("--clear-cfg", action="store_true",
                                  help="Clear the staged runtime cfg override")
    reconf_parser.add_argument("--chunk-size", type=int, default=None,
                               help="Chunk size for runtime cfg transfer (default: 256 UART / 512 MQTT)")
    reconf_parser.add_argument("--mqtt-delay", type=float, default=0.0,
                               help="Inter-chunk delay seconds for MQTT transport (default: transport-dependent)")
    reconf_parser.add_argument("--version", help="Expected version substring when --verify is enabled")
    reconf_verify_group = reconf_parser.add_mutually_exclusive_group()
    reconf_verify_group.add_argument("--verify", dest="verify", action="store_true", default=False,
                                     help="Require startup output to contain the expected version substring")
    reconf_verify_group.add_argument("--no-verify", dest="verify", action="store_false",
                                     help="Skip runtime version verification")
    reconf_welcome_group = reconf_parser.add_mutually_exclusive_group(required=True)
    reconf_welcome_group.add_argument("--welcome", dest="welcome", action="store_true",
                                      help="Expect welcome/startup output on the next boot")
    reconf_welcome_group.add_argument("--no-welcome", dest="welcome", action="store_false",
                                      help="Do not expect welcome/startup output on the next boot")
    reconf_parser.add_argument("--reconf-timeout", type=float, default=90.0,
                               help="Seconds to wait for radar to return to running (default: 90)")
    add_transport_args(reconf_parser)
    reconf_parser.set_defaults(func=cmd_radar_reconf)

    radar_fw_parser = radar_sub.add_parser("fw", help="Manage radar firmware lifecycle and slots")
    radar_fw_sub = radar_fw_parser.add_subparsers(dest="firmware_action", required=True)

    flash_parser = radar_fw_sub.add_parser("flash", help="Flash firmware via UART/MQTT (chunk transfer)")
    flash_parser.add_argument("--fw", required=True, help="Firmware binary file path")
    flash_parser.add_argument("--cfg", help="Config file path (optional)")
    flash_parser.add_argument("--chunk-size", type=int, default=None,
                              help="Transfer chunk size in bytes (default: 256 UART, 512 MQTT)")
    flash_parser.add_argument("--mqtt-delay", type=float, default=0.05,
                              help="Inter-chunk delay for MQTT in seconds (default: 0.05)")
    flash_parser.add_argument("--progress-interval", type=int, default=5,
                              help="How often (seconds) device reports flash progress (default: 5, 0=disable)")
    flash_parser.add_argument("--reboot-delay", type=int, default=5,
                              help="Seconds to wait after flash success before rebooting ESP (default: 5, 0=disable)")
    flash_parser.add_argument("--version", help="Firmware version string used for optional verification")
    flash_verify_group = flash_parser.add_mutually_exclusive_group()
    flash_verify_group.add_argument("--verify", dest="verify", action="store_true", default=None,
                                    help="Require the welcome text to contain the expected version string")
    flash_verify_group.add_argument("--no-verify", dest="verify", action="store_false",
                                    help="Skip version matching even if metadata provides a version")
    flash_welcome_group = flash_parser.add_mutually_exclusive_group()
    flash_welcome_group.add_argument("--welcome", dest="welcome", action="store_true", default=None,
                                     help="Expect this firmware to emit a welcome/startup banner")
    flash_welcome_group.add_argument("--no-welcome", dest="welcome", action="store_false",
                                     help="Declare that this firmware does not emit a welcome/startup banner")
    add_transport_args(flash_parser)
    flash_parser.set_defaults(func=cmd_radar_flash)

    ota_parser = radar_fw_sub.add_parser("ota", help="Flash firmware via HTTP or MQTT stream OTA")
    ota_parser.add_argument("--fw", required=True, help="Firmware binary file path")
    ota_parser.add_argument("--cfg", help="Config file path (optional)")
    ota_parser.add_argument("--http-port", type=int, default=8380,
                            help="Local HTTP server port (default: 8380)")
    ota_parser.add_argument("--base-url", help="External base URL (skip local HTTP server)")
    ota_parser.add_argument("--version", help="Firmware version string used for optional verification")
    ota_verify_group = ota_parser.add_mutually_exclusive_group()
    ota_verify_group.add_argument("--verify", dest="verify", action="store_true", default=None,
                                  help="Require the welcome text to contain the expected version string")
    ota_verify_group.add_argument("--no-verify", dest="verify", action="store_false",
                                  help="Skip version matching even if metadata provides a version")
    ota_welcome_group = ota_parser.add_mutually_exclusive_group()
    ota_welcome_group.add_argument("--welcome", dest="welcome", action="store_true", default=None,
                                   help="Expect this firmware to emit a welcome/startup banner")
    ota_welcome_group.add_argument("--no-welcome", dest="welcome", action="store_false",
                                   help="Declare that this firmware does not emit a welcome/startup banner")
    ota_parser.add_argument("--ota-timeout", type=float, default=300.0,
                            help="OTA timeout in seconds (default: 300)")
    ota_parser.add_argument("--force", action="store_true",
                            help="Force OTA even when the target version already matches")
    ota_parser.add_argument("--progress-interval", type=int, default=5,
                            help="How often (seconds) device reports flash progress (default: 5, 0=disable)")
    ota_parser.add_argument(
        "--raw-resp-output",
        help="Capture startup-trimmed command-port response text during OTA to this file (armed before OTA command)",
    )
    ota_parser.add_argument(
        "--raw-broker",
        help="MQTT broker URI/host override for OTA raw_resp capture (defaults to radar raw/node info)",
    )
    ota_parser.add_argument(
        "--raw-resp",
        dest="raw_resp",
        help="MQTT raw_resp topic override for OTA capture (defaults to radar raw/node info)",
    )
    ota_parser.add_argument(
        "--raw-timeout",
        type=float,
        default=10.0,
        help="MQTT subscribe-ready timeout for OTA raw_resp capture in seconds (default: 10)",
    )
    add_ota_transport_arg(ota_parser)
    add_transport_args(ota_parser)
    ota_parser.set_defaults(func=cmd_radar_ota)

    version_parser = radar_fw_sub.add_parser("version", help="Query running firmware version")
    add_transport_args(version_parser)
    version_parser.set_defaults(func=cmd_radar_version)

    fw_list_parser = radar_fw_sub.add_parser("list", help="List firmware images")
    add_transport_args(fw_list_parser)
    fw_list_parser.set_defaults(func=cmd_fw_list)

    fw_set_parser = radar_fw_sub.add_parser("set", help="Set default boot firmware partition")
    fw_set_parser.add_argument("--index", type=int, required=True, help="Partition index")
    add_transport_args(fw_set_parser)
    fw_set_parser.set_defaults(func=cmd_fw_set)

    fw_switch_parser = radar_fw_sub.add_parser("switch", help="Switch the running firmware image immediately")
    fw_switch_parser.add_argument("--index", type=int, required=True, help="Partition index")
    fw_switch_parser.add_argument("--persist", action="store_true",
                                  help="Also persist the selected firmware as the default boot image")
    add_transport_args(fw_switch_parser)
    fw_switch_parser.set_defaults(func=cmd_radar_fw_switch)

    fw_del_parser = radar_fw_sub.add_parser("del", help="Delete a firmware partition")
    fw_del_parser.add_argument("--index", type=int, required=True, help="Partition index")
    add_transport_args(fw_del_parser)
    fw_del_parser.set_defaults(func=cmd_fw_del)

    fw_dl_parser = radar_fw_sub.add_parser("download", help="Download firmware image to device")
    fw_dl_parser.add_argument("--source", required=True, help="Download source URL")
    fw_dl_parser.add_argument("--name", required=True, help="Firmware name")
    fw_dl_parser.add_argument("--fw-version", required=True, help="Firmware version")
    fw_dl_parser.add_argument("--size", type=int, required=True, help="File size in bytes")
    add_transport_args(fw_dl_parser)
    fw_dl_parser.set_defaults(func=cmd_fw_download)

    # radar raw route
    radar_raw_parser = radar_sub.add_parser(
        "raw",
        help="Inspect or change the raw radar route",
    )
    radar_raw_sub = radar_raw_parser.add_subparsers(dest="raw_action", required=True)

    radar_raw_status_parser = radar_raw_sub.add_parser("status", help="Show raw route status")
    add_transport_args(radar_raw_status_parser)
    radar_raw_status_parser.set_defaults(func=cmd_radar_raw)

    for raw_mode, mode_help in (
        ("runtime", "Open a raw route for the current radar service"),
        ("reconnect", "Arm one-shot auto-mode MQTT DATA after reconnect"),
        ("off", "Close a selected raw route"),
    ):
        raw_mode_parser = radar_raw_sub.add_parser(raw_mode, help=mode_help)
        raw_mode_parser.add_argument(
            "--channel",
            choices=["wire", "mqtt", "both"],
            help="Raw route shorthand for command and data paths",
        )
        raw_mode_parser.add_argument(
            "--ctrl",
            choices=["wire", "mqtt", "both"],
            help="Raw command/response route (runtime host only)",
        )
        raw_mode_parser.add_argument(
            "--data",
            choices=["wire", "mqtt", "both"],
            help="Raw radar-data route (runtime host only)",
        )
        raw_mode_parser.add_argument(
            "--baud",
            type=int,
            help="Wire raw data baud (maximum 1000000; default 1000000)",
        )
        raw_mode_parser.add_argument(
            "--escape",
            help="Wire host escape sequence (default +++; guarded by one second idle windows)",
        )
        add_transport_args(raw_mode_parser)
        raw_mode_parser.set_defaults(func=cmd_radar_raw)

    # radar record
    radar_record_parser = radar_sub.add_parser(
        "record",
        help="Start, stop, or trigger a radar recording",
    )
    radar_record_sub = radar_record_parser.add_subparsers(dest="record_action", required=True)

    radar_record_status_parser = radar_record_sub.add_parser("status", help="Show recorder state")
    add_transport_args(radar_record_status_parser)
    radar_record_status_parser.set_defaults(func=cmd_radar_record)

    radar_record_config_parser = radar_record_sub.add_parser("config", help="Read or write recorder config")
    radar_record_config_sub = radar_record_config_parser.add_subparsers(
        dest="record_config_action", required=True
    )
    radar_record_config_get_parser = radar_record_config_sub.add_parser("get", help="Read recorder config")
    add_transport_args(radar_record_config_get_parser)
    radar_record_config_get_parser.set_defaults(record_action="config_get", func=cmd_radar_record)

    radar_record_config_set_parser = radar_record_config_sub.add_parser("set", help="Write recorder config")
    radar_record_config_set_parser.add_argument(
        "--json",
        required=True,
        help="JSON object string, @file, or file path containing the record config",
    )
    add_transport_args(radar_record_config_set_parser)
    radar_record_config_set_parser.set_defaults(record_action="config_set", func=cmd_radar_record)

    radar_record_start_parser = radar_record_sub.add_parser("start", help="Start the recorder")
    radar_record_start_parser.add_argument("--uri", help="Upload target URI override")
    add_transport_args(radar_record_start_parser)
    radar_record_start_parser.set_defaults(func=cmd_radar_record)

    radar_record_stop_parser = radar_record_sub.add_parser("stop", help="Stop the recorder")
    add_transport_args(radar_record_stop_parser)
    radar_record_stop_parser.set_defaults(func=cmd_radar_record)

    radar_record_trigger_parser = radar_record_sub.add_parser("trigger", help="Trigger a recording window")
    radar_record_trigger_parser.add_argument("--event", help="Trigger event name (default: manual)")
    radar_record_trigger_parser.add_argument("--duration-s", dest="duration_s", type=int,
                                              help="Recording duration in seconds")
    add_transport_args(radar_record_trigger_parser)
    radar_record_trigger_parser.set_defaults(func=cmd_radar_record)

    # radar diag
    diag_parser = radar_sub.add_parser("diag", help="Manage/query radar diagnostics")
    diag_parser.add_argument("op", nargs="?", choices=["set", "get", "snapshot", "reset"], default="snapshot",
                             help="Diagnostic operation (default: snapshot)")
    diag_parser.add_argument("--packets", choices=["on", "off"],
                             help="Enable/disable packet counters (set only)")
    diag_parser.add_argument("--frames", choices=["on", "off"],
                             help="Enable/disable frame counters (set only)")
    add_transport_args(diag_parser)
    diag_parser.set_defaults(func=cmd_radar_debug)

    # -- node --
    node_parser = subparsers.add_parser("node", help="Node management surface")
    node_sub = node_parser.add_subparsers(dest="action", required=True)

    node_info_parser = node_sub.add_parser("info", help="Node status handshake")
    add_transport_args(node_info_parser)
    node_info_parser.set_defaults(func=cmd_node_info)

    node_factory_reset_parser = node_sub.add_parser(
        "factory-reset", help="Trigger factory reset and reboot"
    )
    add_transport_args(node_factory_reset_parser)
    node_factory_reset_parser.set_defaults(func=cmd_node_factory_reset)

    node_claim_parser = node_sub.add_parser("claim", help="Claim route identity and credentials")
    node_claim_parser.add_argument("--prod", default="mmwk",
                                   help="Product route segment to store (default: mmwk)")
    node_claim_parser.add_argument("--oid", default="mmwk",
                                   help="Organization route segment to store (default: mmwk)")
    node_claim_parser.add_argument("--cid", default="",
                                   help="Claimed device route segment to store")
    node_claim_parser.add_argument("--endpoint", help="Claim endpoint override for this attempt")
    node_claim_parser.add_argument("--token", help="One-time claim token for this attempt")
    add_transport_args(node_claim_parser, include_route_args=False)
    node_claim_parser.set_defaults(func=cmd_node_claim)

    node_key_parser = node_sub.add_parser("key", help="Manage CLI protection key")
    node_key_sub = node_key_parser.add_subparsers(dest="key_action", required=True)

    node_key_status_parser = node_key_sub.add_parser("status", help="Show CLI key protection status")
    add_transport_args(node_key_status_parser)
    node_key_status_parser.set_defaults(func=cmd_node_key)

    node_key_set_parser = node_key_sub.add_parser("set", help="Set or update CLI protection key")
    node_key_set_parser.add_argument("--new-key", required=True,
                                     help="New CLI protection key")
    add_transport_args(node_key_set_parser)
    node_key_set_parser.set_defaults(func=cmd_node_key)

    node_key_clear_parser = node_key_sub.add_parser("clear", help="Clear CLI protection key")
    add_transport_args(node_key_clear_parser)
    node_key_clear_parser.set_defaults(func=cmd_node_key)

    device_reboot_parser = node_sub.add_parser("reboot", help="Reboot the node")
    add_transport_args(device_reboot_parser)
    device_reboot_parser.set_defaults(func=cmd_node_reboot)

    device_ota_parser = node_sub.add_parser("ota", help="Update ESP or radar firmware")
    device_ota_parser.add_argument("--target", choices=["esp", "radar"], default="esp",
                                   help="OTA target (default: esp)")
    device_ota_src = device_ota_parser.add_mutually_exclusive_group(required=True)
    device_ota_src.add_argument("--fw", help="Local OTA firmware path")
    device_ota_src.add_argument("--url", help="Remote ESP OTA URL (only with --target esp)")
    device_ota_parser.add_argument("--cfg", help="Radar config file path when --target radar")
    device_ota_parser.add_argument("--http-port", type=int, default=8380,
                                   help="Local HTTP server port for OTA (default: 8380)")
    device_ota_parser.add_argument("--https", action="store_true",
                                   help="Serve local OTA artifact over HTTPS (requires --https-cert and --https-key)")
    device_ota_parser.add_argument("--https-cert",
                                   help="Path to local HTTPS certificate PEM")
    device_ota_parser.add_argument("--https-key",
                                   help="Path to local HTTPS private key PEM")
    device_ota_parser.add_argument("--version", help="Radar firmware version string used for optional verification")
    device_ota_verify_group = device_ota_parser.add_mutually_exclusive_group()
    device_ota_verify_group.add_argument("--verify", dest="verify", action="store_true", default=None,
                                         help="Require radar welcome text to contain the expected version")
    device_ota_verify_group.add_argument("--no-verify", dest="verify", action="store_false",
                                         help="Skip radar version matching even if metadata provides a version")
    device_ota_welcome_group = device_ota_parser.add_mutually_exclusive_group()
    device_ota_welcome_group.add_argument("--welcome", dest="welcome", action="store_true", default=None,
                                          help="Expect radar welcome/startup output")
    device_ota_welcome_group.add_argument("--no-welcome", dest="welcome", action="store_false",
                                          help="Declare that radar firmware does not emit a welcome banner")
    device_ota_parser.add_argument("--force", action="store_true",
                                   help="Force radar OTA even when the target version already matches")
    device_ota_parser.add_argument("--progress-interval", type=int, default=None,
                                   help="Radar flash progress interval seconds (default: 5, 0=disable)")
    device_ota_parser.add_argument("--ota-timeout", type=float, default=300.0,
                                   help="OTA timeout in seconds (default: 300)")
    add_ota_transport_arg(device_ota_parser)
    add_transport_args(device_ota_parser)
    device_ota_parser.set_defaults(func=cmd_device_ota)

    device_agent_parser = node_sub.add_parser(
        "agent",
        help="Configure built-in agents and WDR local-control startup policy",
    )
    device_agent_parser.add_argument("--mqtt", type=int, choices=[0, 1], default=None,
                                     help="MQTT agent enable (0=off, 1=on)")
    device_agent_parser.add_argument("--uart", type=int, choices=[0, 1], default=None,
                                     help="UART agent enable (0=off, 1=on)")
    device_agent_parser.add_argument("--uart-split", dest="uart_split", type=int, choices=[0, 1], default=None,
                                     help="Split single-UART runtime data after sensorStart (0=off, 1=on)")
    device_agent_parser.add_argument("--led", type=int, choices=[0, 1], default=None,
                                     help="LED error display enable (0=off, 1=on)")
    device_agent_parser.add_argument("--reboot-ms", dest="reboot_ms", type=int, default=None,
                                     help="Reboot threshold when MQTT stays disconnected")
    device_agent_parser.add_argument(
        "--usb-ms",
        dest="usb_ms",
        type=_usb_ms_arg,
        default=None,
        help="WDR/WSR UART idle window before USB CDC takeover (0=stay on UART, max 60000)",
    )
    add_transport_args(device_agent_parser)
    device_agent_parser.set_defaults(func=cmd_device_agent)

    device_hb_parser = node_sub.add_parser("heartbeat", help="Configure system heartbeat")
    device_hb_parser.add_argument("--interval", type=int, required=True,
                                  help="Heartbeat period in seconds (0=disable, min 30)")
    device_hb_parser.add_argument("--fields", nargs="+",
                                  help="Payload fields (e.g. rssi heap uptime)")
    add_transport_args(device_hb_parser)
    device_hb_parser.set_defaults(func=cmd_device_heartbeat)

    proto_parser = subparsers.add_parser("proto", help="Inspect node public protocol directory")
    proto_sub = proto_parser.add_subparsers(dest="proto_action", required=True)

    proto_list_parser = proto_sub.add_parser("list", help="List node public protocol directory entries")
    add_transport_args(proto_list_parser)
    proto_list_parser.set_defaults(func=cmd_device_proto)

    proto_status_parser = proto_sub.add_parser("status", help="Show public protocol directory status")
    proto_status_parser.add_argument("name", help="Public protocol directory entry to inspect")
    add_transport_args(proto_status_parser)
    proto_status_parser.set_defaults(func=cmd_device_proto)

    proto_manifest_parser = proto_sub.add_parser("manifest", help="Show public protocol manifest")
    proto_manifest_parser.add_argument("name", help="Public protocol directory entry to inspect")
    add_transport_args(proto_manifest_parser)
    proto_manifest_parser.set_defaults(func=cmd_device_proto)

    # -- collect --
    collect_parser = subparsers.add_parser(
        "collect",
        help="Collect radar raw DATA through local host UART/USB, MQTT, or split routes",
    )
    collect_parser.add_argument("--duration", type=int, default=10,
                                help="Collection time in seconds (default: 10)")
    collect_parser.add_argument("--transport", choices=["uart", "usb", "mqtt"], default="uart",
                                help="Control/data transport (default: uart; local host collection)")
    collect_parser.add_argument("--mode", choices=["host", "auto"], default="host",
                                help="Radar ownership mode (default: host)")
    collect_parser.add_argument("--raw-baud", type=int, default=None,
                                help="Local UART raw DATA baud (max 1000000; USB rejects this option)")
    collect_parser.add_argument("--escape", default="+++",
                                help="Wire raw escape sequence (1-16 printable characters; default: +++)")
    collect_parser.add_argument("--cfg", help="Radar cfg file for a local host collection")
    collect_parser.add_argument("--attach", action="store_true",
                                help=("Borrow an existing radar lifecycle without reconfiguring it; "
                                      "auto mode requires an active MQTT DATA route"))
    collect_parser.add_argument("--ctrl-transport", choices=["uart", "usb", "mqtt"],
                                help="Split-session command transport (requires --data-transport)")
    collect_parser.add_argument("--data-transport", choices=["uart", "usb", "mqtt"],
                                help="Split-session DATA transport (requires --ctrl-transport)")
    collect_parser.add_argument("--allow-lossy", action="store_true",
                                help="Allow explicitly lossy local UART capture (never claims lossless output)")
    collect_parser.add_argument("--wire-output",
                                help="Optional complete merged raw-wire audit output")
    collect_parser.add_argument("--events-output",
                                help="Optional JSON-lines phase and cleanup event log")
    collect_parser.add_argument("--overwrite", action="store_true",
                                help="Atomically replace existing collection outputs")
    collect_parser.add_argument("--summary-output",
                                help="Optional JSON summary output path")
    collect_parser.add_argument("--protocol", choices=["mcp", "cli"],
                                help="Control protocol for optional device discovery (default: cli)")
    collect_parser.add_argument(
        "--data-output",
        default=None,
        help=("Output file for validated radar DATA bytes; MQTT and split routes are DATA-only "
              "(default: collections/<did>/<timestamp>/radar.sraw)"),
    )
    collect_parser.add_argument(
        "--resp-output",
        default=None,
        help=("Output file for parsed setup/close acknowledgements in local host mode, "
              "or MQTT raw/resp payloads in remote host mode "
              "(default: collections/<did>/<timestamp>/commands.log)"),
    )
    collect_parser.add_argument(
        "--resp-optional",
        action="store_true",
        help=(
            "Compatibility flag accepted only with --attach; borrowed auto DATA never requires "
            "a raw/resp topic"
        ),
    )
    collect_parser.add_argument("--broker",
                                help="MQTT broker URI/host for collection (e.g. mqtt://127.0.0.1:1883)")
    collect_parser.add_argument("--mqtt-port", type=int, default=1883,
                                help="MQTT broker port (default: 1883)")
    collect_parser.add_argument("--mqtt-user",
                                help="MQTT username (defaults to broker URI/device profile)")
    collect_parser.add_argument("--mqtt-password",
                                help="MQTT password (never written to summaries or event logs)")
    collect_parser.add_argument("--mqtt-ca",
                                help="CA certificate path for mqtts:// broker verification")
    collect_parser.add_argument("--did",
                                help="DID for MQTT route fallback")
    collect_parser.add_argument("--prod", default="mmwk",
                                help="MQTT product route segment (default: mmwk)")
    collect_parser.add_argument("--oid", default="mmwk",
                                help="MQTT organization route segment (default: mmwk)")
    collect_parser.add_argument("--cid", default="",
                                help="MQTT claimed route id; when set it takes precedence over --did")
    collect_parser.add_argument("--data-topic",
                                help="MQTT raw/data topic to subscribe (DATA bytes only)")
    collect_parser.add_argument("--resp-topic",
                                help="MQTT raw/resp topic to subscribe (host command-port output)")
    collect_parser.add_argument("--port", "-p",
                                help="Optional UART serial port for auto-discovery via node info")
    collect_parser.add_argument("--baudrate", "-b", type=int, default=115200,
                                help="UART baudrate when --port is used (default: 115200)")
    collect_parser.add_argument("--reset", action="store_true",
                                help="Reset device before auto-discovery when --port is used")
    collect_parser.add_argument("--timeout", type=float, default=10.0,
                                help="Timeout for auto-discovery in seconds (default: 10)")
    collect_parser.add_argument("--data-ready-timeout", type=float, default=10.0,
                                help="Seconds to wait for the first radar DATA frame (default: 10)")
    collect_parser.add_argument("-v", "--verbose", action="store_true",
                                help="Enable debug logging")
    collect_parser.set_defaults(func=cmd_collect, transport=None)

    # -- endpoint --
    endpoint_parser = subparsers.add_parser("endpoint", help="Matter-oriented endpoint discovery, state, and config inspection")
    endpoint_sub = endpoint_parser.add_subparsers(dest="action", required=True)

    endpoint_list_parser = endpoint_sub.add_parser("list", help="List active endpoint ids")
    endpoint_list_parser.add_argument("--json", action="store_true",
                                      help="Print full catalog JSON instead of endpoint ids")
    add_transport_args(endpoint_list_parser)
    endpoint_list_parser.set_defaults(func=cmd_endpoint_list)

    endpoint_describe_parser = endpoint_sub.add_parser("describe", help="Describe an endpoint")
    endpoint_describe_parser.add_argument("id", help="Endpoint id, e.g. mgmt.device")
    add_transport_args(endpoint_describe_parser)
    endpoint_describe_parser.set_defaults(func=cmd_endpoint_describe)

    endpoint_read_parser = endpoint_sub.add_parser("read", help="Read endpoint state")
    endpoint_read_parser.add_argument("id", help="Endpoint id, e.g. mgmt.device")
    add_transport_args(endpoint_read_parser)
    endpoint_read_parser.set_defaults(func=cmd_endpoint_read)

    endpoint_config_parser = endpoint_sub.add_parser("config", help="Read or write endpoint config")
    endpoint_config_sub = endpoint_config_parser.add_subparsers(dest="config_action", required=True)

    endpoint_config_get_parser = endpoint_config_sub.add_parser("get", help="Read endpoint config")
    endpoint_config_get_parser.add_argument("id", help="Endpoint id, e.g. radar.record")
    add_transport_args(endpoint_config_get_parser)
    endpoint_config_get_parser.set_defaults(func=cmd_endpoint_config_get)

    endpoint_config_set_parser = endpoint_config_sub.add_parser("set", help="Write endpoint config")
    endpoint_config_set_parser.add_argument("id", help="Endpoint id, e.g. radar.record")
    endpoint_config_set_parser.add_argument(
        "--config-json",
        required=True,
        help="JSON object string, @file, or file path containing the config patch",
    )
    add_transport_args(endpoint_config_set_parser)
    endpoint_config_set_parser.set_defaults(func=cmd_endpoint_config_set)

    # -- scene --
    scene_parser = subparsers.add_parser("scene", help="Scene orchestration and config management")
    scene_sub = scene_parser.add_subparsers(dest="action", required=True)

    scene_read_parser = scene_sub.add_parser("read", help="Show active scene config")
    add_transport_args(scene_read_parser)
    scene_read_parser.set_defaults(func=cmd_scene_show)

    scene_set_parser = scene_sub.add_parser("set", help="Apply a scene.v1.config patch")
    scene_set_parser.add_argument(
        "--config-json",
        required=True,
        help="JSON object string, @file, or file path containing the scene config patch",
    )
    add_transport_args(scene_set_parser)
    scene_set_parser.set_defaults(func=cmd_scene_set)

    scene_apply_parser = scene_sub.add_parser("apply", help="Apply the current scene and restart radar if needed")
    add_transport_args(scene_apply_parser)
    scene_apply_parser.set_defaults(func=cmd_scene_apply)

    scene_wait_parser = scene_sub.add_parser("wait", help="Wait until radar is ready after scene apply")
    scene_wait_parser.add_argument("--timeout-ms", type=int, default=30000,
                                   help="Timeout in milliseconds (default: 30000)")
    scene_wait_parser.add_argument("--interval-ms", type=int, default=500,
                                   help="Polling interval in milliseconds (default: 500)")
    add_transport_args(scene_wait_parser)
    scene_wait_parser.set_defaults(func=cmd_scene_wait_ready)

    # -- network --
    net_parser = subparsers.add_parser("network", help="Network configuration")
    net_sub = net_parser.add_subparsers(dest="action", required=True)

    # network mqtt
    net_mqtt = net_sub.add_parser("mqtt", help="Get/Set MQTT configuration")
    net_mqtt.add_argument("--uri", help="Set MQTT Broker URI")
    net_mqtt.add_argument("--user", help="Set MQTT Username")
    net_mqtt.add_argument("--pass", dest="passphrase", help="Set MQTT Password")
    add_transport_args(net_mqtt)
    net_mqtt.set_defaults(func=cmd_network)

    # network wifi
    net_wifi = net_sub.add_parser("wifi", help="Set Wi-Fi credentials")
    net_wifi.add_argument("--ssid", required=True, help="Wi-Fi SSID")
    net_wifi.add_argument("--pass", dest="passphrase", required=True, help="Wi-Fi Password")
    add_transport_args(net_wifi)
    net_wifi.set_defaults(func=cmd_network)

    # network 4g
    net_4g = net_sub.add_parser("4g", help="Get/Set 4G configuration")
    net_4g.add_argument("--apn", help="Set 4G APN")
    net_4g.add_argument("--user", help="Set 4G username")
    net_4g.add_argument("--pass", dest="passphrase", help="Set 4G password")
    add_transport_args(net_4g)
    net_4g.set_defaults(func=cmd_network)

    # network priority
    net_priority = net_sub.add_parser("priority", help="Get/Set preferred network: wifi or 4g")
    net_priority.add_argument("--pref", choices=["wifi", "4g"], help="Preferred network")
    add_transport_args(net_priority)
    net_priority.set_defaults(func=cmd_network)

    # network prov
    net_prov = net_sub.add_parser("prov", help="Control Wi-Fi provisioning")
    net_prov_grp = net_prov.add_mutually_exclusive_group(required=True)
    net_prov_grp.add_argument("--enable", action="store_true", help="Enable provisioning mode")
    net_prov_grp.add_argument("--disable", action="store_true", help="Disable provisioning mode")
    add_transport_args(net_prov)
    net_prov.set_defaults(func=cmd_network)

    # network status
    net_status = net_sub.add_parser("status", help="Query network runtime status")
    add_transport_args(net_status)
    net_status.set_defaults(func=cmd_network)

    # network diag
    net_diag = net_sub.add_parser("diag", help="Query network diagnostics")
    add_transport_args(net_diag)
    net_diag.set_defaults(func=cmd_network)

    # network ntp
    net_ntp = net_sub.add_parser("ntp", help="Configure NTP time sync")
    net_ntp.add_argument("--server", help="NTP server address")
    net_ntp.add_argument("--tz-offset", type=int, help="Timezone offset from UTC in seconds")
    net_ntp.add_argument("--ntp-interval", type=int, help="NTP polling interval in seconds")
    add_transport_args(net_ntp)
    net_ntp.set_defaults(func=cmd_network)

    args = parser.parse_args()
    _finalize_protocol_args(args)

    if hasattr(args, 'verbose') and args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not hasattr(args, 'func'):
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except TimeoutError as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
