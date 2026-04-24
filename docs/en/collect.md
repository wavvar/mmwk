# Local `server.sh` + `mmwk_cli.sh` Wi-Fi Flash and 5-Minute Collection Example

## Raw Semantics Contract

- `raw_resp = startup-trimmed command-port output from on_cmd_data`
- `raw_data = raw data-port bytes from on_radar_data`
- `on_cmd_resp` is an application-layer command response, and it is different from raw capture.
- `on_radar_frame` is an application-layer frame callback, and it is different from raw capture.

## 1. Goal and Constraints

This example shows how to:

1. Use `./mmwk_cli/server.sh` to provide local MQTT and HTTP services on the host.
2. Use `./mmwk_cli/mmwk_cli.sh` over Wi-Fi/MQTT to control the device and let it download radar firmware and config from the local HTTP server.
3. Collect more than 300 seconds of `raw_data` and `raw_resp`.

The following constraints were respected during validation:

- The device default startup mode was not changed.
- `raw_resp` was treated as startup-trimmed command-port output from `on_cmd_data`.
- `welcome=true` was treated as "any non-empty radar startup output string", not as a fixed string, and multi-line output is allowed.

## 2. Inputs Used in This Example

The commands below assume the current working directory is the `mmwk` project root, meaning the directory that contains `firmwares/` and `mmwk_cli/`.

Placeholders used in this document:

- `<artifact-dir>`
  - Demo firmware directory. In the current main-branch validation this was `./firmwares/radar/iwr6843/vital_signs`.
- `<demo-output-dir>`
  - Demo output directory for command files, logs, and captured data.

Example values used below:

- Serial port: `/dev/cu.usbserial-0001`
- Device IP after Wi-Fi join: `192.168.4.8`
- Host IP: `192.168.4.9`
- Local MQTT: `mqtt://192.168.4.9:1883`
- Local HTTP: `http://192.168.4.9:8380/`
- Wi-Fi SSID: `ventropic`
- Wi-Fi password: `ve12345678`
- MQTT client id: `dc5475c879c0`
- Device control topics:
  - `mmwk/dc5475c879c0/device/cmd`
  - `mmwk/dc5475c879c0/device/resp`
- Raw topics:
  - `mmwk/dc5475c879c0/raw/data`
  - `mmwk/dc5475c879c0/raw/resp`
- Radar firmware: `<artifact-dir>/vital_signs_tracking_6843AOP_demo.bin`
- Radar config: `<artifact-dir>/vital_signs_AOP_2m.cfg`

For your own run, do not assume the example MQTT id and topics above. After `network mqtt` plus reboot, use `device hi --transport mqtt` to read the actual `client_id`, control topics, and raw topics, then substitute those values into the later MQTT commands.

`collect` remains the official command for the strict startup-aware flow in this document. If you need an external pure-MQTT helper outside `mmwk_cli.sh`, use `./tools/mmwk_raw.sh` from the `mmwk_cli` directory instead. Use `./tools/mmwk_cfg.sh` when you need to push Wi-Fi/MQTT settings first.

Unless a specific broker override is required, the default MQTT port is `1883`. Earlier `1884` examples in this document were historical local-server residue, not the CLI or `server.sh` default.

From the `mmwk_cli` directory, the external helper supports:

```bash
./tools/mmwk_raw.sh --trigger none
./tools/mmwk_raw.sh --trigger radar-restart
./tools/mmwk_raw.sh --trigger device-reboot
```

This helper is pure MQTT for both control and raw capture. Use `./tools/mmwk_cfg.sh` when you need to push Wi-Fi/MQTT settings first, and let `./tools/mmwk_raw.sh` consume the resulting broker or `server.sh` state.

## 3. Validated Notes and Parameter Meanings

### 3.1 `server.sh`

- `run`
  - Foreground mode. Recommended for a dedicated terminal or automation session.
- `--state-dir`
  - Directory for `pid`, `env`, `mosquitto.log`, `http.log`, and related runtime state.
- `--serve-dir`
  - Directory exposed by the local HTTP server. In this example it is written as `<artifact-dir>`.
- `--host-ip`
  - Host address the device should use. In this example it is `192.168.4.9`.
- `--mqtt-port`
  - Local MQTT listen port. In this example it is `1883`.
- `--http-port`
  - Local HTTP listen port. In this example it is `8380`.

### 3.2 `mmwk_cli.sh`

