# Collect Trigger Helper

`collect.sh --trigger` is a pure-MQTT raw capture helper for cases where you intentionally want both control and raw capture to stay off UART.

Pure-MQTT raw capture helper for external MQTT-only workflows.

The working directory is the `cli` directory:

```bash
cd ./cli
```

Examples below use POSIX shell syntax. On Windows PowerShell, use `.\collect.ps1 --trigger ...`; this pure-MQTT trigger mode runs without Bash as long as Python 3.10+ dependencies are installed. If Bash is installed, `collect.ps1` delegates to `collect.sh` for full wrapper behavior.

## What It Does

- Captures `raw_data` into `data_resp.sraw`
- Captures startup-trimmed command-port bytes into `cmd_resp.log`
- Keeps runtime control and raw capture on MQTT only
- Supports `trigger=none`, `trigger=radar-restart`, and `trigger=device-reboot`

This helper is not a replacement for the strict startup-aware `collect -p` path.

## Broker Resolution

Unless a specific broker override is required, the default MQTT port is `1883`.

If `--broker` is absent and `MMWK_SERVER_MQTT_URI` is unset, `collect.sh --trigger` auto-loads the broker from server.sh state. By default it checks `./build_output/local_server/server.env`, or you can point it somewhere else with `--server-state-dir`.

`collect.sh --trigger` still needs the MQTT route identity. Pass `--did` for an unclaimed device, or `--prod --oid --cid` for a claimed route. Environment fallbacks are `MMWK_DID`, `MMWK_PROD`, `MMWK_OID`, and `MMWK_CID`.

## Examples

### 1. Late-attach steady-state capture

```bash
./collect.sh --trigger none \
  --broker mqtt://192.168.1.100:1883 \
  --did dc5475c879c0 \
  --data-output ./data_resp.sraw \
  --resp-output ./cmd_resp.log \
  --resp-optional
```

### 2. Reuse local `server.sh` state

```bash
./config.sh set --server-local \
  --ssid "MyWiFi" \
  --password "MyPass" \
  --port /dev/cu.usbserial-0001 \
  --reboot

./collect.sh --server-state-dir ./build_output/local_server \
  --trigger device-reboot \
  --did dc5475c879c0
```

### 3. Trigger a fresh startup window over MQTT

```bash
./collect.sh --trigger device-reboot \
  --did dc5475c879c0 \
  --resp-output ./cmd_resp.log \
  --data-output ./data_resp.sraw
```

## Key Options

- `--did`: DID route fallback; required unless `--cid` or `MMWK_CID` is set.
- `--prod` / `--oid` / `--cid`: product, tenant, and claimed route segments; `cid` takes precedence over `did`.
- `--raw-data` / `--raw-resp`: override raw topics directly. If omitted, `collect.sh --trigger` derives them from `prod/oid/cid/did`, and for restart/reboot triggers it can also fall back to runtime-reported topics.
- `--duration`: capture length in seconds (default: `10`).
- `--timeout`: MQTT subscribe/control setup timeout in seconds (default: `10`).
- `--resp-optional`: valid only with `--trigger none`, for late-attach steady-state windows where no fresh startup `raw_resp` is expected.
- `--server-state-dir`: default is `./build_output/local_server`; the wrapper reads `server.env` there when broker settings are not passed explicitly.

## Trigger Notes

- `trigger=none`: late-attach steady-state collection; `--resp-optional` is valid only here.
- `trigger=radar-restart`: subscribe first, then restart the radar over MQTT using the derived `cmd` / `resp` control topics.
- `trigger=device-reboot`: subscribe first, then send `node reboot` over MQTT. This requires working MQTT control and `raw_auto=1`.
