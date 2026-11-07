"""Use CMake script mode to exercise the real consumer-side asset catalog.

No IDF, private sibling checkout, network, hardware, or publisher required.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "sdk/examples/presence/presence_asset_profiles.cmake"
PROJECT = ROOT / "sdk/examples/presence/CMakeLists.txt"


class PresenceAssetCMakeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.assets = self.directory / "firmwares/radar"
        for filename in (
            "iwr6843/oob/out_of_box_6843_aop.bin",
            "iwr6843/oob/out_of_box_6843_aop.cfg",
            "iwrl6432/presence/presence.appimage",
            "iwrl6432/presence/presence.cfg",
        ):
            file = self.assets / filename
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b"fixture")
        script = self.directory / "probe.cmake"
        self.aggregate = self.directory / "sdk/assets"
        for filename in (
            "radar68xx/out_of_box_6843_aop.bin",
            "radar68xx/out_of_box_6843_aop.cfg",
            "radarl64xx/presence.appimage",
            "radarl64xx/presence.cfg",
        ):
            file = self.aggregate / filename
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b"locked aggregate bytes")
        script.write_text(f'include("{HELPER.as_posix()}")\n'
                          'presence_resolve_asset_profile("${RADAR_ROOT}")\n'
                          'presence_resolve_asset_staging_dir("${STAGING_ROOT}" '
                          '"${PRESENCE_RADAR_FAMILY}" "${PRESENCE_RADAR_FW_SRC}" '
                          '"${PRESENCE_RADAR_CFG_SRC}" STAGE_DIR)\n'
                          'message("STAGED:${STAGE_DIR}")\n'
                          'message("RESULT:${PRESENCE_RADAR_FAMILY}:'
                          '${PRESENCE_RADAR_FW_NAME}:${PRESENCE_RADAR_CFG_NAME}:'
                          '${PRESENCE_RADAR_FID}")\n')
        self.script = script

    def probe(self, board, target, chip, aggregate=False, root=None):
        return subprocess.run(
            ["cmake", f"-DCONFIG_RADAR_BOARD_{board}=y",
             f"-DCONFIG_RADAR_BOARD_NAME={board}",
             f"-DCONFIG_RADAR_BOARD_RADAR_CHIP={chip}",
             f"-DIDF_TARGET={target}",
             f"-DMMWK_PRESENCE_AGGREGATE_ASSETS={'ON' if aggregate else 'OFF'}",
             f"-DRADAR_ROOT={root or (self.aggregate if aggregate else self.assets)}",
             f"-DSTAGING_ROOT={self.directory / 'output'}",
             "-P", str(self.script)],
            capture_output=True, text=True)

    def test_approved_board_resources_and_firmware_ids(self):
        for board, target, chip, expected in (
            ("MINI", "esp32", 6843,
             "RESULT:radar68xx:out_of_box_6843_aop.bin:out_of_box_6843_aop.cfg:2"),
            ("PRO", "esp32s3", 6843,
             "RESULT:radar68xx:out_of_box_6843_aop.bin:out_of_box_6843_aop.cfg:2"),
            ("WDR", "esp32s3", 6432,
             "RESULT:radarl64xx:presence.appimage:presence.cfg:1"),
        ):
            with self.subTest(board=board):
                result = self.probe(board, target, chip)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, result.stderr)

    def test_staging_rejects_links_directories_and_hidden_bytes(self):
        check = self.directory / "verify-staging.cmake"
        check.write_text(f'include("{HELPER.as_posix()}")\n'
                         'presence_validate_asset_staging("${DIR}" "firmware.bin" "config.cfg")\n')
        staging = self.directory / "staged"
        staging.mkdir()
        def verify():
            return subprocess.run(
                ["cmake", f"-DDIR={staging}", "-P", str(check)],
                capture_output=True, text=True)
        self.assertEqual(verify().returncode, 0)
        for name in ("firmware.bin", "config.cfg", "meta.json"):
            (staging / name).write_bytes(b"reviewed")
        self.assertEqual(verify().returncode, 0)
        old = staging / "meta.json"
        old.unlink()
        old.symlink_to(self.directory / "outside")
        self.assertIn("unsafe link", verify().stderr)
        old.unlink()
        (staging / ".hidden").write_bytes(b"extra")
        self.assertIn("unexpected firmware file", verify().stderr)
        (staging / ".hidden").unlink()
        (staging / "config.cfg").unlink()
        (staging / "config.cfg").mkdir()
        self.assertIn("unsafe link or directory", verify().stderr)

    def test_staging_directory_changes_with_input_content(self):
        from re import search
        def stage(result):
            self.assertEqual(result.returncode, 0, result.stderr)
            match = search(r"STAGED:([^\r\n]+)", result.stderr)
            self.assertIsNotNone(match)
            return match.group(1)
        old = stage(self.probe("WDR", "esp32s3", 6432, aggregate=True))
        self.assertIn("/presence_assets/radarl64xx/", old)
        (self.aggregate / "radarl64xx/presence.cfg").write_bytes(b"new cfg")
        cfg_changed = stage(self.probe("WDR", "esp32s3", 6432, aggregate=True))
        self.assertNotEqual(cfg_changed, old)
        (self.aggregate / "radarl64xx/presence.appimage").write_bytes(b"new firmware")
        fw_changed = stage(self.probe("WDR", "esp32s3", 6432, aggregate=True))
        self.assertNotEqual(fw_changed, cfg_changed)
        legacy = stage(self.probe("WDR", "esp32s3", 6432))
        self.assertNotEqual(legacy, fw_changed)
        mini = stage(self.probe("MINI", "esp32", 6843, aggregate=True))
        pro = stage(self.probe("PRO", "esp32s3", 6843, aggregate=True))
        self.assertEqual(mini, pro)

    def test_spi_flash_staging_checks_stale_or_extra_files(self):
        source = PROJECT.read_text()
        self.assertIn("presence_resolve_asset_staging_dir(", source)
        self.assertIn("unexpected firmware file in SPIFFS staging", HELPER.read_text())
        self.assertIn("presence_validate_asset_staging(", source)
        self.assertIn("SPIFFS staging does not match locked source firmware/config", source)
        self.assertIn("file(SHA256", source)

    def test_aggregate_uses_package_assets_and_never_falls_back_to_native(self):
        for board, target, chip in (
            ("MINI", "esp32", 6843), ("PRO", "esp32s3", 6843),
            ("WDR", "esp32s3", 6432),
        ):
            with self.subTest(board=board):
                result = self.probe(board, target, chip, aggregate=True)
                self.assertEqual(result.returncode, 0, result.stderr)
        (self.aggregate / "radarl64xx/presence.cfg").unlink()
        rejected = self.probe("WDR", "esp32s3", 6432, aggregate=True)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("firmware/config pair missing", rejected.stderr)
        wrong_root = self.probe("WDR", "esp32s3", 6432, aggregate=True,
                                root=self.assets)
        self.assertNotEqual(wrong_root.returncode, 0)

    def test_aggregate_asset_symlink_is_not_accepted(self):
        path = self.aggregate / "radarl64xx/presence.cfg"
        path.unlink()
        path.symlink_to(self.assets / "iwrl6432/presence/presence.cfg")
        result = self.probe("WDR", "esp32s3", 6432, aggregate=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlinked radar firmware/config", result.stderr)

    def test_real_project_selects_aggregate_root_only_with_manifest(self):
        source = PROJECT.read_text()
        self.assertIn("MMWK_PRESENCE_AGGREGATE_ASSETS ON", source)
        self.assertIn("MMWK_USER_SDK_ROOT}/assets", source)
        self.assertIn("linked aggregate SDK manifest is forbidden", source)
        self.assertIn("non-default capability requires a verified aggregate SDK", source)

    def test_wrong_target_or_chip_or_unknown_board_rejected(self):
        for board, target, chip in (
            ("WDR", "esp32s3", 6843),
            ("WDR", "esp32", 6432),
            ("PRO", "esp32s3", 6432),
            ("MINI", "esp32s3", 6843),
            ("IOT", "esp32s3", 6843),
        ):
            with self.subTest(board=board, target=target, chip=chip):
                result = self.probe(board, target, chip)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("presence:", result.stderr)

    def test_missing_firmware_config_pair_blocks_packaging(self):
        (self.assets / "iwrl6432/presence/presence.cfg").unlink()
        result = self.probe("WDR", "esp32s3", 6432)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("firmware/config pair missing", result.stderr)

    def test_no_neighbor_checkout_fallback(self):
        source = PROJECT.read_text()
        self.assertIn("presence_resolve_asset_profile", source)
        self.assertNotIn("MMWK_PRIVATE_REPO_ROOT", source)
        self.assertIn("spiffs_create_partition_image(assets", source)


if __name__ == "__main__":
    unittest.main()
