# Radar Task Tools

These task-oriented wrappers stay outside `mmwk_cli.sh` and center on two local radar workflows:

- `config.sh`: one registry-backed entrypoint with `init`, `update`, and `list`
- `collect.sh`: registry-backed MQTT raw collection

The registry file is `<working>/device.yml`. The default `<working>` resolution is:

1. `./collect` if it already exists under your current working directory
2. `~/.mmwk/collect` if it already exists
3. otherwise create and use `./collect`

Pass `--working DIR` on either wrapper when you want a different location.

Each device record in `device.yml` stores the resolved transport endpoints that the wrappers need later:

- `device_id`
- `mqtt_server` / `mqtt_port` / `mqtt_uri`
- `http_server` / `http_port` / `http_base_url`
- optional `ssid`
- `updated_at`

## 1. Initialize A UART-Connected Device

Use `config.sh init` when the board is still on UART and you want to store its server binding into `<working>/device.yml`:

```bash
./tools/config.sh init --port /dev/ttyUSB1
```

If Wi-Fi credentials still need to be provisioned, add them explicitly:

```bash
./tools/config.sh init \
  --port /dev/ttyUSB1 \
  --ssid YOUR_WIFI \
  --password YOUR_PASSWORD \
  --working ./collect-lab
```

If `--mqtt-server` and `--http-server` are omitted, the tool resolves the local machine through `server.sh`.

On success the script prints:

- the detected device id
- the resolved MQTT URI
- the resolved HTTP base URL
- the `<working>` path
- the `device.yml` path
- copy-paste-ready `config.sh update` and `collect.sh` commands

`config.sh init` writes `device.yml` only after UART configuration, reboot, and MQTT readiness verification all succeed.

## 2. Update Radar Firmware Or Runtime Cfg

Use `config.sh update` after the device is already registered in `device.yml`.

Firmware OTA:

```bash
./tools/config.sh update \
  --device-id 0123456789ab \
  --fw ../firmwares/radar/iwr6843/oob/out_of_box_6843_aop.bin \
  --cfg ../firmwares/radar/iwr6843/oob/out_of_box_6843_aop.cfg \
  --working ./collect-lab
```

Runtime cfg only:

```bash
./tools/config.sh update \
  --device-id 0123456789ab \
  --cfg ./runtime.cfg \
  --working ./collect-lab
```

`config.sh update` resolves MQTT and HTTP endpoints from `device.yml`. With `--fw`, it uses `radar fw ota`; with cfg-only updates, it uses `radar config apply`.

## 3. List Registered Devices

Use `config.sh list` to inspect the current registry:

```bash
./tools/config.sh list --working ./collect-lab
```

The output includes:

- `device_id`
- MQTT URI
- HTTP base URL

Use this to confirm which registry entry `config.sh update` and `collect.sh` will consume.

## 4. Collect Raw Data

Use `collect.sh` for late-attach MQTT collection windows after the device has already been registered:

```bash
./tools/collect.sh \
  --device-id 0123456789ab \
  --duration 10 \
  --working ./collect-lab
```

If you want the helper to restart the radar service after subscriptions are ready and raw forwarding is enabled, add `--reboot` so startup `raw_resp` traffic is captured in the same window:

```bash
./tools/collect.sh \
  --device-id 0123456789ab \
  --duration 20 \
  --reboot \
  --working ./collect-lab
```

If `--duration` is omitted, the helper runs until you press `Ctrl-C`:

```bash
./tools/collect.sh \
  --device-id 0123456789ab \
  --working ./collect-lab
```

Each run writes its artifacts under `<working>/data/<device-id>/` with a start-time prefix, for example:

- `20260424-153000_raw_data.sraw`
- `20260424-153000_raw_data.log`
- `20260424-153000_summary.json`
- `20260424-153000_state_events.log`

The helper prints high-level states such as MQTT connection, command traffic seen, raw data seen, disconnect, reconnect, and shutdown.

Add `--reboot` only when you intentionally want `collect.sh` to restart the radar service after subscribe-ready bootstrap so startup `raw_resp` from that same window lands in the capture.

If you need a publication-safe 6843 vs 6432 board-selection walkthrough built around these wrappers, start with [Develop Radar With Bridge](bridge-ti-radar-debug.md).
