"""Run actual FlashCommand._send_file_chunks logic without device or CLI extras.

The method is loaded from the checked-out source AST, so fake transports test
the real retry loop, not a duplicate implementation. This is not device proof.
"""
import ast
import base64
import json
from pathlib import Path
import re
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "mmwk/commands/flash.py"


class _Log:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


class _Time:
    def __init__(self):
        self.waits = []

    def sleep(self, delay):
        self.waits.append(delay)


class _Mcp:
    def __init__(self, failed_seq, error_message, fail_count=None):
        self.transport = object()  # UART, not an MQTT transport
        self.failed_seq = failed_seq
        self.message = error_message
        self.fail_count = fail_count
        self.attempts = []

    def call_tool(self, name, args, timeout=None):
        assert name == "uart_data"
        self.attempts.append(args.get("seq", "cancel"))
        if args.get("seq") == self.failed_seq:
            if self.fail_count is None or self.fail_count > 0:
                if self.fail_count is not None:
                    self.fail_count -= 1
                raise RuntimeError(self.message)
        return {"text": json.dumps({"status": "success"})}

    def extract_text(self, result):
        return result["text"]


def _load_real_chunk_method(fake_time):
    source = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    klass = next(node for node in source.body
                 if isinstance(node, ast.ClassDef) and node.name == "FlashCommand")
    method = next(node for node in klass.body
                  if isinstance(node, ast.FunctionDef) and node.name == "_send_file_chunks")
    # Resolve only standard-library dependencies used by this function.
    fake_mqtt_class = type("_NotTheUARTTransport", (), {})
    namespace = {
        "base64": base64, "json": json, "re": re,
        "time": fake_time, "logger": _Log(),
        "MqttTransport": fake_mqtt_class,
    }
    program = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    exec(compile(program, str(SOURCE), "exec"), namespace)
    return namespace["_send_file_chunks"]


class FlashInactiveErrnoTests(unittest.TestCase):
    def _run(self, code, failed_seq=0, count=None, length=4):
        clock = _Time()
        method = _load_real_chunk_method(clock)
        message = f"Failed to process UART data chunk (err={code})"
        mcp = _Mcp(failed_seq, message, fail_count=count)
        command = types.SimpleNamespace(mcp=mcp)
        result = method(command, b"12345678"[:length], "firmware", 4, show_progress=False)
        return result, mcp.attempts, clock.waits

    def test_old_and_new_inactive_code_bound_retries(self):
        for code in (-2, -3415):
            for failed_seq in (0, 1):
                with self.subTest(code=code, failed_seq=failed_seq):
                    ok, seq, waits = self._run(code, failed_seq, length=8)
                    self.assertFalse(ok)
                    self.assertEqual(seq, [0, 0] if failed_seq == 0
                                     else [0, 1, 1, 1])
                    self.assertEqual(waits, [1.0] if failed_seq == 0
                                     else [0.05, 1.0, 1.0])

    def test_unrelated_error_codes_are_not_partial_matches(self):
        for code in (-20, -34150, -3401, -3417):
            with self.subTest(code=code):
                ok, seq, waits = self._run(code)
                self.assertFalse(ok)
                self.assertEqual(seq, [0] * 24 + ["cancel"])
                self.assertEqual(waits, [1.0] * 23)

    def test_one_transient_inactive_response_recovers(self):
        for code in (-2, -3415):
            with self.subTest(code=code):
                ok, seq, waits = self._run(code, count=1, length=8)
                self.assertTrue(ok)
                self.assertEqual(seq, [0, 0, 1])
                self.assertEqual(waits, [1.0, 0.05, 0.05])


if __name__ == "__main__":
    unittest.main()
