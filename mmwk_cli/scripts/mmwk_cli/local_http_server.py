"""Lightweight local HTTP server for OTA downloads and optional uploads."""

from __future__ import annotations

import argparse
import functools
import json
import os
import re
import threading
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


def _safe_path_label(path: str) -> str:
    text = (path or "/").strip().strip("/")
    if not text:
        text = "upload"
    text = text.replace("/", "_")
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    return text[:80] or "upload"


class _LocalHttpHandler(SimpleHTTPRequestHandler):
    """Serve files and accept POST uploads into an output directory."""

    def __init__(self, *args, upload_dir: str | None = None, **kwargs):
        self._upload_dir = upload_dir
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path.split("?", 1)[0] == "/healthz":
            self._send_json({"status": "ok"})
            return
        super().do_GET()

    def do_HEAD(self):
        if self.path.split("?", 1)[0] == "/healthz":
            payload = json.dumps({"status": "ok"}).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            return
        super().do_HEAD()

    def do_POST(self):
        if not self._upload_dir:
            self._send_json({"status": "error", "msg": "uploads disabled"}, status=HTTPStatus.NOT_FOUND)
            return

        try:
            content_len = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_len = 0
        body = self.rfile.read(content_len) if content_len > 0 else b""

        os.makedirs(self._upload_dir, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        millis = int((time.time() % 1) * 1000)
        label = _safe_path_label(self.path.split("?", 1)[0])
        out_name = f"{ts}_{millis:03d}_{label}.bin"
        out_path = os.path.join(self._upload_dir, out_name)
        with open(out_path, "wb") as fp:
            fp.write(body)

        self._send_json(
            {
                "status": "ok",
                "bytes": len(body),
                "path": out_path,
            }
        )

    def log_message(self, fmt, *args):
        print(f"[local_http] {self.address_string()} - {fmt % args}", flush=True)

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK):
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class LocalTransferHTTPServer:
    """Threaded local HTTP server with static file and upload support."""

    def __init__(self, serve_dir: str, bind: str = "0.0.0.0", port: int = 8380, upload_dir: str | None = None):
        self.serve_dir = os.path.abspath(serve_dir)
        self.bind = bind
        self.port = int(port)
        self.upload_dir = os.path.abspath(upload_dir) if upload_dir else None
        self.httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self):
        handler = functools.partial(
            _LocalHttpHandler,
            directory=self.serve_dir,
            upload_dir=self.upload_dir,
        )
        self.httpd = ThreadingHTTPServer((self.bind, self.port), handler)
        self.port = int(self.httpd.server_address[1])
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None


def _main() -> int:
    parser = argparse.ArgumentParser(description="Run a local HTTP server for OTA downloads and uploads")
    parser.add_argument("--serve-dir", required=True, help="Directory to serve over HTTP")
    parser.add_argument("--bind", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8380, help="Listen port (default: 8380)")
    parser.add_argument("--upload-dir", help="Optional directory for POST upload dumps")
    args = parser.parse_args()

    server = LocalTransferHTTPServer(
        serve_dir=args.serve_dir,
        bind=args.bind,
        port=args.port,
        upload_dir=args.upload_dir,
    ).start()
    print(
        json.dumps(
            {
                "status": "started",
                "bind": args.bind,
                "port": server.port,
                "serve_dir": server.serve_dir,
                "upload_dir": server.upload_dir or "",
            },
            separators=(",", ":"),
        ),
        flush=True,
    )
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
