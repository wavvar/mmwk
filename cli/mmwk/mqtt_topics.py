"""Canonical MMWK MQTT topic derivation."""

from __future__ import annotations

import re


_HEX_MAC_RE = re.compile(r"^[0-9a-f]{12}$")


def normalize_topic_id(value: str) -> str:
    """Normalize a topic id to the canonical lowercase MAC form when possible."""

    topic_id = str(value or "").strip().lower()
    if not topic_id:
        raise ValueError("MQTT topic id is required")

    if topic_id.startswith("mmwk_"):
        suffix = topic_id[5:]
        if _HEX_MAC_RE.fullmatch(suffix):
            return suffix

    compact = topic_id.replace(":", "").replace("-", "")
    if _HEX_MAC_RE.fullmatch(compact):
        return compact

    return topic_id


def build_mqtt_topics(topic_id: str, include_raw_cmd: bool = True) -> dict[str, str]:
    """Build the canonical mmwk/{id}/{domain}/{action} topic map."""

    client_id = normalize_topic_id(topic_id)
    topics = {
        "client_id": client_id,
        "cmd_topic": f"mmwk/{client_id}/device/cmd",
        "resp_topic": f"mmwk/{client_id}/device/resp",
        "hub_inquiry_topic": f"mmwk/{client_id}/hub/inquiry",
        "hub_config_topic": f"mmwk/{client_id}/hub/config",
        "raw_data_topic": f"mmwk/{client_id}/raw/data",
        "raw_resp_topic": f"mmwk/{client_id}/raw/resp",
        "raw_cmd_topic": f"mmwk/{client_id}/raw/cmd" if include_raw_cmd else "",
    }
    return topics
