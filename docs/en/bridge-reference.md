# Bridge Reference

Use this reference after the short [Bridge](./bridge.md) entry point when you need the bridge-specific command order, parameter contracts, and runtime proof checklist.

Run examples from the package root unless a section explicitly says to enter `./cli`. Replace `/dev/cu.usbserial-0001` with the real serial port on your host.

```bash
export PORT=/dev/cu.usbserial-0001
export FW=./firmwares/radar/iwr6843/vital_signs/vital_signs_tracking_6843AOP_demo.bin
export CFG=./firmwares/radar/iwr6843/vital_signs/vital_signs_AOP_2m.cfg
```

## Identity and Readiness

Start with UART for local bring-up:

```bash
./cli/run.sh node info -p "$PORT"
./cli/run.sh network status -p "$PORT"
```

`node info` identifies the ESP firmware profile and publishes route fields such as `did`, `prod`, `oid`, `cid`, `cmd`, `resp`, `raw_data`, and `raw_resp`. Use `network status` for readiness: `state=connected && ready=true` is the network-ready contract, and `mqtt_state=connected` is the MQTT-ready contract for MQTT-dependent flows.

After `radar fw flash`, `radar fw ota`, `radar config apply`, or the first boot after factory/baseline recovery, poll `radar status` until it returns `running`. Do not replace that gate with a fixed sleep.

## Raw Semantics Contract

- `raw_resp = startup-trimmed command-port output from on_cmd_data`
- `raw_data = raw data-port bytes from on_radar_data`
- `on_cmd_resp is an application-layer command response`, and it is different from raw capture.
- `on_radar_frame is an application-layer frame callback`, and it is different from raw capture.
- `cmd_resp.log` starts at the first printable ASCII byte after startup trimming.

## Radar Firmware Commands

The public CLI groups radar firmware lifecycle commands under `radar fw`.

```bash
./cli/run.sh radar fw flash --fw "$FW" --cfg "$CFG" -p "$PORT"
./cli/run.sh radar fw ota --fw "$FW" --cfg "$CFG" -p "$PORT"
./cli/run.sh radar fw version -p "$PORT"
```

Shared parameters:

| Parameter | Applies to | Meaning |
| --- | --- | --- |
| `--fw <file.bin>` | `radar fw flash`, `radar fw ota` | Radar firmware binary written to the radar chip. |
| `--cfg <file.cfg>` | `radar fw flash`, `radar fw ota` | Optional radar cfg text matched to the selected firmware. |
| `--version <str>` | `radar fw flash`, `radar fw ota` | Expected startup version substring when verification is enabled. |
| `--welcome` / `--no-welcome` | `radar fw flash`, `radar fw ota` | Whether startup output is expected. |
| `--verify` / `--no-verify` | `radar fw flash`, `radar fw ota` | Whether startup output must contain the expected version substring. |

## Managed Firmware Catalog

Use the `radar fw` catalog commands when you want to inspect or change the ESP-side radar firmware catalog instead of pushing a host-side binary at that moment.

```bash
./cli/run.sh radar fw list -p "$PORT"
./cli/run.sh radar fw set --index 0 -p "$PORT"
```

`radar fw list` marks saved defaults and the currently running entry. `radar fw set --index <n>` is a persistent default switch routed through the radar update path; it is not a metadata-only toggle.

## Runtime Configuration (`radar config apply`)

Use `radar config apply` when the radar firmware binary is already correct and you only need to change startup expectations or the runtime cfg selection without flashing firmware again.

```bash
./cli/run.sh radar config apply --welcome --no-verify -p "$PORT"
./cli/run.sh radar config apply --welcome --verify --version "1.2.3" -p "$PORT"
./cli/run.sh radar config apply --welcome --no-verify --cfg ./runtime.cfg -p "$PORT"
./cli/run.sh radar config apply --welcome --no-verify --clear-cfg -p "$PORT"
```

Contract:

- `--cfg` maps to `cfg_action=replace`, uploads only a runtime cfg, and finishes with `uart_data action=reconf_done`.
- `--clear-cfg` maps to `cfg_action=clear` and removes the persisted runtime cfg override.
- No `--cfg` flag maps to `cfg_action=keep` and preserves the current runtime cfg selection.
- `radar config apply` does not flash firmware and does not replace the radar binary.
- After any apply, wait for `radar status` to return `running` before relying on `radar fw version` or late-attach collection.

## Runtime CFG Readback (`radar cfg`)

