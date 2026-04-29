"""Protocol-aware control client factory."""

from mmwk.control_cli_client import ControlCliClient
from mmwk.mcp_client import McpClient


def create_protocol_client(
    protocol: str,
    transport,
    key: str = None,
    request_retries: int = 1,
    request_retry_delay: float = 1.0,
):
    if protocol == "cli":
        return ControlCliClient(
            transport,
            request_key=key,
            request_retries=request_retries,
            request_retry_delay=request_retry_delay,
        )
    if protocol == "mcp":
        return McpClient(
            transport,
            request_retries=request_retries,
            request_retry_delay=request_retry_delay,
        )
    raise ValueError(f"unsupported protocol: {protocol}")
