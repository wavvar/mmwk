"""Source guard: native presence has one static radar backend linker root.

This does not claim a built public aggregate or real ESP target linking.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "sdk/examples/presence/main/main.c"


class PresenceBackendBindingTests(unittest.TestCase):
    def test_selected_descriptor_is_public_and_not_an_sdk_registry(self):
        source = SOURCE.read_text()
        self.assertIn("#ifdef MMWK_SENSOR_STARTUP_SPI_BACKEND_POLICY_V1", source)
        self.assertIn("startup.spi_backend = &mmwk_driver_spi_backend_xwrl6432;", source)
        self.assertIn("startup.spi_backend = &mmwk_driver_spi_backend_xwr6843;", source)
        self.assertNotIn("mmwk_driver_spi_backend_registry", source)
        self.assertLess(source.index("startup.spi_backend ="), source.index("mmwk_sensor_bridge_run("))

    def test_preprocessor_selects_one_symbol_or_legacy_none(self):
        source = SOURCE.read_text()
        start = source.index("#ifdef MMWK_SENSOR_STARTUP_SPI_BACKEND_POLICY_V1")
        end = source.index("#endif\n    ESP_ERROR_CHECK(presence_ui_configure", start)
        snippet = source[start:end + len("#endif")]
        with tempfile.TemporaryDirectory() as folder:
            tmp = Path(folder)
            unit = tmp / "selection.c"
            unit.write_text(
                "struct startup_t {const void *spi_backend;};\n"
                "struct startup_t startup;\n"
                "extern int mmwk_driver_spi_backend_xwrl6432;\n"
                "extern int mmwk_driver_spi_backend_xwr6843;\n"
                + snippet + "\n")
            for chip, expected in ((6432, "xwrl6432"), (6843, "xwr6843")):
                args = ["cc", "-E", "-P", "-DMMWK_SENSOR_STARTUP_SPI_BACKEND_POLICY_V1=1",
                        f"-DCONFIG_RADAR_BOARD_RADAR_CHIP={chip}", str(unit)]
                result = subprocess.run(args, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                lines = [x for x in result.stdout.splitlines()
                         if x.strip().startswith("startup.spi_backend =")]
                self.assertEqual(len(lines), 1)
                self.assertIn(expected, lines[0])
            legacy = subprocess.run(["cc", "-E", "-P", str(unit)], capture_output=True, text=True)
            self.assertEqual(legacy.returncode, 0, legacy.stderr)
            self.assertNotIn("startup.spi_backend =", legacy.stdout)
            invalid = subprocess.run(
                ["cc", "-E", "-P", "-DMMWK_SENSOR_STARTUP_SPI_BACKEND_POLICY_V1=1",
                 "-DCONFIG_RADAR_BOARD_RADAR_CHIP=9999", str(unit)],
                capture_output=True, text=True)
            self.assertNotEqual(invalid.returncode, 0)
            self.assertIn("approved radar SPI backend", invalid.stderr)


if __name__ == "__main__":
    unittest.main()
