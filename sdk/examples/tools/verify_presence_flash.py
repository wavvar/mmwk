#!/usr/bin/env python3
"""Fail-closed ESP-IDF presence flash manifest preflight (no MMWK CLI)."""
import argparse
import json
from pathlib import Path
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
    images = []
    for offset, relative in flash_files.items():
        try:
            int(offset, 0)
        except (TypeError, ValueError):
            fail("invalid flash offset")
        if not isinstance(relative, str) or not relative or relative.startswith("/"):
            fail("unsafe flash image path")
        parts = relative.split("/")
        if any(part in ("", ".", "..") for part in parts) or "\\" in relative:
            fail("unsafe flash image path")
        path = build_dir.joinpath(*parts)
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(build_dir):
            fail("flash image missing or outside build: " + relative)
        images.append(path.name)
    if "assets.bin" not in images:
        fail("first-flash radar assets.bin missing from flash_files")
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
