"""CLI entry point for mmwk."""

import sys
import json
import logging
import argparse
import os

from mmwk._logging import logger
from mmwk.transport import create_transport
from mmwk.protocol_client import create_protocol_client
from mmwk.commands.flash import FlashCommand
from mmwk.commands.ota import OtaCommand
from mmwk.commands.reconf import ReconfCommand
from mmwk.commands.device_ota import DeviceOtaCommand
from mmwk.commands.collect import CollectCommand
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
        return create_transport(args, retries=retries, retry_delay=retry_delay)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)


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


def add_transport_args(parser):
    """Add common transport arguments to a parser."""
    group = parser.add_argument_group("Transport")
    group.add_argument("--protocol", choices=["mcp", "cli"],
                       help="Control protocol (default: cli; use mcp as fallback)")
    group.add_argument("--transport", "-t", default="uart",
                       choices=["uart", "mqtt"], help="Transport layer (default: uart)")
    group.add_argument("--port", "-p", help="Serial port (for UART, e.g. /dev/ttyUSB0)")
    group.add_argument("--baudrate", "-b", type=int, default=115200,
                       help="Serial baudrate (default: 115200)")
    group.add_argument("--reset", action="store_true",
                       help="Reset device via DTR/RTS before connecting")
    group.add_argument("--uart-proxy", choices=["auto", "off"], default=None,
                       help="Use persistent local UART proxy for short CLI calls (default: auto; env MMWK_CLI_UART_PROXY_MODE)")
    group.add_argument("--broker", default="localhost",
                       help="MQTT broker address (default: localhost)")
    group.add_argument("--mqtt-port", type=int, default=1883,
                       help="MQTT broker port (default: 1883)")
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


