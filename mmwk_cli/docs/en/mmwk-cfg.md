# MMWK CFG

`mmwk_cfg.sh` configures device Wi-Fi and MQTT settings without changing the official `mmwk_cli.sh` command surface.

Configure device Wi-Fi and MQTT settings over UART or MQTT.

The working directory is the `mmwk_cli` directory:

```bash
cd ./mmwk_cli
```

## What It Does

- Push Wi-Fi credentials with `network config`
- Push MQTT settings with `network mqtt`
- Optionally reboot the device with `device reboot`
- Optionally start or reuse `server.sh` and feed its local broker URI back into the device

This tool can talk to the device over UART or over an existing MQTT control path.

## Common Flows

### 1. UART + local `server.sh`

Use this when the device is on your desk, you still have serial access, and you want the script to prepare the local broker for later raw capture:

```bash
./tools/mmwk_cfg.sh --server-local \
  --ssid "MyWiFi" \
  --password "MyPass" \
  --port /dev/cu.usbserial-0001 \
  --reboot
```

When `--server-local` is set, `mmwk_cfg.sh` starts or reuses `server.sh`, reads the resolved MQTT URI from its env output, and pushes that URI back into the device. `server.sh` now prints requested ports, resolved ports, log paths, and the env file path so you can diagnose what happened.

### 2. MQTT control path only

Use this when the device is already online and you want to re-point it without opening UART:

```bash
./tools/mmwk_cfg.sh --transport mqtt \
  --broker 192.168.1.100 \
  --mqtt-port 1883 \
  --device-id dc5475c879c0 \
  --mqtt-uri mqtt://192.168.1.200:1883 \
  --reboot
```

`--transport mqtt` uses the current control-plane broker and topics only to deliver the configuration commands. The device-side MQTT identity is fixed to the Wi-Fi STA MAC, so `network mqtt` now stores only broker/auth settings and exposes the canonical topics as read-only derived values.

## Key Options

- `--transport uart|mqtt`: current control path used to push settings
- `--ssid` / `--password`: Wi-Fi credentials
- `--mqtt-uri`: stored broker URI
- `--server-local`: start or reuse `server.sh` and use its resolved broker URI
- `--server-state-dir`: choose which `server.sh` state dir to reuse
- `--reboot`: reboot after writing settings

## Notes

- If you use `--server-local`, do not also pass `--mqtt-uri`; the tool resolves the broker from `server.sh`.
- MQTT topics are fixed to `mmwk/{mac}/device/cmd`, `mmwk/{mac}/device/resp`, and `mmwk/{mac}/raw/...`; `mmwk_cfg.sh` does not accept topic or client-id overrides.
- If you skip `--reboot`, the tool still writes the settings, but the device may not use them until the next reboot.
