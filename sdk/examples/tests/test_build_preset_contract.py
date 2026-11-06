"""CLI-only shell selection checks, using a fake idf.py instead of hardware."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "sdk/examples/build.sh"


class PresenceBuildSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.log = self.dir / "calls.txt"
        self.env_log = self.dir / "preset-env.txt"
        mock = self.dir / "idf.py"
        mock.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$*" >> "$MMWK_TEST_BUILD_LOG"\n'
            'printf "%s\\n" "${MMWK_STAGE1_PRESET-UNSET}" >> "$MMWK_TEST_ENV_LOG"\n')
        mock.chmod(0o755)
        self.env = {**os.environ, "PATH": str(self.dir) + os.pathsep + os.environ.get("PATH", ""),
                    "MMWK_TEST_BUILD_LOG": str(self.log),
                    "MMWK_TEST_ENV_LOG": str(self.env_log)}

    def run_build(self, *args):
        return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True,
                              text=True, env=self.env)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_native_host_runner_never_invokes_target_or_publisher(self):
        runner = ROOT / "sdk/examples/tests/run_host_checks.sh"
        self.assertTrue(runner.is_file())
        script = runner.read_text()
        self.assertIn("unittest discover", script)
        self.assertIn("PYTHONDONTWRITEBYTECODE=1", script)
        self.assertNotIn("idf.py build", script)
        self.assertNotIn("release_publisher.py", script)

    def test_legacy_default_entry_stays_compatible(self):
        run = self.run_build("presence", "mini")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(self.calls()), 1)
        self.assertIn("/build/presence/mini", self.calls()[0])
        self.assertNotIn("/build/presence/mini/default", self.calls()[0])

    def test_legacy_build_ignores_stale_inherited_stage1_selection(self):
        self.env["MMWK_STAGE1_PRESET"] = "offline"
        self.env["MMWK_STAGE1_BOARD"] = "wdr"
        self.env["MMWK_STAGE1_ABI"] = "untrusted"
        self.env["MMWK_STAGE1_LOCK_FILE"] = "/nonexistent.lock"
        outcome = self.run_build("presence", "mini")
        self.assertEqual(outcome.returncode, 0, outcome.stderr)
        self.assertEqual(self.env_log.read_text().splitlines(), ["default"])
        self.assertEqual(len(self.calls()), 1)
        self.assertIn("MMWK_STAGE1_PRESET=default", self.calls()[0])
        self.assertNotIn("MMWK_STAGE1_BOARD=wdr", self.calls()[0])

    def test_explicit_default_isolated_output(self):
        run = self.run_build("presence", "pro", "--preset", "default")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("/build/presence/pro/default", self.calls()[0])
        self.assertIn("set-target esp32s3 build", self.calls()[0])

    def test_old_package_rejects_unimplemented_presets(self):
        for name in ("offline", "local-control", "wifi-data"):
            with self.subTest(name=name):
                result = self.run_build("presence", "wdr", "--preset", name)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("requires a verified aggregate package", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_all_legacy_boards_and_bad_preset(self):
        run = self.run_build("all")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(self.calls()), 3)
        bad = self.run_build("presence", "mini", "--preset", "future")
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("Unknown preset", bad.stderr)


if __name__ == "__main__":
    unittest.main()
