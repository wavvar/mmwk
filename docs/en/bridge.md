# MMWK Bridge Mode

MMWK Bridge is the default operating mode. This page is the canonical getting-started guide for bridge mode: identify your current board state, choose the right next path, and then continue into the detailed procedure docs.

## Who This Guide Is For

Use this guide if one of these is true:

- you are bringing up an MMWK board in bridge mode for the first time
- bridge firmware is already running and you want the first end-to-end radar flash plus collection flow
- bridge firmware is already running and you need the shortest route to the correct next document

If you already know the start path and only need deeper technical semantics, skip to [MMWK Sensor BRIDGE Reference](./bridge-reference.md).

## Before You Start

- Hardware: see the [module overview](../../modules/README.md) and the board-specific guides such as [RPX](../../modules/rpx.md) or [ML6432Ax](../../modules/ml6432ax.md)
- Host: macOS or Linux with `bash` recommended for `./mmwk_cli/mmwk_cli.sh`
- Tooling: Python 3.10+
- Local access: know the device serial port before running CLI commands
- Decision point: first decide whether your board is blank/erased, already running bridge, or already running bridge and only needs ESP OTA

## Path A: Blank Board -> Factory Flash

Choose this path if the ESP is blank, erased, or otherwise not yet running bridge firmware.

- Start with [Bridge Factory Flash Guide](./flash.md).
- The current public bridge release is delivered as `factory.zip` plus `ota.zip`; `flash.md` explains how to use `factory.zip` for the first flash.
- After factory flash succeeds, come back here and continue with Path B for the first radar flash plus collection flow, or Path C if you only need ESP OTA later.

## Path B: Bridge Running -> Radar Flash + Collect

Choose this path if `device hi` already reports bridge identity and you want the first validated end-to-end bridge workflow.

Recommended order:

1. Confirm the device is reachable over UART with `./mmwk_cli/mmwk_cli.sh device hi -p <port>`.
2. If Wi-Fi and MQTT are not configured yet, follow the bring-up sequence in [Local `server.sh` + `mmwk_cli.sh` Wi-Fi Flash and 5-Minute Collection Example](./collect.md).
3. Use [Local `server.sh` + `mmwk_cli.sh` Wi-Fi Flash and 5-Minute Collection Example](./collect.md) for the validated radar flash plus 5-minute collection walkthrough.

`collect.md` owns the full detailed procedure. Use [MMWK Sensor BRIDGE Reference](./bridge-reference.md) when you need the flash parameter contract, `meta.json`, welcome/version semantics, topic split, or raw capture details.

## Path C: ESP OTA

Choose this path if bridge firmware is already running and you only need to update the ESP firmware itself.

- Go directly to [Bridge Device OTA Guide](./ota.md).
- This is the maintenance path for bridge devices that do not need the larger bridge bring-up flow.

## What To Read Next

- [Bridge Factory Flash Guide](./flash.md): first flash for blank or erased boards
- [Local `server.sh` + `mmwk_cli.sh` Wi-Fi Flash and 5-Minute Collection Example](./collect.md): full bridge bring-up with radar flash plus collection
- [Bridge Device OTA Guide](./ota.md): ESP OTA for already-running bridge devices
- [MMWK Sensor BRIDGE Reference](./bridge-reference.md): raw semantics, topic split, welcome/version handling, and runtime verification details
- [CLI README](../../mmwk_cli/docs/en/README.md): full CLI command reference

## Bridge Startup Modes

Use these terms consistently across bridge docs and CLI:

- `start_mode` is the saved/configured default mode reported by radar-facing status surfaces.
- `supported_start_modes` is the capability list exposed by the active profile on radar-facing status surfaces.
- `fw.boot_mode` is the runtime radar boot path (`flash`, `host`, `uart`, `spi`).
- Bridge reports `supported_start_modes: ["auto", "host"]`.
- `auto` means ESP-managed radar bring-up.
- `host` means host-controlled radar bring-up.
- `raw_auto` only controls raw-plane auto-start; it does not decide who owns radar startup.

Operationally:

- `radar start --mode auto|host` persists the new default startup policy and then starts or restarts the current radar service in that mode.
- `radar start` without `--mode` uses the saved `start_mode`.
- `radar stop` stops the current radar service without rewriting `start_mode`.
- `radar status` is query-only and no longer accepts `--set`.
- In bridge `host`, the ESP still exposes raw transport, but it does not automatically send radar configuration as part of boot ownership.

## Production / After-Sales 1-Page SOP

Target audience: production testing, after-sales, field deployment.
Goal: shortest path to power-up, WiFi provisioning, MQTT connection, raw forwarding, and record/upload verification.

### 0. SOP Prerequisites

