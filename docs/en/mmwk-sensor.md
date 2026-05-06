# mmWave Sensor Development Kit

MMWK is a mmWave Sensor Development Kit for radar firmware development, raw data capture, networked control, and product validation. The same platform behavior applies across supported radar and controller variants, including IWR6843 / IWRL6432 and ESP / ESP32-S3 based boards, as long as the firmware is built on the `mmwk_sensor` stack.

The bridge capability described in older documents is a platform capability, not only a single firmware mode. `mmwk_sensor_bridge` is the baseline passthrough profile built on this platform; other profiles such as `mmwk_sensor_hub` also keep the shared sensor capabilities while adding their own higher-level profile semantics.

## 1. Overview

Use this guide if one of these is true:

- you are bringing up an MMWK board for the first time
- the device is already running an `mmwk_sensor` firmware profile and you want the first end-to-end radar flash plus collection flow
- you need the shortest route to the right factory, OTA, collection, or reference document
- you want to understand which behavior belongs to the shared sensor platform and which behavior belongs to a specific firmware profile

If you already know the start path and only need deeper technical semantics, skip to [mmWave Sensor Development Kit Reference](./mmwk-sensor-reference.md).

## 2. Supported Firmware Profiles

### 2.1 mmwk_sensor_bridge

`mmwk_sensor_bridge` is the baseline transparent-passthrough firmware profile. It provides the shared `mmwk_sensor` platform behavior and focuses on radar firmware development, flashing, configuration, tuning, raw data capture, and host-side validation.

It does not define a higher-level sensor hub product surface. Use it when the immediate goal is to close the loop between the host, ESP, radar firmware, radar configuration, and raw radar data streams.

### 2.2 mmwk_sensor_hub

`mmwk_sensor_hub` is another firmware profile built on the same `mmwk_sensor` platform. It has the same shared sensor capabilities, and it adds a sensor hub profile definition and implementation.

This public documentation uses hub only as a profile example. Hub internal modules, algorithms, and product-specific behavior are intentionally outside this document.

## 3. Shared Platform Capabilities

### 3.1 CLI Control

The platform exposes the canonical CLI JSON control surface over UART and MQTT. The host-side `./cli/run.sh` wrapper is the recommended entry point on macOS and Linux.

### 3.2 Wi-Fi Provisioning

Factory or unconfigured devices expose an AP provisioning flow. Users can configure Wi-Fi through the browser portal or through CLI commands over UART.

### 3.3 MQTT Transport

After network configuration, MQTT becomes the recommended remote control and data path. Device command/response topics and raw radar topics are derived from the device MQTT identity.

### 3.4 4G / Network Priority

Boards with cellular hardware can store 4G settings and choose Wi-Fi or 4G as the preferred network. If the preferred network cannot come online, the device may use an available fallback while preserving the saved preference.

### 3.5 OTA and Firmware Management

The platform supports ESP OTA for device firmware maintenance and radar firmware/config management for radar-side development and validation.

### 3.6 Raw Radar Passthrough

Raw passthrough is a shared `mmwk_sensor` capability. It forwards radar DATA bytes and startup-trimmed command-port output to host-visible raw channels. In host mode, the platform can also expose raw command ingress.

### 3.7 KEY and LED Interaction

