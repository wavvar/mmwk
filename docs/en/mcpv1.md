# Wavvar MMWK MCP Protocol Specification V1.3

This document outlines the capabilities, behavior, and configuration interfaces of the Model Context Protocol (MCP) compatibility server exposed by the MMWK bridge/hub firmware.

The default builtin protocol is canonical CLI JSON (CLIv1). See [CLIv1.md](./CLIv1.md). Use this document when callers explicitly select `--protocol mcp`.

## Raw Semantics Contract

- `raw_resp = startup-trimmed command-port output from on_cmd_data`
- `raw_data = raw data-port bytes from on_radar_data`
- `on_cmd_resp is an application-layer command response`, and it is different from raw capture.
- `on_radar_frame is an application-layer frame callback`, and it is different from raw capture.
- `raw_resp` begins at the first printable ASCII byte after driver-side startup trim.

## Transport and Framing

- **UART**: UART0, 115200 baud, newline-delimited JSON-RPC (`\n`/`\r\n`).
- **MQTT**: JSON-RPC on configured `cmd_topic` (request) / `resp_topic` (response).

Notes:

- UART parser is line-based; send one complete JSON-RPC request per line.
- Batch JSON-RPC arrays are supported by the server core.

## JSON-RPC Methods Implemented

| Method | Implemented | Notes |
|---|---|---|
| `initialize` | Yes | Returns protocol/server info and capabilities |
| `notifications/initialized` | Yes | Notification only (no response) |
| `tools/list` | Yes | Mode-aware discovery: BRIDGE returns full list, HUB returns compatibility subset `help` |
| `tools/call` | Yes | Main command entry |
| `resources/list` | Yes | Returns static placeholder resource list |
| `resources/read` | Yes | Returns mock content (not real file streaming) |
| `ping` | Yes | Returns empty result object |

### `initialize`

