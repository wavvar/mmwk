from __future__ import annotations

import argparse
import ipaddress
import os
import platform
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


DEFAULT_AP_CIDR = "192.168.4.2/24"


@dataclass(frozen=True)
class InterfaceInfo:
    name: str
    mac: str = ""
    cidrs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ApLinkPlan:
    iface: str
    cidr: str
    host_ip: str
    already_present: bool
    add_command: list[str] | None


def _interface(value: str) -> ipaddress.IPv4Interface:
    parsed = ipaddress.ip_interface(value)
    if parsed.version != 4:
        raise ValueError(f"AP CIDR must be IPv4: {value}")
    return parsed


def _prefix_to_netmask(prefixlen: int) -> str:
    network = ipaddress.IPv4Network(f"0.0.0.0/{prefixlen}")
    return str(network.netmask)


def _normalize_mac(value: str) -> str:
    parts = re.findall(r"[0-9a-fA-F]{2}", value or "")
    if len(parts) != 6:
        return ""
    return ":".join(part.lower() for part in parts)


def _interface_ip_in_network(cidrs: Iterable[str], network: ipaddress.IPv4Network) -> str:
    for cidr in cidrs:
        try:
            parsed = _interface(cidr)
        except ValueError:
            continue
        if parsed.ip in network:
            return str(parsed.ip)
    return ""


def _linux_add_command(cidr: str, iface: str) -> list[str]:
    return ["sudo", "ip", "addr", "add", cidr, "dev", iface]


def _darwin_add_command(cidr: str, iface: str) -> list[str]:
    target = _interface(cidr)
    return [
        "sudo",
        "ifconfig",
        iface,
        "alias",
        str(target.ip),
        "netmask",
        _prefix_to_netmask(target.network.prefixlen),
    ]


def _wifi_name_candidate(name: str) -> bool:
    lowered = name.lower()
    if lowered in {"lo", "awdl0", "llw0"}:
        return False
    if lowered.startswith(("wl", "wlan", "wifi")):
        return True
    return False


def _candidate_names(
    *,
    system: str,
    interfaces: Sequence[InterfaceInfo],
    requested_iface: str | None,
    linux_wifi_ifaces: Sequence[str],
    darwin_wifi_ifaces: Sequence[str],
    windows_wifi_macs: Sequence[str],
) -> list[str]:
    if requested_iface:
        return [requested_iface]

    names: list[str] = []
    known_names = {iface.name for iface in interfaces}

    def append(name: str) -> None:
        if name and name in known_names and name not in names:
            names.append(name)

    if system == "Linux":
        windows_macs = {_normalize_mac(mac) for mac in windows_wifi_macs}
        windows_macs.discard("")
        for iface in interfaces:
            if _normalize_mac(iface.mac) in windows_macs:
                append(iface.name)
        for name in linux_wifi_ifaces:
            append(name)
        for iface in interfaces:
            if _wifi_name_candidate(iface.name):
                append(iface.name)
    elif system == "Darwin":
        for name in darwin_wifi_ifaces:
            append(name)
        for iface in interfaces:
            if _wifi_name_candidate(iface.name):
                append(iface.name)

    return names


def _format_interfaces(interfaces: Sequence[InterfaceInfo]) -> str:
    if not interfaces:
        return "none"
    lines = []
    for iface in interfaces:
        mac = iface.mac or "-"
        cidrs = ",".join(iface.cidrs) if iface.cidrs else "-"
        lines.append(f"{iface.name} mac={mac} ipv4={cidrs}")
    return "; ".join(lines)


