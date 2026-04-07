# MMWK Sensor BRIDGE Reference

Use this document when you already know your start path from [MMWK Bridge Mode](./bridge.md) and need the deeper bridge semantics, parameter contracts, and runtime verification details.

## Validated Execution Context

- Run the shell examples from `./mmwk_cli` so `./mmwk_cli.sh` and the `../firmwares/...` reference paths resolve exactly as written.
- Replace `PORT=/dev/cu.usbserial-0001` with your real UART port before you copy the commands.
- This reference assumes `./mmwk_cli.sh device hi -p "$PORT"` already reports `name = mmwk_sensor_bridge`. If it reports another profile such as `mmwk_sensor_hub`, go back to [MMWK Bridge Mode](./bridge.md) first and switch to the correct path.
- `mmwk_cli.sh` now defaults to canonical CLI JSON. If an older caller still depends on MCP, add `--protocol mcp` explicitly as a compatibility fallback.
- This reference does not replace Wi-Fi or MQTT bring-up. Before you run `collect`, `device hi` should already expose bridge MQTT fields such as `mqtt_uri`, `client_id`, `raw_data_topic`, and `raw_resp_topic`, and the device should already have usable runtime networking such as a non-zero `ip`. If those fields are still missing or the device is still at `ip = 0.0.0.0`, return to [MMWK Bridge Mode](./bridge.md) and then [Local `server.sh` + `mmwk_cli.sh` Wi-Fi Flash and 5-Minute Collection Example](./collect.md).
- If you just ran `radar flash`, `radar ota`, `radar reconf`, or the first boot after a factory / baseline recovery path, wait for `radar status` to return `running` before you rely on any late-attach `collect` flow.

Use these validated shell variables in the command examples below:

```bash
cd ./mmwk_cli
export PORT=/dev/cu.usbserial-0001
export FW=../firmwares/radar/iwr6843/vital_signs/vital_signs_tracking_6843AOP_demo.bin
export CFG=../firmwares/radar/iwr6843/vital_signs/vital_signs_AOP_2m.cfg
```

## Raw Semantics Contract

- `raw_resp = startup-trimmed command-port output from on_cmd_data`
- `raw_data = raw data-port bytes from on_radar_data`
- `on_cmd_resp is an application-layer command response`, and it is different from raw capture.
- `on_radar_frame is an application-layer frame callback`, and it is different from raw capture.
- Startup noise before the first printable ASCII byte is trimmed in the radar driver before command-port output is surfaced to the host.
- `cmd_resp.log` keeps the startup-trimmed command-port text stream that starts at the first printable ASCII byte.

## Flash Parameter Reference

The current bridge build already bundles `out_of_box_6843_aop.bin` + `out_of_box_6843_aop.cfg` as the default on-device radar asset. The reference example below intentionally switches to TI `vital_signs` assets so you validate a real radar replacement flow:

- `../firmwares/radar/iwr6843/vital_signs/vital_signs_tracking_6843AOP_demo.bin`
- `../firmwares/radar/iwr6843/vital_signs/vital_signs_AOP_2m.cfg`

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

## Managed Firmware Catalog (`fw list` / `fw set`)

Use the `fw` commands when you want to manage the ESP-side radar firmware catalog rather than push a new radar image from the host in that moment.

Examples:

```bash
./mmwk_cli.sh fw list -p "$PORT"
./mmwk_cli.sh fw set --index 0 -p "$PORT"
```

Contract:

- `fw list` is the bridge-facing catalog surface. Each entry includes `default` and `running` flags so you can tell which firmware is the saved default and which managed catalog entry is running now.
- Current bridge builds expose bundled firmware/config pairs from a build-generated bundled catalog derived from the staged asset set, so `fw list` shows those bundled rows alongside manifest-managed entries.
- Those bundled rows are runtime assets, not host-uploaded storage objects, so treat them as bundled/read-only catalog rows.
- `fw set --index <n>` is a persistent default change, not a metadata-only toggle. The bridge routes it through the UART radar update/flash path, and on success that firmware becomes the new default entry.
- `device hi` now exposes nested firmware state as `fw.default`, `fw.running`, `fw.switch`, and `fw.mode`.
- `fw.default` and `fw.running` each include `source`, `index`, `name`, `version`, and `config`.
- `fw.default` is the saved persistent default entry; `fw.running` is the live runtime entry for the current session.
- `fw.running.source=runtime` means the current radar session is pinned to an explicit staged runtime artifact pair instead of a catalog/default firmware row.
- `fw.switch` reports the profile-gated switch capability flags. Current bridge builds report `fw.switch.persist=true` and `fw.switch.temp=false`.
- `fw.mode` reports how the current radar session booted: `flash`, `uart`, `spi`, or `host`.
- Legacy aliases `radar_fw`, `radar_fw_version`, and `radar_cfg` still mirror `fw.running` for compatibility.
- Runtime-only non-default switching (`radar switch persist=false`) is not part of the validated bridge reference flow. It is not exposed by `mmwk_cli`, and with current bridge builds you should treat it as unsupported until temporary SPI boot is validated on the active radar family.

