"""Shared helpers for MMWK network runtime payloads."""

from __future__ import annotations


_TRUTHY = {"1", "true", "yes", "on"}


def unwrap_tool_payload(payload: dict | list | object) -> dict:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            return data
        return payload
    return {}


def normalize_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in _TRUTHY
    if isinstance(value, (int, float)):
        return int(value) != 0
    return False


def valid_runtime_ip(value: object) -> bool:
    if not isinstance(value, str):
        return False
    ip = value.strip()
    if not ip or ip == "0.0.0.0":
        return False
    if ip.startswith("169.254."):
        return False
    return True


def network_state(payload: dict | list | object) -> str:
    value = unwrap_tool_payload(payload).get("state")
    return value.strip().lower() if isinstance(value, str) else ""


def network_ip_ready(payload: dict | list | object) -> bool:
    return normalize_bool(unwrap_tool_payload(payload).get("ip_ready"))


def network_ready(payload: dict | list | object) -> bool:
    data = unwrap_tool_payload(payload)
    return network_state(data) == "connected" and network_ip_ready(data)


def network_runtime_ip(payload: dict | list | object) -> str:
    data = unwrap_tool_payload(payload)
    candidates = [data.get("sta_ip"), data.get("ip")]

    if isinstance(payload, dict):
        device_hi = payload.get("device_hi")
        if isinstance(device_hi, dict):
            candidates.append(device_hi.get("ip"))
        network_status = payload.get("network_status")
        if isinstance(network_status, dict):
            nested = unwrap_tool_payload(network_status)
            candidates.append(nested.get("sta_ip"))
            candidates.append(nested.get("ip"))

    for candidate in candidates:
        if valid_runtime_ip(candidate):
            return candidate.strip()

    return ""


def terminal_network_failure(
    status_payload: dict | list | object,
    diag_payload: dict | list | object | None = None,
) -> bool:
    if network_state(status_payload) == "failed":
        return True
    if diag_payload is None:
        return False
    return normalize_bool(unwrap_tool_payload(diag_payload).get("terminal_failure"))


def network_runtime_summary(
    status_payload: dict | list | object,
    *,
    diag_payload: dict | list | object | None = None,
    device_ip: str = "",
) -> str:
    status = unwrap_tool_payload(status_payload)
    diag = unwrap_tool_payload(diag_payload) if diag_payload is not None else {}
    detail = [
        f"device_ip={device_ip or '<none>'}",
        f"state={network_state(status) or '<none>'}",
        f"sta_ip={network_runtime_ip(status) or '<none>'}",
        f"ip_ready={network_ip_ready(status)}",
    ]

    if diag:
        detail.append(f"terminal_failure={normalize_bool(diag.get('terminal_failure'))}")
        detail.append(f"failure_source={diag.get('failure_source') or '<none>'}")

    return ", ".join(detail)