def build_ap_link_plan(
    *,
    system: str,
    cidr: str,
    interfaces: Sequence[InterfaceInfo],
    requested_iface: str | None = None,
    linux_wifi_ifaces: Sequence[str] = (),
    darwin_wifi_ifaces: Sequence[str] = (),
    windows_wifi_macs: Sequence[str] = (),
) -> ApLinkPlan:
    target = _interface(cidr)
    target_network = target.network
    by_name = {iface.name: iface for iface in interfaces}
    candidates = _candidate_names(
        system=system,
        interfaces=interfaces,
        requested_iface=requested_iface,
        linux_wifi_ifaces=linux_wifi_ifaces,
        darwin_wifi_ifaces=darwin_wifi_ifaces,
        windows_wifi_macs=windows_wifi_macs,
    )

    for name in candidates:
        iface = by_name.get(name)
        if iface is None:
            continue
        existing_ip = _interface_ip_in_network(iface.cidrs, target_network)
        if existing_ip:
            return ApLinkPlan(
                iface=name,
                cidr=cidr,
                host_ip=existing_ip,
                already_present=True,
                add_command=None,
            )

    if not candidates:
        raise RuntimeError(f"no Wi-Fi interface found; interfaces: {_format_interfaces(interfaces)}")

    iface_name = candidates[0]
    if system == "Linux":
        add_command = _linux_add_command(cidr, iface_name)
    elif system == "Darwin":
        add_command = _darwin_add_command(cidr, iface_name)
    else:
        raise RuntimeError(f"AP link setup is supported on Linux and macOS only, not {system}")

    return ApLinkPlan(
        iface=iface_name,
        cidr=cidr,
        host_ip=str(target.ip),
        already_present=False,
        add_command=add_command,
    )


