"""Helpers for reading radar firmware metadata from adjacent meta.json files."""

from dataclasses import dataclass
import json
import os
from typing import Optional


@dataclass(frozen=True)
class RadarUpdateRequest:
    welcome: bool
    verify: bool
    version: Optional[str]


def infer_radar_update_meta(fw_path: str) -> Optional[RadarUpdateRequest]:
    """Infer radar welcome/version metadata from a sibling meta.json."""
    if not fw_path:
        return None

    fw_name = os.path.basename(fw_path)
    fw_dir = os.path.dirname(os.path.abspath(fw_path))
    meta_path = os.path.join(fw_dir, "meta.json")
    if not os.path.exists(meta_path):
        return None

    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
    except Exception:
        return None

    fws = meta.get("fws", [])
    if not isinstance(fws, list):
        return None

    for item in fws:
        if not isinstance(item, dict):
            continue
        if item.get("firmware") != fw_name:
            continue
        welcome = item.get("welcome")
        if not isinstance(welcome, bool):
            return None

        version = item.get("version")
        resolved_version = None
        if isinstance(version, str) and version.strip():
            resolved_version = version.strip()

        return RadarUpdateRequest(
            welcome=welcome,
            verify=bool(welcome and resolved_version),
            version=resolved_version,
        )

    return None


def resolve_radar_update_request(fw_path: str, *, welcome=None,
                                 verify=None, version: Optional[str] = None) -> RadarUpdateRequest:
    """Resolve explicit/update metadata into a single request contract."""
    meta = infer_radar_update_meta(fw_path)

    resolved_welcome = welcome if isinstance(welcome, bool) else None
    if resolved_welcome is None and meta is not None:
        resolved_welcome = meta.welcome
    if resolved_welcome is None:
        raise ValueError("Missing radar welcome metadata; provide --welcome/--no-welcome or adjacent meta.json")

    resolved_version = None
    if isinstance(version, str) and version.strip():
        resolved_version = version.strip()
    elif verify is False:
        resolved_version = None
    elif meta is not None:
        resolved_version = meta.version

    if verify is None:
        resolved_verify = bool(resolved_welcome and resolved_version)
    else:
        resolved_verify = bool(verify)

    if resolved_verify and not resolved_welcome:
        raise ValueError("Version verification requires welcome=true")
    if resolved_verify and not resolved_version:
        raise ValueError("Version verification requires a version string")

    return RadarUpdateRequest(
        welcome=resolved_welcome,
        verify=resolved_verify,
        version=resolved_version,
    )


def infer_radar_version(fw_path: str) -> Optional[str]:
    """Backward-compatible wrapper for callers that only need version."""
    meta = infer_radar_update_meta(fw_path)
    return meta.version if meta else None
