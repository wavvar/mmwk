# Config Helper

`config.sh set` configures device Wi-Fi and MQTT settings without changing the official `run.sh` command surface. `config.sh search` discovers nearby MMWK devices over mDNS.

Configure device Wi-Fi and MQTT settings over UART or MQTT, or find device ids advertised on the local link.

The working directory is the `cli` directory:

```bash
cd ./cli
```

## What It Does

- Push Wi-Fi credentials with `network wifi`
- Point 4G users to the official `network 4g` and `network priority` commands
- Push MQTT settings with `network mqtt`
- Discover MMWK device ids advertised through `_mmwk._tcp.local.`
- Optionally reboot the device with `node reboot`
- Optionally start or reuse `server.sh` and feed its local broker URI back into the device

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

### 2. MQTT control path only

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

### 3. 4G and network priority

`config.sh set` remains focused on Wi-Fi/MQTT onboarding. For PRO/WDR 4G configuration, use the official `run.sh` network commands directly:

```bash
./run.sh network 4g --apn YOUR_APN -p /dev/cu.usbserial-0001
./run.sh network priority --pref 4g -p /dev/cu.usbserial-0001
./run.sh network priority --pref wifi -p /dev/cu.usbserial-0001
```

Saving Wi-Fi credentials does not change a 4G preference. 4G failure does not automatically fall back to Wi-Fi; switch the preference explicitly when you want Wi-Fi.

### 4. Find devices with mDNS

Use `search` when you need the device id before choosing an MQTT topic or updating `device.yml`:

```bash
./config.sh search
./config.sh search --json
```

Default output is a compact table with device id, name, board, version, mode, addresses, and hostname. JSON output returns the same fields under `devices`.

When the host is connected to a device provisioning AP but the interface does not have an address in the AP subnet, pass the interface explicitly:

```bash
./config.sh search --ap-iface wlan0 --ap-cidr 192.168.4.2/24
```

`--ap-iface` temporarily adds `--ap-cidr` to that interface, skips the add if the CIDR is already present, performs the mDNS browse, and removes the temporary address afterwards unless `--keep-ap-alias` is set. It does not guess interfaces or change routes. The host still needs to be on the same Wi-Fi link as the device AP.

## Key Options

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
- `--ap-iface IFACE`: host interface to receive the temporary AP-subnet address
- `--ap-cidr CIDR`: temporary host address for device AP discovery, default `192.168.4.2/24`
- `--keep-ap-alias`: leave the temporary address configured after search

## Notes

- If you use `--server-local`, do not also pass `--mqtt-uri`; the tool resolves the broker from `server.sh`.
- Device-side MQTT identity and canonical topics are fixed to the Wi-Fi STA MAC. `--device-id`, `--cmd-topic`, and `--resp-topic` only help `config.sh set` reach the current MQTT control path; they do not rewrite the stored topic identity.
- If you skip `--reboot`, the tool still writes the settings, but the device may not use them until the next reboot.
- `config.sh search` depends on mDNS multicast, so it discovers devices on the current local link rather than through routed networks.