- Firmware: bridge firmware, **BRIDGE** mode. `device hi.name` typically reports `mmwk_sensor_bridge`.
- Serial port: `UART0 / 115200 baud`.
- A phone or PC that can connect to the device AP.
- An accessible MQTT broker (LAN preferred).
- An accessible HTTP upload endpoint (for `record` verification).

### 1. Power-On LED Status

- **WiFi not connected**: Fast blink (~100ms).
- **MQTT connected**: Solid ON for ~30 seconds.
- **MQTT disconnected**: 1s ON / 1s OFF blink cycle.

Long-press the button for 10 seconds to erase NVS and reboot (factory reset).

### 2. WiFi Provisioning (When No WiFi or Connection Failed)

1. Scan and connect to AP: `MMWK_XXXX` (open network, XXXX = last 4 MAC digits).
2. Open `http://192.168.4.1/` in a browser.
3. Enter WiFi SSID and password, then submit.
4. The device switches to STA mode and connects directly (no automatic reboot).

Alternatively, configure Wi-Fi via CLI (UART):

```bash
./mmwk_cli/mmwk_cli.sh network config --ssid "YOUR_SSID" --password "YOUR_PASSWORD" -p /dev/cu.usbserial-0001
./mmwk_cli/mmwk_cli.sh device reboot -p /dev/cu.usbserial-0001
```

### 3. Minimum Command Set (CLI via UART)

#### 3.1 Inspect or Override Current Agent Settings

Fresh bridge devices already default to `mqtt_en=1` and `raw_auto=1` when the keys are missing. Use `device agent` when you want to inspect the persisted state or manually override older settings during production bring-up or troubleshooting:

```bash
./mmwk_cli/mmwk_cli.sh device agent --mqtt-en 1 --raw-auto 1 -p /dev/cu.usbserial-0001
```

> **Note:** `mqtt_en`, `uart_en`, `raw_auto`, and `single_uart_split` are persisted to NVS. Missing bridge agent keys fall back to `mqtt_en=1` and `raw_auto=1`; missing hub agent keys fall back to `mqtt_en=0` and `raw_auto=1`. Reboot the device after changing persisted values to verify the final state.
>
> On single-UART `WDR/xWRL6432` boards, `single_uart_split` controls where runtime raw bytes go:
> - `0`: legacy behavior; runtime bytes continue to appear mainly on `raw_resp`
> - `1`: after `sensorStart` succeeds, runtime bytes move to `raw_data`; temporary runtime command-response windows still return to `raw_resp`

#### 3.2 Configure MQTT Parameters

```bash
./mmwk_cli/mmwk_cli.sh network mqtt --mqtt-uri mqtt://192.168.1.100:1883 -p /dev/cu.usbserial-0001
```

`network mqtt` configures the device MQTT identity plus the MCP interaction channel `mmwk/{mac}/device/cmd` and `mmwk/{mac}/device/resp`. It is the recommended remote application/control path.

Reboot the device after configuration and continue verification.

#### 3.3 Verify Raw Data Forwarding

Enable raw forwarding. In bridge/auto mode the MQTT raw plane auto-derives `mmwk/{mac}/raw/data` and `mmwk/{mac}/raw/resp`. In host mode it additionally derives `mmwk/{mac}/raw/cmd`:

```bash
# Enable raw forwarding
./mmwk_cli/mmwk_cli.sh radar raw --enable -p /dev/cu.usbserial-0001

# Query raw forwarding status
./mmwk_cli/mmwk_cli.sh radar raw -p /dev/cu.usbserial-0001
```

Here the topic meanings are:
- `raw_data`: radar DATA UART passthrough bytes (`data_resp`, binary capture)
- `raw_resp`: radar CMD UART startup-trimmed command-port output (`cmd_resp`, from `on_cmd_data`)
- `raw_cmd`: optional radar CMD UART ingress, available only in host mode, and distinct from the MCP topic `mmwk/{mac}/device/cmd`

When the current radar service is running in host mode and `raw_auto=1`, bridge auto-start also derives `mmwk/{mac}/raw/cmd` together with `mmwk/{mac}/raw/data` and `mmwk/{mac}/raw/resp`.

For single-UART `WDR/xWRL6432` boards there is no physical DATA UART. In that case:
- with `single_uart_split=0`, runtime raw bytes remain on `raw_resp`
- with `single_uart_split=1`, the driver switches runtime bytes to `raw_data` after `sensorStart` succeeds, while command-response windows still publish on `raw_resp`

#### 3.4 Device Identity Check

```bash
./mmwk_cli/mmwk_cli.sh device hi -p /dev/cu.usbserial-0001
```

Returns: `name`, `board`, `version`, `id`, `ip`, `mqtt_uri`, `client_id`, `cmd_topic`, `resp_topic`, `mqtt_en`, `uart_en`, `raw_auto`, `single_uart_split`, `radar_fw`, `radar_fw_version`, `radar_cfg`, `fw`, `raw_data_topic`, `raw_resp_topic`, and, in host mode, `raw_cmd_topic`.

