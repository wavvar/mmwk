# mmWave Sensor Development Kit Reference

Use this document when you already know your start path from [mmWave Sensor Development Kit](./mmwk-sensor.md) and need deeper platform semantics, parameter contracts, and runtime verification details.

## 1. Validated Execution Context

- Run shell examples from `./cli` so `./run.sh` and the `../firmwares/...` reference paths resolve exactly as written.
- Replace `PORT=/dev/cu.usbserial-0001` with your real UART port before using command examples.
- This reference assumes `./run.sh device hi -p "$PORT"` or `./run.sh node info -p "$PORT"` already reports an `mmwk_sensor` firmware profile such as `mmwk_sensor_bridge`.
- `run.sh` defaults to canonical CLI JSON. If an older caller still depends on MCP, add `--protocol mcp` explicitly as a compatibility fallback.
- This reference does not replace Wi-Fi or MQTT bring-up. Before you run `collect`, the device should already have usable runtime networking such as a non-zero `ip`, and MQTT-dependent flows should show `mqtt_state=connected`.
- If you just ran `radar flash`, `radar ota`, `radar reconf`, or the first boot after a factory / baseline recovery path, wait for `radar status` to return `running` before relying on any late-attach `collect` flow.

Use these shell variables in the examples below:

```bash
cd ./cli
export PORT=/dev/cu.usbserial-0001
export FW=../firmwares/radar/iwr6843/vital_signs/vital_signs_tracking_6843AOP_demo.bin
export CFG=../firmwares/radar/iwr6843/vital_signs/vital_signs_AOP_2m.cfg
```

## 2. Platform Model

### 2.1 mmwk_sensor Shared Capability Layer

`mmwk_sensor` is the shared firmware platform for supported MMWK boards. It provides the common control, networking, OTA, radar firmware management, raw passthrough, startup verification, and user-interaction surfaces used by firmware profiles built on the platform.

These capabilities are not tied to one radar chip family or one ESP generation. They apply across supported 6843 / 6432 and ESP / ESP32-S3 variants when the active firmware profile is based on `mmwk_sensor`.

### 2.2 Firmware Profiles

Firmware profiles define what the product surface does on top of the shared platform layer.

- `mmwk_sensor_bridge` is the baseline transparent-passthrough profile.
- `mmwk_sensor_hub` is a profile that keeps the shared platform behavior and adds a sensor hub profile definition and implementation.

### 2.3 Bridge Capability vs mmwk_sensor_bridge Profile

Bridge capability means the platform can expose radar-side command/data streams through host-visible control and raw transport channels. It includes CLI control, MQTT transport, raw topic derivation, startup observation, and optional host-mode raw command ingress.

`mmwk_sensor_bridge` is the public baseline profile that focuses on this capability and avoids adding a higher-level sensor hub product surface. Use it for radar firmware development, flashing, configuration, tuning, raw data capture, and host-side validation.

### 2.4 Hub Profile Boundary

`mmwk_sensor_hub` is mentioned here only as a bounded profile example. It has the same shared `mmwk_sensor` sensor capabilities, and it adds sensor hub semantics above that shared layer.

Hub internals, algorithms, private modules, and product-specific behavior are outside this public reference.

## 3. User Interaction Reference

### 3.1 LED Behavior

ESP-side LED behavior is consistent by default across supported `mmwk_sensor` boards. Board-specific LED placement and GPIO details live in the corresponding `modules/` hardware documents.

| State | Pattern | Meaning |
|-------|---------|---------|
| **INIT** | Solid ON for 3s, then OFF | Boot indicator |
| **OFF** | LED off | Normal idle/running display |
| **CONFIRM short** | OFF, ON 500ms, OFF | Short interaction acknowledgement |
| **CONFIRM double** | OFF, ON 500ms, OFF 100ms, ON 500ms, OFF | 4G preferred-network confirmation |
| **CONFIRM normal** | OFF, ON 500ms, OFF 100ms, ON 500ms, OFF | Configuration or connection acknowledgement |
| **CONFIRM long** | OFF, then 500ms ON / 100ms OFF repeated 3 times | Long interaction acknowledgement, including factory-reset hold |
| **MQTT connected** | Solid ON for about 30 seconds | MQTT connection-success indication |
| **ERROR warning** | 1000ms ON / 1000ms OFF loop | MQTT disconnected, MQTT connection error, or MQTT start/reconnect failure |
| **ERROR severe** | 200ms ON / 100ms OFF loop | Network connection failure after Wi-Fi or CAT1/4G cannot come online |

LED is not a network readiness signal. Use `network status` (`state=connected && ready=true`) for network readiness and `mqtt_state=connected` for MQTT-dependent flows.

