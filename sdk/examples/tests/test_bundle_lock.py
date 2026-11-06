"""Host-only package preflight tests, with a synthetic SDK v2 bundle."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "sdk/examples/tools/mmwk_sdk_bundle.py"
SPEC = importlib.util.spec_from_file_location("mmwk_sdk_bundle", TOOL)
bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle)


def digest(content):
    return hashlib.sha256(content).hexdigest()


class BundleLockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "sdk"
        self.root.mkdir()
        self.header = "components/mmwk_sdk/include/mmwk_sensor.h"
        self.board_header = "components/mmwk_board/include/mmwk_board_config.h"
        self.board_source = "components/mmwk_board/mmwk_board_config.c"
        self.lib = "components/mmwk_sdk/lib/esp32s3/os-idf553/libmmwk_sdk.a"
        self.fw = "assets/radarl64xx/presence.appimage"
        self.cfg = "assets/radarl64xx/presence.cfg"
        self.contents = {
            self.header: b"public sdk header",
            self.board_header: b"board header",
            self.board_source: b"board data",
            self.lib: b"the same archive for PRO/WDR",
            self.fw: b"6432 firmware",
            self.cfg: b"6432 config",
        }
        for name, content in self.contents.items():
            file = self.root / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(content)
        self.manifest = {
            "schema": 3, "format": "mmwk-sdk-aggregate-v2",
            "board_config_abi": 2,
            "target_groups": {"esp32s3": {
                "target": "esp32s3", "abi": "os-idf553",
                "boards": ["pro", "wdr"],
                "archive": {"path": self.lib, "sha256": digest(self.contents[self.lib])},
            }},
            "boards": {"wdr": {
                "target": "esp32s3", "radar_chip": 6432,
                "asset_family": "radarl64xx",
                "capabilities": ["core", "network", "local_control", "portal", "mqtt_control"],
            }},
            "headers": {self.header: digest(self.contents[self.header])},
            "board_sources": {
                self.board_header: digest(self.contents[self.board_header]),
                self.board_source: digest(self.contents[self.board_source]),
            },
            "asset_pairs": {"radarl64xx": {
                "firmware": {"path": self.fw, "sha256": digest(self.contents[self.fw])},
                "config": {"path": self.cfg, "sha256": digest(self.contents[self.cfg])},
            }},
            "managed_paths": list(self.contents),
            "file_sha256": {name: digest(blob) for name, blob in self.contents.items()},
        }

    def put_manifest(self, obj=None):
        (self.root / "release-manifest.json").write_text(json.dumps(
            self.manifest if obj is None else obj, sort_keys=True))

    def inspect(self, manifest=None, preset="offline"):
        self.put_manifest(manifest)
        return bundle.inspect(self.root, "wdr", preset, "os-idf553")

    def test_rejects_wrong_board_configuration_abi(self):
        import copy
        for value in (1, "2", True, None):
            with self.subTest(value=value):
                spec = copy.deepcopy(self.manifest)
                spec["board_config_abi"] = value
                with self.assertRaisesRegex(ValueError, "board configuration ABI"):
                    self.inspect(spec)

    def test_good_bundle_and_exact_consumer_lock(self):
        lock = self.root.parent / "mmwk-sdk.lock.json"
        expected = self.inspect()
        self.assertEqual(expected["board"], "wdr")
        bundle.create_lock(lock, expected)
        bundle.read_lock(lock, self.inspect())
        self.assertEqual(lock.read_text().count('"manifest_sha256"'), 1)
        with self.assertRaisesRegex(ValueError, "exists"):
            bundle.create_lock(lock, expected)
        wrong = {**expected, "preset": "wifi-data"}
        with self.assertRaisesRegex(ValueError, "mismatched"):
            bundle.read_lock(lock, wrong)

    def test_selected_caps_and_abi(self):
        self.inspect(preset="wifi-data")
        self.inspect(preset="local-control")
        self.inspect(preset="default")
        spec = copy.deepcopy(self.manifest)
        spec["boards"]["wdr"]["capabilities"] = ["core"]
        with self.assertRaisesRegex(ValueError, "not supported"):
            self.inspect(spec, preset="default")
        with self.assertRaisesRegex(ValueError, "ABI mismatch"):
            self.inspect_with_abi("incompatible")

    def inspect_with_abi(self, abi):
        self.put_manifest()
        return bundle.inspect(self.root, "wdr", "offline", abi)

    def test_resource_pair_and_public_board_sources(self):
        spec = copy.deepcopy(self.manifest)
        spec["asset_pairs"]["radarl64xx"]["firmware"]["path"] = self.cfg
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.inspect(spec)
        spec = copy.deepcopy(self.manifest)
        spec["board_sources"].pop(self.board_source)
        with self.assertRaisesRegex(ValueError, "board config C"):
            self.inspect(spec)
        spec = copy.deepcopy(self.manifest)
        spec["managed_paths"].remove(self.board_header)
        with self.assertRaisesRegex(ValueError, "incomplete managed"):
            self.inspect(spec)

    def test_full_managed_file_inventory_detects_unselected_tampering(self):
        extra = "components/mmwk_sdk/CMakeLists.txt"
        data = b"reviewed CMake payload"
        path = self.root / extra
        path.write_bytes(data)
        manifest = copy.deepcopy(self.manifest)
        manifest["managed_paths"].append(extra)
        manifest["file_sha256"][extra] = digest(data)
        self.inspect(manifest)
        path.write_bytes(b"unreviewed CMake change")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.inspect(manifest)
        manifest["file_sha256"].pop(extra)
        with self.assertRaisesRegex(ValueError, "SHA256 inventory"):
            self.inspect(manifest)

    def test_wrong_hash_set_and_malformed_managed_items_fail_closed(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["file_sha256"].pop(self.lib)
        with self.assertRaisesRegex(ValueError, "SHA256 inventory"):
            self.inspect(manifest)
        manifest = copy.deepcopy(self.manifest)
        manifest["managed_paths"].append({"path": "../oops"})
        with self.assertRaisesRegex(ValueError, "invalid managed"):
            self.inspect(manifest)
        manifest = copy.deepcopy(self.manifest)
        manifest["managed_paths"].append(self.lib.swapcase())
        with self.assertRaisesRegex(ValueError, "invalid managed"):
            self.inspect(manifest)

    def test_corrupted_archive_and_missing_assets(self):
        (self.root / self.lib).write_bytes(b"unexpected library")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.inspect()
        (self.root / self.lib).write_bytes(self.contents[self.lib])
        (self.root / self.cfg).unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            self.inspect()

    def test_legacy_mix_and_symlink_attack(self):
        legacy = self.root / "components/mmwk_sdk/lib/wdr/libmmwk_sdk.a"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_bytes(b"legacy")
        with self.assertRaisesRegex(ValueError, "mixed legacy"):
            self.inspect()
        legacy.unlink()
        target = self.root / self.fw
        target.unlink()
        target.symlink_to(self.root / self.cfg)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.inspect()

    def test_hidden_and_windows_alias_paths_fail_consumer_preflight(self):
        for name in (
            "C:/bad/driver.h",
            "components/mmwk_sdk/include/.private.h",
            "components/mmwk_sdk/.cache/hidden",
            "components/mmwk_sdk/include/colon:file.h",
            "components/mmwk_sdk/include/nul\x00byte.h",
        ):
            with self.subTest(name=repr(name)):
                with self.assertRaisesRegex(ValueError, "unsafe|invalid"):
                    bundle.safe_path(self.root, name)

    def test_bad_manifest_syntax_or_unsafe_path(self):
        self.put_manifest()
        (self.root / "release-manifest.json").write_bytes(b'{"schema":3,"schema":3}')
        with self.assertRaisesRegex(ValueError, "duplicate JSON"):
            bundle.inspect(self.root, "wdr", "offline", "os-idf553")
        spec = copy.deepcopy(self.manifest)
        spec["managed_paths"].append("../escape")
        with self.assertRaisesRegex(ValueError, "unsafe"):
            self.inspect(spec)

    def test_exact_owned_inventory_rejects_extra_sdk_header_archive_and_link(self):
        self.inspect()
        native = self.root / "examples/presence/main/main.c"
        native.parent.mkdir(parents=True, exist_ok=True)
        native.write_bytes(b"native example is not SDK-managed")
        self.inspect()
        for name in (
            "components/mmwk_sdk/include/unlisted.h",
            "components/mmwk_sdk/lib/esp32s3/rogue/libmmwk_sdk.a",
            "components/mmwk_board/include/extra.h",
            "assets/radarl64xx/hidden.cfg",
        ):
            with self.subTest(name=name):
                path = self.root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"untracked")
                with self.assertRaisesRegex(ValueError, "exact managed file inventory"):
                    self.inspect()
                path.unlink()
        link = self.root / "components/mmwk_sdk/include/alias.h"
        link.symlink_to(self.root / self.header)
        with self.assertRaisesRegex(ValueError, "symlink in SDK-owned payload"):
            self.inspect()

    def test_cli_create_check_and_bad_lock(self):
        self.put_manifest()
        lock = self.root.parent / "customer.lock.json"
        cmd = [sys.executable, str(TOOL), "--sdk-root", str(self.root),
               "--board", "wdr", "--preset", "offline", "--abi", "os-idf553"]
        made = subprocess.run(cmd + ["--create-lock", str(lock)], capture_output=True, text=True)
        self.assertEqual(made.returncode, 0, made.stderr)
        self.assertEqual(json.loads(made.stdout)["status"], "PASS")
        check = subprocess.run(cmd + ["--check-lock", str(lock)], capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stderr)
        lock.write_text('{"schema":1}')
        fail = subprocess.run(cmd + ["--check-lock", str(lock)], capture_output=True, text=True)
        self.assertNotEqual(fail.returncode, 0)
        self.assertIn("lock", fail.stderr)


if __name__ == "__main__":
    unittest.main()
