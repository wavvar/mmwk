from __future__ import annotations

import argparse
import ipaddress
import json
import platform
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Iterable, Sequence


SERVICE_TYPE = "_mmwk._tcp.local."
DEFAULT_TIMEOUT_SEC = 3.0
DEFAULT_AP_CIDR = "192.168.4.2/24"


@dataclass(frozen=True)
class DeviceRecord:
    service_name: str
    device_id: str
    client_id: str
    name: str
    board: str
    version: str
    mode: str
    addresses: tuple[str, ...]
    hostname: str
    port: int

    def to_json(self) -> dict:
        return {
            "id": self.device_id,
            "client_id": self.client_id,
            "name": self.name,
            "board": self.board,
            "version": self.version,
            "mode": self.mode,
            "addresses": list(self.addresses),
            "hostname": self.hostname,
            "port": self.port,
            "service": self.service_name,
        }


@dataclass(frozen=True)
class ApAliasPlan:
    add_command: list[str] | None
    delete_command: list[str] | None
    already_present: bool


def _decode_txt_item(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    return str(value).strip()


def _txt_properties(properties: object) -> dict[str, str]:
    result: dict[str, str] = {}
    if not isinstance(properties, dict):
        return result
    for raw_key, raw_value in properties.items():
        key = _decode_txt_item(raw_key)
        if not key:
            continue
        result[key] = _decode_txt_item(raw_value)
    return result


def _id_from_service_name(service_name: str) -> str:
    first_label = service_name.split(".", 1)[0].strip()
    if first_label.startswith("mmwk-"):
        return first_label[len("mmwk-") :]
    return first_label


def normalize_service_info(service_name: str, info: object) -> DeviceRecord:
    txt = _txt_properties(getattr(info, "properties", {}))
    parsed_addresses = getattr(info, "parsed_addresses", None)
    if callable(parsed_addresses):
        addresses = tuple(str(addr) for addr in parsed_addresses() if addr)
    else:
        addresses = ()

    hostname = str(getattr(info, "server", "") or "")
    port = int(getattr(info, "port", 0) or 0)
    fallback_id = _id_from_service_name(service_name)
    device_id = txt.get("id") or txt.get("client_id") or fallback_id
    client_id = txt.get("client_id") or device_id
    name = txt.get("name") or hostname.rstrip(".") or device_id

    return DeviceRecord(
        service_name=service_name,
        device_id=device_id,
        client_id=client_id,
        name=name,
        board=txt.get("board", ""),
        version=txt.get("version", ""),
        mode=txt.get("mode", "unknown") or "unknown",
        addresses=addresses,
        hostname=hostname,
        port=port,
    )


def _pick(existing: str, candidate: str) -> str:
    if existing and existing != "unknown":
        return existing
    return candidate


def _merge_records(first: DeviceRecord, second: DeviceRecord) -> DeviceRecord:
    addresses = list(first.addresses)
    for address in second.addresses:
        if address not in addresses:
            addresses.append(address)
    return DeviceRecord(
        service_name=first.service_name,
        device_id=first.device_id or second.device_id,
        client_id=first.client_id or second.client_id,
        name=_pick(first.name, second.name),
        board=_pick(first.board, second.board),
        version=_pick(first.version, second.version),
        mode=_pick(first.mode, second.mode),
        addresses=tuple(addresses),
        hostname=first.hostname or second.hostname,
        port=first.port or second.port,
    )


def sort_and_deduplicate(devices: Iterable[DeviceRecord]) -> list[DeviceRecord]:
    merged: dict[str, DeviceRecord] = {}
    ordered = sorted(devices, key=lambda item: (item.device_id or item.service_name, item.service_name))
    for device in ordered:
        key = device.device_id or device.service_name
        if key in merged:
            merged[key] = _merge_records(merged[key], device)
        else:
            merged[key] = device
    return [merged[key] for key in sorted(merged)]


def _format_table(rows: list[list[str]]) -> str:
    widths = [0] * len(rows[0])
    for row in rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    lines = []
    for row in rows:
        padded = [value.ljust(widths[idx]) for idx, value in enumerate(row)]
        lines.append("  ".join(padded).rstrip())
    return "\n".join(lines) + "\n"


def format_devices_table(devices: Iterable[DeviceRecord]) -> str:
    records = sort_and_deduplicate(devices)
    if not records:
        return "no mmwk devices found\n"

    rows = [["device-id", "name", "board", "version", "mode", "addresses", "hostname"]]
    for device in records:
        rows.append(
            [
                device.device_id or "-",
                device.name or "-",
                device.board or "-",
                device.version or "-",
                device.mode or "-",
                ",".join(device.addresses) or "-",
                device.hostname or "-",
            ]
        )
    return _format_table(rows)


def format_devices_json(devices: Iterable[DeviceRecord]) -> str:
    records = sort_and_deduplicate(devices)
    return json.dumps({"devices": [device.to_json() for device in records]}, indent=2, sort_keys=True) + "\n"


def _interface(value: str) -> ipaddress.IPv4Interface:
    parsed = ipaddress.ip_interface(value)
    if parsed.version != 4:
        raise ValueError(f"AP alias CIDR must be IPv4: {value}")
    return parsed


def _cidr_present(target: ipaddress.IPv4Interface, existing_cidrs: Iterable[str]) -> bool:
    for cidr in existing_cidrs:
        try:
            if _interface(cidr) == target:
                return True
        except ValueError:
            continue
    return False


def _prefix_to_netmask(prefixlen: int) -> str:
    network = ipaddress.IPv4Network(f"0.0.0.0/{prefixlen}")
    return str(network.netmask)


def build_ap_alias_plan(
    *,
    system: str,
    iface: str,
    cidr: str,
    existing_cidrs: Sequence[str],
) -> ApAliasPlan:
    target = _interface(cidr)
    if _cidr_present(target, existing_cidrs):
        return ApAliasPlan(add_command=None, delete_command=None, already_present=True)

    ip_text = str(target.ip)
    if system == "Linux":
        return ApAliasPlan(
            add_command=["sudo", "ip", "addr", "add", str(target), "dev", iface],
            delete_command=["sudo", "ip", "addr", "del", str(target), "dev", iface],
            already_present=False,
        )
    if system == "Darwin":
        return ApAliasPlan(
            add_command=["sudo", "ifconfig", iface, "alias", ip_text, "netmask", _prefix_to_netmask(target.network.prefixlen)],
            delete_command=["sudo", "ifconfig", iface, "-alias", ip_text],
            already_present=False,
        )
    raise ValueError(f"AP alias setup is supported on Linux and macOS only, not {system}")


def _linux_interface_cidrs(iface: str) -> list[str]:
    output = subprocess.check_output(
        ["ip", "-o", "-4", "addr", "show", "dev", iface],
        stderr=subprocess.DEVNULL,
        text=True,
    )
    cidrs = []
    for line in output.splitlines():
        parts = line.split()
        if "inet" not in parts:
            continue
        inet_index = parts.index("inet")
        if inet_index + 1 < len(parts):
            cidrs.append(parts[inet_index + 1])
    return cidrs


def _darwin_interface_cidrs(iface: str) -> list[str]:
    output = subprocess.check_output(["ifconfig", iface], stderr=subprocess.DEVNULL, text=True)
    cidrs = []
    for line in output.splitlines():
        match = re.search(r"\binet\s+(\d+\.\d+\.\d+\.\d+)\s+netmask\s+(0x[0-9a-fA-F]+)", line)
        if not match:
            continue
        ip_text, hex_mask = match.groups()
        mask_text = str(ipaddress.IPv4Address(int(hex_mask, 16)))
        prefix = ipaddress.IPv4Network(f"0.0.0.0/{mask_text}", strict=False).prefixlen
        cidrs.append(f"{ip_text}/{prefix}")
    return cidrs


def interface_ipv4_cidrs(iface: str, *, system: str | None = None) -> list[str]:
    current_system = system or platform.system()
    try:
        if current_system == "Linux":
            return _linux_interface_cidrs(iface)
        if current_system == "Darwin":
            return _darwin_interface_cidrs(iface)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []
    return []


def apply_ap_alias(iface: str, cidr: str, *, system: str | None = None) -> ApAliasPlan:
    current_system = system or platform.system()
    existing = interface_ipv4_cidrs(iface, system=current_system)
    plan = build_ap_alias_plan(system=current_system, iface=iface, cidr=cidr, existing_cidrs=existing)
    if plan.add_command is not None:
        subprocess.run(plan.add_command, check=True)
    return plan


class _DiscoveryListener:
    def __init__(self, zeroconf: object):
        self._zeroconf = zeroconf
        self._lock = threading.Lock()
        self.records: dict[str, DeviceRecord] = {}

    def add_service(self, zc: object, service_type: str, name: str) -> None:
        self._refresh(service_type, name)

    def update_service(self, zc: object, service_type: str, name: str) -> None:
        self._refresh(service_type, name)

    def remove_service(self, zc: object, service_type: str, name: str) -> None:
        with self._lock:
            self.records.pop(name, None)

    def _refresh(self, service_type: str, name: str) -> None:
        get_info = getattr(self._zeroconf, "get_service_info")
        info = get_info(service_type, name, timeout=1000)
        if info is None:
            return
        record = normalize_service_info(name, info)
        with self._lock:
            self.records[name] = record


def discover_devices(timeout: float = DEFAULT_TIMEOUT_SEC) -> list[DeviceRecord]:
    try:
        from zeroconf import ServiceBrowser, Zeroconf
    except ImportError as exc:
        raise RuntimeError("zeroconf is required for mDNS discovery; run from config.sh so dependencies are installed") from exc

    zeroconf = Zeroconf()
    listener = _DiscoveryListener(zeroconf)
    browser = ServiceBrowser(zeroconf, SERVICE_TYPE, listener)
    try:
        time.sleep(max(0.0, timeout))
        with listener._lock:
            return sort_and_deduplicate(listener.records.values())
    finally:
        cancel = getattr(browser, "cancel", None)
        if callable(cancel):
            cancel()
        zeroconf.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="config.sh search",
        description="Discover MMWK devices over mDNS.",
    )
    parser.add_argument("--timeout", metavar="SEC", type=float, default=DEFAULT_TIMEOUT_SEC, help="mDNS browse duration")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument(
        "--ap-iface",
        metavar="IFACE",
        help="temporarily add --ap-cidr to this host interface before browsing",
    )
    parser.add_argument(
        "--ap-cidr",
        metavar="CIDR",
        default=DEFAULT_AP_CIDR,
        help=f"temporary host address for device AP discovery (default: {DEFAULT_AP_CIDR})",
    )
    parser.add_argument(
        "--keep-ap-alias",
        action="store_true",
        help="leave the temporary AP address configured after search",
    )
    return parser


def run(args: argparse.Namespace) -> int:
    alias_plan: ApAliasPlan | None = None
    try:
        if args.ap_iface:
            alias_plan = apply_ap_alias(args.ap_iface, args.ap_cidr)
        devices = discover_devices(args.timeout)
        output = format_devices_json(devices) if args.json else format_devices_table(devices)
        print(output, end="")
        return 0
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"config.sh search: {exc}", file=sys.stderr)
        return 1
    finally:
        if alias_plan is not None and alias_plan.delete_command is not None and not args.keep_ap_alias:
            try:
                subprocess.run(alias_plan.delete_command, check=True)
            except subprocess.CalledProcessError as exc:
                print(f"config.sh search: failed to remove AP alias: {exc}", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
