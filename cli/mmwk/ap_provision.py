from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Callable, Sequence
from urllib import request

from mmwk import ap_link


DEFAULT_BASE_URL = "http://192.168.4.1"


class ApProvisionError(RuntimeError):
    def __init__(self, phase: str, message: str):
        super().__init__(f"{phase}: {message}")
        self.phase = phase


@dataclass(frozen=True)
class ProvisionResult:
    ap_ssid: str
    restored: bool
    base_url: str


CommandRunner = Callable[[Sequence[str]], str]
EnsureLink = Callable[[str], str | None]
Submitter = Callable[[str, str, str, float], None]


def select_ap_ssid(explicit_ssid: str, ap_prefix: str, scan_results: Sequence[str]) -> str:
    explicit = (explicit_ssid or "").strip()
    if explicit:
        return explicit

    prefix = (ap_prefix or "").strip()
    if not prefix:
        raise ApProvisionError("ap_not_found", "set --ap-ssid or --ap-prefix")

    matches = sorted({ssid for ssid in scan_results if ssid.startswith(prefix)})
    if not matches:
        raise ApProvisionError("ap_not_found", f"no AP matched prefix {prefix!r}")
    if len(matches) > 1:
        raise ApProvisionError("ap_not_found", f"multiple APs matched prefix {prefix!r}: {', '.join(matches)}")
    return matches[0]


def build_connect_command(system: str, iface: str, ssid: str) -> list[str]:
    if system == "Linux":
        return ["nmcli", "dev", "wifi", "connect", ssid, "ifname", iface]
    if system == "Darwin":
        return ["networksetup", "-setairportnetwork", iface, ssid]
    raise ApProvisionError("wifi_tool_missing", f"unsupported platform: {system}")


def submit_portal_credentials(base_url: str, target_ssid: str, target_password: str, timeout: float = 10.0) -> None:
    url = base_url.rstrip("/") + "/submit"
    payload = json.dumps({"ssid": target_ssid, "password": target_password}).encode("utf-8")
    req = request.Request(url, data=payload, method="POST", headers={"Content-Type": "application/json"})

    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if resp.status < 200 or resp.status >= 300:
                raise ApProvisionError("portal_submit_failed", f"HTTP {resp.status}: {body}")
            data = json.loads(body or "{}")
            if data.get("success") is not True:
                raise ApProvisionError("portal_submit_failed", f"portal returned {body!r}")
    except ApProvisionError:
        raise
    except Exception as exc:
        raise ApProvisionError("portal_submit_failed", str(exc)) from exc


def _run_command(command: Sequence[str]) -> str:
    try:
        return subprocess.check_output(command, stderr=subprocess.STDOUT, text=True, timeout=30)
    except FileNotFoundError as exc:
        raise ApProvisionError("wifi_tool_missing", command[0]) from exc
    except subprocess.CalledProcessError as exc:
        output = (exc.output or "").strip()
        raise ApProvisionError("ap_connect_failed", output or "command failed: " + " ".join(command)) from exc
    except subprocess.TimeoutExpired as exc:
        raise ApProvisionError("ap_connect_failed", "command timed out: " + " ".join(command)) from exc


def _linux_current_ssid(runner: CommandRunner) -> str:
    output = runner(["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"])
    for line in output.splitlines():
        if line.startswith("yes:"):
            return line.split(":", 1)[1].replace("\\:", ":").strip()
    return ""


def _linux_scan(runner: CommandRunner, iface: str) -> list[str]:
    output = runner(["nmcli", "-t", "-f", "SSID", "dev", "wifi", "list", "ifname", iface, "--rescan", "yes"])
    return [line.replace("\\:", ":").strip() for line in output.splitlines() if line.strip()]


def _darwin_current_ssid(runner: CommandRunner, iface: str) -> str:
    output = runner(["networksetup", "-getairportnetwork", iface])
    marker = "Current Wi-Fi Network:"
    if marker in output:
        return output.split(marker, 1)[1].strip()
    return ""


def _darwin_scan(runner: CommandRunner) -> list[str]:
    airport = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
    output = runner([airport, "-s"])
    ssids: list[str] = []
    for raw_line in output.splitlines()[1:]:
        line = raw_line.strip()
        if not line:
            continue
        marker = " BSSID "
        if marker in line:
            ssids.append(line.split(marker, 1)[0].strip())
            continue
        parts = line.split()
        if parts:
            ssids.append(parts[0])
    return ssids


