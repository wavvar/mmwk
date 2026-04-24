"""CLI entry point for mmwk_cli."""

import sys
import json
import logging
import argparse
import os

from mmwk_cli._logging import logger
from mmwk_cli.transport import create_transport
from mmwk_cli.protocol_client import create_protocol_client
from mmwk_cli.commands.flash import FlashCommand
from mmwk_cli.commands.ota import OtaCommand
from mmwk_cli.commands.reconf import ReconfCommand
from mmwk_cli.commands.device_ota import DeviceOtaCommand
from mmwk_cli.commands.collect import CollectCommand
from mmwk_cli.commands.cfg import CfgCommand

_ACTIVE_PROTOCOL = "cli"


def McpClient(transport):
    return create_protocol_client(_ACTIVE_PROTOCOL, transport)


def _cli_create_transport(args):
    """Thin wrapper: catch ValueError from create_transport and exit."""
    if hasattr(args, "protocol"):
        _set_active_protocol(getattr(args, "protocol", None) or "cli")
    try:
        return create_transport(args)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)


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


def _finalize_protocol_args(args):
    if not hasattr(args, "protocol"):
        return

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
    group.add_argument("--broker", default="localhost",
                       help="MQTT broker address (default: localhost)")
    group.add_argument("--mqtt-port", type=int, default=1883,
                       help="MQTT broker port (default: 1883)")
    group.add_argument("--device-id", help="Device ID for MQTT topics")
    group.add_argument("--cmd-topic", help="Custom MQTT command topic")
    group.add_argument("--resp-topic", help="Custom MQTT response topic")
    group.add_argument("--timeout", type=float, default=10.0,
                       help="Response timeout in seconds (default: 10)")
    group.add_argument("-v", "--verbose", action="store_true",
                       help="Enable debug logging")


def cmd_radar_flash(args):
    """Handle: mmwk_cli radar flash ..."""
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
    """Handle: mmwk_cli radar ota ..."""
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
            raw_capture_broker=getattr(args, "raw_capture_broker", None),
            raw_resp_topic=getattr(args, "raw_resp_topic", None),
            raw_capture_timeout=getattr(args, "raw_capture_timeout", 10.0),
        )
        sys.exit(0 if ok else 1)
    finally:
        transport.close()