`node agent --led 0|1` controls only ERROR display. INIT and CONFIRM always display; when `led=0`, ERROR keeps the hardware LED off while the logical error state is still present.

### 3.2 KEY Behavior

ESP-side KEY behavior is consistent by default across supported `mmwk_sensor` boards. Board-specific KEY placement and GPIO details live in the corresponding `modules/` hardware documents.

- **Single short press**: confirms the preferred network. One blink = Wi-Fi; two blinks = 4G.
- **Three short presses**: toggles the preferred network between Wi-Fi and 4G on devices that support 4G.
- **Long press for 10 seconds**: factory reset, clearing NVS and rebooting.

## 4. Control and Transport

### 4.1 UART Interface

UART is the local factory, debug, recovery, and bench bring-up path. Another MCU
can connect directly to the board UART when voltage levels and pins match. UART
pin assignments are board-specific; check the board schematic before wiring.

When a PC connects to UART on current boards, use an external UART-to-USB
adapter. A PC USB port cannot communicate directly with bare UART pins.

WDR and new designs are the current exception for normal CLI/control use: they
support built-in USB serial through UART and USB multiplexing, so a separate
UART-to-USB adapter is not required for the normal control interface.

ESP chip-level flashing is separate from the normal control interface. All
boards still require the appropriate external converter or flashing fixture for
ESP chip-level flashing.

The recommended host entry point is:

```bash
./run.sh node info -p "$PORT"
```

UART commands use the canonical CLI JSON protocol by default. Protected commands require `--key` after CLI key protection is enabled.

### 4.2 UART and USB Multiplexing

UART and USB multiplexing selects the local control interface between UART and
USB CDC during the boot or restore idle window. It is currently supported only
by WDR and new designs.

The selection is independent of the preferred network bearer. If UART activity
is detected during the idle window, the control path remains on UART. If the
window expires without UART activity, the control path switches to USB CDC.

On WDR, CAT1/4G USB-DTE ownership is still arbitrated separately when 4G
actually starts or runs; 4G preference alone does not prevent the device from
entering UART and USB multiplexing.

### 4.3 CLI JSON over MQTT

MQTT is the recommended remote application/control path after network setup. Configure it with:

```bash
./run.sh network mqtt --uri mqtt://192.168.1.100:1883 -p "$PORT"
```

Then verify readiness with:

```bash
./run.sh network status -p "$PORT"
```

Treat `state=connected && ready=true` as the network-ready contract and `mqtt_state=connected` as the MQTT-ready contract.

### 4.4 MQTT Topic Identity

`network mqtt` configures broker/auth settings. Device MQTT identity and canonical topic derivation remain tied to the device identity.

Canonical control topics:

| Topic | Content |
| --- | --- |
| `mmwk/{mac}/device/cmd` | CLI JSON command input configured by `network mqtt`. |
| `mmwk/{mac}/device/resp` | CLI JSON command responses and status events configured by `network mqtt`. |

## 5. Raw Radar Passthrough

### 5.1 Raw Semantics Contract

- `raw_resp = startup-trimmed command-port output from on_cmd_data`
- `raw_data = raw data-port bytes from on_radar_data`
- `on_cmd_resp is an application-layer command response`, and it is different from raw capture.
- `on_radar_frame is an application-layer frame callback`, and it is different from raw capture.
- Startup noise before the first printable ASCII byte is trimmed in the radar driver before command-port output is surfaced to the host.
- `cmd_resp.log` keeps the startup-trimmed command-port text stream that starts at the first printable ASCII byte.

### 5.2 Topic Split

`radar raw` reuses the configured MQTT broker/client and derives the raw radar passthrough plane.

| Topic | Content |
| --- | --- |
| `mmwk/{mac}/raw/data` | Raw radar DATA UART payloads derived by `radar raw`. |
| `mmwk/{mac}/raw/resp` | Raw radar command-port bytes from `on_cmd_data`, derived by `radar raw`. |
| `mmwk/{mac}/raw/cmd` | Optional radar CMD UART ingress channel derived by `radar raw`, available only in host mode. |

On fresh `mmwk_sensor_bridge` devices, `network mqtt` plus reboot is enough to bring up MQTT control.
When the agent keys are missing from NVS, `mmwk_sensor_bridge` defaults are `mqtt_en=1` and `raw_auto=1`.
Other profiles may choose different profile defaults while preserving the same platform control model.

### 5.3 Host Mode Raw Command Ingress

`mmwk/{mac}/raw/cmd` is available only when the current radar session is in host mode. It is distinct from the CLI JSON topic `mmwk/{mac}/device/cmd`.

In auto mode, the MQTT raw plane is output-only.

