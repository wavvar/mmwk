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
        script.write_text(f'include("{HELPER.as_posix()}")\n'
                          'presence_resolve_asset_profile("${RADAR_ROOT}")\n'
                          'message("RESULT:${PRESENCE_RADAR_FAMILY}:'
                          '${PRESENCE_RADAR_FW_NAME}:${PRESENCE_RADAR_CFG_NAME}:'
                          '${PRESENCE_RADAR_FID}")\n')
        self.script = script

    def probe(self, board, target, chip):
        return subprocess.run(
            ["cmake", f"-DCONFIG_RADAR_BOARD_{board}=y",
             f"-DCONFIG_RADAR_BOARD_NAME={board}",
             f"-DCONFIG_RADAR_BOARD_RADAR_CHIP={chip}",
             f"-DIDF_TARGET={target}", f"-DRADAR_ROOT={self.assets}",
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