- `network mqtt`
  - Configures the broker URI, client id, and MQTT CLI JSON topics.
  - On fresh bridge devices, `network mqtt` now only writes broker/auth settings while MQTT topic identity is fixed to the Wi-Fi STA MAC.
- `device agent --mqtt-en 1 --raw-auto 1`
  - Missing bridge agent keys now default to `mqtt_en=1` and `raw_auto=1`, so `network mqtt` plus reboot is enough for MQTT control.
  - In this validation, the fresh baseline already reported `mqtt_en=1` and `raw_auto=1`; the run did not separately prove whether those keys were absent in NVS.
  - Use `device agent --mqtt-en 1 --raw-auto 1` only as a manual override or troubleshooting command.
- `--transport mqtt`
  - Controls the device over MQTT instead of direct UART CLI JSON transport.
- `--broker 192.168.4.9 --mqtt-port 1883`
  - Points to the broker provided by the local `server.sh`.
- `--device-id dc5475c879c0`
  - Here this is only an example MQTT `client_id` / topic id. In your own run, use the value returned by `device hi --transport mqtt`.
- `--cmd-topic` / `--resp-topic`
  - Explicitly pins the device control topics. Use the topics returned by `device hi --transport mqtt` in your own run.
- `--base-url http://192.168.4.9:8380/`
  - Makes the device download OTA files from the local HTTP service.
- `--welcome`
  - Declares that the firmware should emit some non-empty startup text.
- `--no-verify`
  - Does not require a specific version substring inside that startup text.
- `collect -p /dev/cu.usbserial-0001`
  - Keeps UART available for auto-discovery and `radar raw` bootstrap before collection begins.
  - The CLI also waits for the device to regain a non-zero runtime IP before arming MQTT raw capture, which reduces the chance of losing startup `raw_resp` while Wi-Fi/MQTT is still reconnecting.
  - Treat this as the strict startup-aware collection path. If you use it as proof for a fresh reboot or radar restart window, require non-empty `raw_resp`.
- `--resp-optional`
  - Use this only for a pure-MQTT late-attach observation window after `radar status` already returned `running`.
  - Do not use `--resp-optional` as startup proof after radar restart, OTA, reconf, or factory/baseline recovery.
- `--reset`
  - Helpful for post-reboot UART checks if runtime logs on the command port temporarily corrupt CLI JSON framing.
  - Once MQTT control is up, prefer MQTT for follow-up commands.
- `--data-topic`
  - Subscribes to radar DATA UART passthrough (`raw_data` from `on_radar_data`).
- `--resp-topic`
  - Subscribes to startup-trimmed radar command-port output (`raw_resp` from `on_cmd_data`).

Topic split reminder:
- `mmwk/{mac}/device/cmd` and `mmwk/{mac}/device/resp` are the MQTT CLI JSON control topics configured by `network mqtt`.
- `mmwk/{mac}/raw/data` and `mmwk/{mac}/raw/resp` are the radar passthrough output topics.
- `mmwk/{mac}/raw/cmd` is a separate optional radar ingress topic that exists only in host mode and is distinct from `mmwk/{mac}/device/cmd`.
- In bridge/auto mode the MQTT raw plane is intentionally output-only, so collection only needs `mmwk/{mac}/raw/data` and `mmwk/{mac}/raw/resp`.

### 3.3 Important Validated Caveats

- Fresh-device behavior matters.
  - On current main, a fresh factory image should come up with `mqtt_en=1`, `raw_auto=1`, an empty `mqtt_uri`, `state=prov_waiting`, `ip_ready=false`, and an empty `sta_ip`.
  - That means `network mqtt` plus reboot is the step that explicitly chooses the private/local broker to use.
  - If you still see a public broker URI on a device, treat that device image as older than current main and reflash before continuing.
- Pre-OTA radar state may still report `updating`.
  - In the current main-branch validation, the first MQTT-side `radar status` checks still returned `updating` even before the new OTA command was sent.
  - That did not block the later OTA flow. Treat `running` or a stable pre-OTA `updating` result as acceptable before Step 8, as long as MQTT control itself is working.
- UART CLI JSON and runtime logs can overlap.
  - During validation, immediate post-reboot UART CLI JSON commands could fail with corrupt JSON because runtime logs were appearing on the command port.
  - Do not run concurrent UART commands against the same port.
  - If a post-reboot UART query fails, retry once with `--reset` or switch to MQTT as soon as MQTT is available.