## 6. Radar Firmware Management

### 6.1 Flash / OTA Parameters

Shared parameters:

| Parameter | Applies to | Meaning |
| --- | --- | --- |
| `--fw <file.bin>` | `radar ota`, `radar flash` | Required radar firmware binary written to the radar chip. |
| `--cfg <file.cfg>` | `radar ota`, `radar flash` | Optional radar config text matched to the selected firmware. |
| `-p <serial_port>` | reference examples | UART serial port used by the CLI to reach the device control service. |

HTTP OTA specific parameters:

| Parameter | Meaning |
| --- | --- |
| `--http-port <port>` | Local HTTP port used when the CLI starts a temporary file server. |
| `--base-url <url>` | Skip the local HTTP server and let the device download from an existing HTTP base URL. |
| `--version <str>` | Explicit expected radar firmware version string. |
| `--ota-timeout <sec>` | Maximum time to wait for OTA download plus apply. |
| `--progress-interval <sec>` | How often the device emits flash progress updates. |

Chunk-transfer (`radar flash`) specific parameters:

| Parameter | Meaning |
| --- | --- |
| `--chunk-size <bytes>` | Size of each firmware chunk sent to the device. |
| `--mqtt-delay <sec>` | Delay between chunks when `radar flash` runs over MQTT transport. |
| `--progress-interval <sec>` | How often the device reports flash progress during chunk transfer. |
| `--reboot-delay <sec>` | Delay before the ESP reboots after a successful flash session. |

### 6.2 Managed Firmware Catalog

Use the `fw` commands when you want to manage the ESP-side radar firmware catalog rather than push a new radar image from the host in that moment.

```bash
./run.sh fw list -p "$PORT"
./run.sh fw set --index 0 -p "$PORT"
```

Contract:

- `fw list` is the profile-facing catalog surface. Each entry includes `default` and `running` flags so you can tell which firmware is the saved default and which managed catalog entry is running now.
- Bundled rows are runtime assets, not host-uploaded storage objects. Treat them as bundled/read-only catalog rows.
- `fw set --index <n>` is a persisted default firmware switch, not just a metadata toggle.

### 6.3 Runtime Firmware State

`device hi` / `node info` returns nested firmware state:

- `fw.default`
- `fw.running`
- `fw.switch`
- `fw.boot_mode`

`fw.default` is the persisted default entry. `fw.running` is the entry actually used by the current session. `fw.boot_mode` is the runtime radar boot path: `flash`, `uart`, `spi`, or `host`.

Legacy fields such as `radar_fw`, `radar_fw_version`, and `radar_cfg` remain available and map to `fw.running`.

### 6.4 Runtime Reconfiguration

Use `radar reconf` when you want to change the runtime radar contract without flashing firmware again. This can switch `welcome` / `verify` / `version` semantics and optionally replace or clear the runtime cfg while keeping the current radar firmware binary in place.

```bash
./run.sh radar reconf --welcome --no-verify -p "$PORT"
./run.sh radar reconf --welcome --verify --version "1.2.3" -p "$PORT"
./run.sh radar reconf --welcome --no-verify --cfg ./runtime.cfg -p "$PORT"
./run.sh radar reconf --welcome --no-verify --clear-cfg -p "$PORT"
```

Contract:

- Host mode is rejected for runtime reconfiguration.
- `cfg_action` values are `keep | replace | clear`.
- `--cfg` maps to `cfg_action=replace`, uploads only a runtime cfg, and finishes with `uart_data action=reconf_done`.
- `--clear-cfg` maps to `cfg_action=clear` and removes the persisted runtime cfg override.
- No `--cfg` flag maps to `cfg_action=keep` and preserves the current runtime cfg selection.
- Unlike `radar flash` or `radar ota`, `radar reconf` does not flash firmware and does not replace the radar binary.
- Treat `radar reconf` as an optional advanced step. After any `radar reconf`, re-check `radar status` and wait for `state=running` before relying on `radar version` or `collect`.

### 6.5 Runtime CFG Readback

Use `radar cfg` when you need to read back the current effective radar cfg text without changing firmware or runtime contract state.

```bash
./run.sh radar cfg -p "$PORT"
```

Contract:

- Default behavior reads the current effective file cfg text.
- The effective file cfg is the selected runtime override cfg when one is present; otherwise it is the default firmware metadata cfg.
- After `radar flash` with an explicit firmware/config pair, the platform persists the exact staged runtime pair instead of silently rebinding to a bundled catalog entry with the same version.
- If a persisted explicit runtime firmware or cfg path cannot be reopened exactly on the next startup, startup fails instead of silently substituting a different bundled asset pair.
- If the selected file cfg is missing, unreadable, or empty, the request fails directly.
- CLI prints only the cfg text to stdout, so redirecting the output preserves the raw cfg content.

