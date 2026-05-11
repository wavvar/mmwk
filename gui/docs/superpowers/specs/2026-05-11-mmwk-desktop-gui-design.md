# MMWK Desktop GUI Design

Date: 2026-05-11
Target package: `../mmwk/gui`
Status: Approved design

## Goal

Build a local, cross-platform desktop GUI for MMWK device operation. The GUI must cover the public CLI behavior and the bridge/hub firmware functions represented in the SDK test coverage, without using Python or shelling out to `../mmwk/cli`.

Primary requirements:

- Manage multiple device connection profiles.
- Reuse server profiles when adding devices.
- Provide fully embedded local MQTT and HTTP services for MMWK devices.
- Collect data across devices.
- Provide a dedicated interface for managing and controlling one device.
- Run on Windows, macOS, and Linux.
- Avoid Python entirely.
- Support bridge and hub firmware profiles, including hub sidecars and event recording.

## Architecture

Use Tauri v2 with a Rust backend and a TypeScript frontend.

The frontend owns device lists, server profiles, live collection views, event playback, per-device control forms, logs, charts, and artifact browsing. The Rust backend owns all native services: CLIv1 protocol handling, serial transport, MQTT transport, embedded MQTT broker, HTTP file/upload server, stream OTA, raw collection, event recording, artifact manifests, and local persistence.

The existing `../mmwk/cli` remains a behavioral reference, not a runtime dependency. The GUI must not call the Python CLI or require a Python environment.

Local persistence uses SQLite for profiles, runs, command history, and indexes. Secrets such as CLI keys and broker credentials should use the OS keychain where practical, with masked fallback storage only when necessary.

## Capability Model

The GUI must be profile-driven. Available controls are derived from:

- `projects/mmwk_sensor_bridge/cli/protocol_coverage.json`
- `projects/mmwk_sensor_hub/tests/cli/protocol_coverage.hub.json`
- `projects/mmwk_sensor_bridge/cli/capability_matrix.json`

Supported profile axes:

- Bridge boards: `mini`, `pro`, `wdr`, `rpi`, `cfh`, `iot`
- Hub boards: `pro`, `wdr`
- Hub sidecars: `cli`, `care`, `rmaker`

The capability layer gates UI controls by profile, board, sidecar, transport, and discovered protocol/endpoint manifests. Unsupported actions must not appear as normal clickable controls.

## GUI Workspaces

### Devices

Manage saved devices with name, board, profile, sidecar, DID, prod/oid/cid, UART port, baudrate, MQTT route, auth key reference, preferred server profile, and notes. Device creation can use serial `node info`, mDNS-style discovery, or manual entry.

### Local Servers

Manage embedded MMWK-only MQTT and HTTP services. Server profiles store host IP, broker URI, HTTP base URL, ports, serve directory, upload directory, and runtime status. Devices can reuse these profiles during onboarding and collection.

The MQTT broker is scoped to MMWK device topics. It is not intended to be a general-purpose broker for unrelated clients.

### Device Console

Dedicated per-device management surface for common control operations:

- `node`: info, agent, heartbeat, OTA, claim, key status/set/clear, factory reset, and reboot where the profile supports it.
- `network`: Wi-Fi, MQTT, 4G, priority, provisioning, NTP, status, diagnostics.
- `endpoint`: list, describe, read, config get/set.
- `proto`: list, status, manifest.

The console should show raw JSON/text details on demand while defaulting to concise status, progress, and next-step guidance.

### Radar

Radar lifecycle and maintenance surface:

- `radar`: status, start, stop.
- `radar.config`: read, apply.
- `radar.fw`: version, flash, OTA, list, set, switch, delete, download.
- `radar.raw`: status, config get/set, start, stop, trigger.
- `radar.diag`: debug set/get/snapshot/reset and calibration get/set/clear.

Firmware/config operations must preserve metadata semantics such as welcome, verify, expected version, transport, and restore notes.

### Live Recording & Collection

Collect raw radar data across devices. Sessions support strict startup-aware collection, late attach, MQTT-only trigger modes, device reboot trigger, radar restart trigger, live counters, raw command text, data rates, and persisted artifacts.

Optional video support is controlled by local `video_config`. If no video configuration is present, the UI remains radar-only. If video is configured, a video view appears beside the radar/raw collection view. Video sources are modeled generically as local camera, RTSP/HTTP stream, or file/mock source. Video artifacts, sync markers, and errors are linked into the same run manifest as radar data.

### Hub Events

Hub devices require a first-class event interface. The GUI must record every received hub event, not only display live counters.

The hub event panel supports:

- Live event feed with timestamp, source topic, decoded event type, decoded fields, and raw payload access.
- Counters per device and event family.
- Pause/resume/stop of event recording.
- Standalone event recording without raw radar collection.
- Event recording linked to live collection/video runs when active.
- Timeline playback, filtering by event type/topic/device/time, decoded table/JSON view, raw payload view, counter recomputation, and export.

