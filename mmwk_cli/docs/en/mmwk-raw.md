# MMWK RAW

`mmwk_raw.sh` is a pure-MQTT raw capture helper for cases where you intentionally want both control and raw capture to stay off UART.

Pure-MQTT raw capture helper for external MQTT-only workflows.

The working directory is the `mmwk_cli` directory:

```bash
cd ./mmwk_cli
```

## What It Does

- Captures `raw_data` into `data_resp.sraw`
- Captures startup-trimmed command-port bytes into `cmd_resp.log`
- Keeps runtime control and raw capture on MQTT only
- Supports `trigger=none`, `trigger=radar-restart`, and `trigger=device-reboot`

This helper is not a replacement for the strict startup-aware `collect -p` path.

## Broker Resolution

Unless a specific broker override is required, the default MQTT port is `1883`.

If `--broker` is absent and `MMWK_SERVER_MQTT_URI` is unset, `mmwk_raw.sh` auto-loads the broker from server.sh state. By default it checks `./output/local_server/server.env`, or you can point it somewhere else with `--server-state-dir`.

`mmwk_raw.sh` still needs a device id. Pass `--device-id`, or export `MMWK_DEVICE_ID` yourself.

## Examples

### 1. Late-attach steady-state capture

```bash
./tools/mmwk_raw.sh --trigger none \
  --broker mqtt://192.168.1.100:1883 \
  --device-id mmwk_demo_01 \
  --data-output ./data_resp.sraw \
  --resp-output ./cmd_resp.log
```

### 2. Reuse local `server.sh` state

```bash
./tools/mmwk_cfg.sh --server-local \
  --ssid "MyWiFi" \
  --password "MyPass" \
  --port /dev/cu.usbserial-0001 \
  --reboot

./tools/mmwk_raw.sh --server-state-dir ./output/local_server \
  --trigger device-reboot \
  --device-id mmwk_demo_01
```

### 3. Trigger a fresh startup window over MQTT

```bash
./tools/mmwk_raw.sh --trigger device-reboot \
  --device-id mmwk_demo_01 \
  --resp-output ./cmd_resp.log \
  --data-output ./data_resp.sraw
```

## Trigger Notes

- `trigger=none`: late-attach steady-state collection; `--resp-optional` is valid only here.
- `trigger=radar-restart`: subscribe first, then restart the radar over MQTT.
- `trigger=device-reboot`: subscribe first, then send `device reboot` over MQTT. This requires working MQTT control and `raw_auto=1`.
