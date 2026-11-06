"""Compile the real consumer-owned asset table for approved and invalid board profiles.

Host GCC proves descriptor selection and fail-closed behavior, not actual firmware.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "sdk/examples/presence/main/presence_radar_assets.c"
PROBE = Path(__file__).resolve().parent / "presence_assets_check.c"


class AssetProviderTests(unittest.TestCase):
    def test_three_supported_and_five_rejected_combinations(self):
        cases = (
            ("MINI", "esp32", 6843, False),
            ("PRO", "esp32s3", 6843, False),
            ("WDR", "esp32s3", 6432, False),
            ("WDR", "esp32", 6432, True),
            ("PRO", "esp32s3", 6432, True),
            ("MINI", "esp32s3", 6843, True),
            ("OTHER", "esp32s3", 6843, True),
            ("WDR", "esp32s3", 9999, True),
        )
        with tempfile.TemporaryDirectory() as dirname:
            tmp = Path(dirname)
            (tmp / "sdkconfig.h").write_text("#pragma once\n")
            for board, target, chip, invalid in cases:
                with self.subTest(board=board, target=target, chip=chip):
                    name = "CONFIG_IDF_TARGET_ESP32" if target == "esp32" else "CONFIG_IDF_TARGET_ESP32S3"
                    flags = [f'-DCONFIG_RADAR_BOARD_NAME="{board}"',
                             f"-DCONFIG_RADAR_BOARD_RADAR_CHIP={chip}",
                             f"-D{name}=1"]
                    if invalid:
                        flags.append("-DEXPECT_INVALID=1")
                    output = tmp / "probe"
                    compilation = subprocess.run(
                        ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                         "-I", str(tmp), "-I", str(SOURCE.parent), *flags,
                         str(SOURCE), str(PROBE), "-o", str(output)],
                        capture_output=True, text=True)
                    self.assertEqual(compilation.returncode, 0, compilation.stderr)
                    run = subprocess.run([str(output)], capture_output=True, text=True)
                    self.assertEqual(run.returncode, 0, run.stderr)

    def test_application_rejects_mismatched_pair_before_runtime_start(self):
        main = (SOURCE.parent / "main.c").read_text()
        self.assertIn("presence_radar_assets_current()", main)
        self.assertIn("if (!assets)", main)
        self.assertLess(main.index("if (!assets)"),
                        main.index("mmwk_sensor_bridge_run("))


if __name__ == "__main__":
    unittest.main()