- `radar ota` completion timing varies by run.
  - In the validated 2026-03-19 run, the CLI timed out first, and follow-up polling still showed `updating` before later returning to `running`.
  - In the validated 2026-04-01 rerun, the CLI automatically extended phase 3 by 30 seconds and returned success after `148.4` seconds even though the OTA-stage `raw_resp` capture remained empty.
  - Do not immediately reflash on timeout, and always follow OTA with the same `radar status = running` ready gate.
- Radar restart actions need an explicit ready gate.
  - After `radar flash`, `radar ota`, `radar reconf`, or the first boot after factory / baseline recovery, poll `radar status` until it reports `running`.
  - Do not replace that gate with a fixed sleep.
- `radar version` was not a reliable success check in this validation.
  - In this environment it returned the same payload as `device hi`, not a separate radar version string.
  - Primary success proof should therefore be `radar status = running` plus raw startup bytes in `raw_resp`.
- `raw_resp` is a startup-trimmed command-port capture.
  - It starts at the first printable ASCII byte instead of preserving the dirty startup prefix.
  - Separators and partial banner text after that point are still expected.
  - In the current main-branch validations, OTA-stage `raw_resp` either captured startup bytes beginning with `xWR64xx MMW Demo 03.06.00.00` or stayed empty, and the later 300-second collect ranged from a truncated `IWR6843AOP Vital Signs...` banner to a longer `IWR6843AOP Vital Signs with People Tracking` command transcript.
  - Any non-empty startup output satisfies `welcome=true`.

## 4. Validated Execution Flow

### Step 0: Start Local `server.sh`

Command:

```bash
./mmwk_cli/server.sh run \
  --state-dir <demo-output-dir>/local_server \
  --serve-dir <artifact-dir> \
  --host-ip 192.168.4.9 \
  --mqtt-port 1883 \
  --http-port 8380
```

Success evidence:

- `server.sh status` reports `MQTT Up   : yes` and `HTTP Up   : yes`
- `server.sh env` reports:
  - `MMWK_SERVER_MQTT_URI=mqtt://192.168.4.9:1883`
  - `MMWK_SERVER_HTTP_BASE_URL=http://192.168.4.9:8380/`
- `<demo-output-dir>/local_server/http.log` records local HTTP activity

### Step 1: Read Baseline Device State over UART

Commands:

```bash
./mmwk_cli/mmwk_cli.sh device hi --reset -p /dev/cu.usbserial-0001
./mmwk_cli/mmwk_cli.sh network status --reset -p /dev/cu.usbserial-0001
```

Validated baseline:

- Device model: `mmwk_sensor_bridge`
- Board: `mini`
- `mqtt_uri = ""` (not configured yet)
- `mqtt_en = 1`
- `raw_auto = 1`
- `state = prov_waiting`
- `ip_ready = false`
- `sta_ip = ""`

This is an important fresh-device baseline. The device is still waiting for Wi-Fi provisioning, but fresh bridge defaults already keep `mqtt_en=1` and `raw_auto=1`.

### Step 2: Write Wi-Fi Credentials

Command:

```bash
./mmwk_cli/mmwk_cli.sh network config \
  --ssid ventropic \
  --password ve12345678 \
  -p /dev/cu.usbserial-0001
```

Success evidence:

- Returns `WiFi credentials saved. Connecting...`

### Step 3: Write Local MQTT Settings

Command:

```bash
./mmwk_cli/mmwk_cli.sh network mqtt \
  --mqtt-uri mqtt://192.168.4.9:1883 \
  -p /dev/cu.usbserial-0001
```

Success evidence:

- Returns `MQTT config updated. Reboot applying...`

Important:

- This step stores the broker settings; MQTT topic identity remains fixed to the Wi-Fi STA MAC.
- The MQTT `client_id` is now fixed to the Wi-Fi STA MAC. After reboot, use `device hi --transport mqtt` to confirm the derived `client_id` and canonical topics.
- On a fresh bridge device, rebooting after this step should be enough to make MQTT CLI JSON control usable.

### Step 4: Optional Manual Override for Older Persisted Agent Settings

Command:

```bash
./mmwk_cli/mmwk_cli.sh device agent \
  --mqtt-en 1 \
  --uart-en 1 \
  --raw-auto 1 \
  --reset \
  -p /dev/cu.usbserial-0001
```

Success evidence:

- Returns `{"status":"success","msg":"Agent config updated"}`

Use this only when the device is carrying older persisted values or you are troubleshooting a bridge whose MQTT control path was manually disabled. Fresh bridge defaults should not require this step.

