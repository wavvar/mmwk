"""
MMWK CLI — Command-line tool for MMWK bridge/hub devices.

Communicates with MMWK bridge/hub devices over UART or MQTT using the
canonical CLI JSON protocol by default, with MCP still available as fallback.
"""

from importlib import import_module

from mmwk_cli._logging import logger
from mmwk_cli.transport import RadarTransport, UartTransport, MqttTransport, create_transport
from mmwk_cli.control_cli_client import ControlCliClient
from mmwk_cli.mcp_client import McpClient
from mmwk_cli.protocol_client import create_protocol_client

__all__ = [
    "logger",
    "RadarTransport",
    "UartTransport",
    "MqttTransport",
    "create_transport",
    "ControlCliClient",
    "McpClient",
    "create_protocol_client",
    "FlashCommand",
    "OtaCommand",
    "DeviceOtaCommand",
    "FirmwareHttpServer",
    "get_local_ip",
]

_LAZY_EXPORTS = {
    "FlashCommand": ("mmwk_cli.commands.flash", "FlashCommand"),
    "OtaCommand": ("mmwk_cli.commands.ota", "OtaCommand"),
    "DeviceOtaCommand": ("mmwk_cli.commands.device_ota", "DeviceOtaCommand"),
    "FirmwareHttpServer": ("mmwk_cli.http_server", "FirmwareHttpServer"),
    "get_local_ip": ("mmwk_cli.http_server", "get_local_ip"),
}


def __getattr__(name):
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = target
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