ESP-side KEY and LED behavior is consistent by default across supported boards. See [3. User Interaction Reference](./mmwk-sensor-reference.md#3-user-interaction-reference) for the complete behavior table.

## 4. Startup Modes

Use these terms consistently across sensor docs and CLI:

- `mode` is the saved/configured default mode reported by radar-facing status surfaces.
- `modes` is the capability list exposed by the active firmware profile.
- `fw.boot_mode` is the runtime radar boot path (`flash`, `host`, `uart`, `spi`).
- `auto` means ESP-managed radar bring-up.
- `host` means host-controlled radar bring-up.
- `raw_auto` only controls raw-plane auto-start; it does not decide who owns radar startup.

Operationally:

- `radar start --mode auto|host` persists the new default startup policy and then starts or restarts the current radar service in that mode.
- `radar start` without `--mode` uses the saved `mode`.
- `radar stop` stops the current radar service without rewriting `mode`.
- `radar status` is query-only and no longer accepts `--set`.

## 5. Production / After-Sales SOP

Target audience: production testing, after-sales, field deployment.
Goal: shortest path to power-up, Wi-Fi provisioning, MQTT connection, raw forwarding, and record/upload verification.

### 5.1 SOP Prerequisites

- Firmware: an `mmwk_sensor` firmware profile. For the current public baseline profile, `node info.name` typically reports `mmwk_sensor_bridge`.
- Serial port: `UART0 / 115200 baud`.
- A phone or PC that can connect to the device AP.
- An accessible MQTT broker (LAN preferred).
- An accessible HTTP upload endpoint (for `record` verification).

### 5.2 Path A: Blank Board -> Factory Flash

Choose this path if the ESP is blank, erased, or otherwise not yet running the current public `mmwk_sensor_bridge` firmware package.

- Start with [Factory Flash Guide](./flash.md).
- The current public baseline release is delivered as `factory.zip` plus `ota.zip`; `flash.md` explains how to use `factory.zip` for the first flash.
- After factory flash succeeds, come back here and continue with Path B for the first radar flash plus collection flow, or Path C if you only need ESP OTA later.

### 5.3 Path B: Sensor Firmware Running -> Radar Flash + Collect

Choose this path if `node info` already reports a reachable `mmwk_sensor` firmware profile and you want the first validated end-to-end workflow.

Recommended order:

1. Confirm the device is reachable over UART with `./cli/run.sh node info -p <port>`.
2. If Wi-Fi and MQTT are not configured yet, follow the bring-up sequence in [Local `server.sh` + `run.sh` Wi-Fi Flash and 5-Minute Collection Example](./collect.md).
3. Use [Local `server.sh` + `run.sh` Wi-Fi Flash and 5-Minute Collection Example](./collect.md) for the validated radar flash plus 5-minute collection walkthrough.

`collect.md` owns the full detailed procedure. Use [mmWave Sensor Development Kit Reference](./mmwk-sensor-reference.md) when you need parameter contracts, welcome/version semantics, topic split, raw capture details, or startup-mode boundaries.

### 5.4 Path C: ESP OTA

Choose this path if the device is already running the current public `mmwk_sensor_bridge` package and you only need to update the ESP firmware itself.

- Go directly to [Device OTA Guide](./ota.md).
- This is the maintenance path for devices that do not need the larger bring-up flow.

### 5.5 Power-On User Interaction

After power-on, use [3. User Interaction Reference](./mmwk-sensor-reference.md#3-user-interaction-reference) to confirm LED and KEY behavior. Long-press the button for 10 seconds to erase NVS and reboot (factory reset).

### 5.6 Configure Wi-Fi

When no Wi-Fi is configured or the device cannot connect:

1. Scan and connect to AP: `MMWK_XXXX` (open network, XXXX = last 4 MAC digits).
2. Open `http://192.168.4.1/` in a browser.
3. Enter Wi-Fi SSID and password, then submit.
4. The device switches to STA mode and connects directly (no automatic reboot).

Alternatively, configure Wi-Fi via CLI over UART:

```bash
./cli/run.sh network wifi --ssid "YOUR_SSID" --pass "YOUR_PASSWORD" -p /dev/cu.usbserial-0001
./cli/run.sh node reboot -p /dev/cu.usbserial-0001
```

### 5.7 Configure MQTT and Raw Passthrough

Fresh `mmwk_sensor_bridge` devices default to `mqtt=1` and `raw_auto=1` when the agent keys are missing. Other profiles may choose different profile defaults while keeping the same platform control surface.

```bash
./cli/run.sh node agent --mqtt 1 --raw-auto 1 -p /dev/cu.usbserial-0001
./cli/run.sh network mqtt --uri mqtt://192.168.1.100:1883 -p /dev/cu.usbserial-0001
./cli/run.sh node reboot -p /dev/cu.usbserial-0001
```

After reboot, verify:

```bash
./cli/run.sh network status -p /dev/cu.usbserial-0001
./cli/run.sh radar raw status -p /dev/cu.usbserial-0001
```

Use `network status` as the network-readiness contract: `state=connected && ready=true`. Use `mqtt_state=connected` for MQTT-dependent flows.

### 5.8 Device Identity Check

```bash
./cli/run.sh node info -p /dev/cu.usbserial-0001
```

`name` / `version` identify the ESP firmware currently running on the MMWK board. `radar_fw` / `radar_fw_version` / `radar_cfg` describe the ESP-side selected/default radar metadata entry, not the authoritative live radar image after a direct flash/OTA. For runtime confirmation, use `radar fw version` plus `radar status`.

### 5.9 Host-Side Collection Smoke Test

```bash
./cli/run.sh collect --duration 12 \
  --data-output ./data_resp.sraw \
  --resp-output ./cmd_resp.log \
  -p /dev/cu.usbserial-0001
```

Minimum pass criteria:

- `Resp topic frames (CMD UART / startup-trimmed command-port text) > 0`
- `Data topic frames (DATA UART / binary) > 0`
- `data_resp.sraw` is non-empty
- `cmd_resp.log` is non-empty
- `cmd_resp.log` starts at the first printable ASCII byte and reads as startup-trimmed command-port text

`Resp topic frames` and `Data topic frames` count MQTT messages, not mmWave TLV frames. On single-UART `WDR/xWRL6432` boards with `single_uart_split=1`, it is normal for `resp_topic` to show only a small number of boot or command-response chunks while the steady runtime payload appears on `data_topic`.

### 5.10 Record and Upload Verification

Start recording (`uri` must be a reachable HTTP URL):

```bash
./cli/run.sh raw record start --uri "http://192.168.1.100:8080/upload" -p /dev/cu.usbserial-0001
```

Trigger a 30-second event:

```bash
./cli/run.sh raw record trigger --event "factory_test" --duration 30 -p /dev/cu.usbserial-0001
```

Stop recording:

```bash
./cli/run.sh raw record stop -p /dev/cu.usbserial-0001
```

## 6. Common Fault Quick Reference

| Symptom | Solution |
|---|---|
| Device AP not visible | Power-cycle the device; if still absent, long-press button 10s to clear NVS. |
| MQTT never connects | Check `uri`, LAN reachability, firewall rules, and topic ACLs. |
| `raw_auto` not working | Confirm MQTT is enabled and MQTT transport is connected before checking. |
| `record` not uploading | Check `start` URI reachability and HTTP server status. |
| Wi-Fi connects but no IP | Verify DHCP server on the target network; try a different SSID. |
| `collect` command timeout | Ensure MQTT broker is reachable from both device and host. |
| Radar config was sent but no data returns | The `.cfg` is most likely wrong for the currently running radar firmware, so the radar firmware enters a bad/hung state after config. Re-check the exact firmware/demo pairing, board variant, and CLI commands, and first prove that the same firmware + config works correctly on the radar development board itself. |

## 7. Related Documents

- [Factory Flash Guide](./flash.md)
- [Local `server.sh` + `run.sh` Wi-Fi Flash and 5-Minute Collection Example](./collect.md)
- [Device OTA Guide](./ota.md)
- [mmWave Sensor Development Kit Reference](./mmwk-sensor-reference.md)
- [CLI README](../../cli/docs/en/README.md)
- [Radar Task Tools](../../cli/docs/en/radar-task-tools.md)
- [Develop Radar With Bridge](../../cli/docs/en/bridge-ti-radar-debug.md)
- [module overview](../../modules/README.md)