The firmware-side action is `radar cfg`; the public CLI command is `radar config read`.

```bash
./cli/run.sh radar config read -p "$PORT"
./cli/run.sh radar config read --gen -p "$PORT"
```

Older SDK protocol notes may show `./run.sh radar cfg -p "$PORT"` for the same action. In the published CLI tree, use `radar config read`.

Contract:

- Default behavior reads the current effective file cfg text.
- The effective file cfg is the selected runtime override cfg when one is present; otherwise it is the default firmware metadata cfg.
- do not use `--gen` in the bridge reference flow; bridge rejects it explicitly because bridge has no generated cfg source.
- `--gen` requests the hub-generated cfg and is supported only on hub runtimes; it must not fall back to the file cfg.
- Missing, unreadable, empty, or otherwise unavailable cfg targets are hard errors.
- CLI prints only the cfg text to stdout, so redirecting the output preserves the raw cfg content.

## Startup Modes

Use these terms consistently:

- `mode` is the saved/configured default mode reported by radar-facing status surfaces.
- `modes` is the supported mode list for the active firmware profile.
- `fw.boot_mode` is the runtime radar boot path: `flash`, `host`, `uart`, or `spi`.
- `auto` means ESP-managed radar bring-up.
- `host` means host-controlled radar bring-up.
- `raw_auto` only controls raw-plane auto-start; it does not decide startup ownership.

```bash
./cli/run.sh radar start --mode auto -p "$PORT"
./cli/run.sh radar start --mode host -p "$PORT"
./cli/run.sh radar stop -p "$PORT"
./cli/run.sh radar status -p "$PORT"
```

In `auto` mode, the device may select firmware/cfg metadata, wait for startup output, verify version metadata, and send radar configuration. In `host` mode, the host owns radar bring-up; the device still exposes transport surfaces, and `{prod}/{oid}/{cid-or-did}/raw/cmd` is available only in host mode.

## Collection and Helper Scripts

Treat `collect` as the official command for the startup-aware bridge checklist:

```bash
./cli/run.sh collect --duration 12 \
  --data-output ./data_resp.sraw \
  --resp-output ./cmd_resp.log \
  -p "$PORT"
```

Minimum evidence:

- `cmd_resp.log` is non-empty for startup/welcome proof windows.
- `data_resp.sraw` is non-empty when the radar firmware/cfg pair is expected to emit data.
- `Resp topic frames` and `Data topic frames` count MQTT messages, not mmWave TLV frames.

The external pure-MQTT startup helper is available when you intentionally want to stay outside the main CLI startup-aware path:

```bash
./cli/config.sh set --server-local
./cli/collect.sh --trigger device-reboot
```

Use `./cli/config.sh set` when Wi-Fi/MQTT settings must be pushed first. Use `./cli/collect.sh --trigger none` only after `radar status` already reports `running`, and only with `--resp-optional` for a late-attach observation window.

## Recorder Surface

Use the public `radar raw` surface for recorder state/config and recording triggers:

```bash
./cli/run.sh radar raw status -p "$PORT"
./cli/run.sh radar raw config get -p "$PORT"
./cli/run.sh radar raw config set --json '{"auto_upload": true, "max_duration_sec": 30}' -p "$PORT"
./cli/run.sh radar raw start --uri http://192.168.1.100:8080/upload -p "$PORT"
./cli/run.sh radar raw trigger --event MANUAL --duration-s 10 -p "$PORT"
./cli/run.sh radar raw stop -p "$PORT"
```

## Runtime Verification Checklist

Use this sequence after radar firmware flash, OTA, runtime config apply, or first boot after factory/baseline recovery:

```bash
./cli/run.sh node info -p "$PORT" | tee ./bridge_info.json
./cli/run.sh network status -p "$PORT" | tee ./network_status.json
./cli/run.sh radar status -p "$PORT" | tee ./radar_status.json
./cli/run.sh radar fw version -p "$PORT" | tee ./radar_version.json
./cli/run.sh collect --duration 12 \
  --data-output ./data_resp.sraw \
  --resp-output ./cmd_resp.log \
  -p "$PORT"
```

Expected evidence:

- `node info` identifies an `mmwk_sensor_bridge` profile.
- `network status` reports `state=connected && ready=true` before MQTT-dependent flows.
- `radar status` returns `running`.
- `cmd_resp.log` starts at the first printable ASCII byte and reads as startup-trimmed command-port text.
- `data_resp.sraw` is non-empty when the selected radar firmware/cfg pair should emit data.
