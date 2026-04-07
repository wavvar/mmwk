"""MCP (Model Context Protocol) client over JSON-RPC 2.0."""

import json
import time

from mmwk_cli._logging import logger
from mmwk_cli.transport import RadarTransport


class McpClient:
    """MCP (Model Context Protocol) client over JSON-RPC 2.0."""

    def __init__(self, transport: RadarTransport):
        self.transport = transport
        self._initialized = False

    def initialize(self, timeout: float = 10.0) -> dict:
        """Perform MCP handshake: initialize + notifications/initialized.

        The device may still be rebooting right after flash/reset, so retry
        within the caller-provided timeout budget instead of failing on the
        first unanswered handshake.
        """
        deadline = time.time() + timeout
        attempt = 0
        last_resp = None

        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                break

            attempt += 1
            msg_id = self.transport.next_msg_id()
            self.transport.send_json({
                "jsonrpc": "2.0",
                "id": msg_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "v1.3",
                    "capabilities": {},
                    "clientInfo": {"name": "mmwk_cli", "version": "1.0"}
                }
            })

            wait_timeout = min(2.0, remaining)
            resp = self.transport.wait_for_response(msg_id, timeout=wait_timeout)
            if resp and "error" not in resp:
                last_resp = resp
                break

            last_resp = resp
            remaining = deadline - time.time()
            if remaining <= 0:
                break

            sleep_sec = min(0.5, remaining)
            logger.debug(
                "MCP initialize attempt %d failed (resp=%s); retrying in %.1fs",
                attempt,
                resp,
                sleep_sec,
            )
            time.sleep(sleep_sec)

        if not last_resp or "error" in last_resp:
            raise RuntimeError(f"MCP initialize failed: {last_resp}")

        # Send initialized notification
        self.transport.send_json({
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        })

        self._initialized = True
        server_info = resp.get("result", {}).get("serverInfo", {})
        logger.info(f"Connected to {server_info.get('name', '?')} v{server_info.get('version', '?')}")
        return resp.get("result", {})

    def tools_list(self, timeout: float = 10.0) -> list:
        """Query available tools."""
        msg_id = self.transport.next_msg_id()
        self.transport.send_json({
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": "tools/list"
        })
        resp = self.transport.wait_for_response(msg_id, timeout=timeout)
        if resp and "result" in resp:
            return resp["result"].get("tools", [])
        logger.warning("tools/list returned no result")
        return []

    def call_tool(self, name: str, arguments: dict, timeout: float = 30.0) -> dict:
        """Call an MCP tool and wait for the response."""
        msg_id = self.transport.next_msg_id()
        self.transport.send_json({
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments
            }
        })
        resp = self.transport.wait_for_response(msg_id, timeout=timeout)
        if not resp:
            raise TimeoutError(f"Timeout waiting for tool '{name}' response")
        if "error" in resp:
            err = resp["error"]
            raise RuntimeError(f"Tool '{name}' error [{err.get('code')}]: {err.get('message')}")
        return resp.get("result", {})

    def extract_text(self, result: dict) -> str:
        """Extract text from MCP result content array."""
        content = result.get("content", [])
        if content and isinstance(content, list):
            return content[0].get("text", "")
        return json.dumps(result)