### Step 5: Reboot the Device

Command:

```bash
./mmwk_cli/mmwk_cli.sh device reboot -p /dev/cu.usbserial-0001
```

Success evidence:

- Returns `{"status":"rebooting"}`

### Step 6: Handshake Again over Local MQTT

Command:

```bash
./mmwk_cli/mmwk_cli.sh device hi \
  --transport mqtt \
  --broker 192.168.4.9 \
  --mqtt-port 1883 \
  --device-id dc5475c879c0 \
  --cmd-topic mmwk/dc5475c879c0/device/cmd \
  --resp-topic mmwk/dc5475c879c0/device/resp
```

Success evidence:

- `MQTT connected, subscribing to mmwk/dc5475c879c0/device/resp`
- Returned:
  - `ip = 192.168.4.8`
  - `mqtt_uri = mqtt://192.168.4.9:1883`
  - `mqtt_en = 1`
  - `raw_auto = 1`
  - `wifi_rssi = -57`

### Step 7: Check Radar Status Before OTA

Command:

```bash
./mmwk_cli/mmwk_cli.sh radar status \
  --transport mqtt \
  --broker 192.168.4.9 \
  --mqtt-port 1883 \
  --device-id dc5475c879c0 \
  --cmd-topic mmwk/dc5475c879c0/device/cmd \
  --resp-topic mmwk/dc5475c879c0/device/resp
```

Success evidence:

- Returns a valid radar state over MQTT.
- In the current main-branch validation, the pre-OTA MQTT-side state still returned `{"state":"updating"}`.
- If your device already reports `{"state":"running"}`, that is also fine.

### Step 8: Run Wi-Fi OTA Flash

Command:

```bash
./mmwk_cli/mmwk_cli.sh radar ota \
  --fw <artifact-dir>/vital_signs_tracking_6843AOP_demo.bin \
  --cfg <artifact-dir>/vital_signs_AOP_2m.cfg \
  --welcome \
  --no-verify \
  --ota-timeout 300 \
  --progress-interval 5 \
  --raw-resp-output <demo-output-dir>/ota_cmd_resp.log \
  --transport mqtt \
  --broker 192.168.4.9 \
  --mqtt-port 1883 \
  --device-id dc5475c879c0 \
  --cmd-topic mmwk/dc5475c879c0/device/cmd \
  --resp-topic mmwk/dc5475c879c0/device/resp \
  --base-url http://192.168.4.9:8380/
```

Validated observations:

- The device accepted the OTA command.
- `<demo-output-dir>/local_server/http.log` recorded:
  - `GET /vital_signs_tracking_6843AOP_demo.bin HTTP/1.1" 200`
  - `GET /vital_signs_AOP_2m.cfg HTTP/1.1" 200`
- `radar status` entered `updating`.
- The displayed OTA progress restarted from `0%` after the firmware stage because the config stage began. That reset was expected in this run.
- In the validated 2026-03-19 run, the OTA-stage `raw_resp` capture recorded `2` messages / `128` bytes, and the CLI still eventually reported `OTA timeout`.
- In the validated 2026-04-01 rerun, the OTA-stage `raw_resp` capture stayed empty, but the CLI auto-extended phase 3 by 30 seconds and completed with `flash_success` in `148.4` seconds.

This means:

- The local HTTP service worked.
- Device-side OTA definitely started.
- Current main may either finish during the built-in phase 3 grace window or still time out first.
- The OTA-step `raw_resp` capture remains best-effort and can be empty even on a successful non-timeout run.

### Step 9: Verify `running` After OTA

Recommended command:

```bash
./mmwk_cli/mmwk_cli.sh radar status \
  --transport mqtt \
  --broker 192.168.4.9 \
  --mqtt-port 1883 \
  --device-id dc5475c879c0 \
  --cmd-topic mmwk/dc5475c879c0/device/cmd \
  --resp-topic mmwk/dc5475c879c0/device/resp
```

Validated observations:

- In the 2026-03-19 timeout case, the validated device still returned `{"state":"updating"}` immediately after timeout, and only later returned `{"state":"running"}` without reflashing.
- In the 2026-04-01 rerun, `radar ota` itself returned success after the phase-3 grace window, and the immediate follow-up poll already returned `{"state":"running"}`.

Conclusion:

- Always poll `radar status` until it returns `running`, even if `radar ota` itself reported success.
- If `radar ota` times out, do not immediately reflash.
- Apply the same explicit `radar status = running` gate after `radar flash`, `radar reconf`, or the first boot after a factory / baseline recovery path.
- Use the later `raw_resp` capture to confirm the radar emitted startup output.
- Capturing `raw_resp` from the `radar ota` step itself with `--raw-resp-output` is best-effort only. In the 2026-03-19 main validation it captured `2` messages / `128` bytes before timeout, while in the successful 2026-04-01 rerun it stayed empty.
- Treat `radar status = running` plus later post-recovery `raw_resp` startup bytes as the reliable proof path.

### Step 10: Collect 300 Seconds of `raw_data` and `raw_resp`

Command:

```bash
./mmwk_cli/mmwk_cli.sh collect \
  --duration 300 \
  --broker mqtt://192.168.4.9:1883 \
  --device-id dc5475c879c0 \
  --data-topic mmwk/dc5475c879c0/raw/data \
  --resp-topic mmwk/dc5475c879c0/raw/resp \
  --data-output <demo-output-dir>/data_resp_300s.sraw \
  --resp-output <demo-output-dir>/cmd_resp_300s.log \
  -p /dev/cu.usbserial-0001
```

Important runtime note:

- With `-p/--port`, `collect` now waits for the bridge to recover Wi-Fi/MQTT connectivity before arming raw MQTT capture and the restart probe.
- This matters on real hardware because the earliest startup `raw_resp` can otherwise be dropped while the device-side MQTT client is still offline.
- Keep pure-MQTT late-attach collection behind the Step 9 ready gate. If you switch to `collect --resp-optional`, do it only after `radar status` already reports `running`.
- When `collect -p` is used as the startup proof path, `cmd_resp_300s.log` / `raw_resp` should not be empty.

Validated example results:

- 2026-03-19 run:
  - `Collected frames: 3135`
  - `Collected bytes: 384044`
  - `Data topic frames (DATA UART / binary): 3134`
  - `Data topic bytes (DATA UART / binary): 383980`
  - `Resp topic frames (CMD UART / startup-trimmed command-port text): 1`
  - `Resp topic bytes (CMD UART / startup-trimmed command-port text): 64`
- 2026-04-01 rerun:
  - `Collected frames: 3152`
  - `Collected bytes: 313470`
  - `Data topic frames (DATA UART / binary): 3107`
  - `Data topic bytes (DATA UART / binary): 311546`
  - `Resp topic frames (CMD UART / startup-trimmed command-port text): 45`
  - `Resp topic bytes (CMD UART / startup-trimmed command-port text): 1924`

Example output files for this step:

- `<demo-output-dir>/data_resp_300s.sraw`: non-empty `raw_data` capture for the 300-second run
- `<demo-output-dir>/cmd_resp_300s.log`: ranged from `64` bytes in the 2026-03-19 run to `1924` bytes in the 2026-04-01 rerun, always starting at the first printable ASCII byte

Hard acceptance gate for this step:

- `data_resp` must be at least `100 KB`.
- `cmd_resp` must show multiple logical lines of command-port output.
- `radar status` must still be `running` after collection.

Validated `raw_resp` example:

```text
***********************************
\rIWR6843AOP Vital Signs with People Tracking
\rmmwDemo:/>sensorStop
```

Notes:

- `raw_resp` still originates from `on_cmd_data`, but startup noise before the first printable ASCII byte is trimmed in the driver.
- Observed `raw_resp` volume can vary significantly across valid runs, from a single truncated banner chunk to a multi-line command transcript.
- Partial banner text is still acceptable.
- From the user perspective, `cmd_resp.log` should already read as clean command-port text.

### Step 11: Recheck Radar Status After Collection

Command:

```bash
./mmwk_cli/mmwk_cli.sh radar status \
  --transport mqtt \
  --broker 192.168.4.9 \
  --mqtt-port 1883 \
  --device-id dc5475c879c0 \
  --cmd-topic mmwk/dc5475c879c0/device/cmd \
  --resp-topic mmwk/dc5475c879c0/device/resp
```

Success evidence:

- Returns `{"state":"running"}`

### Step 12: Stop Local `server.sh`

Command:

```bash
./mmwk_cli/server.sh stop --state-dir <demo-output-dir>/local_server
```

Success evidence:

- Returns `Local server stopped`

## 5. Recommended Manual Demo Flow

In terminal A:

```bash
./mmwk_cli/server.sh run \
  --serve-dir <artifact-dir> \
  --host-ip 192.168.4.9 \
  --mqtt-port 1883 \
  --http-port 8380
```

In terminal B:

```bash
./mmwk_cli/mmwk_cli.sh network config --ssid ventropic --password ve12345678 --reset -p /dev/cu.usbserial-0001
./mmwk_cli/mmwk_cli.sh network mqtt --mqtt-uri mqtt://192.168.4.9:1883 --reset -p /dev/cu.usbserial-0001
./mmwk_cli/mmwk_cli.sh device reboot --reset -p /dev/cu.usbserial-0001
./mmwk_cli/mmwk_cli.sh device hi --transport mqtt --broker 192.168.4.9 --mqtt-port 1883 --device-id dc5475c879c0 --cmd-topic mmwk/dc5475c879c0/device/cmd --resp-topic mmwk/dc5475c879c0/device/resp
./mmwk_cli/mmwk_cli.sh radar ota --fw <artifact-dir>/vital_signs_tracking_6843AOP_demo.bin --cfg <artifact-dir>/vital_signs_AOP_2m.cfg --welcome --no-verify --raw-resp-output ./ota_cmd_resp.log --transport mqtt --broker 192.168.4.9 --mqtt-port 1883 --device-id dc5475c879c0 --cmd-topic mmwk/dc5475c879c0/device/cmd --resp-topic mmwk/dc5475c879c0/device/resp --base-url http://192.168.4.9:8380/
```

If MQTT control is still disabled because the device is carrying older persisted agent values, run this manual override before rebooting:

```bash
./mmwk_cli/mmwk_cli.sh device agent --mqtt-en 1 --raw-auto 1 --reset -p /dev/cu.usbserial-0001
```

If `radar ota` times out, or if you want an explicit ready gate before collection:

```bash
while true; do
  ./mmwk_cli/mmwk_cli.sh radar status --transport mqtt --broker 192.168.4.9 --mqtt-port 1883 --device-id dc5475c879c0 --cmd-topic mmwk/dc5475c879c0/device/cmd --resp-topic mmwk/dc5475c879c0/device/resp
  sleep 10
done
```

After the radar returns `running`:

```bash
./mmwk_cli/mmwk_cli.sh collect --duration 300 --broker mqtt://192.168.4.9:1883 --device-id dc5475c879c0 --data-topic mmwk/dc5475c879c0/raw/data --resp-topic mmwk/dc5475c879c0/raw/resp --data-output ./data_resp_300s.sraw --resp-output ./cmd_resp_300s.log -p /dev/cu.usbserial-0001
```

If an immediate post-reboot UART CLI JSON query fails, retry once with `--reset` instead of assuming the device is broken.

## 6. Output Artifacts

- Demo directory: `<demo-output-dir>`
- Key artifacts:
  - `<demo-output-dir>/data_resp_300s.sraw`
  - `<demo-output-dir>/cmd_resp_300s.log`
  - `<demo-output-dir>/ota_cmd_resp.log`
  - `<demo-output-dir>/collect_300s.log`
  - `<demo-output-dir>/local_server/mosquitto.log`
  - `<demo-output-dir>/local_server/http.log`
  - This document: `./collect.md`

## 7. Final Result

This validated flow completed successfully on a fresh mini bridge device:

- Local `server.sh` provided MQTT and HTTP successfully, serving the repo-shipped `./firmwares/radar/iwr6843/vital_signs` assets from main.
- The fresh device was expected to reach MQTT control after `network mqtt` plus reboot, with `device agent --mqtt-en 1 --raw-auto 1` kept only as a manual override / troubleshooting path for older persisted settings.
- The pre-OTA MQTT-side `radar status` may already report either `updating` or `running`; both were observed across validations and neither blocked the later OTA flow.
- The device downloaded `.bin` and `.cfg` over Wi-Fi from the local HTTP service.
- `radar ota` completion timing varied across repeated validations: the 2026-03-19 run timed out first and later recovered to `running`, while the 2026-04-01 rerun completed in `148.4` seconds after the built-in phase-3 grace. In both cases no reflash was needed.
- OTA-stage `raw_resp` capture remained best-effort only: one validated run recorded `2` messages / `128` bytes, while another successful rerun recorded `0` bytes.
- Repeated 300-second collections completed successfully. Observed `raw_data` ranged from `311546` to `383980` bytes, observed `raw_resp` ranged from `64` to `1924` bytes, and the final `radar status` remained `running`.
