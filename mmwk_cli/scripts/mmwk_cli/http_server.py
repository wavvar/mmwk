"""HTTP firmware server for OTA downloads."""

import ipaddress
import os
import socket
import functools
import ssl
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

from mmwk_cli._logging import logger


def _parse_ipv4(ip: str):
    try:
        return ipaddress.IPv4Address((ip or "").strip())
    except Exception:
        return None


def _is_private_ip(ip: str) -> bool:
    """Return True if ip is a RFC-1918 private address (suitable for LAN use)."""
    addr = _parse_ipv4(ip)
    if addr is None:
        return False
    octets = tuple(int(part) for part in str(addr).split("."))
    return (
        octets[0] == 10 or
        (octets[0] == 172 and 16 <= octets[1] <= 31) or
        (octets[0] == 192 and octets[1] == 168)
    )


def _pick_routed_local_ip(target_ip: str = None) -> str:
    """Prefer the host address actually routed to the device/default network."""
    probe_targets = []
    target_addr = _parse_ipv4(target_ip)
    if target_addr is not None and target_addr.is_private:
        probe_targets.append(str(target_addr))
    probe_targets.extend(("8.8.8.8", "1.1.1.1"))

    for probe in probe_targets:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect((probe, 80))
            local_ip = sock.getsockname()[0]
            sock.close()
            if _is_private_ip(local_ip):
                return local_ip
        except Exception:
            pass

    return ""


def _same_subnet24(ip: str, target_ip: str) -> bool:
    try:
        ip_parts = list(map(int, ip.split('.')))
        target_parts = list(map(int, target_ip.split('.')))
        return ip_parts[:3] == target_parts[:3]
    except Exception:
        return False


def get_local_ip(target_ip: str = None) -> str:
    """Return the best local private-range IP for hosting a LAN HTTP server.

    Strategy:
      1. Prefer the local address the kernel would route to `target_ip`
         (or the default route when `target_ip` is unknown).
      2. Enumerate all addresses bound to this host.
      3. If `target_ip` is known, prefer candidates on the same /24 subnet.
      4. Prefer 192.168.x.x, then 10.x.x.x, then 172.16-31.x.x.
      5. Fall back to 0.0.0.0 if nothing suitable is found.

    This avoids advertising a provisioning-side address like 192.168.4.x when
    the device is already on the main LAN, while still allowing same-subnet
    provisioning paths when `target_ip` points there.
    """
    for env_name in ("MMWK_HTTP_HOST_IP", "MMWK_HOST_IP"):
        env_ip = os.getenv(env_name, "").strip()
        if _is_private_ip(env_ip):
            return env_ip

    test_host_ip = os.getenv("TEST_HOST_IP", "").strip()
    if _is_private_ip(test_host_ip):
        if not _is_private_ip(target_ip) or _same_subnet24(test_host_ip, target_ip):
            return test_host_ip

    candidates = []
    try:
        hostname = socket.gethostname()
        for ai in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = ai[4][0]
            if _is_private_ip(ip):
                candidates.append(ip)
    except Exception:
        pass

    routed_ip = _pick_routed_local_ip(target_ip)

    if _is_private_ip(target_ip):
        same_subnet = [ip for ip in candidates if _same_subnet24(ip, target_ip)]
        if same_subnet:
            if routed_ip and _same_subnet24(routed_ip, target_ip):
                return routed_ip
            return same_subnet[0]

    if routed_ip:
        return routed_ip

    if not candidates:
        return "0.0.0.0"

    # Prefer 192.168.x.x > 10.x.x.x > 172.16-31.x.x
    def _priority(ip):
        parts = list(map(int, ip.split('.')))
        if parts[0] == 192:
            return 0
        if parts[0] == 10:
            return 1
        return 2

    candidates.sort(key=_priority)
    return candidates[0]


class ReuseAddrHTTPServer(HTTPServer):
    """HTTPServer with SO_REUSEADDR enabled to avoid 'Address already in use' errors."""
    allow_reuse_address = True


