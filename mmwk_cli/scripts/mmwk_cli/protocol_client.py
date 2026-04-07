"""Protocol-aware control client factory."""

from mmwk_cli.control_cli_client import ControlCliClient
from mmwk_cli.mcp_client import McpClient


def create_protocol_client(protocol: str, transport):
    if protocol == "cli":
        return ControlCliClient(transport)
    if protocol == "mcp":
        return McpClient(transport)
    raise ValueError(f"unsupported protocol: {protocol}")