def _default_wifi_iface(system: str) -> str:
    if system == "Linux":
        names = ap_link.linux_wifi_interfaces()
    elif system == "Darwin":
        names = ap_link.darwin_wifi_interfaces()
    else:
        names = ()

    if not names:
        raise ApProvisionError("wifi_tool_missing", f"no Wi-Fi interface found for {system}")
    return names[0]


def _ensure_ap_link(iface: str) -> str:
    plan = ap_link.ensure_ap_link(iface=iface or None)
    return plan.iface


def _require_tool(system: str, runner: CommandRunner) -> None:
    if runner is not _run_command:
        return
    if system == "Linux" and shutil.which("nmcli") is None:
        raise ApProvisionError("wifi_tool_missing", "nmcli not found")
    if system == "Darwin" and shutil.which("networksetup") is None:
        raise ApProvisionError("wifi_tool_missing", "networksetup not found")


def run_provision(
    *,
    target_ssid: str,
    target_password: str,
    ap_ssid: str,
    ap_prefix: str,
    base_url: str = DEFAULT_BASE_URL,
    wifi_iface: str = "",
    restore_wifi: bool = True,
    timeout: float = 10.0,
    system: str | None = None,
    runner: CommandRunner = _run_command,
    submitter: Submitter = submit_portal_credentials,
    ensure_link: EnsureLink = _ensure_ap_link,
) -> ProvisionResult:
    current_system = system or platform.system()
    if not target_ssid:
        raise ApProvisionError("portal_submit_failed", "target Wi-Fi SSID is required")
    if current_system not in {"Linux", "Darwin"}:
        raise ApProvisionError("wifi_tool_missing", f"unsupported platform: {current_system}")

    _require_tool(current_system, runner)

    iface = wifi_iface or _default_wifi_iface(current_system)
    if current_system == "Linux":
        original_ssid = _linux_current_ssid(runner)
        scan_results = _linux_scan(runner, iface)
    else:
        original_ssid = _darwin_current_ssid(runner, iface)
        scan_results = _darwin_scan(runner) if not ap_ssid else [ap_ssid]

    selected_ap = select_ap_ssid(ap_ssid, ap_prefix, scan_results)
    runner(build_connect_command(current_system, iface, selected_ap))
    time.sleep(2)
    ensured_iface = ensure_link(iface)
    if ensured_iface:
        iface = ensured_iface
    submitter(base_url, target_ssid, target_password, timeout)

    restored = False
    if restore_wifi and original_ssid:
        runner(build_connect_command(current_system, iface, original_ssid))
        restored = True

    return ProvisionResult(ap_ssid=selected_ap, restored=restored, base_url=base_url)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Provision device Wi-Fi through the local MMWK portal")
    parser.add_argument("--target-ssid", required=True, help="target infrastructure Wi-Fi SSID to submit")
    parser.add_argument("--target-password", required=True, help="target infrastructure Wi-Fi password to submit")
    parser.add_argument("--ap-ssid", default="", help="exact provisioning AP SSID")
    parser.add_argument("--ap-prefix", default="", help="provisioning AP prefix to scan for")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"portal base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--wifi-iface", default="", help="host Wi-Fi interface override")
    parser.add_argument("--timeout", type=float, default=10.0, help="portal HTTP timeout in seconds")
    parser.add_argument("--no-restore-wifi", action="store_true", help="do not reconnect the original host Wi-Fi")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    return parser


def run(args: argparse.Namespace) -> int:
    try:
        result = run_provision(
            target_ssid=args.target_ssid,
            target_password=args.target_password,
            ap_ssid=args.ap_ssid,
            ap_prefix=args.ap_prefix,
            base_url=args.base_url,
            wifi_iface=args.wifi_iface,
            restore_wifi=not args.no_restore_wifi,
            timeout=args.timeout,
        )
    except ApProvisionError as exc:
        if args.json:
            print(json.dumps({"status": "error", "phase": exc.phase, "message": str(exc)}), file=sys.stderr)
        else:
            print(f"phase={exc.phase} status=error message={str(exc)}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({"status": "ok", "ap_ssid": result.ap_ssid, "restored": result.restored, "base_url": result.base_url}))
    else:
        print(f"phase=portal_provision status=ok ap_ssid={result.ap_ssid} restored={1 if result.restored else 0}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
