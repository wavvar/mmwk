# Config Helper

`config.sh init` registers a UART-connected device into `device.yml`, `config.sh set` configures device Wi-Fi and MQTT settings without changing the official `run.sh` command surface, and `config.sh search` discovers nearby MMWK devices over mDNS.

Configure device Wi-Fi and MQTT settings over UART or MQTT, or find device ids advertised on the local link.

The working directory is the `cli` directory:

```bash
cd ./cli
```

Examples below use POSIX shell syntax. On Windows PowerShell, run `.\config.ps1 ...` only when Bash is available, for example through Git Bash; the PowerShell wrapper delegates to `config.sh` to keep behavior identical. If Bash is not available, use the main CLI directly with `.\run.ps1 network wifi|mqtt|status ...` for manual configuration, or install Git Bash before using the registry helper.

## What It Does

- Push Wi-Fi credentials with `network wifi`
- Point 4G users to the official `network 4g` and `network priority` commands
- Push MQTT settings with `network mqtt`
- Discover MMWK device ids advertised through `_mmwk._tcp.local.`
- Optionally reboot the device with `node reboot`
- Optionally start or reuse `server.sh` and feed its local broker URI back into the device
- Optionally prepare the host Wi-Fi interface for the bridge provisioning AP subnet before `init`

This tool can talk to the device over UART or over an existing MQTT control path.

## Common Flows

### 1. UART + local `server.sh`

Use this when the device is on your desk, you still have serial access, and you want the script to prepare the local broker for later raw capture:

```bash
./config.sh set --server-local \
  --ssid "MyWiFi" \
  --password "MyPass" \
  --port /dev/cu.usbserial-0001 \
  --reboot
```

When `--server-local` is set, `config.sh set` starts or reuses `server.sh`, reads the resolved MQTT URI from its env output, and pushes that URI back into the device. `server.sh` now prints requested ports, resolved ports, log paths, and the env file path so you can diagnose what happened.

### 2. UART init through the bridge AP link

Use `init --ap-link` when the host is connected to a bridge provisioning AP such as `VENTROPIC-*`, and the bridge needs to reach MQTT/HTTP services on the same AP subnet:

```bash
./config.sh init --port /dev/ttyUSB1 --ap-link
```

`--ap-link` means "prepare the host side of the bridge AP link". It is not an Ethernet option. The helper looks for the host Wi-Fi interface, checks whether it already has an address inside the requested AP subnet, and only runs `sudo` when the address is missing.

Default address:

```text
192.168.4.2/24
```

If the Wi-Fi interface already has any `192.168.4.x` address in that `/24`, `init --ap-link` leaves the interface unchanged and uses the existing host IP. If not, it adds the requested alias and keeps it after `init` exits, because later mDNS discovery, OTA, capture, and debugging may still need the same AP-link address.

Automatic interface discovery is platform-specific:

- Linux: uses kernel Wi-Fi metadata under `/sys/class/net/*/wireless`, `iw dev`, and Wi-Fi-style names such as `wlan0` or `wl*`.
- WSL: asks Windows for adapters named or described as `Wi-Fi`, `Wireless`, `WLAN`, or `802.11`, then maps their MAC addresses back to Linux interfaces. This is what avoids accidentally selecting the default WSL `eth0` / vEthernet path.
- macOS: uses `networksetup -listallhardwareports` and selects the `Wi-Fi` / `AirPort` device, usually `en0` or `en1`.

Override the detected interface when you already know it:

```bash
./config.sh init --port /dev/ttyUSB1 --ap-link --ap-iface eth1
./config.sh init --port /dev/cu.usbserial-0001 --ap-link --ap-iface en0
```

Change the host AP CIDR when the lab setup uses a non-default address:

```bash
./config.sh init --port /dev/ttyUSB1 --ap-link --ap-cidr 192.168.4.10/24
```

When an address must be added, the helper runs one of these commands:

```bash
# Linux / WSL
sudo ip addr add 192.168.4.2/24 dev <wifi-iface>

# macOS
sudo ifconfig <wifi-iface> alias 192.168.4.2 netmask 255.255.255.0
```

If `sudo` fails or you prefer to run the privileged step yourself, the error prints the exact command to run manually. After running it, rerun the same `config.sh init --ap-link ...` command; the helper will see the AP-subnet address and skip `sudo`.

When `--mqtt-server` or `--http-server` is omitted, `init --ap-link` also passes the selected AP host IP into `server.sh`. This keeps the generated MQTT and HTTP URLs on the bridge AP subnet, for example `mqtt://192.168.4.2:1883`, instead of accidentally advertising another host interface.

Manual cleanup is optional. Use it only when you no longer need bridge AP discovery or capture from that host:

```bash
# Linux / WSL
sudo ip addr del 192.168.4.2/24 dev <wifi-iface>

# macOS
sudo ifconfig <wifi-iface> -alias 192.168.4.2
```

### 3. MQTT control path only

Use this when the device is already online and you want to re-point it without opening UART:

```bash
./config.sh set --transport mqtt \
  --broker 192.168.1.100 \
  --mqtt-port 1883 \
  --device-id dc5475c879c0 \
  --mqtt-uri mqtt://192.168.1.200:1883 \
  --reboot
```

