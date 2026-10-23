"""Local HTTP transfers must work even when host name resolution is unavailable."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from urllib.request import urlopen


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mmwk.local_http_server import LocalTransferHTTPServer


class LocalHttpServerTests(unittest.TestCase):
    def test_start_and_serve_without_reverse_dns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            server = LocalTransferHTTPServer(directory, bind="0.0.0.0", port=0)
            self.addCleanup(server.stop)
            # Reverse DNS can block for longer than the server startup timeout
            # on macOS. Local transfers do not require a resolved host name.
            with mock.patch("socket.getfqdn", side_effect=OSError("DNS unavailable")):
                server.start()
            with urlopen(f"http://127.0.0.1:{server.port}/healthz", timeout=5) as response:
                self.assertEqual(json.load(response), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
