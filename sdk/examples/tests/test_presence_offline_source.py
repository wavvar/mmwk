"""Isolated source/IDF registration contract for Stage1 RAW-only presence.

The new aggregate archive, ESP target builds, and hardware are not verified
by these host-side checks.
"""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]
SRC=ROOT/"sdk/examples/presence/main"
ROOT_CMAKE=ROOT/"sdk/examples/presence/CMakeLists.txt"


class PresenceOfflineSourceTests(unittest.TestCase):
    def resolve(self, preset):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            source=folder/"CMakeLists.txt"
            source.write_text(
                'cmake_minimum_required(VERSION 3.16)\n'
                'project(presence_source_selection C)\n'
                'set(MMWK_STAGE1_PRESET '+preset+')\n'
                'function(idf_component_register)\n'
                '  cmake_parse_arguments(C "" "" "SRCS;INCLUDE_DIRS;REQUIRES;PRIV_REQUIRES" ${ARGN})\n'
                '  file(WRITE "${CMAKE_BINARY_DIR}/source_list.txt" "${C_SRCS}")\n'
                '  file(WRITE "${CMAKE_BINARY_DIR}/deps.txt" "${C_REQUIRES}")\n'
                '  add_library(probe STATIC ${C_SRCS})\n'
                'endfunction()\n'
                'add_subdirectory("'+SRC.as_posix()+'" sample)\n')
            result=subprocess.run(["cmake","-S",str(folder),"-B",str(folder/"out")],
                                  capture_output=True,text=True,
                                  env={**os.environ,"MMWK_STAGE1_PRESET":preset})
            self.assertEqual(result.returncode,0,result.stderr+result.stdout)
            return (set((folder/"out/source_list.txt").read_text().split(";")),
                    set((folder/"out/deps.txt").read_text().split(";")))

    def test_one_business_state_for_offline_and_default(self):
        offline,offline_deps=self.resolve("offline")
        legacy,legacy_deps=self.resolve("default")
        self.assertIn("presence_state.c",offline)
        self.assertIn("presence_state.c",legacy)
        self.assertIn("presence_offline.c",offline)
        self.assertNotIn("main.c",offline)
        self.assertNotIn("presence_cli.c",offline)
        self.assertNotIn("presence_ui.c",offline)
        self.assertIn("main.c",legacy)
        self.assertNotIn("presence_offline.c",legacy)
        self.assertEqual(len(offline_deps),len(set(offline_deps)))
        self.assertFalse({"mqtt","esp_wifi","esp_http_client",
                          "esp_driver_gpio"} & offline_deps)
        self.assertIn("mmwk_sdk",offline_deps)
        self.assertIn("mmwk_board",offline_deps)

    def test_application_raw_lifecycle_and_early_choice_are_explicit(self):
        source=(SRC/"presence_offline.c").read_text()
        self.assertIn("mmwk_service_init(&s_service, NULL, &cfg)",source)
        self.assertIn("mmwk_service_raw_subscribe(s_service",source)
        self.assertIn("mmwk_service_start(s_service, MMWK_SERVICE_START_HOST)",source)
        self.assertIn("mmwk_service_stop(s_service)",source)
        self.assertIn("mmwk_service_raw_unsubscribe(s_service, s_subscription)",source)
        self.assertIn("mmwk_service_deinit(s_service)",source)
        self.assertIn(".disable_external_raw_commands = true",source)
        self.assertIn(".spi_backend = s_backend",source)
        self.assertIn("presence_state_update_raw",source)
        self.assertNotIn("mmwk_sensor_bridge_run",source)
        self.assertNotIn("mmwk_sensor_network",source)
        self.assertNotIn("presence_ui_configure",source)
        self.assertIn("MMWK_STAGE1_PRESET",ROOT_CMAKE.read_text())


if __name__=="__main__":
    unittest.main()
