"""Exercise public CLI wrappers with local fixtures and no radar hardware."""

from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
from urllib.request import urlopen
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_DIR = REPO_ROOT / "cli"
WINDOWS = os.name == "nt"


class WrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.shell = shutil.which("pwsh") if WINDOWS else "/bin/bash"
        if not cls.shell:
            raise RuntimeError("PowerShell (pwsh) is required to test Windows wrappers")

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="mmwk cli tests ")
        self.addCleanup(temporary.cleanup)
        self.caller = Path(temporary.name).resolve()
        self.env = os.environ.copy()
        for name in list(self.env):
            if name.startswith("MMWK_"):
                del self.env[name]
        # Wrappers must locate mmwk themselves, even outside the checkout.
        self.env.pop("PYTHONPATH", None)
        self.env["PYTHONUTF8"] = "1"
        self.env["MMWK_SERVER_START_TIMEOUT_SEC"] = "30"

    def run_wrapper(self, name: str, *args: str) -> subprocess.CompletedProcess:
        extension = "ps1" if WINDOWS else "sh"
        script = str(CLI_DIR / f"{name}.{extension}")
        if WINDOWS:
            command = [
                self.shell, "-NoLogo", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-File", script,
            ]
        else:
            command = [self.shell, script]
        result = subprocess.run(
            [*command, *args],
            cwd=self.caller,
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        return result

    def assert_success(self, result: subprocess.CompletedProcess) -> str:
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(result.stdout.strip(), "wrapper returned empty output")
        return result.stdout

    def test_all_wrappers_provide_help_from_another_directory(self) -> None:
        for name in ("run", "server", "config", "collect"):
            for flag in ("-h", "--help"):
                with self.subTest(wrapper=name, flag=flag):
                    output = self.assert_success(self.run_wrapper(name, flag))
                    self.assertIn("usage:", output.lower())

    def test_run_forwards_subcommand_help(self) -> None:
        for command, option in (("node", "info"), ("radar", "status"), ("collect", "--duration")):
            with self.subTest(command=command):
                output = self.assert_success(self.run_wrapper("run", command, "--help"))
                self.assertIn(option, output)

    def test_collect_forwards_transport_options(self) -> None:
        for transport in ("uart", "usb", "mqtt"):
            with self.subTest(transport=transport):
                output = self.assert_success(self.run_wrapper(
                    "collect", "--transport", transport, "--help",
                ))
                self.assertIn("--data-output", output)
                self.assertIn("--ctrl-transport", output)

    def test_collect_dispatches_trigger_helper(self) -> None:
        for trigger in ("none", "radar-restart", "device-reboot"):
            with self.subTest(trigger=trigger):
                output = self.assert_success(self.run_wrapper(
                    "collect", "--trigger", trigger, "--help",
                ))
                self.assertIn("Pure-MQTT raw capture helper", output)
                self.assertIn("--trigger", output)

    def test_invalid_commands_return_failure(self) -> None:
        cases = (
            ("run", ("not-a-command",)),
            ("server", ("not-a-command",)),
            ("config", ("not-a-command",)),
            ("collect", ("--transport", "not-a-transport")),
        )
        for name, args in cases:
            with self.subTest(wrapper=name):
                result = self.run_wrapper(name, *args)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertRegex(result.stdout.lower(), "invalid|unknown|unsupported")

    def test_collect_rejects_invalid_duration_before_opening_serial(self) -> None:
        result = self.run_wrapper(
            "collect", "--transport", "uart", "--port", "unused", "--duration", "0",
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("duration must be positive", result.stdout)

    def test_collect_reports_missing_caller_relative_config(self) -> None:
        result = self.run_wrapper(
            "collect", "--transport", "uart", "--port", "unused",
            "--cfg", "missing radar.cfg", "--duration", "1",
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("missing radar.cfg", result.stdout)
        self.assertRegex(result.stdout.lower(), "no such file|not found")

    def test_collection_preserves_caller_relative_config_with_spaces(self) -> None:
        cfg = self.caller / "radar config.cfg"
        shutil.copyfile(
            REPO_ROOT / "firmwares/radar/iwr6843/oob/out_of_box_6843_aop.cfg", cfg,
        )
        # A path inside the new temporary directory cannot name a real device.
        port = str(self.caller / "absent serial port")
        for name, prefix in (("run", ("collect",)), ("collect", ())):
            with self.subTest(wrapper=name):
                result = self.run_wrapper(
                    name, *prefix, "--transport", "uart", "--port", port,
                    "--protocol", "cli", "--cfg", cfg.name, "--duration", "1",
                )
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("could not open port", result.stdout.lower())
                self.assertIn("absent serial port", result.stdout)

    def test_config_reads_caller_relative_registry_with_spaces(self) -> None:
        working = self.caller / "collection registry"
        working.mkdir()
        (working / "device.yml").write_text(json.dumps({
            "devices": {"example-device": {"mqtt_server": "localhost", "mqtt_port": 1883}},
        }), encoding="utf-8")
        output = self.assert_success(self.run_wrapper(
            "config", "list", "--working", working.name,
        ))
        self.assertIn("example-device", output)
        self.assertIn("localhost", output)

    def test_local_server_start_status_env_http_and_stop(self) -> None:
        state = "server state"
        serving = self.caller / "served files"
        serving.mkdir()
        payload = b"MMWK CLI CI fixture\n"
        (serving / "fixture.txt").write_bytes(payload)
        with ExitStack() as stack:
            listeners = [stack.enter_context(socket.socket()) for _ in range(2)]
            for listener in listeners:
                listener.bind(("127.0.0.1", 0))
            mqtt_port, http_port = [listener.getsockname()[1] for listener in listeners]

        # Cleanup is registered before start, including when an assertion fails.
        def stop_server() -> None:
            self.assert_success(self.run_wrapper("server", "stop", "--state-dir", state))

        self.addCleanup(stop_server)
        started = self.run_wrapper(
            "server", "start", "--state-dir", state, "--serve-dir", serving.name,
            "--upload-dir", "uploaded files", "--host-ip", "127.0.0.1",
            "--mqtt-port", str(mqtt_port), "--http-port", str(http_port),
        )
        logs = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in (self.caller / state).glob("*.log")
        )
        self.assertEqual(started.returncode, 0, started.stdout + logs)
        status = self.assert_success(self.run_wrapper("server", "status", "--state-dir", state))
        self.assertIn("MQTT Up   : yes", status)
        self.assertIn("HTTP Up   : yes", status)
        environment = self.assert_success(self.run_wrapper("server", "env", "--state-dir", state))
        values = dict(line.split("=", 1) for line in environment.splitlines() if "=" in line)
        mqtt_url = urlsplit(values["MMWK_SERVER_MQTT_URI"])
        http_url = urlsplit(values["MMWK_SERVER_HTTP_BASE_URL"])
        self.assertEqual((mqtt_url.scheme, mqtt_url.hostname), ("mqtt", "127.0.0.1"))
        self.assertEqual((http_url.scheme, http_url.hostname), ("http", "127.0.0.1"))
        # The server may select a nearby port if a requested port was taken.
        mqtt_port, http_port = mqtt_url.port, http_url.port
        with urlopen(f"http://127.0.0.1:{http_port}/fixture.txt", timeout=5) as response:
            self.assertEqual(response.read(), payload)
        self.assert_success(self.run_wrapper("server", "stop", "--state-dir", state))
        stopped = self.assert_success(self.run_wrapper("server", "status", "--state-dir", state))
        self.assertIn("MQTT Up   : no", stopped)
        self.assertIn("HTTP Up   : no", stopped)
        for port in (mqtt_port, http_port):
            with socket.socket() as connection:
                connection.settimeout(2)
                self.assertNotEqual(connection.connect_ex(("127.0.0.1", port)), 0)


if __name__ == "__main__":
    unittest.main()
