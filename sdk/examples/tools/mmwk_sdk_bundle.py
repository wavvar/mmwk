#!/usr/bin/env python3
"""Inspect and lock one local *new-format* MMWK aggregate SDK package.

This consumer-side checker has no dependency on a sibling SDK checkout or
MMWK host CLI. A matching hash is not a signature or proof of firmware build.
Legacy per-board packages remain valid only through legacy default entrypoints.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

FORMAT = "mmwk-sdk-aggregate-v2"
PROFILES = {
    "mini": ("esp32", 6843, "radar68xx"),
    "pro": ("esp32s3", 6843, "radar68xx"),
    "wdr": ("esp32s3", 6432, "radarl64xx"),
}
PRESETS = {
    "offline": {"core"},
    "local-control": {"core", "local_control"},
    "wifi-data": {"core", "network"},
    "default": {"core", "local_control", "network", "portal", "mqtt_control"},
}
LEGACY_ARCHIVES = (
    "components/mmwk_sdk/lib/mini/libmmwk_sdk.a",
    "components/mmwk_sdk/lib/pro/libmmwk_sdk.a",
    "components/mmwk_sdk/lib/wdr/libmmwk_sdk.a",
)


def parse_json(data: bytes) -> dict:
    def object_pairs(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("duplicate JSON key: " + key)
            obj[key] = value
        return obj
    def reject_constant(value):
        raise ValueError("non-finite JSON value: " + value)
    obj = json.loads(data, object_pairs_hook=object_pairs,
                     parse_constant=reject_constant)
    if type(obj) is not dict:
        raise ValueError("JSON root must be an object")
    return obj


def safe_path(root: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or name.startswith("/") or \
            "\\" in name or "\0" in name:
        raise ValueError("invalid SDK file path")
    parts = name.split("/")
    if any(x in ("", ".", "..", ".git", ".gitmodules", ".lfsconfig") for x in parts):
        raise ValueError("unsafe SDK file path: " + name)
    candidate = root
    for part in parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError("symlink forbidden in SDK file path: " + name)
    if not candidate.is_file() or not candidate.resolve().is_relative_to(root):
        raise ValueError("missing or outside SDK file: " + name)
    return candidate


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def expected_hash(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{64}", value):
        raise ValueError("invalid SHA256 in SDK manifest")
    return value


def check_hash(root: Path, filename: str, digest: str) -> None:
    expected = expected_hash(digest)
    if sha256(safe_path(root, filename).read_bytes()) != expected:
        raise ValueError("SDK file digest mismatch: " + filename)


def check_record(root: Path, record: object) -> str:
    if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
        raise ValueError("SDK file record must contain only path and sha256")
    check_hash(root, record["path"], record["sha256"])
    return record["path"]


def inspect(root: Path, board: str, preset: str, abi: str) -> dict:
    root = root.resolve(strict=True)
    if board not in PROFILES:
        raise ValueError("unsupported public SDK board")
    if preset not in PRESETS:
        raise ValueError("unsupported preset")
    target, chip, family = PROFILES[board]
    manifest_raw = safe_path(root, "release-manifest.json").read_bytes()
    manifest = parse_json(manifest_raw)
    if manifest.get("schema") != 3 or manifest.get("format") != FORMAT:
        raise ValueError("not an aggregate SDK v2 package")
    if any((root / old).exists() or (root / old).is_symlink() for old in LEGACY_ARCHIVES):
        raise ValueError("mixed legacy and aggregate SDK libraries")
    groups = manifest.get("target_groups")
    board_map = manifest.get("boards")
    asset_pairs = manifest.get("asset_pairs")
    headers = manifest.get("headers")
    board_sources = manifest.get("board_sources")
    managed = manifest.get("managed_paths")
    if not all(type(x) is dict and x for x in
               (groups, board_map, asset_pairs, headers, board_sources)):
        raise ValueError("incomplete aggregate SDK manifest")
    if type(managed) is not list or not managed or len(set(managed)) != len(managed):
        raise ValueError("invalid managed paths")
    if any(not isinstance(x, str) for x in managed):
        raise ValueError("invalid managed path element")
    for name in managed:
        # Directories can contain more than the packaged payload, but an
        # explicitly managed file may not be absent or an unsafe symlink.
        safe_path(root, name)
    board_entry = board_map.get(board)
    if type(board_entry) is not dict or (
        board_entry.get("target"), board_entry.get("radar_chip"),
        board_entry.get("asset_family")
    ) != (target, chip, family):
        raise ValueError("board target, chip or resource family mismatch")
    caps = board_entry.get("capabilities")
    if type(caps) is not list or any(type(x) is not str for x in caps) or \
            len(set(caps)) != len(caps) or not PRESETS[preset] <= set(caps):
        raise ValueError("requested preset not supported by SDK board")
    group = groups.get(target)
    if type(group) is not dict or group.get("target") != target or \
            group.get("abi") != abi or board not in group.get("boards", []):
        raise ValueError("SDK target or ABI mismatch")
    archive = check_record(root, group.get("archive"))
    prefix = "components/mmwk_sdk/lib/" + target + "/"
    if not archive.startswith(prefix) or not archive.endswith("/libmmwk_sdk.a"):
        raise ValueError("unexpected aggregate library path")
    source_paths = []
    for name, digest in headers.items():
        if not name.startswith("components/mmwk_sdk/include/") or not name.endswith(".h"):
            raise ValueError("unapproved SDK public header path")
        check_hash(root, name, digest)
        source_paths.append(name)
    board_source_paths = []
    for name, digest in board_sources.items():
        if not name.startswith("components/mmwk_board/") or \
                not name.endswith((".c", ".h")):
            raise ValueError("unapproved board config source path")
        check_hash(root, name, digest)
        board_source_paths.append(name)
    if not any(x.endswith(".c") for x in board_source_paths) or not any(
        x.endswith("mmwk_board_config.h") for x in board_source_paths
    ):
        raise ValueError("board config C implementation/header is missing")
    pair = asset_pairs.get(family)
    if type(pair) is not dict or set(pair) != {"firmware", "config"}:
        raise ValueError("incomplete selected radar firmware/config pair")
    firmware, config = (check_record(root, pair[k]) for k in ("firmware", "config"))
    if firmware == config or not all(
        path.startswith("assets/" + family + "/") for path in (firmware, config)
    ):
        raise ValueError("mixed radar firmware/config resource family")
    required = {archive, firmware, config, *source_paths, *board_source_paths}
    if not required <= set(managed):
        raise ValueError("incomplete managed SDK paths")
    return {
        "schema": 1,
        "manifest_sha256": sha256(manifest_raw),
        "board": board, "target": target,
        "abi": abi, "preset": preset, "asset_family": family,
    }


def read_lock(lock_file: Path, expected: dict) -> None:
    old = parse_json(lock_file.read_bytes())
    if old != expected:
        raise ValueError("stale or mismatched mmwk-sdk.lock.json")


def create_lock(lock_file: Path, expected: dict) -> None:
    if lock_file.is_symlink() or lock_file.exists():
        raise ValueError("lock destination already exists (no implicit overwrite)")
    if not lock_file.parent.is_dir():
        raise ValueError("lock destination directory is missing")
    # For a normal local application we do not require lock storage inside the
    # package. The caller owns this explicit destination path.
    with lock_file.open("xb") as out:
        out.write((json.dumps(expected, sort_keys=True, indent=2) + "\n").encode())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--board", required=True, choices=PROFILES)
    parser.add_argument("--preset", required=True, choices=PRESETS)
    parser.add_argument("--abi", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check-lock", type=Path)
    group.add_argument("--create-lock", type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = inspect(args.sdk_root, args.board, args.preset, args.abi)
        if args.check_lock:
            read_lock(args.check_lock, receipt)
        else:
            create_lock(args.create_lock, receipt)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print("MMWK SDK bundle preflight failed: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps({"status": "PASS", **receipt}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