class _TrackingHandler(SimpleHTTPRequestHandler):
    """HTTP handler that records when a full file transfer completes."""

    def __init__(self, *args, tracker=None, **kwargs):
        self._tracker = tracker
        super().__init__(*args, **kwargs)

    def end_headers(self):
        super().end_headers()

    def copyfile(self, source, outputfile):
        """Hook: called when the server sends a file body to the client."""
        try:
            super().copyfile(source, outputfile)
            # If we get here, full file was transferred without exception
            path = self.path.split('?')[0]  # strip query string
            if self._tracker is not None:
                self._tracker.record_complete(path)
        except Exception:
            raise  # let the base class handle errors normally

    def log_message(self, fmt, *args):
        logger.debug(f"HTTP » {fmt % args}")


class _DownloadTracker:
    """Thread-safe tracker: records which paths have been fully downloaded."""

    def __init__(self):
        self._lock = threading.Lock()
        self._completed: set = set()

    def record_complete(self, path: str):
        with self._lock:
            self._completed.add(path)
        logger.info(f"  [http] File fully served: {path}")

    def is_complete(self, filename: str) -> bool:
        """Return True if the file with this basename was fully transferred."""
        with self._lock:
            for p in self._completed:
                if p.rstrip('/').split('/')[-1] == filename:
                    return True
        return False


class FirmwareHttpServer:
    """Simple HTTP server that serves firmware files for OTA download."""

    def __init__(
        self,
        directory: str,
        host: str = "0.0.0.0",
        port: int = 8380,
        scheme: str = "http",
        certfile: str = None,
        keyfile: str = None,
    ):
        self.directory = os.path.abspath(directory)
        self.host = host
        self.port = port
        self.scheme = (scheme or "http").strip().lower()
        self.certfile = os.path.abspath(certfile) if certfile else None
        self.keyfile = os.path.abspath(keyfile) if keyfile else None
        self.httpd = None
        self._thread = None
        self.tracker = _DownloadTracker()
        self._advertised_host = None

    def start(self, target_ip: str = None):
        if self.scheme not in ("http", "https"):
            raise ValueError(f"Unsupported server scheme: {self.scheme}")

        tracker = self.tracker
        handler = functools.partial(_TrackingHandler,
                                    directory=self.directory,
                                    tracker=tracker)
        # Try the requested port, then fall back to nearby ports if still occupied
        tried = []
        for candidate in [self.port] + list(range(self.port + 1, self.port + 10)):
            try:
                self.httpd = ReuseAddrHTTPServer((self.host, candidate), handler)
                self.port = candidate
                break
            except OSError as e:
                tried.append(candidate)
                logger.warning(f"Port {candidate} unavailable ({e}), trying next...")
        else:
            raise OSError(f"[Errno 48] Address already in use — "
                          f"could not bind to any port in {tried}. "
                          f"Kill the process holding the port: "
                          f"lsof -ti :{tried[0]} | xargs kill -9")

        if self.scheme == "https":
            if not self.certfile or not self.keyfile:
                raise ValueError("HTTPS server requires certfile and keyfile")
            if not os.path.isfile(self.certfile):
                raise FileNotFoundError(f"HTTPS cert file not found: {self.certfile}")
            if not os.path.isfile(self.keyfile):
                raise FileNotFoundError(f"HTTPS key file not found: {self.keyfile}")
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certfile=self.certfile, keyfile=self.keyfile)
            self.httpd.socket = context.wrap_socket(self.httpd.socket, server_side=True)

        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()
        self._advertised_host = get_local_ip(target_ip=target_ip)
        logger.info(f"{self.scheme.upper()} server started at {self.scheme}://{self._advertised_host}:{self.port}/ "
                     f"(serving {self.directory})")

    def get_base_url(self, target_ip: str = None) -> str:
        host = self._advertised_host or get_local_ip(target_ip=target_ip)
        return f"{self.scheme}://{host}:{self.port}/"

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            logger.info("HTTP server stopped")