## Runtime Reconfiguration (`radar reconf`)

Use `radar reconf` when you want to change the runtime radar contract without flashing firmware again. This is the bridge-side shortcut for switching `welcome` / `verify` / `version` semantics and optional runtime cfg selection while keeping the current radar firmware binary in place.

Examples:

```bash
./mmwk_cli.sh radar reconf --welcome --no-verify -p "$PORT"
./mmwk_cli.sh radar reconf --welcome --verify --version "1.2.3" -p "$PORT"
./mmwk_cli.sh radar reconf --welcome --no-verify --cfg ./runtime.cfg -p "$PORT"
./mmwk_cli.sh radar reconf --welcome --no-verify --clear-cfg -p "$PORT"
```

Contract:

- bridge-only runtime reconfiguration; host mode is rejected.
- `cfg_action` values are `keep | replace | clear`.
- `--cfg` maps to `cfg_action=replace`, uploads only a runtime cfg, and finishes with `uart_data action=reconf_done`.
- `--clear-cfg` maps to `cfg_action=clear` and removes the persisted runtime cfg override.
- no `--cfg` flag maps to `cfg_action=keep` and preserves the current runtime cfg selection.
- unlike `radar flash` or `radar ota`, `radar reconf` does not flash firmware and does not replace the radar binary.
- Treat `radar reconf` as an optional advanced step, not as the minimal validated bridge-reference flow below. After any `radar reconf`, re-check `radar status` and wait for `state=running` before you rely on `radar version` or `collect`.

## Runtime CFG Readback (`radar cfg`)

Use `radar cfg` when you need to read back the current effective radar cfg text without changing firmware or runtime contract state.

Example:

```bash
./mmwk_cli.sh radar cfg -p "$PORT"
```

Contract:

- default behavior reads the current effective file cfg text.
- the effective file cfg is the selected runtime override cfg when one is present; otherwise it is the default firmware metadata cfg.
- After `radar flash` with an explicit firmware/config pair, bridge persists the exact staged runtime pair instead of silently rebinding to a bundled `/assets` catalog entry with the same version.
- If a persisted explicit runtime firmware or cfg path cannot be reopened exactly on the next startup, bridge fails startup instead of silently substituting a different bundled asset pair.
- do not use `--gen` in the bridge reference flow; bridge rejects it explicitly because bridge has no generated cfg source.
- `--gen` is hub-only and reads the hub-generated cfg only; it must not fall back to the file cfg.
- if the selected file cfg is missing, unreadable, or empty, the request fails directly.
- CLI prints only the cfg text to stdout, so redirecting the output preserves the raw cfg content.

## Startup Mode Contract

- `startup_mode` means the saved/configured default mode.
- `supported_modes` means the capability list for the active profile.
- bridge supports `["auto", "host"]`.
- hub supports `["auto"]`.
- `device startup --mode auto|host` updates the saved default mode.
- `radar status --set start --mode auto|host` is a one-shot start request for the current radar service and does not overwrite the saved default mode.
- `raw_auto` only controls raw-plane auto-start. It does not decide who owns radar startup.

Bridge startup-mode meaning:

- `auto` means ESP-managed radar bring-up. The device may select firmware/config metadata, wait for startup CLI/welcome output, verify version metadata, and send radar configuration.
- `host` means host-controlled radar bring-up. The device still exposes transport surfaces, but it does not automatically send radar configuration, does not automatically wait for welcome text, and does not automatically verify version metadata as part of startup ownership.
- In bridge `host`, explicit maintenance commands such as `radar flash` and `radar ota` still work when you invoke them directly.
- In bridge `host` with `raw_auto=1`, the auto-started raw plane includes `mmwk/{mac}/raw/data`, `mmwk/{mac}/raw/resp`, and `mmwk/{mac}/raw/cmd`.

## Version Handling: With and Without a Version String