def cmd_radar_flash(args):
    """Handle: mmwk radar flash ..."""
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
    if getattr(args, "transport", "uart") != "uart":
        print("Error: node claim is only supported over UART/local transport")
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

        ota = DeviceOtaCommand(mcp)
        ok = ota.execute(
            fw_path=args.fw,
            url=args.url,
            http_port=args.http_port,
            use_https=args.https,
            https_cert=args.https_cert,
            https_key=args.https_key,
            timeout=args.ota_timeout,
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
        if args.raw_auto is not None:
            dev_args["raw_auto"] = args.raw_auto
        if getattr(args, "uart_split", None) is not None:
            dev_args["uart_split"] = args.uart_split
        if getattr(args, "led", None) is not None:
            dev_args["led"] = args.led
        if getattr(args, "reboot_ms", None) is not None:
            dev_args["reboot_ms"] = args.reboot_ms

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


def cmd_record(args):
    """Handle: mmwk record ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        rec_args = {"action": args.action}
        if args.action == "start" and getattr(args, 'uri', None):
            rec_args["uri"] = args.uri
        elif args.action == "trigger":
            if getattr(args, 'event', None):
                rec_args["event"] = args.event
            if getattr(args, 'duration', None) is not None:
                rec_args["duration_sec"] = args.duration

        result = mcp.call_tool("record", rec_args, timeout=args.timeout)
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
    payload = {}
    if args.raw_group == "status":
        payload = {"action": "status"}
    elif args.raw_group == "config":
        if args.raw_config_action == "get":
            payload = {"action": "config_get"}
        else:
            payload = {
                "action": "config_set",
                "config": _load_json_object_arg(args.json),
            }
    elif args.raw_group == "start":
        payload = {"action": "start"}
        if getattr(args, "uri", None):
            payload["uri"] = args.uri
    elif args.raw_group == "stop":
        payload = {"action": "stop"}
    elif args.raw_group == "trigger":
        payload = {"action": "trigger"}
        if getattr(args, "event", None):
            payload["event"] = args.event
        if getattr(args, "duration_s", None) is not None:
            payload["duration_s"] = args.duration_s

    _call_tool_and_print_json(args, "radar.raw", payload)


def cmd_collect(args):
    """Handle: mmwk collect ..."""
    transport = None
    mcp = None

    try:
        if args.port:
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
            timeout=args.timeout,
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

    ota_parser = radar_fw_sub.add_parser("ota", help="Flash firmware via HTTP OTA (device downloads)")
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
    ota_parser.add_argument("--ota-timeout", type=float, default=120.0,
                            help="OTA timeout in seconds (default: 120)")
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

    # radar raw
    radar_raw_parser = radar_sub.add_parser("raw", help="Inspect raw recorder state, config, and recorder lifecycle")
    radar_raw_sub = radar_raw_parser.add_subparsers(dest="raw_group", required=True)

    radar_raw_status_parser = radar_raw_sub.add_parser("status", help="Show radar raw recorder status")
    add_transport_args(radar_raw_status_parser)
    radar_raw_status_parser.set_defaults(func=cmd_radar_raw)

    radar_raw_config_parser = radar_raw_sub.add_parser("config", help="Get or update radar raw config")
    radar_raw_config_sub = radar_raw_config_parser.add_subparsers(dest="raw_config_action", required=True)

    radar_raw_config_get_parser = radar_raw_config_sub.add_parser("get", help="Read radar raw config")
    add_transport_args(radar_raw_config_get_parser)
    radar_raw_config_get_parser.set_defaults(func=cmd_radar_raw)

    radar_raw_config_set_parser = radar_raw_config_sub.add_parser("set", help="Write radar raw config")
    radar_raw_config_set_parser.add_argument(
        "--json",
        required=True,
        help="JSON object string, @file, or file path containing the raw config patch",
    )
    add_transport_args(radar_raw_config_set_parser)
    radar_raw_config_set_parser.set_defaults(func=cmd_radar_raw)

    radar_raw_start_parser = radar_raw_sub.add_parser("start", help="Arm the raw recorder")
    radar_raw_start_parser.add_argument("--uri", help="Upload target URI override")
    add_transport_args(radar_raw_start_parser)
    radar_raw_start_parser.set_defaults(func=cmd_radar_raw)

    radar_raw_stop_parser = radar_raw_sub.add_parser("stop", help="Stop the raw recorder")
    add_transport_args(radar_raw_stop_parser)
    radar_raw_stop_parser.set_defaults(func=cmd_radar_raw)

    radar_raw_trigger_parser = radar_raw_sub.add_parser("trigger", help="Trigger a raw recording window")
    radar_raw_trigger_parser.add_argument("--event", help="Trigger event name (default: manual)")
    radar_raw_trigger_parser.add_argument("--duration-s", dest="duration_s", type=int,
                                          help="Recording duration in seconds (defaults to radar.raw config)")
    add_transport_args(radar_raw_trigger_parser)
    radar_raw_trigger_parser.set_defaults(func=cmd_radar_raw)

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
    node_claim_parser.add_argument("--endpoint", help="Claim endpoint override for this attempt")
    node_claim_parser.add_argument("--token", help="One-time claim token for this attempt")
    add_transport_args(node_claim_parser)
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

    device_ota_parser = node_sub.add_parser("ota", help="Update ESP firmware via HTTP OTA (.bin only, supports full app+assets bundle)")
    device_ota_src = device_ota_parser.add_mutually_exclusive_group(required=True)
    device_ota_src.add_argument("--fw", help="Local ESP OTA .bin path (plain app image or *_full.bin bundle)")
    device_ota_src.add_argument("--url", help="Remote ESP OTA .bin URL (plain app image or full bundle)")
    device_ota_parser.add_argument("--http-port", type=int, default=8380,
                                   help="Local HTTP server port for OTA (default: 8380)")
    device_ota_parser.add_argument("--https", action="store_true",
                                   help="Serve local OTA artifact over HTTPS (requires --https-cert and --https-key)")
    device_ota_parser.add_argument("--https-cert",
                                   help="Path to local HTTPS certificate PEM")
    device_ota_parser.add_argument("--https-key",
                                   help="Path to local HTTPS private key PEM")
    device_ota_parser.add_argument("--ota-timeout", type=float, default=300.0,
                                   help="OTA timeout in seconds (default: 300)")
    add_transport_args(device_ota_parser)
    device_ota_parser.set_defaults(func=cmd_device_ota)

    device_agent_parser = node_sub.add_parser("agent", help="Enable/disable built-in agent services")
    device_agent_parser.add_argument("--mqtt", type=int, choices=[0, 1], default=None,
                                     help="MQTT agent enable (0=off, 1=on)")
    device_agent_parser.add_argument("--uart", type=int, choices=[0, 1], default=None,
                                     help="UART agent enable (0=off, 1=on)")
    device_agent_parser.add_argument("--raw-auto", type=int, choices=[0, 1], default=None,
                                     help="Auto-enable raw stream on boot (0=off, 1=on)")
    device_agent_parser.add_argument("--uart-split", dest="uart_split", type=int, choices=[0, 1], default=None,
                                     help="Split single-UART runtime data after sensorStart (0=off, 1=on)")
    device_agent_parser.add_argument("--led", type=int, choices=[0, 1], default=None,
                                     help="LED error display enable (0=off, 1=on)")
    device_agent_parser.add_argument("--reboot-ms", dest="reboot_ms", type=int, default=None,
                                     help="Reboot threshold when MQTT stays disconnected")
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
        help="Collect MQTT raw_data/raw_resp into raw data plus trimmed cmd_resp text files",
    )
    collect_parser.add_argument("--duration", type=int, default=10,
                                help="Collection time in seconds (default: 10)")
    collect_parser.add_argument("--protocol", choices=["mcp", "cli"],
                                help="Control protocol for optional device discovery (default: cli)")
    collect_parser.add_argument(
        "--data-output",
        default="data_resp.sraw",
        help="Output file for raw_data/data_resp payloads (raw DATA UART bytes, default: data_resp.sraw)",
    )
    collect_parser.add_argument(
        "--resp-output",
        default="cmd_resp.log",
        help="Output file for raw_resp/cmd_resp payloads (startup-trimmed CMD UART text, default: cmd_resp.log)",
    )
    collect_parser.add_argument(
        "--resp-optional",
        action="store_true",
        help=(
            "Allow late-attach collect to succeed when no raw_resp payload is captured during "
            "this window; do not use for startup/welcome proof"
        ),
    )
    collect_parser.add_argument("--broker",
                                help="MQTT broker URI/host for collection (e.g. mqtt://127.0.0.1:1883)")
    collect_parser.add_argument("--mqtt-port", type=int, default=1883,
                                help="MQTT broker port (default: 1883)")
    collect_parser.add_argument("--did",
                                help="DID for MQTT route fallback")
    collect_parser.add_argument("--prod", default="mmwk",
                                help="MQTT product route segment (default: mmwk)")
    collect_parser.add_argument("--oid", default="mmwk",
                                help="MQTT organization route segment (default: mmwk)")
    collect_parser.add_argument("--cid", default="",
                                help="MQTT claimed route id; when set it takes precedence over --did")
    collect_parser.add_argument("--data-topic",
                                help="MQTT raw_data topic to subscribe (DATA UART raw data-port bytes)")
    collect_parser.add_argument("--resp-topic",
                                help="MQTT raw_resp topic to subscribe (CMD UART startup-trimmed command-port output)")
    collect_parser.add_argument("--port", "-p",
                                help="Optional UART serial port for auto-discovery via node info")
    collect_parser.add_argument("--baudrate", "-b", type=int, default=115200,
                                help="UART baudrate when --port is used (default: 115200)")
    collect_parser.add_argument("--reset", action="store_true",
                                help="Reset device before auto-discovery when --port is used")
    collect_parser.add_argument("--timeout", type=float, default=10.0,
                                help="Timeout for auto-discovery in seconds (default: 10)")
    collect_parser.add_argument("-v", "--verbose", action="store_true",
                                help="Enable debug logging")
    collect_parser.set_defaults(func=cmd_collect, transport="uart")

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
    endpoint_config_get_parser.add_argument("id", help="Endpoint id, e.g. radar.raw")
    add_transport_args(endpoint_config_get_parser)
    endpoint_config_get_parser.set_defaults(func=cmd_endpoint_config_get)

    endpoint_config_set_parser = endpoint_config_sub.add_parser("set", help="Write endpoint config")
    endpoint_config_set_parser.add_argument("id", help="Endpoint id, e.g. radar.raw")
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