Example:

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"v1.3","capabilities":{},"clientInfo":{"name":"client","version":"1.0"}}}
```

Typical response (BRIDGE example):

```json
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"v1.3","capabilities":{"tools":{},"resources":{"listChanged":false,"subscribe":false}},"serverInfo":{"name":"mmwk_sensor_bridge","version":"1.0.0"}}}
```

- `serverInfo.name` is mode-specific: `mmwk_sensor_bridge` or `mmwk_sensor_hub`.
- `serverInfo.version` comes from the published firmware build metadata for the active operating mode.
- `device hi.name` / `device hi.version` are the canonical ESP firmware identity fields and should match `serverInfo.name` / `serverInfo.version`.

Auth note:

- If firmware config sets `auth_token`, `initialize` requires token match in either `params.clientInfo.token` or `params.token`.
- On mismatch, server returns error code `-32001` (`Unauthorized`).

## `tools/call` Response Envelope

Successful `tools/call` replies are wrapped as:

```json
{
  "jsonrpc":"2.0",
  "id":<same id>,
  "result":{
    "content":[
      {"type":"text","text":"<JSON string payload>"}
    ]
  }
}
```

Important:

- `text` is a JSON **string**, not a nested JSON object.
- Payload shape varies by tool/mode/action.

## Server Notifications

Server push format:

```json
{"jsonrpc":"2.0","method":"notifications/message","params":{"level":"info","data":{...}}}
```

Emitted from runtime events (sensor/update/protocol forwarding). `params.data` may be:

- parsed JSON object, or
- raw string when payload is not valid JSON.

## Tool Availability Matrix

| Tool | Listed in `tools/list` | BRIDGE | HUB | Notes |
|---|---|---|---|---|
| `radar` | BRIDGE: Yes, HUB: No | Yes | Yes | HUB hides from discovery but remains callable by name |
| `record` | BRIDGE: Yes, HUB: No | Yes | Yes | HUB hides from discovery but remains callable by name |
| `uart_data` | BRIDGE: Yes, HUB: No | Yes | Yes | Chunk OTA streaming control; HUB hides from discovery |
| `hub` | BRIDGE: No, HUB: No | No | Yes | HUB runtime-only tool in help-only discovery mode |
| `device` | BRIDGE: Yes, HUB: No | Yes | Yes | Action behavior differs by mode; HUB hides from discovery |
| `network` | BRIDGE: Yes, HUB: No | Yes | Yes | HUB hides from discovery but remains callable by name |
| `help` | BRIDGE: Yes, HUB: Yes | Yes | Yes | Discovery anchor for HUB (`help.url`) |
| `fw` | BRIDGE: Yes, HUB: No | Yes | Yes | Advanced firmware catalog management; HUB hides from discovery |
| `catalog` | BRIDGE: Yes, HUB: No | Yes | Yes | IoT endpoint registry discovery; HUB hides from discovery |
| `entity` | BRIDGE: Yes, HUB: No | Yes | Yes | Standard entity management; HUB hides from discovery |
| `adapter` | BRIDGE: Yes, HUB: No | Yes | Yes | Standard adapter management; HUB hides from discovery |
| `scene` | BRIDGE: Yes, HUB: No | Yes | Yes | Standard scene management; HUB hides from discovery |
| `policy` | BRIDGE: Yes, HUB: No | Yes | Yes | Standard policy management; HUB hides from discovery |
| `raw_capture` | BRIDGE: Yes, HUB: No | Yes | Yes | Extended capture management; HUB hides from discovery |

## Tool Details (Runtime Behavior)

### `radar`

`action` enum in schema: `ota`, `flash`, `reconf`, `cfg`, `start`, `stop`, `status`, `switch`, `raw`, `debug`, `version`.

#### `action=ota`

Required:

- `base` (string)
- `firmware` (string)

Optional:

- `config` (string)
- `version` (string)
- `force` (boolean)
- `prog_intvl` (number)

HUB path also parses:

- `fw_topic` (string)
- `cert_url` (string)

#### `action=flash`

Required:

- `firmware_size` (number)

Optional:

- `config_size` (number)
- `chunk_size` (number)
- `prog_intvl` (number)

BRIDGE path additionally supports:

- `reboot_delay` (number, seconds after flash success)

#### `action=reconf`

Runtime-only radar contract update. This keeps the current radar firmware binary and updates startup expectations and optional runtime cfg selection without flashing firmware again.

Required:

- `welcome` (boolean)

Optional:

- `verify` (boolean)
- `version` (string, required when `verify=true`)
- `cfg_action` (`keep` | `replace` | `clear`, defaults to `keep`)
- `config_size` (number, required when `cfg_action="replace"`)
- `chunk_size` (number, optional hint for cfg chunk upload)

Contract notes:

- bridge-only runtime reconfiguration; host mode is rejected.
- `cfg_action=keep` preserves the existing persisted runtime cfg path.
- `cfg_action=replace` expects a follow-up `uart_data` config upload and `action: "reconf_done"`.
- `cfg_action=clear` removes the persisted runtime cfg override and falls back to the normal firmware/default cfg source.
- unlike `action=flash` or `action=ota`, `action=reconf` does not transfer or replace the radar firmware binary.

#### `action=cfg`

Current radar cfg readback.

Optional:

- `gen` (boolean, defaults to `false`)

Contract notes:

- without `gen` or with `gen=false`, the server returns the current effective file cfg text.
- the effective file cfg is the selected runtime override cfg when one is present; otherwise it is the default firmware metadata cfg.
- `gen=true` requests the hub-generated cfg only.
- BRIDGE rejects `gen=true`; it never falls back to the file cfg.
- success payload is `{ "cfg": "...full radar cfg text..." }`.
- missing, unreadable, empty, or otherwise unavailable cfg targets are hard errors.

#### `action=start`

Optional:

- `mode: "auto" | "host"`

Start contract:

- without `mode`, the service uses the saved `start_mode`.
- with `mode`, the service persists the new default startup policy and then starts or restarts the current radar service in that mode.
- BRIDGE accepts `auto` and `host`.
- HUB supports only `auto` and rejects `host`.
- `raw_auto` is independent of startup ownership. It only controls raw-plane auto-start.

#### `action=stop`

- no extra args
- stops the current radar service without rewriting the persisted `start_mode`.

#### `action=status`

No extra arguments. This is a query-only surface; callers must use `action=start` or `action=stop` to change runtime state.

When queried, implementations return at least:

- `state`: `running` | `stopped` | `starting` | `updating` | `error`
- `start_mode`: saved/configured default mode
- `supported_start_modes`: startup modes supported by the active profile
- `details` (optional): structured startup/run failure details, present when `state=error`
  - `kind`
  - `stage`
  - `message`
  - `error_code`
  - `error_name`
  - `expected_welcome`
  - `expected_version`

Compatibility rule:

- Here "startup CLI/welcome output" means any non-empty startup text from the radar. It may span multiple lines and must not be treated as a fixed banner template.
- If `welcome=true` and no startup CLI/welcome output arrives before timeout, implementations should keep `state=error` and report `details.kind = startup_failed`.
- BRIDGE reports `supported_start_modes: ["auto", "host"]`.
- HUB reports `supported_start_modes: ["auto"]`.

#### `action=switch`

Required:

- `index` (number)

Optional:

- `persist` (boolean, defaults to `false`)

Contract notes:

- `persist=true` requests a persistent default-firmware change.
- `persist=true` uses the UART update/flash path; on success the selected catalog entry becomes the new default firmware.
- `persist=false` requests a runtime-only switch.
- when `persist=false` targets the current default entry, the service resolves to the normal default-flash boot path.
- when `persist=false` targets a non-default entry, the service resolves to the temporary SPI boot path only if the active profile reports `fw.switch.temp=true`.
- if the target already matches the current running firmware and `persist=false`, the service returns success with `changed=false` and does nothing.
- if the target already matches the current running firmware but the caller still sets `persist=true`, the service still follows the persistent-default contract unless the target is already both the default and the running entry.
- current profile gates are reported through `device hi.fw.switch` and `mgmt.radar_runtime.fw.switch`.
- BRIDGE-family runtimes currently report `fw.switch.persist=true` and `fw.switch.temp=false`.
- HUB-family runtimes currently report `fw.switch.persist=false` and `fw.switch.temp=false`.
- because current shipped profiles report `fw.switch.temp=false`, do not assume runtime-only SPI switching is available yet. This is especially important for xWRL6432-family temporary boot, which remains unvalidated.
- success payload includes `action`, `index`, `persist`, and `changed`.

#### `action=version`

- Implemented in BRIDGE path.
- Implemented in HUB path as well.

#### `action=raw`

Set mode (when `enabled` exists):

- `enabled` (boolean)
- `uri` (string, optional; if omitted or same as device `mqtt_uri`, reuses shared MQTT client)

Raw topics are fixed in both BRIDGE and HUB:
- runtime always derives `mmwk/{mac}/raw/data` and `mmwk/{mac}/raw/resp`
- in host mode runtime additionally derives `mmwk/{mac}/raw/cmd`
- bridge/auto mode keeps the MQTT raw plane output-only, so `raw_cmd_topic` is empty there
- explicit `data_topic` / `resp_topic` / `cmd_topic` requests with `enabled=true` are rejected

Wire-level meaning of these topics:
- `data_topic` carries raw bytes mirrored from the radar DATA UART path (`data_resp`, typically collected as `data_resp.sraw`).
- `resp_topic` carries startup-trimmed command-port output from `on_cmd_data` (`cmd_resp.log` starts at the first printable ASCII byte).
- `on_cmd_resp` and `on_radar_frame` are application-layer callbacks and must stay separate from raw topic capture.
- `cmd_topic` is an optional radar CMD UART passthrough ingress available only in host mode. It is distinct from the MCP interaction topic `mmwk/{mac}/device/cmd`.

BRIDGE-only extension:

- `uart_enabled` (boolean): forward `RADAR_SVC_EVT_SENSOR_DATA` notifications to UART transport.

Get mode (when `enabled` is absent):

- returns current raw config (at least `enabled`; implementations may include `uri/topics`).

#### `action=debug`

Unified debug surface for runtime diagnostics.

Sub-operations (`op`):

- `set`: requires `packets` (bool) and `frames` (bool), updates debug switches.
- `get`: returns current debug switches.
- `snapshot` (default): returns data-path counters.
  - always includes `raw_bytes_in`, `record_bytes_in`
  - includes packet/frame counters only when corresponding debug switch is enabled
- `reset`: clears diagnostic counters to zero.

Persistence:

- Debug switches are runtime-only (non-persistent). Device reboot restores defaults.

### `fw`

#### `action=info`

- no extra args

#### `action=list`

- no extra args
- returns a JSON array of catalog entries.
- each entry includes `index`, `name`, `version`, `config_name`, `source`, `path`, `size`, `default`, and `running`.
- `default=true` marks the current persistent default firmware entry.
- `running=true` marks the current managed runtime entry when the active radar session came from the ESP firmware catalog.

#### `action=set`

- `index` (number) required
- persistent default-firmware update alias.
- equivalent to `radar action=switch` with `persist=true`.
- if the requested index is already both the current default and the current running catalog entry, the service returns success with `changed=false`.
- otherwise the service uses the UART update/flash path and the selected index becomes the new default entry on success.
- success payload includes `action`, `index`, `persist`, and `changed`.

#### `action=del`

- `index` (number) required
- the current running entry cannot be deleted.
- default/factory protection still comes from the firmware manager; callers should not assume arbitrary catalog entries are deletable.

#### `action=download`

- `source` (string)
- `name` (string)
- `version` (string)
- `size` (number)

### `record`

#### `action=start`

- `uri` (string): upload target.

Implementation note:

- BRIDGE dispatch layer may pass empty URI string through.
- Recorder runtime requires a usable HTTP URL for successful uploads.

#### `action=stop`

- no extra args

#### `action=trigger`

Optional:

- `event` (string)
- `duration_sec` (number, default `10`)

Mode nuance:

- HUB path defaults missing event to `"MANUAL"`.
- BRIDGE path leaves event empty if omitted.

### `hub` (HUB firmware only)

Schema requires:

- `sensor` in `fall|presence|vs|tracker|zone|gate|hotplace`

Typical optional fields:

- `sensitivity`, `empty_delay_ms`
- `zid`, `gid`, `boundary`

If BRIDGE firmware receives `hub` tool call, it returns "Unknown tool".

### `device`

Schema actions:

- BRIDGE: `agent`, `heartbeat`, `hi`, `reboot`
- HUB: `agent`, `heartbeat`, `hi`

Legacy removal:

- `action=startup` is removed from the schema. Use `radar action=start` with optional `mode`. Servers reject `device startup`.

#### `action=hi`

- returns device identity/status payload.
- canonical ESP firmware identity fields are `name` and `version`.
- `esp_fw` and `esp_fw_version` are not returned; use `name` / `version` instead.
- startup ownership is exposed on radar-facing surfaces instead: `radar status` and `mgmt.radar_runtime` return `start_mode` and `supported_start_modes`.
- BRIDGE runtime includes extended fields for zero-config collection:
  - `radar_fw`, `radar_fw_version`, `radar_cfg`
  - `fw.default`, `fw.running`, `fw.switch`, `fw.boot_mode`
  - `mqtt_uri`, `client_id`, `cmd_topic`, `resp_topic`
  - `mqtt_en`, `uart_en`, `raw_auto`
  - `raw_data_topic`, `raw_resp_topic`
  - `raw_cmd_topic` when the current bridge runtime boot mode is `host`
- `fw.default` and `fw.running` are objects with `source`, `index`, `name`, `version`, and `config`.
- `fw.default` is the saved persistent default entry; `fw.running` is the live runtime entry for the current session.
- `fw.switch` contains the profile-gated switch capability flags `persist` and `temp`.
- `fw.boot_mode` reports the current radar boot path: `flash`, `uart`, `spi`, or `host`.
- legacy aliases `radar_fw`, `radar_fw_version`, and `radar_cfg` remain mapped to `fw.running`.

Profile capability contract:

- BRIDGE radar-facing status surfaces report `supported_start_modes: ["auto", "host"]`.
- HUB radar-facing status surfaces report `supported_start_modes: ["auto"]`.
- BRIDGE currently reports `fw.switch.persist=true` and `fw.switch.temp=false`.
- HUB currently reports `fw.switch.persist=false` and `fw.switch.temp=false`.

#### `action=heartbeat`

- `interval` (number)
- `fields` (array of strings, schema-declared)

Mode nuance:

- Both BRIDGE and HUB support `fields` array conversion.

#### `action=agent`

- Handled by `app_config_process_agent_cmd()` (both BRIDGE and HUB).
- Supports read/write of `mqtt_en`, `uart_en`, `raw_auto` via NVS.
- When the NVS keys are missing, BRIDGE defaults are `mqtt_en=1` and `raw_auto=1`.
- When the NVS keys are missing, HUB defaults are `mqtt_en=0` and `raw_auto=1`.
- These are read-time fallbacks only; runtime does not auto-write the derived defaults back into NVS on first boot.
- When no write fields are provided, returns current agent config values.

#### `action=reboot`

- Supported in BRIDGE runtime handler.
- Declared in BRIDGE `tools/list` schema.
- Not available in HUB profile.

### `network`

Schema actions: `config`, `prov`, `ntp`, `mqtt`, `status`, `diag`.

#### `action=config`

- `ssid`, `password`

#### `action=prov`

- `enable` (`1` start provisioning, `0` stop)

#### `action=mqtt`

Supports:

- `cid`
- `mqtt_uri`
- `mqtt_user`
- `mqtt_pass`
- `cmd_topic`
- `resp_topic`

#### `action=ntp`

- `server`, `tz_offset`, `interval` (schema)

Both BRIDGE and HUB apply `server`, `tz_offset`, and `interval`.

#### `action=status`

No extra arguments. Returns runtime observability fields:

- `state`: `initializing` | `connecting` | `retry_backoff` | `connected` | `prov_waiting` | `failed`
- `sta_ip`: current runtime STA IP, or `0.0.0.0` when not ready
- `ip_ready`: normalized readiness bit; only `true` when the device has a usable runtime STA IP
- `prov_wait_remaining_sec`: remaining seconds before auto STA retry (0 if inactive)
- `led_state`: current LED state keyword

Normal ready semantics are strict: callers should continue only when `state=connected` and `ip_ready=true`.

#### `action=diag`

No extra arguments. Returns diagnostic-only network runtime fields:

- `state`
- `retry_count`
- `max_retry`
- `retry_backoff_ms`
- `last_disconnect_reason_code`
- `last_disconnect_reason_name`
- `terminal_failure`
- `failure_source`: `none` | `retry_exhausted` | `manual_provisioning`

### `help`

- returns command summary + documentation URL.
- response fields:
  - `commands`
  - `mode`
  - `url` (from `CONFIG_MMWK_MCP_HELP_URL`)
  - `format` (`text/markdown`)

### `uart_data`

BRIDGE: listed in `tools/list` and callable in runtime.
HUB: not listed in `tools/list` (help-only compatibility mode), but still callable by name.

Supported forms:

1. chunk upload:
- `file` (string)
- `seq` (number)
- `data` (base64 string)

2. control:
- `action: "complete"` or `"cancel"` or `"reconf_done"`

Used for UART chunk firmware update flow, and for `action=reconf` when `cfg_action="replace"` uploads a runtime cfg file before `action: "reconf_done"`.

### `catalog`

- No extra arguments.
- Returns a list of standard endpoints such as `entities`, `adapters`, `scenes`, and `policies`.

### `entity`

Schema actions: `list`, `get`, `add`, `del`.

- `action=add`: requires `id` (string), `type` (string), optional `config` (object), `state` (object).
- `action=get` or `action=del`: requires `id` (string).
- `action=list`: optional `type` (string) to filter by.

Management entity notes:

- `mgmt.radar_runtime` exposes the current `radar_state` plus `start_mode`, `supported_start_modes`, and nested `fw.default`, `fw.running`, `fw.switch`, and `fw.boot_mode`.
- `mgmt.firmware_catalog` exposes the same top-level `fw` summary plus a `firmwares` array whose entries carry `default` and `running` flags.

### `adapter`

Schema actions: `list`, `get`, `set`, `manifest`.

- `action=set`: requires `id` (string), `config` (object).
- `action=get` or `action=manifest`: requires `id` (string).

### `scene`

Schema actions: `list`, `get`, `set`, `active`.

- `action=set`: requires `id` (string), optional `name` (string), `trigger` (object), `actions` (array).
- `action=get`: requires `id` (string).

### `policy`

Schema actions: `list`, `get`, `set`, `del`.

- `action=set`: requires `id` (string), optional `name` (string), `condition` (object), `enforcement` (object).
- `action=get` or `action=del`: requires `id` (string).

### `raw_capture`

Schema actions: `start`, `stop`, `trigger`.

- Semantics similar to `record`, tailored for raw capture streams. Supported dynamically when bridging features apply.

### Resources API (Current State)

#### `resources/list`

Returns a static placeholder resource:

- `file://sdcard/logs/latest.log`

