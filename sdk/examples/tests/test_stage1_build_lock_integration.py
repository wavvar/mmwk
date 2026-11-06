"""Run the actual presence build entry with a synthetic v2 package and fake idf.py.

The package verifier runs *for real*. Only idf.py is mocked; no target image
is built. Tests require a valid pinned per-board lock before invoking IDF.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "sdk/examples/build.sh"
BUNDLE = REPO / "sdk/examples/tools/mmwk_sdk_bundle.py"
SPEC = importlib.util.spec_from_file_location("stage1_consumer_bundle", BUNDLE)
bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle)


class Stage1BuildLockTests(unittest.TestCase):
    def setUp(self):
        # The manifest/asset files are synthetic, not firmware. Reuse the
        # existing package fixture rather than rewriting its hash policy.
        import test_bundle_lock as fixtures
        self.fixture = fixtures.BundleLockTests(
            "test_good_bundle_and_exact_consumer_lock")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.sdk = self.fixture.root
        self.fixture.put_manifest()
        self.home = self.sdk.parent
        self.examples = self.sdk / "examples"
        self.examples.mkdir()
        (self.examples / "tools").mkdir()
        (self.examples / "presence/main").mkdir(parents=True)
        shutil.copyfile(SCRIPT, self.examples / "build.sh")
        shutil.copyfile(BUNDLE, self.examples / "tools/mmwk_sdk_bundle.py")
        (self.examples / "presence/main/presence_offline.c").write_text("/* owned by app */")
        self.log = self.home / "idf-invocations.txt"
        fake_idf = self.home / "idf.py"
        fake_idf.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$*" >> "$STAGE1_BUILD_LOG"\n')
        fake_idf.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": str(self.home) + os.pathsep + os.environ.get("PATH", ""),
            "STAGE1_BUILD_LOG": str(self.log),
            "MMWK_STAGE1_ABI": "os-idf553",
            "MMWK_STAGE1_LOCK_FILE": str(self.home / "consumer.lock.json"),
        }

    def lock(self, preset):
        selection = bundle.inspect(self.sdk, "wdr", preset, "os-idf553")
        destination = self.home / "consumer.lock.json"
        destination.write_text(json.dumps(selection, sort_keys=True))

    def call(self, preset):
        return subprocess.run(["bash", str(self.examples / "build.sh"),
                               "presence", "wdr", "--preset", preset],
                              env=self.env, capture_output=True, text=True)

    def invocations(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_verified_offline_archive_and_lock_are_used_before_idf(self):
        self.lock("offline")
        result = self.call("offline")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.invocations()), 1)
        command = self.invocations()[0]
        self.assertIn("MMWK_STAGE1_PRESET=offline", command)
        self.assertIn("MMWK_STAGE1_BOARD=wdr", command)
        self.assertIn("MMWK_STAGE1_ABI=os-idf553", command)
        self.assertIn("set-target esp32s3 build", command)

    def test_wrong_lock_and_tampered_package_do_not_invoke_idf(self):
        self.lock("default")
        wrong = self.call("offline")
        self.assertNotEqual(wrong.returncode, 0)
        self.assertEqual(self.invocations(), [])
        self.lock("offline")
        (self.sdk / self.fixture.fw).write_bytes(b"tampered image")
        changed = self.call("offline")
        self.assertNotEqual(changed.returncode, 0)
        self.assertEqual(self.invocations(), [])

    def test_missing_abi_and_unimplemented_presets_fail_closed(self):
        self.lock("offline")
        env = dict(self.env)
        env.pop("MMWK_STAGE1_ABI")
        bad = subprocess.run(["bash", str(self.examples / "build.sh"),
                              "presence", "wdr", "--preset", "offline"],
                             env=env, capture_output=True, text=True)
        self.assertNotEqual(bad.returncode, 0)
        for preset in ("local-control", "wifi-data"):
            with self.subTest(preset=preset):
                self.assertNotEqual(self.call(preset).returncode, 0)
        self.assertEqual(self.invocations(), [])

    def test_default_requires_matching_new_package_lock(self):
        self.lock("default")
        result = self.call("default")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("MMWK_STAGE1_PRESET=default", self.invocations()[0])


if __name__ == "__main__":
    unittest.main()
