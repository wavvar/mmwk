"""Mock-idf.py validation of direct flashing without the MMWK host CLI.

All generated build files live in a fresh temporary *copy* of the example
scripts. Never touch a user's actual firmware build or physical device.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "flash.sh"
CHECK = ROOT / "tools/verify_presence_flash.py"


class FlashScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.package = self.base / "package"
        (self.package / "presence").mkdir(parents=True)
        (self.package / "tools").mkdir()
        shutil.copyfile(SCRIPT, self.package / "flash.sh")
        shutil.copyfile(CHECK, self.package / "tools/verify_presence_flash.py")
        self.script = self.package / "flash.sh"
        fake_idf = self.base / "idf.py"
        fake_idf.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALL_LOG"\n')
        fake_idf.chmod(0o755)
        self.log = self.base / "calls"
        self.env = {**os.environ, "PATH": str(self.base) + os.pathsep + os.environ["PATH"],
                    "CALL_LOG": str(self.log)}

    def make_build(self, board="mini", explicit=False, assets=True):
        path = self.package / "build" / "presence" / board
        if explicit:
            path = path / "default"
        path.mkdir(parents=True)
        target = "esp32" if board == "mini" else "esp32s3"
        (path / "sdkconfig").write_text(
            f"CONFIG_RADAR_BOARD_{board.upper()}=y\n"
            f'CONFIG_IDF_TARGET="{target}"\n'
            "CONFIG_COMPILER_OPTIMIZATION_SIZE=y\n")
        (path / "bootloader.bin").write_bytes(b"boot")
        (path / "mmwk_presence_example.bin").write_bytes(b"application")
        images = {"0x0": "bootloader.bin", "0x10000": "mmwk_presence_example.bin"}
        if assets:
            (path / "assets.bin").write_bytes(b"radar assets")
            images["0x210000"] = "assets.bin"
        (path / "flasher_args.json").write_text(json.dumps({"flash_files": images}))
        return path

    def call(self, *args):
        return subprocess.run(["bash", str(self.script), *args], env=self.env,
                              text=True, capture_output=True)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_flash_monitor_from_legacy_build_dir(self):
        self.make_build()
        result = self.call("presence", "mini", "--port", "/dev/ttyUSB42", "--monitor")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"assets_included": true', result.stdout)
        self.assertEqual(len(self.calls()), 1)
        self.assertIn("-p /dev/ttyUSB42 flash monitor", self.calls()[0])
        self.assertIn("/build/presence/mini", self.calls()[0])

    def test_explicit_default_isolated_dir(self):
        self.make_build("pro", explicit=True)
        result = self.call("presence", "pro", "--port", "COM4",
                           "--preset", "default")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("/build/presence/pro/default", self.calls()[0])

    def test_monitor_only_never_flashes_or_requires_assets(self):
        path = self.make_build("wdr", assets=False)
        (path / "flasher_args.json").unlink()
        result = self.call("presence", "wdr", "--port", "/dev/ttyACM7",
                           "--monitor-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.calls()), 1)
        self.assertTrue(self.calls()[0].endswith("monitor"))
        self.assertNotIn(" flash ", " " + self.calls()[0] + " ")

    def test_missing_assets_prevents_flash(self):
        self.make_build(assets=False)
        result = self.call("presence", "mini", "--port", "/dev/ttyUSB42")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("assets.bin missing", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_mismatched_board_prevents_flash(self):
        path = self.make_build()
        cfg = path / "sdkconfig"
        cfg.write_text(cfg.read_text().replace("CONFIG_RADAR_BOARD_MINI=y",
                                              "CONFIG_RADAR_BOARD_PRO=y"))
        result = self.call("presence", "mini", "--port", "/dev/ttyUSB42")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("board configuration", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_missing_port_and_unimplemented_presets_refuse(self):
        for preset in ("offline", "wifi-data", "local-control"):
            with self.subTest(preset=preset):
                result = self.call("presence", "mini", "--port", "/dev/ttyUSB42",
                                   "--preset", preset)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("not enabled", result.stderr)
        result = self.call("presence", "mini")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--port is mandatory", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_flash_offset_alias_and_overlap_are_rejected_before_idf(self):
        path = self.make_build("mini")
        args_file = path / "flasher_args.json"
        args = json.loads(args_file.read_text())
        # Different JSON keys can express the same numeric flash offset.
        args["flash_files"]["65536"] = "assets.bin"
        args_file.write_text(json.dumps(args))
        duplicate = self.call("presence", "mini", "--port", "/dev/ttyUSB42")
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertIn("duplicate numeric flash offset", duplicate.stderr)
        self.assertEqual(self.calls(), [])

        args["flash_files"].pop("65536")
        (path / "bootloader.bin").write_bytes(b"A" * (0x10000 + 1))
        args_file.write_text(json.dumps(args))
        overlap = self.call("presence", "mini", "--port", "/dev/ttyUSB42")
        self.assertNotEqual(overlap.returncode, 0)
        self.assertIn("overlapping flash image ranges", overlap.stderr)
        self.assertEqual(self.calls(), [])

    def test_empty_unaligned_and_hidden_image_paths_rejected(self):
        path = self.make_build()
        args_file = path / "flasher_args.json"
        original = json.loads(args_file.read_text())
        for entry, expected in (
            ({"0x123": "bootloader.bin", "0x10000": "mmwk_presence_example.bin",
              "0x210000": "assets.bin"}, "unaligned flash offset"),
            ({"-1": "bootloader.bin", "0x10000": "mmwk_presence_example.bin",
              "0x210000": "assets.bin"}, "invalid flash offset"),
        ):
            with self.subTest(expected=expected):
                args_file.write_text(json.dumps({"flash_files": entry}))
                result = self.call("presence", "mini", "--port", "/dev/ttyUSB42")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)
        (path / "assets.bin").write_bytes(b"")
        args_file.write_text(json.dumps(original))
        failed = self.call("presence", "mini", "--port", "/dev/ttyUSB42")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("empty or oversized", failed.stderr)
        self.assertEqual(self.calls(), [])

    def test_in_tree_symlink_intermediate_directory_rejected(self):
        path = self.make_build()
        (path / "real").mkdir()
        (path / "real" / "assets.bin").write_bytes(b"firmware assets")
        (path / "alias").symlink_to(path / "real", target_is_directory=True)
        args_file = path / "flasher_args.json"
        args = json.loads(args_file.read_text())
        args["flash_files"]["0x210000"] = "alias/assets.bin"
        args_file.write_text(json.dumps(args))
        result = self.call("presence", "mini", "--port", "/dev/ttyUSB42")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink in flash image path", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_path_escape_in_flash_manifest_refuses(self):
        path = self.make_build()
        (path / "flasher_args.json").write_text(json.dumps(
            {"flash_files": {"0x0": "../outside.bin"}}))
        result = self.call("presence", "mini", "--port", "/dev/ttyUSB42")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe flash image path", result.stderr)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