`name` / `version` identify the ESP firmware currently running on the MMWK board. `radar_fw` / `radar_fw_version` / `radar_cfg` describe the ESP-side selected/default radar metadata entry, not the authoritative live radar image after a direct flash/OTA. For runtime confirmation, use `radar version` plus `radar status`.
`radar status` reports the saved/configured `start_mode` together with `supported_start_modes`, while `device hi.fw.boot_mode` reports the live radar boot path for the current session.

#### 3.5 IoT Entity & Capability Registry (Optional)

Query the device's dynamic capabilities (entities, adapters, scenes, policies):

```bash
./mmwk_cli/mmwk_cli.sh entity list --json -p /dev/cu.usbserial-0001
```

#### 3.6 Host-Side Collection Smoke Test

```bash
./mmwk_cli/mmwk_cli.sh collect --duration 12 \
  --data-output ./data_resp.sraw \
  --resp-output ./cmd_resp.log \
  -p /dev/cu.usbserial-0001
```

If you intentionally need a UART-free host-side capture after MQTT control is already working, keep `collect` as the official command for this checklist and use the external `./mmwk_cli/tools/mmwk_raw.sh` helper from the `mmwk_cli` directory instead. That helper is pure MQTT only and supports `trigger=none`, `trigger=radar-restart`, and `trigger=device-reboot`. Use `./mmwk_cli/tools/mmwk_cfg.sh` first when you need to push Wi-Fi/MQTT settings or point the device at a local `server.sh` broker.

Minimum pass criteria:
- `Resp topic frames (CMD UART / startup-trimmed command-port text) > 0`
- `Data topic frames (DATA UART / binary) > 0`
- `data_resp.sraw` is non-empty
- `cmd_resp.log` is non-empty
- `cmd_resp.log` starts at the first printable ASCII byte and reads as startup-trimmed command-port text

`Resp topic frames` and `Data topic frames` here count MQTT messages, not mmWave TLV frames. On single-UART `WDR/xWRL6432` boards with `single_uart_split=1`, it is normal for `resp_topic` to show only a small number of boot or command-response chunks while the steady runtime payload appears on `data_topic`.

### 4. Record and Upload Verification (Optional but Recommended)

Start recording (`uri` must be a reachable HTTP URL):

```bash
./mmwk_cli/mmwk_cli.sh raw record start --uri "http://192.168.1.100:8080/upload" -p /dev/cu.usbserial-0001
```

Trigger a 30-second event:

```bash
./mmwk_cli/mmwk_cli.sh raw record trigger --event "factory_test" --duration 30 -p /dev/cu.usbserial-0001
```

Stop recording:

```bash
./mmwk_cli/mmwk_cli.sh raw record stop -p /dev/cu.usbserial-0001
```

### 5. Factory Acceptance Criteria (Minimum Pass Standard)

- Device AP provisioning page is reachable and target WiFi connects successfully.
- `network mqtt` configuration is applied and MQTT connects after reboot.
- `radar raw` enable/disable works and MQTT broker receives both `raw_data` and `raw_resp`.
- Host-side `collect` verifies both `data_resp.sraw` and `cmd_resp.log`.
- `record start + trigger` results in HTTP POST received by the upload server.
- 10-second button long-press triggers factory reset (device reboots into un-provisioned state).
- `device hi` returns complete identity payload with all expected fields populated.

### 6. Common Fault Quick Reference

| Symptom | Solution |
|---|---|
| Device AP not visible | Power-cycle the device; if still absent, long-press button 10s to clear NVS. |
| MQTT never connects | Check `mqtt_uri`, LAN reachability, firewall rules, and topic ACLs. |
| `raw_auto` not working | Confirm `mqtt_en=1` and MQTT transport is connected before checking. |
| `record` not uploading | Check `start` URI reachability and HTTP server status. |
| WiFi connects but no IP | Verify DHCP server on the target network; try a different SSID. |
| `collect` command timeout | Ensure MQTT broker is reachable from both device and host. |
| Radar config was sent but no data returns | The `.cfg` is most likely wrong for the currently running radar firmware, so the radar firmware enters a bad/hung state after config. Re-check the exact firmware/demo pairing, board variant, and CLI commands, and first prove that the same firmware + config works correctly on the radar development board itself. |

## Troubleshooting / Reference Links

- [Bridge Factory Flash Guide](./flash.md)
- [Local `server.sh` + `mmwk_cli.sh` Wi-Fi Flash and 5-Minute Collection Example](./collect.md)
- [Bridge Device OTA Guide](./ota.md)
- [MMWK Sensor BRIDGE Reference](./bridge-reference.md)
- [CLI README](../../mmwk_cli/docs/en/README.md)
- [module overview](../../modules/README.md)
