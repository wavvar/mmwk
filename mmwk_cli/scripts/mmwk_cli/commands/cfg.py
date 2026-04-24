"""Radar cfg readback command helper."""

import json


class CfgCommand:
    """Fetch radar cfg text via MCP radar tool."""

    def __init__(self, mcp_client):
        self._mcp = mcp_client

    def execute(self, gen=False, timeout=10.0):
        payload = {"action": "cfg"}
        if gen:
            payload["gen"] = True

        try:
            result = self._mcp.call_tool("radar", payload, timeout=timeout)
            text = self._mcp.extract_text(result)
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid radar cfg response: {exc}") from exc

        if not isinstance(parsed, dict):
            raise ValueError("Invalid radar cfg response: expected JSON object")

        cfg = parsed.get("cfg")
        if not isinstance(cfg, str) or not cfg:
            raise ValueError("Missing cfg in radar cfg response")

        return cfg
