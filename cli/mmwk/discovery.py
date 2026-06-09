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
    did: str
    prod: str
    oid: str
    cid: str
    name: str
    board: str
    version: str
    mode: str
    addresses: tuple[str, ...]
    hostname: str
    port: int

    def to_json(self) -> dict:
        return {
            "did": self.did,
            "prod": self.prod,
            "oid": self.oid,
            "cid": self.cid,
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
    prod = txt.get("prod") or "mmwk"
    oid = txt.get("oid") or "mmwk"
    did = txt.get("did") or fallback_id
    cid = txt.get("cid") or ""
    name = txt.get("name") or hostname.rstrip(".") or cid or did

    return DeviceRecord(
        service_name=service_name,
        did=did,
        prod=prod,
        oid=oid,
        cid=cid,
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
        did=first.did or second.did,
        prod=first.prod or second.prod,
        oid=first.oid or second.oid,
        cid=first.cid or second.cid,
        name=_pick(first.name, second.name),
        board=_pick(first.board, second.board),
        version=_pick(first.version, second.version),
        mode=_pick(first.mode, second.mode),
        addresses=tuple(addresses),
        hostname=first.hostname or second.hostname,
        port=first.port or second.port,
    )


def _record_route_key(device: DeviceRecord) -> str:
    return device.cid or device.did


def sort_and_deduplicate(devices: Iterable[DeviceRecord]) -> list[DeviceRecord]:
    merged: dict[str, DeviceRecord] = {}
    ordered = sorted(devices, key=lambda item: (_record_route_key(item) or item.service_name, item.service_name))
    for device in ordered:
        key = _record_route_key(device) or device.service_name
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

    rows = [["did", "prod", "oid", "cid", "name", "board", "version", "mode", "addresses", "hostname"]]
    for device in records:
        rows.append(
            [
                device.did or "-",
                device.prod or "-",
                device.oid or "-",
                device.cid or "-",
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


def route_identity(device: DeviceRecord) -> str:
    return _record_route_key(device).strip()


def device_label(device: DeviceRecord) -> str:
    return (
        f"{route_identity(device) or '<unknown>'} "
        f"name={device.name or '<unnamed>'} "
        f"board={device.board or '<unknown>'} "
        f"addresses={','.join(device.addresses) or '<no-ip>'}"
    )


def filter_devices_by_route(
    devices: Iterable[DeviceRecord],
    *,
    did: str = "",
    cid: str = "",
    prod: str = "",
    oid: str = "",
) -> list[DeviceRecord]:
    records = sort_and_deduplicate(devices)
    requested_did = did.strip()
    requested_cid = cid.strip()
    requested_prod = prod.strip()
    requested_oid = oid.strip()
    if not any((requested_did, requested_cid, requested_prod, requested_oid)):
        return records
    filtered = records
    if requested_did:
        filtered = [device for device in filtered if device.did.strip() == requested_did]
    if requested_cid:
        filtered = [device for device in filtered if device.cid.strip() == requested_cid]
    if requested_prod:
        filtered = [device for device in filtered if device.prod.strip() == requested_prod]
    if requested_oid:
        filtered = [device for device in filtered if device.oid.strip() == requested_oid]
    return filtered


def expect_one_device(devices: Sequence[DeviceRecord], requested: str = "") -> DeviceRecord:
    if len(devices) == 1:
        return devices[0]

    if not devices:
        if requested:
            raise RuntimeError(f"no MMWK device matching {requested} discovered over mDNS")
        raise RuntimeError("no MMWK devices discovered over mDNS")

    lines = ["multiple MMWK devices discovered over mDNS; provide --did or --cid:"]
    lines.extend(f"  {device_label(device)}" for device in devices)
    raise RuntimeError("\n".join(lines))


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
    parser.add_argument("--did", metavar="DID", default="", help="filter by discovered DID")
    parser.add_argument("--prod", metavar="PROD", default="", help="filter by discovered product route segment")
    parser.add_argument("--oid", metavar="OID", default="", help="filter by discovered organization route segment")
    parser.add_argument("--cid", metavar="CID", default="", help="filter by discovered claimed route id")
    parser.add_argument("--expect-one", action="store_true", help="fail unless exactly one matching device is discovered")
    parser.add_argument(
        "--print-did",
        action="store_true",
        help="with --expect-one, print only the selected did",
    )
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
        devices = filter_devices_by_route(
            devices,
            did=getattr(args, "did", ""),
            cid=getattr(args, "cid", ""),
            prod=getattr(args, "prod", ""),
            oid=getattr(args, "oid", ""),
        )
        if args.print_did and not args.expect_one:
            raise ValueError("--print-did requires --expect-one")
        if args.expect_one:
            requested = " ".join(
                part
                for part in (
                    f"--did {args.did}" if getattr(args, "did", "") else "",
                    f"--cid {args.cid}" if getattr(args, "cid", "") else "",
                    f"--prod {args.prod}" if getattr(args, "prod", "") else "",
                    f"--oid {args.oid}" if getattr(args, "oid", "") else "",
                )
                if part
            )
            selected = expect_one_device(devices, requested)
            devices = [selected]
            if args.print_did:
                print(selected.did)
                return 0
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
