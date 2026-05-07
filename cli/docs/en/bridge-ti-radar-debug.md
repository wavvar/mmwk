# Develop Radar With Bridge

This guide describes a short, repeatable development workflow for building and iterating TI radar work through `mmwk_sensor_bridge`.

Here, "develop radar with bridge" means using the bridge as the public development carrier for the full host-side loop:

- provision the bridge over UART
- push radar firmware or runtime cfg updates over the network
- capture raw data and startup output over MQTT
- repeat that loop while choosing the right public bridge board for the target radar family

Assume your current working directory is `cli` inside a published `mmwk` package. The examples below only use that public package layout and POSIX shell wrapper names. On Windows PowerShell, use `.\server.ps1`, `.\run.ps1`, and `.\collect.ps1` where available; `.\config.ps1` requires Bash/Git Bash because it delegates to `config.sh`.

## Choose The Right Bridge Board

| Radar family | Recommended bridge board | Public artifact shape | Notes |
|---|---|---|---|
| `IWR6843` / `IWR6843AOP` | `mini` or `pro` | `.bin` + `.cfg` under `../firmwares/radar/iwr6843/...` | Standard 68xx bridge development flow |
| `IWRL6432` | `wdr` | `.appimage` + `.cfg` under `../firmwares/radar/iwrl6432/...` | Single-UART radar development path on the bridge side |

Both paths use the same wrappers: `config.sh init|update|list` plus `collect.sh`. The real differences are the bridge board, the radar artifact pair, and the runtime capture expectations.

## Common Workflow

1. Start a local MQTT + HTTP helper with `server.sh`.
2. Point `server.sh --serve-dir` at the radar artifact directory you plan to OTA.
3. Run `config.sh init` over UART. It stores Wi-Fi and MQTT settings, reboots the device, verifies MQTT reachability, and writes the device entry into `<working>/device.yml`.
4. Run `config.sh update` over MQTT. It resolves the device transport settings from `device.yml` and performs radar OTA or runtime cfg apply.
5. Run `collect.sh` over MQTT. It resolves the device entry from `device.yml` and writes capture outputs under `<working>/data/<device-id>/`.

Recommended pattern:

```bash
./server.sh start --serve-dir <radar-artifact-dir>
eval "$(./server.sh env)"
```

`server.sh` auto-detects the local host IP by default. If it picks the wrong interface, restart it with `--host-ip <your-host-ip>`.

The registry-backed flow keeps using the same server information after `config.sh init`. If you want a different registry root, pass `--working <dir>` consistently to `config.sh` and `collect.sh`.

Useful helper behavior:

- `config.sh list` prints the current `device_id`, MQTT URI, and HTTP base URL from `<working>/device.yml`.
- `collect.sh` writes timestamp-prefixed artifacts under `<working>/data/<device-id>/`: `*_raw_data.sraw`, `*_raw_data.log`, `*_summary.json`, and `*_state_events.log`.
- Add `collect.sh --reboot` only when you intentionally want the helper to restart the radar service after subscribe-ready bootstrap so startup `raw_resp` from that same window is captured.

## 6843 Series

Use `mini` or `pro`. Both are valid bridge boards for the normal 6843 development flow.

The example below uses the public OOB artifact pair. Replace it with your own 6843 `.bin` + `.cfg` pair when needed, but always keep the firmware and config matched.

```bash
cd ./cli

PORT=<serial-port>
SSID=<wifi-ssid>
PASSWORD=<wifi-password>
FW_DIR=../firmwares/radar/iwr6843/oob

./server.sh start --serve-dir "$FW_DIR"
eval "$(./server.sh env)"

WORKING=./collect-lab

./config.sh init \
  --port "$PORT" \
  --ssid "$SSID" \
  --password "$PASSWORD" \
  --working "$WORKING"

DEVICE_ID=<printed-by-config.sh>

./config.sh update \
  --device-id "$DEVICE_ID" \
  --fw "$FW_DIR/out_of_box_6843_aop.bin" \
  --cfg "$FW_DIR/out_of_box_6843_aop.cfg" \
  --working "$WORKING"

./run.sh radar status \
  --transport mqtt \
  --device-id "$DEVICE_ID" \
  --broker "$MMWK_SERVER_HOST_IP"

./run.sh radar fw version \
  --transport mqtt \
  --device-id "$DEVICE_ID" \
  --broker "$MMWK_SERVER_HOST_IP"

./collect.sh \
  --device-id "$DEVICE_ID" \
  --duration 30 \
  --working "$WORKING"
```

What to expect:

- `config.sh init` succeeds only after the bridge can reach the configured MQTT server, and only then updates `device.yml`.
- `config.sh update` waits until `radar status` returns `running`.
- `collect.sh` writes timestamp-prefixed capture files under `<working>/data/<device-id>/`.

## 6432 Series

Use `wdr`. This is the right bridge board for the public 6432 bridge-development path.

The example below uses the public presence artifact pair:

```bash
cd ./cli

PORT=<serial-port>
SSID=<wifi-ssid>
PASSWORD=<wifi-password>
FW_DIR=../firmwares/radar/iwrl6432/presence

./server.sh start --serve-dir "$FW_DIR"
eval "$(./server.sh env)"

WORKING=./collect-lab

./config.sh init \
  --port "$PORT" \
  --ssid "$SSID" \
  --password "$PASSWORD" \
  --working "$WORKING"

DEVICE_ID=<printed-by-config.sh>

./config.sh update \
  --device-id "$DEVICE_ID" \
  --fw "$FW_DIR/presence.appimage" \
  --cfg "$FW_DIR/presence.cfg" \
  --working "$WORKING"

./run.sh radar status \
  --transport mqtt \
  --device-id "$DEVICE_ID" \
  --broker "$MMWK_SERVER_HOST_IP"

./run.sh radar fw version \
  --transport mqtt \
  --device-id "$DEVICE_ID" \
  --broker "$MMWK_SERVER_HOST_IP"

./collect.sh \
  --device-id "$DEVICE_ID" \
  --duration 30 \
  --working "$WORKING"
```

6432-specific notes:

- The bridge-side radar path is single-UART.
- When `uart_split=1`, steady runtime raw bytes mainly appear in `raw_data.sraw`.
- The timestamped `*_raw_data.log` file is still important for boot text and command-response windows.

Do not judge a 6432 capture only from `*_raw_data.log`. Check both `*_raw_data.sraw` and `*_summary.json`.

## Practical Checks

- If `config.sh init` prints the device id and follow-up commands, the UART bring-up step is complete.
- If `config.sh update` exits successfully, the radar OTA or runtime cfg path has already been verified through `radar status`, and for OTA also through `radar fw version`.
- If you need a manual runtime check later, use `./run.sh radar status` first and treat `state=running` as the hard gate.
- If the USB serial path changes after reboot, rediscover the port before rerunning UART commands.

## When To Use `collect.sh` vs `collect -p`

`collect.sh` is a task-oriented MQTT helper for late-attach raw collection windows. It reads MQTT settings from `device.yml` and writes timestamp-prefixed outputs under `<working>/data/<device-id>/`.

If you need startup-time command-port text from the same reboot, flash, or radar restart window, use the official UART-assisted command instead:

```bash
./run.sh collect -p <serial-port> --duration 12
```

Use `collect.sh` when the radar is already on the network and you want a simpler MQTT-only collection loop.