#### `resources/read`

Returns mocked tail content string, not true file chunk streaming yet.

## Sensor Event Payloads (HUB mode)

When HUB sensors are active, `notifications/message` data commonly includes:

- `presence`: `occupied`, `motion`, `seconds`, `ts`
- `fall`: `num_falls`, `falls[]`
- `vs`: `num`, `targets[]`
- `tracker`: `num`, `targets[]`
- `zone`: `zid`, `occupied`, `count`, `seconds`
- `gate`: `gid`, `event`, `tid`
- `hotplace`: `period`, `x`, `y`

## Mode-Aware Contract (Unified)

Current schema and runtime behavior are aligned with these rules:

- Tool discovery is mode-aware:
  - BRIDGE tools: `radar`, `record`, `uart_data`, `fw`, `device`, `network`, `help`
  - HUB `tools/list`: compatibility subset only `help` (other tools remain callable by name)
- HUB help reference URL defaults to the published raw URL for this `docs/en/mcpv1.md` document.
- HUB minimal callable tools (smoke baseline): `radar status`, `device hi`, `network status`.
- `device.mqtt` is removed. MQTT configuration is unified under `network.mqtt`.
- `fw` is advertised in BRIDGE `tools/list` and callable in both BRIDGE and HUB.
- `device.agent` schema/runtime both support `mqtt_en`, `uart_en`, and `raw_auto`.
- `network.mqtt` schema/runtime support `mqtt_uri`, `mqtt_user`, and `mqtt_pass`; `cid`, `cmd_topic`, and `resp_topic` remain read-only derived fields in responses and reject write attempts.
- MCP MQTT transport initialization consumes stored `mqtt_user`/`mqtt_pass` credentials.
- `radar.raw` uses unified semantics in both modes:
  - runtime always derives `mmwk/{mac}/raw/data` and `mmwk/{mac}/raw/resp`
  - host mode additionally derives `mmwk/{mac}/raw/cmd`
  - topic override fields are rejected explicitly when enabling raw forwarding
- `radar.raw` is configuration-only; diagnostics are exposed under `radar.debug`.
- `radar.debug` (`set/get/snapshot/reset`) is available in both BRIDGE and HUB.
- HUB `radar ota` exposes and handles `fw_topic`/`cert_url`.

Validation:

- Host integration contract checks are exercised by the bridge-mode and hub-mode acceptance suites that validate this protocol.
