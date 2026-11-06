#!/usr/bin/env python3
"""Fail-closed ESP-IDF presence flash manifest preflight (no MMWK CLI)."""
import argparse
import json
from pathlib import Path
import re
import sys

BOARD_TARGET = {"mini": "esp32", "pro": "esp32s3", "wdr": "esp32s3"}


def fail(message):
    raise ValueError(message)


def check(build_dir: Path, board: str, action: str):
    if board not in BOARD_TARGET:
        fail("unsupported radar board")
    if action not in {"flash", "flash-monitor", "monitor"}:
        fail("unsupported flash action")
    build_dir = Path(build_dir).resolve(strict=True)
    if not build_dir.is_dir():
        fail("build directory is missing")
    config = build_dir / "sdkconfig"
    if not config.is_file() or config.is_symlink():
        fail("missing build sdkconfig; run build.sh for this board first")
    # Inspect the *built* sdkconfig rather than mutable sdkconfig.defaults.
    lines = set(config.read_text(encoding="utf-8").splitlines())
    target = BOARD_TARGET[board]
    selected_boards = {b for b in BOARD_TARGET if f"CONFIG_RADAR_BOARD_{b.upper()}=y" in lines}
    if selected_boards != {board}:
        fail("firmware board configuration does not match explicit board")
    if not ({f'CONFIG_IDF_TARGET="{target}"',
             f'CONFIG_IDF_TARGET_{target.upper()}=y'} & lines):
        fail("firmware ESP target does not match board")
    if "CONFIG_COMPILER_OPTIMIZATION_SIZE=y" not in lines:
        fail("SDK library requires CONFIG_COMPILER_OPTIMIZATION_SIZE=y")
    if action == "monitor":
        return {"board": board, "target": target, "action": action}

    args_file = build_dir / "flasher_args.json"
    if not args_file.is_file() or args_file.is_symlink():
        fail("missing flasher_args.json; build presence before flashing")
    try:
        args = json.loads(args_file.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        fail(f"invalid flasher_args.json: {exc}")
    flash_files = args.get("flash_files")
    if not isinstance(flash_files, dict) or not flash_files:
        fail("flasher_args.json contains no flash_files")
    # ESP-IDF normally uses hex offsets. Decimal aliases must not allow two
    # distinct dictionary keys to write the same address. Reject overlap,
    # invalid image bytes, or a path that traverses an in-tree symlink.
    images = []
    ranges = []
    seen_offsets = set()
    seen_paths = set()
    for offset, relative in flash_files.items():
        if not isinstance(offset, str) or not re.fullmatch(
            r"(?:0[xX][0-9a-fA-F]+|[1-9][0-9]*|0)", offset
        ):
            fail("invalid flash offset")
        address = int(offset, 0 if offset.lower().startswith("0x") else 10)
        if address < 0 or address > 0xFFFFFFFF or address % 0x1000:
            fail("invalid or unaligned flash offset")
        if address in seen_offsets:
            fail("duplicate numeric flash offset")
        seen_offsets.add(address)
        if not isinstance(relative, str) or not relative or relative.startswith("/"):
            fail("unsafe flash image path")
        parts = relative.split("/")
        if any(part in ("", ".", "..") or part.startswith(".")
               for part in parts) or "\\" in relative or "\x00" in relative:
            fail("unsafe flash image path")
        if relative in seen_paths:
            fail("duplicate flash image path")
        seen_paths.add(relative)
        path = build_dir
        for part in parts:
            path = path / part
            if path.is_symlink():
                fail("symlink in flash image path")
        if not path.is_file() or not path.resolve().is_relative_to(build_dir):
            fail("flash image missing or outside build: " + relative)
        size = path.stat().st_size
        if size <= 0 or size > 0x100000000 - address:
            fail("empty or oversized flash image: " + relative)
        images.append(path.name)
        ranges.append((address, address + size, relative))
    ranges.sort()
    for left, right in zip(ranges, ranges[1:]):
        if left[1] > right[0]:
            fail("overlapping flash image ranges: " + left[2] + " / " + right[2])
    if images.count("assets.bin") != 1:
        fail("first-flash radar assets.bin missing or duplicated in flash_files")
    if not any(name.endswith(".bin") and name not in {
        "assets.bin", "bootloader.bin", "partition-table.bin"
    } for name in images):
        fail("application flash image missing")
    return {"board": board, "target": target, "action": action,
            "flash_image_count": len(images), "assets_included": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--board", choices=BOARD_TARGET, required=True)
    parser.add_argument("--action", choices=("flash", "flash-monitor", "monitor"), required=True)
    options = parser.parse_args()
    try:
        result = check(options.build_dir, options.board, options.action)
    except (ValueError, OSError) as exc:
        print(f"presence flash preflight rejected: {exc}", file=sys.stderr)
        return 2
    print("presence flash preflight: " + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