- `radar flash` and `radar ota` both expose `--version <str>`, `--verify` / `--no-verify`, and `--welcome` / `--no-welcome`.
- `radar flash` and `radar ota` both infer radar metadata from a sibling `meta.json` next to the `--fw` binary: `welcome` plus optional `version`.
- If both CLI flags and `meta.json` are available, the explicit CLI values win.
- The device does not actively query a radar-side version register. Instead, after boot and before any radar config commands are sent, it watches the startup CLI/welcome output.
- `welcome` tells the device whether that startup CLI/welcome output should exist at all.
- For `welcome=true`, any non-empty startup output counts. It is not a fixed banner template and it may span multiple lines.
- `welcome` is operationally important for two separate reasons: it proves the radar firmware really booted far enough to emit its startup CLI text, and it carries the radar firmware's real runtime version string.
- `version` is the substring matched inside that startup CLI/welcome output.
- When verification is enabled, MMWK searches for the version substring anywhere in the accumulated startup text. It does not require a fixed welcome line.
- If `welcome` metadata is wrong, MMWK can either wait for text that will never come, or skip the only runtime proof/version source it has for the radar image.
- If `welcome=true` but no startup CLI/welcome output arrives before timeout, treat that as a radar startup failure: the firmware likely did not boot on the radar. In that case `radar status` keeps `state=error` and includes a `details` object explaining the failure, while the radar-side log prints a boot observation summary.
- `--verify` enables version matching and requires a version string. If `--verify` is not enabled, flashing still works, but `radar version` may be empty because there is no expected string to match and persist.
- The packaged `vital_signs` example used in the bridge flow now ships with a sibling `meta.json`, so both `radar flash` and `radar ota` can infer the expected radar metadata automatically. If you replace it with another custom demo, add a matching `meta.json` yourself or pass `--welcome` / `--version` explicitly.
- If you need to customize the radar firmware version that MMWK recognizes, make the radar firmware's startup CLI output print the desired version string, then ensure the host passes the same expected string via `--version` or adjacent `meta.json`.

Minimal `meta.json` example:

```json
{
  "fws": [
    {
      "firmware": "vital_signs_tracking_6843AOP_demo.bin",
      "welcome": true,
      "version": "<startup-version-string>"
    }
  ]
}
```

## Transport and Topic Split

`network mqtt` configures the device MQTT identity plus the MCP interaction channel. `radar raw` reuses that broker/client and derives the raw radar passthrough plane.

| Topic | Content |
| --- | --- |
| `mmwk/{mac}/device/cmd` | MCP command input configured by `network mqtt`. |
| `mmwk/{mac}/device/resp` | MCP command responses and status events configured by `network mqtt`. |
| `mmwk/{mac}/raw/data` | Raw radar DATA UART payloads derived by `radar raw`. |
| `mmwk/{mac}/raw/resp` | Raw radar command-port bytes from `on_cmd_data`, derived by `radar raw`. |
| `mmwk/{mac}/raw/cmd` | Optional radar CMD UART ingress channel derived by `radar raw`, available only in host mode. |

On fresh bridge devices, `network mqtt` plus reboot is enough to bring up MQTT control.
When the agent keys are missing from NVS, bridge defaults are `mqtt_en=1` and `raw_auto=1`.
Use `device agent --mqtt-en 1 --raw-auto 1` only as a manual override or troubleshooting step.

## Welcome / Startup Output Semantics

- Startup text is a boot observation, not a fixed banner contract.
- The welcome path is the only runtime source MMWK has for both “did the radar app boot?” and “what version string did it print?”.
- If `welcome=true`, the device should observe startup CLI/welcome output before normal config is applied.
- If no such output arrives in time, the device treats the session as failed and persists structured failure information in `radar status`.

## Host Mode vs Bridge Mode Boundaries

- `startup_mode=host` means host-controlled bring-up, not “auto mode plus one more raw topic”.
- `startup_mode=auto` means the ESP owns radar startup/config bring-up for bridge.
- `mmwk/{mac}/raw/cmd` is available only in host mode.
- In bridge/auto mode, the MQTT raw plane is output-only.
- `mmwk/{mac}/raw/cmd` is distinct from the MCP topic `mmwk/{mac}/device/cmd`.
- Real applications, services, dashboards, and agents should normally integrate through MQTT. UART remains valuable for factory setup, flashing, bring-up, bench debugging, and emergency fallback.

## Runtime Verification Checklist

Use these commands together after radar flash, OTA, reconf, or the first boot after a factory / baseline recovery path:

```bash
./mmwk_cli.sh device hi -p "$PORT" | tee ./bridge_hi.json
./mmwk_cli.sh device hi --transport mqtt --broker "$BROKER_HOST" --mqtt-port "$MQTT_PORT" --device-id "$DEVICE_ID" --cmd-topic "$CMD_TOPIC" --resp-topic "$RESP_TOPIC"
./mmwk_cli.sh radar status --transport mqtt --broker "$BROKER_HOST" --mqtt-port "$MQTT_PORT" --device-id "$DEVICE_ID" --cmd-topic "$CMD_TOPIC" --resp-topic "$RESP_TOPIC"
./mmwk_cli.sh radar version --transport mqtt --broker "$BROKER_HOST" --mqtt-port "$MQTT_PORT" --device-id "$DEVICE_ID" --cmd-topic "$CMD_TOPIC" --resp-topic "$RESP_TOPIC"
./mmwk_cli.sh collect --duration 12 \
  --broker "$BROKER_URI" \
  --device-id "$DEVICE_ID" \
  --data-topic "$RAW_DATA_TOPIC" \
  --resp-topic "$RAW_RESP_TOPIC" \
  --resp-optional \
  --data-output ./data_resp.sraw \
  --resp-output ./cmd_resp.log
```

Interpret the results as follows:

- `radar status` should report a usable state such as `running`.
- Right after `radar flash` or `radar reconf`, `radar status` may transiently report `starting`. Wait for `state=running` before you treat `radar version` as decisive runtime proof.
- Treat that `radar status = running` poll as mandatory after `radar flash`, `radar ota`, `radar reconf`, or the first boot after factory / baseline recovery. Do not replace it with a fixed sleep.
- Start with one UART `device hi -p "$PORT"` to confirm you are on bridge and to capture the MQTT identity fields for the current session.
- On current PRO validation, repeated standalone UART commands can re-enter the boot window. Once MQTT control is available, prefer MQTT transport for `device hi`, `radar status`, and `radar version`.
- `device hi` should show the canonical ESP firmware identity in `name` / `version`.
- If `device hi` still reports `ip = 0.0.0.0`, treat the device network as not ready for MQTT raw capture yet. `collect` may wait briefly and then still fail at broker connect time if Wi-Fi/MQTT bring-up has not completed.
- `device hi.fw.default`, `device hi.fw.running`, `device hi.fw.switch`, and `device hi.fw.mode` are the canonical firmware-state fields for bridge-managed multi-firmware sessions.
- Its `radar_fw`, `radar_fw_version`, and `radar_cfg` fields reflect the live running radar metadata entry for the current session; they do not stay pinned to `fw.default` after a successful direct flash, OTA, or runtime-only running-state change.
- `radar_fw`, `radar_fw_version`, and `radar_cfg` are legacy aliases of `fw.running`.
- `fw.switch.persist=true` with `fw.switch.temp=false` means current bridge builds support persistent default changes but do not expose validated runtime-only SPI switching.
- Use `radar version` together with `radar status` as the runtime proof when the session actually persists a runtime version string.
- `radar version` can be empty when the current runtime contract does not persist a version string. Treat `radar status=running` as the primary runtime proof, and treat a non-empty `radar version` as supplemental evidence when present.
- If `radar status` returns `state=error` with a `details` object, treat that object as the structured startup/run failure diagnosis.
- `details.kind=startup_failed` means the firmware likely never reached its startup CLI on the radar.
- `cmd_resp.log` should begin at the first printable ASCII byte and read as startup-trimmed command-port text when the device emits fresh startup command-port bytes during the collection window.
- In this checklist, `collect --resp-optional` is only for a late-attach steady-state window after `radar status` already proves the radar is running. It is not a startup/welcome proof.
- If you instead use `collect -p "$PORT"` as the startup-aware proof path after one of those recovery windows, require non-empty `raw_resp` / `cmd_resp.log`.
- This late-attach runtime check intentionally stays on pure MQTT. Do not add `-p "$PORT"` back here unless you also remove `--resp-optional` and require a non-empty startup `raw_resp`.
- If you need an external pure-MQTT startup helper instead of the official `collect` command, run `./tools/mmwk_raw.sh` from the `mmwk_cli` directory. It supports `trigger=none`, `trigger=radar-restart`, and `trigger=device-reboot`. Use `./tools/mmwk_cfg.sh` first when you need to push Wi-Fi/MQTT settings or point the device at a local `server.sh` broker.
- For a strict startup-text proof, follow [Local `server.sh` + `mmwk_cli.sh` Wi-Fi Flash and 5-Minute Collection Example](./collect.md).

## Validated Runtime Command Chain

When you want one copyable bridge-reference flow that matches the current implementation, use this runtime-verification chain from `./mmwk_cli`:

```bash
./mmwk_cli.sh device hi -p "$PORT" | tee ./bridge_hi.json

export BROKER_URI="$(python3 - <<'PY'
import json
with open("./bridge_hi.json", "r", encoding="utf-8") as fp:
    payload = json.load(fp)
print(payload["mqtt_uri"])
PY
)"
export BROKER_HOST="$(python3 - <<'PY'
from urllib.parse import urlparse
import json
with open("./bridge_hi.json", "r", encoding="utf-8") as fp:
    payload = json.load(fp)
print(urlparse(payload["mqtt_uri"]).hostname or "")
PY
)"
export MQTT_PORT="$(python3 - <<'PY'
from urllib.parse import urlparse
import json
with open("./bridge_hi.json", "r", encoding="utf-8") as fp:
    payload = json.load(fp)
print(urlparse(payload["mqtt_uri"]).port or 1883)
PY
)"
export DEVICE_ID="$(python3 - <<'PY'
import json
with open("./bridge_hi.json", "r", encoding="utf-8") as fp:
    payload = json.load(fp)
print(payload["client_id"])
PY
)"
export CMD_TOPIC="$(python3 - <<'PY'
import json
with open("./bridge_hi.json", "r", encoding="utf-8") as fp:
    payload = json.load(fp)
print(payload["cmd_topic"])
PY
)"
export RESP_TOPIC="$(python3 - <<'PY'
import json
with open("./bridge_hi.json", "r", encoding="utf-8") as fp:
    payload = json.load(fp)
print(payload["resp_topic"])
PY
)"
export RAW_DATA_TOPIC="$(python3 - <<'PY'
import json
with open("./bridge_hi.json", "r", encoding="utf-8") as fp:
    payload = json.load(fp)
print(payload["raw_data_topic"])
PY
)"
export RAW_RESP_TOPIC="$(python3 - <<'PY'
import json
with open("./bridge_hi.json", "r", encoding="utf-8") as fp:
    payload = json.load(fp)
print(payload["raw_resp_topic"])
PY
)"

until ./mmwk_cli.sh device hi --transport mqtt --broker "$BROKER_HOST" --mqtt-port "$MQTT_PORT" --device-id "$DEVICE_ID" --cmd-topic "$CMD_TOPIC" --resp-topic "$RESP_TOPIC"; do
  sleep 3
done
./mmwk_cli.sh radar status --transport mqtt --broker "$BROKER_HOST" --mqtt-port "$MQTT_PORT" --device-id "$DEVICE_ID" --cmd-topic "$CMD_TOPIC" --resp-topic "$RESP_TOPIC"
./mmwk_cli.sh radar version --transport mqtt --broker "$BROKER_HOST" --mqtt-port "$MQTT_PORT" --device-id "$DEVICE_ID" --cmd-topic "$CMD_TOPIC" --resp-topic "$RESP_TOPIC"
./mmwk_cli.sh collect --duration 12 \
  --broker "$BROKER_URI" \
  --device-id "$DEVICE_ID" \
  --data-topic "$RAW_DATA_TOPIC" \
  --resp-topic "$RAW_RESP_TOPIC" \
  --resp-optional \
  --data-output ./data_resp.sraw \
  --resp-output ./cmd_resp.log
```

Interpret this sequence as follows:

- The first UART `device hi` confirms you are on bridge and snapshots the current MQTT identity fields into `./bridge_hi.json`.
- The exported MQTT variables let the rest of the runtime chain stay on MQTT, which matches the current PRO validation better than reopening UART for every step.
- `radar status` remains the decisive runtime-state check. A non-empty `radar version` is helpful evidence, but an empty string is not a failure by itself.
- Because this sequence already attaches after the radar is running, the final `collect --resp-optional` is a late-attach MQTT observation window, not a startup capture.
- `collect --resp-optional` is the final host-side proof that bridge raw forwarding still produces `raw_data`, while still saving `cmd_resp.log` if fresh startup-trimmed command-port output appears during this window.
- If you need fresh startup/welcome proof, do not relax this step: start capture at the beginning of the boot/OTA window and require non-empty `raw_resp`.
- Use the `radar flash`, `radar ota`, and `radar reconf` sections above only when you intentionally want to change firmware, metadata expectations, or runtime contract. After any such advanced step, return to the runtime-verification chain here.

For the full validated bring-up walkthrough, return to [MMWK Bridge Mode](./bridge.md) and continue into [Local `server.sh` + `mmwk_cli.sh` Wi-Fi Flash and 5-Minute Collection Example](./collect.md).