def cmd_radar_reconf(args):
    """Handle: mmwk_cli radar reconf ..."""
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
    """Handle: mmwk_cli radar cfg ..."""
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
    """Handle: mmwk_cli radar version ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        result = mcp.call_tool("radar", {"action": "version"}, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            data = json.loads(text)
            print(json.dumps(data, indent=2))
        except:
            print(text)
    finally:
        transport.close()


def cmd_radar_status(args):
    """Handle: mmwk_cli radar status ..."""
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
    """Handle: mmwk_cli radar start ..."""
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
    """Handle: mmwk_cli radar stop ..."""
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


def cmd_radar_raw(args):
    """Handle: mmwk_cli radar raw ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        radar_args = {"action": "raw"}
        if args.enable:
            radar_args["enabled"] = True
        elif args.disable:
            radar_args["enabled"] = False

        if args.uri:
            radar_args["uri"] = args.uri

        result = mcp.call_tool("radar", radar_args, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            data = json.loads(text)
            print(json.dumps(data, indent=2))
        except Exception:
            print(text)
    finally:
        transport.close()


def cmd_radar_debug(args):
    """Handle: mmwk_cli radar debug ..."""
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

        result = mcp.call_tool("radar", radar_args, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            data = json.loads(text)
            print(json.dumps(data, indent=2))
        except Exception:
            print(text)
    finally:
        transport.close()


def cmd_device_hi(args):
    """Handle: mmwk_cli device hi ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        result = mcp.call_tool("device", {"action": "hi"}, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            data = json.loads(text)
            print(json.dumps(data, indent=2))
        except:
            print(text)
    finally:
        transport.close()


def cmd_device_reboot(args):
    """Handle: mmwk_cli device reboot ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=15)
        resp = mcp.call_tool("device", {"action": "reboot"}, timeout=10)
        text = mcp.extract_text(resp)
        print(text)
    finally:
        transport.close()


def cmd_device_ota(args):
    """Handle: mmwk_cli device ota ..."""
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
    """Handle: mmwk_cli device agent ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        dev_args = {"action": "agent"}
        if args.mqtt_en is not None:
            dev_args["mqtt_en"] = args.mqtt_en
        if args.uart_en is not None:
            dev_args["uart_en"] = args.uart_en
        if args.raw_auto is not None:
            dev_args["raw_auto"] = args.raw_auto

        result = mcp.call_tool("device", dev_args, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            data = json.loads(text)
            print(json.dumps(data, indent=2))
        except Exception:
            print(text)
    finally:
        transport.close()


def cmd_device_heartbeat(args):
    """Handle: mmwk_cli device heartbeat ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        dev_args = {"action": "heartbeat", "interval": args.interval}
        if args.fields:
            dev_args["fields"] = args.fields

        result = mcp.call_tool("device", dev_args, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            data = json.loads(text)
            print(json.dumps(data, indent=2))
        except Exception:
            print(text)
    finally:
        transport.close()


def cmd_fw_list(args):
    """Handle: mmwk_cli fw list ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        result = mcp.call_tool("fw", {"action": "list"}, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            data = json.loads(text)
            print(json.dumps(data, indent=2))
        except Exception:
            print(text)
    finally:
        transport.close()


def cmd_fw_set(args):
    """Handle: mmwk_cli fw set ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        result = mcp.call_tool("fw", {"action": "set", "index": args.index}, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            data = json.loads(text)
            print(json.dumps(data, indent=2))
        except Exception:
            print(text)
    finally:
        transport.close()


def cmd_fw_del(args):
    """Handle: mmwk_cli fw del ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        result = mcp.call_tool("fw", {"action": "del", "index": args.index}, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            data = json.loads(text)
            print(json.dumps(data, indent=2))
        except Exception:
            print(text)
    finally:
        transport.close()


def cmd_fw_download(args):
    """Handle: mmwk_cli fw download ..."""
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
        result = mcp.call_tool("fw", fw_args, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            data = json.loads(text)
            print(json.dumps(data, indent=2))
        except Exception:
            print(text)
    finally:
        transport.close()


def cmd_record(args):
    """Handle: mmwk_cli record ..."""
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


def cmd_raw_record(args):
    """Handle: mmwk_cli raw record ..."""
    payload = {}
    if args.action == "status":
        payload = {"action": "status"}
    elif args.action == "start":
        payload = {"action": "record_start"}
        if getattr(args, "uri", None):
            payload["uri"] = args.uri
    elif args.action == "stop":
        payload = {"action": "record_stop"}
    elif args.action == "trigger":
        payload = {"action": "record_trigger"}
        if getattr(args, "event", None):
            payload["event"] = args.event
        if getattr(args, "duration", None) is not None:
            payload["duration_sec"] = args.duration

    _call_tool_and_print_json(args, "raw_capture", payload)


def cmd_collect(args):
    """Handle: mmwk_cli collect ..."""
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
            device_id=args.device_id,
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
    """Handle: mmwk_cli help ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        result = mcp.call_tool("help", {}, timeout=args.timeout)
        _print_json_payload(mcp.extract_text(result))
    finally:
        transport.close()


def cmd_network(args):
    """Handle: mmwk_cli network ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        net_args = {"action": args.action}
        if args.action == "config":
            net_args["ssid"] = args.ssid
            net_args["password"] = args.password
        elif args.action == "prov":
            net_args["enable"] = 1 if args.enable else 0
        elif args.action == "mqtt":
            if args.mqtt_uri is not None: net_args["mqtt_uri"] = args.mqtt_uri
            if args.mqtt_user is not None: net_args["mqtt_user"] = args.mqtt_user
            if args.mqtt_pass is not None: net_args["mqtt_pass"] = args.mqtt_pass
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
    """Handle: mmwk_cli tools ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        tools = mcp.tools_list(timeout=args.timeout)
        for tool in tools:
            print(f"  {tool.get('name', '?'):12s} — {tool.get('description', '')}")
    finally:
        transport.close()


def cmd_entity_list(args):
    """Handle: mmwk_cli entity list ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        result = mcp.call_tool("catalog", {}, timeout=args.timeout)
        text = mcp.extract_text(result)
        try:
            payload = json.loads(text)
        except Exception:
            print(text)
            return
        if args.json:
            print(json.dumps(payload, indent=2))
            return

        entities = payload.get("entities", []) if isinstance(payload, dict) else []
        for entity in entities:
            if isinstance(entity, dict):
                entity_id = entity.get("id")
                if isinstance(entity_id, str) and entity_id:
                    print(entity_id)
    finally:
        transport.close()


def cmd_entity_describe(args):
    """Handle: mmwk_cli entity describe ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        result = mcp.call_tool(
            "entity",
            {"action": "describe", "entity": args.entity},
            timeout=args.timeout,
        )
        _print_json_payload(mcp.extract_text(result))
    finally:
        transport.close()


def cmd_entity_read(args):
    """Handle: mmwk_cli entity read ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        result = mcp.call_tool(
            "entity",
            {"action": "read_state", "entity": args.entity},
            timeout=args.timeout,
        )
        _print_json_payload(mcp.extract_text(result))
    finally:
        transport.close()


def cmd_entity_config_get(args):
    """Handle: mmwk_cli entity config get ..."""
    transport = _cli_create_transport(args)
    try:
        mcp = McpClient(transport)
        mcp.initialize(timeout=args.timeout)

        result = mcp.call_tool(
            "entity",
            {"action": "read_config", "entity": args.entity},
            timeout=args.timeout,
        )
        _print_json_payload(mcp.extract_text(result))
    finally:
        transport.close()


def cmd_entity_config_set(args):
    """Handle: mmwk_cli entity config set ..."""
    payload = {
        "action": "write_config",
        "entity": args.entity,
        "config": _load_json_object_arg(args.config_json),
    }
    _call_tool_and_print_json(args, "entity", payload)


def cmd_adapter_list(args):
    """Handle: mmwk_cli adapter list ..."""
    _call_tool_and_print_json(args, "adapter", {"action": "list"})


def cmd_adapter_status(args):
    """Handle: mmwk_cli adapter status ..."""
    _call_tool_and_print_json(args, "adapter", {"action": "status", "protocol": args.protocol})


def cmd_adapter_manifest(args):
    """Handle: mmwk_cli adapter manifest ..."""
    _call_tool_and_print_json(args, "adapter", {"action": "manifest", "protocol": args.protocol})


def cmd_scene_show(args):
    """Handle: mmwk_cli scene show ..."""
    _call_tool_and_print_json(args, "scene", {"action": "show"})


def cmd_scene_set(args):
    """Handle: mmwk_cli scene set ..."""
    payload = {"action": "set", "config": _load_json_object_arg(args.config_json)}
    _call_tool_and_print_json(args, "scene", payload)


def cmd_scene_apply(args):
    """Handle: mmwk_cli scene apply ..."""
    _call_tool_and_print_json(args, "scene", {"action": "apply"})


def cmd_scene_wait_ready(args):
    """Handle: mmwk_cli scene wait-ready ..."""
    payload = {
        "action": "wait_ready",
        "timeout_ms": args.timeout_ms,
        "interval_ms": args.interval_ms,
    }
    _call_tool_and_print_json(args, "scene", payload)


def cmd_policy_show(args):
    """Handle: mmwk_cli policy show ..."""
    _call_tool_and_print_json(args, "policy", {"action": "show"})


def cmd_policy_explain(args):
    """Handle: mmwk_cli policy explain ..."""
    _call_tool_and_print_json(args, "policy", {"action": "explain"})


def cmd_policy_set(args):
    """Handle: mmwk_cli policy set ..."""
    if args.config_json:
        payload = {"action": "set", "config": _load_json_object_arg(args.config_json)}
    else:
        payload = {"action": "set"}
        if args.profile:
            payload["profile"] = args.profile
        if args.summary_ms is not None:
            payload["summary_interval_ms"] = args.summary_ms
        if args.report_ms is not None:
            payload["report_interval_ms"] = args.report_ms
        if args.tracker_ms is not None:
            payload["tracker_ms"] = args.tracker_ms
        if args.vs_ms is not None:
            payload["vs_ms"] = args.vs_ms
        if args.presence_ms is not None:
            payload["presence_ms"] = args.presence_ms
        if args.quality_threshold is not None:
            payload["quality_threshold_default"] = args.quality_threshold
        if args.ecg_chunk_samples is not None:
            payload["ecg_stream_chunk_samples"] = args.ecg_chunk_samples
        if args.ecg_buffer_chunks is not None:
            payload["ecg_stream_buffer_chunks"] = args.ecg_buffer_chunks
        if args.raw_record_enabled is not None:
            payload["raw_record_enabled_default"] = args.raw_record_enabled == 1
        if args.raw_record_max_duration_sec is not None:
            payload["raw_record_max_duration_sec"] = args.raw_record_max_duration_sec

    _call_tool_and_print_json(args, "policy", payload)


def main():
    parser = argparse.ArgumentParser(
        prog="mmwk_cli",
        description="MMWK Sensor CLI — Control mmwk devices via canonical CLI JSON or MCP/JSON-RPC 2.0"
    )
    subparsers = parser.add_subparsers(dest="tool", help="Control service namespace")

    # -- radar --
    radar_parser = subparsers.add_parser("radar", help="Radar service control")
    radar_sub = radar_parser.add_subparsers(dest="action", required=True)

    # radar flash -- chunk-based transfer
    flash_parser = radar_sub.add_parser("flash", help="Flash firmware via UART/MQTT (chunk transfer)")
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

    # radar reconf -- runtime-only contract/cfg reconfigure
    reconf_parser = radar_sub.add_parser("reconf", help="Reconfigure runtime radar contract without flashing firmware")
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

    # radar ota -- HTTP OTA download
    ota_parser = radar_sub.add_parser("ota", help="Flash firmware via HTTP OTA (device downloads)")
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
        "--raw-capture-broker",
        help="MQTT broker URI/host override for OTA raw_resp capture (defaults to radar raw/device hi)",
    )
    ota_parser.add_argument(
        "--raw-resp-topic",
        help="MQTT raw_resp topic override for OTA capture (defaults to radar raw/device hi)",
    )
    ota_parser.add_argument(
        "--raw-capture-timeout",
        type=float,
        default=10.0,
        help="MQTT subscribe-ready timeout for OTA raw_resp capture in seconds (default: 10)",
    )
    add_transport_args(ota_parser)
    ota_parser.set_defaults(func=cmd_radar_ota)

    # radar start
    start_parser = radar_sub.add_parser("start", help="Start or restart radar service")
    start_parser.add_argument("--mode", choices=["auto", "host"], default=None,
                              help="Persist start mode, then start/restart radar service in that mode")
    add_transport_args(start_parser)
    start_parser.set_defaults(func=cmd_radar_start)

    # radar stop
    stop_parser = radar_sub.add_parser("stop", help="Stop radar service")
    add_transport_args(stop_parser)
    stop_parser.set_defaults(func=cmd_radar_stop)

    # radar status
    status_parser = radar_sub.add_parser("status", help="Query radar status")
    add_transport_args(status_parser)
    status_parser.set_defaults(func=cmd_radar_status)

    # radar cfg
    cfg_parser = radar_sub.add_parser("cfg", help="Read current radar cfg text")
    cfg_parser.add_argument("--gen", action="store_true",
                            help="Read hub-generated cfg text instead of file cfg")
    add_transport_args(cfg_parser)
    cfg_parser.set_defaults(func=cmd_radar_cfg)

    # radar version
    version_parser = radar_sub.add_parser("version", help="Query running firmware version")
    add_transport_args(version_parser)
    version_parser.set_defaults(func=cmd_radar_version)

    # radar raw
    radar_raw_parser = radar_sub.add_parser("raw", help="Configure/query radar raw forwarding")
    raw_toggle = radar_raw_parser.add_mutually_exclusive_group()
    raw_toggle.add_argument("--enable", action="store_true", help="Enable raw forwarding")
    raw_toggle.add_argument("--disable", action="store_true", help="Disable raw forwarding")
    radar_raw_parser.add_argument("--uri", help="Raw MQTT broker URI (omit to reuse device MQTT broker)")
    add_transport_args(radar_raw_parser)
    radar_raw_parser.set_defaults(func=cmd_radar_raw)

    # radar debug
    debug_parser = radar_sub.add_parser("debug", help="Manage/query radar debug diagnostics")
    debug_parser.add_argument("op", nargs="?", choices=["set", "get", "snapshot", "reset"], default="snapshot",
                              help="Debug sub-operation (default: snapshot)")
    debug_parser.add_argument("--packets", choices=["on", "off"],
                              help="Enable/disable packet counters (set only)")
    debug_parser.add_argument("--frames", choices=["on", "off"],
                              help="Enable/disable frame counters (set only)")
    add_transport_args(debug_parser)
    debug_parser.set_defaults(func=cmd_radar_debug)

    # -- device --
    device_parser = subparsers.add_parser("device", help="Device configuration")
    device_sub = device_parser.add_subparsers(dest="action", required=True)

    hi_parser = device_sub.add_parser("hi", help="Device status handshake")
    add_transport_args(hi_parser)
    hi_parser.set_defaults(func=cmd_device_hi)

    device_reboot_parser = device_sub.add_parser("reboot", help="Reboot the device")
    add_transport_args(device_reboot_parser)
    device_reboot_parser.set_defaults(func=cmd_device_reboot)

    device_ota_parser = device_sub.add_parser("ota", help="Update ESP firmware via HTTP OTA (.bin only, supports full app+assets bundle)")
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

    # device agent
    device_agent_parser = device_sub.add_parser("agent", help="Enable/disable built-in agent services")
    device_agent_parser.add_argument("--mqtt-en", type=int, choices=[0, 1], default=None,
                                     help="MQTT agent enable (0=off, 1=on)")
    device_agent_parser.add_argument("--uart-en", type=int, choices=[0, 1], default=None,
                                     help="UART agent enable (0=off, 1=on)")
    device_agent_parser.add_argument("--raw-auto", type=int, choices=[0, 1], default=None,
                                     help="Auto-enable raw stream on boot (0=off, 1=on)")
    add_transport_args(device_agent_parser)
    device_agent_parser.set_defaults(func=cmd_device_agent)

    # device heartbeat
    device_hb_parser = device_sub.add_parser("heartbeat", help="Configure system heartbeat")
    device_hb_parser.add_argument("--interval", type=int, required=True,
                                  help="Heartbeat period in seconds (0=disable, min 30)")
    device_hb_parser.add_argument("--fields", nargs="+",
                                  help="Payload fields (e.g. rssi heap uptime)")
    add_transport_args(device_hb_parser)
    device_hb_parser.set_defaults(func=cmd_device_heartbeat)

    # -- fw --
    fw_parser = subparsers.add_parser("fw", help="Firmware manager")
    fw_sub = fw_parser.add_subparsers(dest="action", required=True)

    fw_list_parser = fw_sub.add_parser("list", help="List firmware images")
    add_transport_args(fw_list_parser)
    fw_list_parser.set_defaults(func=cmd_fw_list)

    # fw set
    fw_set_parser = fw_sub.add_parser("set", help="Set default boot firmware partition")
    fw_set_parser.add_argument("--index", type=int, required=True, help="Partition index")
    add_transport_args(fw_set_parser)
    fw_set_parser.set_defaults(func=cmd_fw_set)

    # fw del
    fw_del_parser = fw_sub.add_parser("del", help="Delete a firmware partition")
    fw_del_parser.add_argument("--index", type=int, required=True, help="Partition index")
    add_transport_args(fw_del_parser)
    fw_del_parser.set_defaults(func=cmd_fw_del)

    # fw download
    fw_dl_parser = fw_sub.add_parser("download", help="Download firmware image to device")
    fw_dl_parser.add_argument("--source", required=True, help="Download source URL")
    fw_dl_parser.add_argument("--name", required=True, help="Firmware name")
    fw_dl_parser.add_argument("--fw-version", required=True, help="Firmware version")
    fw_dl_parser.add_argument("--size", type=int, required=True, help="File size in bytes")
    add_transport_args(fw_dl_parser)
    fw_dl_parser.set_defaults(func=cmd_fw_download)

    # -- record --
    rec_parser = subparsers.add_parser("record", help="SD Card/Flash recording management")
    rec_sub = rec_parser.add_subparsers(dest="action", required=True)

    # record start
    rec_start = rec_sub.add_parser("start", help="Start recording")
    rec_start.add_argument("--uri", help="Target URI to save recorded data")
    add_transport_args(rec_start)
    rec_start.set_defaults(func=cmd_record)

    # record stop
    rec_stop = rec_sub.add_parser("stop", help="Stop recording")
    add_transport_args(rec_stop)
    rec_stop.set_defaults(func=cmd_record)

    # record trigger
    rec_trigger = rec_sub.add_parser("trigger", help="Trigger event recording snippet")
    rec_trigger.add_argument("--event", help="Trigger event name (default: MANUAL)")
    rec_trigger.add_argument("--duration", type=int, help="Recording duration in seconds (default: 10)")
    add_transport_args(rec_trigger)
    rec_trigger.set_defaults(func=cmd_record)

    # -- raw --
    raw_root_parser = subparsers.add_parser("raw", help="Capability-first raw capture management")
    raw_root_sub = raw_root_parser.add_subparsers(dest="raw_group", required=True)

    raw_record_parser = raw_root_sub.add_parser("record", help="Manage raw capture recorder lifecycle")
    raw_record_sub = raw_record_parser.add_subparsers(dest="action", required=True)

    raw_record_status = raw_record_sub.add_parser("status", help="Show raw capture recording state")
    add_transport_args(raw_record_status)
    raw_record_status.set_defaults(func=cmd_raw_record)

    raw_record_start = raw_record_sub.add_parser("start", help="Arm the raw capture recorder")
    raw_record_start.add_argument("--uri", help="Upload target URI (defaults to raw.capture config upload_target)")
    add_transport_args(raw_record_start)
    raw_record_start.set_defaults(func=cmd_raw_record)

    raw_record_stop = raw_record_sub.add_parser("stop", help="Stop the raw capture recorder")
    add_transport_args(raw_record_stop)
    raw_record_stop.set_defaults(func=cmd_raw_record)

    raw_record_trigger = raw_record_sub.add_parser("trigger", help="Trigger a raw capture upload window")
    raw_record_trigger.add_argument("--event", help="Trigger event name (default: manual)")
    raw_record_trigger.add_argument("--duration", type=int,
                                    help="Recording duration in seconds (defaults to raw.capture config)")
    add_transport_args(raw_record_trigger)
    raw_record_trigger.set_defaults(func=cmd_raw_record)

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
    collect_parser.add_argument("--device-id",
                                help="Device client id used for topic defaults")
    collect_parser.add_argument("--data-topic",
                                help="MQTT raw_data topic to subscribe (DATA UART raw data-port bytes)")
    collect_parser.add_argument("--resp-topic",
                                help="MQTT raw_resp topic to subscribe (CMD UART startup-trimmed command-port output)")
    collect_parser.add_argument("--port", "-p",
                                help="Optional UART serial port for auto-discovery via device hi")
    collect_parser.add_argument("--baudrate", "-b", type=int, default=115200,
                                help="UART baudrate when --port is used (default: 115200)")
    collect_parser.add_argument("--reset", action="store_true",
                                help="Reset device before auto-discovery when --port is used")
    collect_parser.add_argument("--timeout", type=float, default=10.0,
                                help="Timeout for auto-discovery in seconds (default: 10)")
    collect_parser.add_argument("-v", "--verbose", action="store_true",
                                help="Enable debug logging")
    collect_parser.set_defaults(func=cmd_collect, transport="uart")

    # -- tools --
    tools_parser = subparsers.add_parser("tools", help="List available MCP tools")
    add_transport_args(tools_parser)
    tools_parser.set_defaults(func=cmd_tools_list)

    # -- entity --
    entity_parser = subparsers.add_parser("entity", help="Capability entity discovery, state, and config inspection")
    entity_sub = entity_parser.add_subparsers(dest="action", required=True)

    entity_list_parser = entity_sub.add_parser("list", help="List supported capability entities")
    entity_list_parser.add_argument("--json", action="store_true",
                                    help="Print full catalog JSON instead of entity ids")
    add_transport_args(entity_list_parser)
    entity_list_parser.set_defaults(func=cmd_entity_list)

    entity_describe_parser = entity_sub.add_parser("describe", help="Describe a capability entity")
    entity_describe_parser.add_argument("entity", help="Capability entity id, e.g. mgmt.device")
    add_transport_args(entity_describe_parser)
    entity_describe_parser.set_defaults(func=cmd_entity_describe)

    entity_read_parser = entity_sub.add_parser("read", help="Read capability entity state")
    entity_read_parser.add_argument("entity", help="Capability entity id, e.g. mgmt.device")
    add_transport_args(entity_read_parser)
    entity_read_parser.set_defaults(func=cmd_entity_read)

    entity_config_parser = entity_sub.add_parser("config", help="Read or write capability entity config")
    entity_config_sub = entity_config_parser.add_subparsers(dest="config_action", required=True)

    entity_config_get_parser = entity_config_sub.add_parser("get", help="Read capability entity config")
    entity_config_get_parser.add_argument("entity", help="Capability entity id, e.g. raw.capture")
    add_transport_args(entity_config_get_parser)
    entity_config_get_parser.set_defaults(func=cmd_entity_config_get)

    entity_config_set_parser = entity_config_sub.add_parser("set", help="Write capability entity config")
    entity_config_set_parser.add_argument("entity", help="Capability entity id, e.g. raw.capture")
    entity_config_set_parser.add_argument(
        "--config-json",
        required=True,
        help="JSON object string, @file, or file path containing the config patch",
    )
    add_transport_args(entity_config_set_parser)
    entity_config_set_parser.set_defaults(func=cmd_entity_config_set)

    # -- adapter --
    adapter_parser = subparsers.add_parser("adapter", help="Inspect protocol adapter projection status and manifests")
    adapter_sub = adapter_parser.add_subparsers(dest="action", required=True)

    adapter_list_parser = adapter_sub.add_parser("list", help="List available protocol adapters")
    add_transport_args(adapter_list_parser)
    adapter_list_parser.set_defaults(func=cmd_adapter_list)

    adapter_status_parser = adapter_sub.add_parser("status", help="Show adapter status summary")
    adapter_status_parser.add_argument("protocol", help="Adapter protocol to inspect")
    add_transport_args(adapter_status_parser)
    adapter_status_parser.set_defaults(func=cmd_adapter_status)

    adapter_manifest_parser = adapter_sub.add_parser("manifest", help="Show adapter projection manifest")
    adapter_manifest_parser.add_argument("protocol", help="Adapter protocol to inspect")
    add_transport_args(adapter_manifest_parser)
    adapter_manifest_parser.set_defaults(func=cmd_adapter_manifest)

    # -- scene --
    scene_parser = subparsers.add_parser("scene", help="Capability-first scene management")
    scene_sub = scene_parser.add_subparsers(dest="action", required=True)

    scene_show_parser = scene_sub.add_parser("show", help="Show active scene config")
    add_transport_args(scene_show_parser)
    scene_show_parser.set_defaults(func=cmd_scene_show)

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

    scene_wait_parser = scene_sub.add_parser("wait-ready", help="Wait until radar is ready after scene apply")
    scene_wait_parser.add_argument("--timeout-ms", type=int, default=30000,
                                   help="Timeout in milliseconds (default: 30000)")
    scene_wait_parser.add_argument("--interval-ms", type=int, default=500,
                                   help="Polling interval in milliseconds (default: 500)")
    add_transport_args(scene_wait_parser)
    scene_wait_parser.set_defaults(func=cmd_scene_wait_ready)

    # -- policy --
    policy_parser = subparsers.add_parser("policy", help="Capability-first measurement policy management")
    policy_sub = policy_parser.add_subparsers(dest="action", required=True)

    policy_show_parser = policy_sub.add_parser("show", help="Show active policy config")
    add_transport_args(policy_show_parser)
    policy_show_parser.set_defaults(func=cmd_policy_show)

    policy_explain_parser = policy_sub.add_parser("explain", help="Show policy state and effective config")
    add_transport_args(policy_explain_parser)
    policy_explain_parser.set_defaults(func=cmd_policy_explain)

    policy_set_parser = policy_sub.add_parser("set", help="Update policy defaults and runtime intervals")
    policy_set_parser.add_argument(
        "--config-json",
        help="JSON object string, @file, or file path containing the policy config patch",
    )
    policy_set_parser.add_argument("--profile", choices=["default", "custom"],
                                   help="Measurement profile shortcut")
    policy_set_parser.add_argument("--summary-ms", type=int,
                                   help="Summary interval mapped to legacy vs_ms")
    policy_set_parser.add_argument("--report-ms", type=int,
                                   help="Report interval mapped to legacy presence_ms")
    policy_set_parser.add_argument("--tracker-ms", type=int,
                                   help="Legacy tracker interval override")
    policy_set_parser.add_argument("--vs-ms", type=int,
                                   help="Legacy vital-signs interval override")
    policy_set_parser.add_argument("--presence-ms", type=int,
                                   help="Legacy presence interval override")
    policy_set_parser.add_argument("--quality-threshold", type=int,
                                   help="Default quality threshold")
    policy_set_parser.add_argument("--ecg-chunk-samples", type=int,
                                   help="Default ECG chunk size")
    policy_set_parser.add_argument("--ecg-buffer-chunks", type=int,
                                   help="Default ECG buffer chunk count")
    policy_set_parser.add_argument("--raw-record-enabled", type=int, choices=[0, 1],
                                   help="Default raw recording enable flag")
    policy_set_parser.add_argument("--raw-record-max-duration-sec", type=int,
                                   help="Default raw recording max duration")
    add_transport_args(policy_set_parser)
    policy_set_parser.set_defaults(func=cmd_policy_set)

    # -- network --
    net_parser = subparsers.add_parser("network", help="Network configuration")
    net_sub = net_parser.add_subparsers(dest="action", required=True)

    # network mqtt
    net_mqtt = net_sub.add_parser("mqtt", help="Get/Set MQTT configuration")
    net_mqtt.add_argument("--mqtt-uri", help="Set MQTT Broker URI")
    net_mqtt.add_argument("--mqtt-user", help="Set MQTT Username")
    net_mqtt.add_argument("--mqtt-pass", help="Set MQTT Password")
    add_transport_args(net_mqtt)
    net_mqtt.set_defaults(func=cmd_network)

    # network config
    net_cfg = net_sub.add_parser("config", help="Set Wi-Fi credentials")
    net_cfg.add_argument("--ssid", required=True, help="Wi-Fi SSID")
    net_cfg.add_argument("--password", required=True, help="Wi-Fi Password")
    add_transport_args(net_cfg)
    net_cfg.set_defaults(func=cmd_network)

    # network prov
    net_prov = net_sub.add_parser("prov", help="Control Wi-Fi provisioning")
    net_prov_grp = net_prov.add_mutually_exclusive_group(required=True)
    net_prov_grp.add_argument("--enable", action="store_true", help="Enable provisioning mode")
    net_prov_grp.add_argument("--disable", action="store_true", help="Disable provisioning mode")
    add_transport_args(net_prov)
    net_prov.set_defaults(func=cmd_network)

    # network status
    net_status = net_sub.add_parser("status", help="Query Wi-Fi/provisioning runtime status")
    add_transport_args(net_status)
    net_status.set_defaults(func=cmd_network)

    # network ntp
    net_ntp = net_sub.add_parser("ntp", help="Configure NTP time sync")
    net_ntp.add_argument("--server", help="NTP server address")
    net_ntp.add_argument("--tz-offset", type=int, help="Timezone offset from UTC in seconds")
    net_ntp.add_argument("--ntp-interval", type=int, help="NTP polling interval in seconds")
    add_transport_args(net_ntp)
    net_ntp.set_defaults(func=cmd_network)

    # -- help --
    help_parser = subparsers.add_parser("help", help="List all device-supported commands")
    add_transport_args(help_parser)
    help_parser.set_defaults(func=cmd_help)

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
