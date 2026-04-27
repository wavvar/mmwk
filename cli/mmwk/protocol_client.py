"""Protocol-aware control client factory."""

from mmwk.control_cli_client import ControlCliClient
from mmwk.mcp_client import McpClient


def create_protocol_client(protocol: str, transport, key: str = None):
    if protocol == "cli":
        return ControlCliClient(transport, request_key=key)
    if protocol == "mcp":
        return McpClient(transport)
    raise ValueError(f"unsupported protocol: {protocol}")
