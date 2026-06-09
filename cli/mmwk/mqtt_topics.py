"""Canonical MMWK MQTT topic route derivation."""

from __future__ import annotations


def _segment(name: str, value: str | None, *, required: bool = True) -> str:
    segment = str(value or "").strip()
    if not segment:
        if required:
            raise ValueError(f"{name} is required")
        return ""
    if "/" in segment or "\x00" in segment:
        raise ValueError(f"{name} must be a single MQTT topic segment")
    return segment


def normalize_topic_id(value: str) -> str:
    """Validate a topic id import without normalizing its value."""

    return _segment("topic_id", value)


def build_mqtt_topics(
    *,
    prod: str = "mmwk",
    oid: str = "mmwk",
    cid: str = "",
    did: str = "",
    include_raw_cmd: bool = True,
) -> dict[str, str]:
    """Build {prod}/{oid}/{cid_or_did}/{plane}/{action} topic map."""

    product = _segment("prod", prod)
    org = _segment("oid", oid)
    claimed_id = _segment("cid", cid, required=False)
    local_id = _segment("did", did, required=False)
    topic_id = claimed_id or local_id
    if not topic_id:
        raise ValueError("cid or did is required")

    prefix = f"{product}/{org}/{topic_id}"
    return {
        "prod": product,
        "oid": org,
        "cid": claimed_id,
        "did": local_id,
        "cmd": f"{prefix}/device/cmd",
        "resp": f"{prefix}/device/resp",
        "hub_inquiry": f"{prefix}/hub/inquiry",
        "hub_config": f"{prefix}/hub/config",
        "raw_data": f"{prefix}/raw/data",
        "raw_resp": f"{prefix}/raw/resp",
        "raw_cmd": f"{prefix}/raw/cmd" if include_raw_cmd else "",
        "stream_in": f"{prefix}/stream/in",
    }