def _command_output(command: Sequence[str], *, timeout: float | None = None) -> str:
    try:
        return subprocess.check_output(command, stderr=subprocess.DEVNULL, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""


def _linux_interface_cidrs(iface: str) -> tuple[str, ...]:
    output = _command_output(["ip", "-o", "-4", "addr", "show", "dev", iface])
    cidrs: list[str] = []
    for line in output.splitlines():
        parts = line.split()
        if "inet" not in parts:
            continue
        inet_index = parts.index("inet")
        if inet_index + 1 < len(parts):
            cidrs.append(parts[inet_index + 1])
    return tuple(cidrs)


def _darwin_interface_cidrs(iface: str) -> tuple[str, ...]:
    output = _command_output(["ifconfig", iface])
    cidrs: list[str] = []
    for line in output.splitlines():
        match = re.search(r"\binet\s+(\d+\.\d+\.\d+\.\d+)\s+netmask\s+(0x[0-9a-fA-F]+)", line)
        if not match:
            continue
        ip_text, hex_mask = match.groups()
        mask_text = str(ipaddress.IPv4Address(int(hex_mask, 16)))
        prefix = ipaddress.IPv4Network(f"0.0.0.0/{mask_text}", strict=False).prefixlen
        cidrs.append(f"{ip_text}/{prefix}")
    return tuple(cidrs)


def _linux_interfaces() -> list[InterfaceInfo]:
    sys_class_net = Path("/sys/class/net")
    if not sys_class_net.is_dir():
        return []
    interfaces = []
    for item in sorted(sys_class_net.iterdir()):
        name = item.name
        mac = ""
        try:
            mac = item.joinpath("address").read_text(encoding="utf-8").strip()
        except OSError:
            pass
        interfaces.append(InterfaceInfo(name=name, mac=mac, cidrs=_linux_interface_cidrs(name)))
    return interfaces


def _darwin_interfaces() -> list[InterfaceInfo]:
    output = _command_output(["ifconfig", "-l"])
    interfaces = []
    for name in output.split():
        details = _command_output(["ifconfig", name])
        mac_match = re.search(r"\bether\s+([0-9a-fA-F:]{17})\b", details)
        interfaces.append(
            InterfaceInfo(
                name=name,
                mac=mac_match.group(1) if mac_match else "",
                cidrs=_darwin_interface_cidrs(name),
            )
        )
    return interfaces


def collect_interfaces(*, system: str | None = None) -> list[InterfaceInfo]:
    current_system = system or platform.system()
    if current_system == "Linux":
        return _linux_interfaces()
    if current_system == "Darwin":
        return _darwin_interfaces()
    return []


def linux_wifi_interfaces() -> tuple[str, ...]:
    names: list[str] = []

    def append(name: str) -> None:
        if name and name not in names:
            names.append(name)

    sys_class_net = Path("/sys/class/net")
    if sys_class_net.is_dir():
        for item in sorted(sys_class_net.iterdir()):
            if item.joinpath("wireless").exists():
                append(item.name)

    output = _command_output(["iw", "dev"])
    for line in output.splitlines():
        match = re.match(r"\s*Interface\s+(\S+)\s*$", line)
        if match:
            append(match.group(1))

    return tuple(names)


def darwin_wifi_interfaces() -> tuple[str, ...]:
    output = _command_output(["networksetup", "-listallhardwareports"])
    names: list[str] = []
    current_is_wifi = False
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if line.startswith("Hardware Port:"):
            value = line.split(":", 1)[1].strip().lower()
            current_is_wifi = value in {"wi-fi", "airport"}
            continue
        if current_is_wifi and line.startswith("Device:"):
            name = line.split(":", 1)[1].strip()
            if name and name not in names:
                names.append(name)
            current_is_wifi = False
    return tuple(names)


def windows_wifi_macs() -> tuple[str, ...]:
    if not _is_wsl():
        return ()
    script = (
        "Get-NetAdapter | "
        "Where-Object { "
        "$_.Name -match 'Wi-Fi|Wireless|WLAN' -or "
        "$_.InterfaceDescription -match 'Wi-Fi|Wireless|WLAN|802.11' "
        "} | ForEach-Object { $_.MacAddress }"
    )
    output = _command_output(["powershell.exe", "-NoProfile", "-Command", script], timeout=8)
    macs = []
    for line in output.splitlines():
        mac = line.strip()
        if _normalize_mac(mac):
            macs.append(mac)
    return tuple(macs)


def _is_wsl() -> bool:
    if "WSL_DISTRO_NAME" in os.environ:
        return True
    release = platform.uname().release.lower()
    return "microsoft" in release or "wsl" in release


def _wifi_hints(system: str) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    if system == "Linux":
        return linux_wifi_interfaces(), (), windows_wifi_macs()
    if system == "Darwin":
        return (), darwin_wifi_interfaces(), ()
    return (), (), ()


def ensure_ap_link(*, cidr: str = DEFAULT_AP_CIDR, iface: str | None = None) -> ApLinkPlan:
    current_system = platform.system()
    interfaces = collect_interfaces(system=current_system)
    linux_ifaces, darwin_ifaces, windows_macs = _wifi_hints(current_system)
    plan = build_ap_link_plan(
        system=current_system,
        cidr=cidr,
        interfaces=interfaces,
        requested_iface=iface,
        linux_wifi_ifaces=linux_ifaces,
        darwin_wifi_ifaces=darwin_ifaces,
        windows_wifi_macs=windows_macs,
    )
    if plan.add_command is not None:
        try:
            subprocess.run(plan.add_command, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            command = shlex.join(plan.add_command)
            raise RuntimeError(f"failed to configure AP link; run manually: {command}") from exc
    return plan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="config.sh init --ap-link",
        description="Prepare the host Wi-Fi interface for the bridge AP subnet.",
    )
    parser.add_argument("--cidr", metavar="CIDR", default=DEFAULT_AP_CIDR, help=f"host AP subnet CIDR (default: {DEFAULT_AP_CIDR})")
    parser.add_argument("--iface", metavar="IFACE", help="host interface override")
    return parser


def run(args: argparse.Namespace) -> int:
    try:
        plan = ensure_ap_link(cidr=args.cidr, iface=args.iface)
    except (RuntimeError, ValueError) as exc:
        print(f"config.sh init --ap-link: {exc}", file=sys.stderr)
        return 1

    command = shlex.join(plan.add_command) if plan.add_command else ""
    print(f"MMWK_AP_LINK_IFACE={plan.iface}")
    print(f"MMWK_AP_LINK_HOST_IP={plan.host_ip}")
    print(f"MMWK_AP_LINK_CIDR={plan.cidr}")
    print(f"MMWK_AP_LINK_ALREADY_PRESENT={1 if plan.already_present else 0}")
    print(f"MMWK_AP_LINK_COMMAND={command}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
