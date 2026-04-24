"""
MMWK CLI — Command-line tool for MMWK bridge/hub devices.

Communicates with MMWK bridge/hub devices over UART or MQTT using the
canonical CLI JSON protocol by default, with MCP still available as fallback.
"""

from mmwk_cli._logging import logger
from mmwk_cli.transport import RadarTransport, UartTransport, MqttTransport, create_transport
from mmwk_cli.control_cli_client import ControlCliClient
from mmwk_cli.mcp_client import McpClient
from mmwk_cli.protocol_client import create_protocol_client
from mmwk_cli.commands.flash import FlashCommand
from mmwk_cli.commands.ota import OtaCommand
from mmwk_cli.commands.device_ota import DeviceOtaCommand
from mmwk_cli.http_server import FirmwareHttpServer, get_local_ip