`--transport mqtt` uses the current control-plane broker and topics only to deliver the configuration commands. The device-side MQTT identity is fixed to the Wi-Fi STA MAC, so `network mqtt` now stores only broker/auth settings and exposes the canonical topics as read-only derived values.

### 4. 4G and network priority

`config.sh set` remains focused on Wi-Fi/MQTT onboarding. For PRO devices and 4G-equipped WDR devices, use the official `run.sh` network commands directly:

```bash
./run.sh network 4g --apn YOUR_APN -p /dev/cu.usbserial-0001
./run.sh network priority --pref 4g -p /dev/cu.usbserial-0001
./run.sh network priority --pref wifi -p /dev/cu.usbserial-0001
```

Saving Wi-Fi credentials does not change a 4G preference. 4G failure does not automatically fall back to Wi-Fi; switch the preference explicitly when you want Wi-Fi.

### 5. Find devices with mDNS

Use `search` when you need the device id before choosing an MQTT topic or updating `device.yml`:

```bash
./config.sh search
./config.sh search --json
./config.sh search --expect-one --print-device-id
```

Default output is a compact table with device id, name, board, version, mode, addresses, and hostname. JSON output returns the same fields under `devices`.

For scripts, use `--expect-one` when the caller requires an unambiguous device. It returns an error with candidate lines when more than one device is discovered, and it returns an error when none are discovered. `--device-id ID` filters the discovered `id` / `client_id` fields before applying that uniqueness check. `--print-device-id` is intended for shell wrappers and prints only the selected `client_id` / `id`:

```bash
DEVICE_ID="$(./config.sh search --expect-one --print-device-id)"
./config.sh search --device-id "$DEVICE_ID" --expect-one --json
```

mDNS discovery publishes device identity, board, version, mode, hostname, and local-link addresses. It does not publish the MQTT broker URI; pass the broker explicitly or resolve it from `device.yml`, `server.sh`, or your environment.

When the host is connected to a device provisioning AP but the interface does not have an address in the AP subnet, pass the interface explicitly:

```bash
./config.sh search --ap-iface wlan0 --ap-cidr 192.168.4.2/24
```

`search --ap-iface` is intentionally narrower than `init --ap-link`: it temporarily adds `--ap-cidr` to the named interface, skips the add if the CIDR is already present, performs the mDNS browse, and removes the temporary address afterwards unless `--keep-ap-alias` is set. It does not guess interfaces or change routes. The host still needs to be on the same Wi-Fi link as the device AP.

## Key Options

### `config.sh init`

- `--port PORT`: UART serial port used for bring-up
- `--ssid` / `--password`: optional Wi-Fi credentials to store before reboot
- `--mqtt-server`, `--mqtt-port`, `--http-server`, `--http-port`: explicit endpoints; if omitted, `server.sh` is started or reused
- `--ap-link`: prepare the host Wi-Fi interface for the bridge AP subnet before resolving local server defaults
- `--ap-iface IFACE`: host Wi-Fi interface override for `--ap-link`
- `--ap-cidr CIDR`: host AP subnet CIDR for `--ap-link`, default `192.168.4.2/24`
- `--working DIR`: registry root for `device.yml`

### `config.sh set`

- `--transport uart|mqtt`: current control path used to push settings
- `--ssid` / `--password`: Wi-Fi credentials
- `--mqtt-uri` / `--mqtt-user` / `--mqtt-pass`: stored broker and auth settings
- `--device-id`, plus optional `--cmd-topic` / `--resp-topic`: tell `config.sh set` how to reach the current MQTT control path
- `--server-local`: start or reuse `server.sh` and use its resolved broker URI
- `--server-state-dir`, `--server-serve-dir`, `--server-upload-dir`, `--server-host-ip`, `--server-target-ip`, `--server-mqtt-port`, `--server-http-port`: control how `server.sh` is started or reused
- `--reboot`: reboot after writing settings

### `config.sh search`

- `--timeout SEC`: mDNS browse duration
- `--json`: print machine-readable JSON
- `--device-id ID`: filter by discovered `id` or `client_id`
- `--expect-one`: fail unless exactly one matching device is discovered
- `--print-device-id`: with `--expect-one`, print only the selected `client_id` / `id`
- `--ap-iface IFACE`: host interface to receive the temporary AP-subnet address
- `--ap-cidr CIDR`: temporary host address for device AP discovery, default `192.168.4.2/24`
- `--keep-ap-alias`: leave the temporary address configured after search

## Notes

- If you use `--server-local`, do not also pass `--mqtt-uri`; the tool resolves the broker from `server.sh`.
- Device-side MQTT identity and canonical topics are fixed to the Wi-Fi STA MAC. `--device-id`, `--cmd-topic`, and `--resp-topic` only help `config.sh set` reach the current MQTT control path; they do not rewrite the stored topic identity.
- If you skip `--reboot`, the tool still writes the settings, but the device may not use them until the next reboot.
- `config.sh search` depends on mDNS multicast, so it discovers devices on the current local link rather than through routed networks.
- `config.sh search` does not discover MQTT broker endpoints. Discovery callers still need a broker from arguments, env, local server state, or `device.yml`.
- `init --ap-link` changes only the host interface address. It does not connect the host to Wi-Fi, change device Wi-Fi credentials, or remove an existing alias.