Recorded event entries store device ID, profile, sidecar, source topic, raw payload bytes/text, decoded event type, decoded fields, timestamp received, decode status, and run linkage. Unknown or undecodable events are preserved exactly so future decoders can reinterpret them.

### Hub Scene And Sidecars

Hub profile controls add:

- `node inquiry`.
- `scene`: read, set, apply, wait.
- Hub endpoints such as `mgmt.scene`, `occupancy.global`, and supported sensor endpoints.

For `sidecar=care`, include an RFCare workspace:

- Platform downlink framing and handshake/inquiry status.
- `TRANSFER(0x21)` raw `data_rx` enable/disable.
- Device-mode topics: `D/<companyId>/0/<deviceId>/0/control`, event, and `data_rx`.
- Room/scene compatibility: getRoom/setRoom, room area, device position, regions, entries, room type.
- Live and recorded RFCare event families: people location, breath/heart, hot place, app stats, gesture, stay-too-long, in/out region, fall/pre-fall, heartbeat, room/scene responses, and raw `data_rx` transfer packets.

For `sidecar=rmaker`, show the RainMaker sidecar as a protocol extension, validate extension visibility, and expose claim/extension status without mixing it into care/RFCare controls.

### Artifacts & Runs

Browse `.sraw`, command logs, summaries, uploaded recorder payloads, event logs, video recordings, OTA served files, firmware/config pairs, and command history. Every run links to the device profile, server profile, route identity, selected transports, command parameters, counters, timestamps, and errors used at the time.

## Runtime Data Flow

The app has three layers:

1. Profiles: SQLite records for devices, server profiles, firmware/config artifacts, video config, and preferred defaults.
2. Runtime sessions: in-memory Rust tasks for serial sessions, MQTT sessions, embedded broker, HTTP server, stream OTA, raw collection, event recording, video capture, and command execution.
3. Artifacts: files under an app-managed data directory, indexed by SQLite and linked through run manifests.

Adding a device can reuse a server profile, run `node info`, derive DID/route topics, optionally claim route identity, configure Wi-Fi/MQTT, and save the resulting profile. Local server startup publishes a broker URI and HTTP base URL for reuse across devices. Collection sessions subscribe across selected devices and continue writing partial artifacts even if transport drops.

Long-running operations emit progress and structured events to the UI through Tauri events.

## Error Handling And Safety

The Rust backend normalizes command results into a single envelope: success payload, protocol error, transport error, timeout, cancellation, or validation error.

Destructive operations require confirmation and an audit record:

- Factory reset.
- Key changes.
- OTA and flash.
- Firmware delete/switch/set.
- Network overwrite.
- Scene set/apply.
- Raw config set.
- Record start/trigger.
- Stream open.
- Reboot where supported.

Audit records include command args, device, profile, transport, timestamp, result, and restore note from the coverage matrix. Firmware update cancellation must be conservative and clearly warn when interruption can leave a device mid-update.

Transport loss must not discard partial artifacts. Collection, video, and event files stay on disk with interrupted summaries. Secrets are masked in logs.

## Testing And Validation

The GUI must include native tests and coverage contract tests before claiming parity.

Test layers:

- Rust unit tests for CLIv1 framing/parsing, route topic derivation, command schema builders, retries/timeouts, MQTT packet handling, HTTP serve/upload behavior, artifact manifests, event decoding, event persistence, and video config validation.
- Rust integration tests for mock serial devices, embedded MQTT broker, embedded HTTP server, stream OTA frames, raw collection sessions, record upload receiver, interrupted runs, hub event recording, and event playback.
- Frontend tests for profile forms, capability gating, destructive confirmations, live collection state, video panel visibility, hub event panels, event playback/filtering, artifact browsing, and profile/sidecar switching.
- Coverage contract tests that load the bridge and hub protocol coverage JSON files and assert every listed service/action/op has a GUI command model and at least one test.
- Golden protocol tests for node info, endpoint/proto manifests, RFCare frames, MQTT topics, stream frames, raw collection summaries, event fixtures, and run manifests.

Hub event validation must cover:

- Event subscription setup from route identity and sidecar.
- Counter increments by decoded event type.
- Unknown event preservation.
- RFCare fixture decoding.
- Durable event logs.
- Reload/playback and filters.
- Counter recomputation from recorded logs.
- Run manifest linkage.

Manual/on-device validation may only be claimed when the current-session firmware was flashed or selected and exercised on the mapped physical device.

## Open Implementation Notes

- Choose exact Rust crates during planning, with preference for maintained crates for serial, MQTT client, embedded broker behavior, HTTP server, SQLite, OS keychain, and video capture.
- Treat the initial MQTT broker as MMWK-scoped rather than fully general-purpose.
- Keep command models generated or checked against the coverage files to avoid drift.
- Keep bridge-owned and hub-owned tests separate in the GUI test naming so future coverage changes remain traceable.