### 6.6 Metadata Source Contract

`radar flash` and `radar ota` both infer radar metadata from a sibling `meta.json` next to the `--fw` binary: `welcome` plus optional `version`.

If both CLI flags and `meta.json` are available, explicit CLI values win. If you replace packaged examples with a custom demo, add a matching `meta.json` yourself or pass `--welcome` / `--version` explicitly.

## 7. Startup and Version Semantics

### 7.1 Welcome Output

- Startup text is a boot observation, not a fixed banner contract.
- The welcome path is the only runtime source MMWK has for both "did the radar app boot?" and "what version string did it print?".
- If `welcome=true`, the device should observe startup CLI/welcome output before normal config is applied.

### 7.2 Version Matching

- `radar flash` and `radar ota` both expose `--version <str>`, `--verify` / `--no-verify`, and `--welcome` / `--no-welcome`.
- `version` is the substring matched inside startup CLI/welcome output.
- When verification is enabled, MMWK searches for the version substring anywhere in the accumulated startup text. It does not require a fixed welcome line.
- `--verify` enables version matching and requires a version string.
- If `--verify` is not enabled, flashing still works, but `radar version` may be empty because there is no expected string to match and persist.
- If you need to customize the radar firmware version that MMWK recognizes, make the radar firmware's startup CLI output print the desired version string, then ensure the host passes the same expected string via `--version` or adjacent `meta.json`.

### 7.3 Startup Failure Handling

If `welcome=true` but no startup CLI/welcome output arrives before timeout, treat that as a radar startup failure. The firmware likely did not boot on the radar. In that case `radar status` keeps `state=error` and includes a `details` object explaining the failure.

## 8. Startup Mode Boundaries

### 8.1 Auto Mode

`start_mode=auto` means the saved default policy is ESP-managed radar bring-up. The device may select firmware/config metadata, wait for startup CLI/welcome output, verify version metadata, and send radar configuration.

### 8.2 Host Mode

`start_mode=host` means the saved default policy is host-controlled bring-up, not "auto mode plus one more raw topic". The device still exposes transport surfaces, but it does not automatically send radar configuration, does not automatically wait for welcome text, and does not automatically verify version metadata as part of startup ownership.

### 8.3 Runtime Boot Path

`fw.boot_mode=host` means the current radar session actually booted through the host path. `mmwk/{mac}/raw/cmd` is available only when the current radar session is in host mode.

Real applications, services, dashboards, and agents should normally integrate through MQTT. UART remains valuable for factory setup, flashing, bring-up, bench debugging, and emergency fallback.

## 9. Runtime Verification Checklist

Use these commands together after radar flash, OTA, reconf, or the first boot after a factory / baseline recovery path:

```bash
./run.sh device hi -p "$PORT" | tee ./sensor_hi.json
./run.sh radar status -p "$PORT" | tee ./radar_status.json
./run.sh radar version -p "$PORT" | tee ./radar_version.json
./run.sh collect --duration 12 \
  --data-output ./data_resp.sraw \
  --resp-output ./cmd_resp.log \
  -p "$PORT"
```

Minimum expected evidence:

- `device hi` or `node info` identifies an `mmwk_sensor` firmware profile.
- `network status` reports `state=connected && ready=true` before MQTT-dependent flows.
- `radar status` returns `running` after radar flash/OTA/reconf.
- `cmd_resp.log` contains startup-trimmed command-port text.
- `data_resp.sraw` is non-empty when the radar firmware/config pair is expected to emit data.

If `device hi` still reports `ip = 0.0.0.0`, treat the device network as not ready for MQTT raw capture yet.

## 10. Troubleshooting Reference

| Symptom | Likely Cause / Action |
| --- | --- |
| Device AP not visible | Power-cycle the device; if still absent, long-press button 10s to clear NVS. |
| MQTT never connects | Check `uri`, LAN reachability, firewall rules, credentials, and topic ACLs. |
| `raw_auto` not working | Confirm MQTT is enabled and MQTT transport is connected. |
| `collect` times out | Ensure MQTT broker is reachable from both device and host. |
| `details.kind=startup_failed` | The firmware likely never reached its startup CLI on the radar. |
| Radar config was sent but no data returns | Re-check firmware/config pairing, board variant, and radar CLI commands. First prove the same firmware + config on the radar development board. |

For the full validated bring-up walkthrough, return to [mmWave Sensor Development Kit](./mmwk-sensor.md) and continue into [Local `server.sh` + `run.sh` Wi-Fi Flash and 5-Minute Collection Example](./collect.md).
