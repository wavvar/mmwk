# MMWK Desktop GUI Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a zero-Python cross-platform desktop GUI in `gui/` for bridge and hub MMWK devices, including native protocol control, embedded local services, multi-device collection, hub event recording/playback, and optional video views.

**Architecture:** Use a Tauri v2 app with a TypeScript frontend and Rust backend. Rust owns CLIv1 protocol, serial/MQTT transport, embedded MMWK-only MQTT/HTTP services, SQLite persistence, collection, event logs, and artifact manifests. The frontend calls Rust through Tauri commands and receives long-running operation updates through Tauri events.

**Tech Stack:** Tauri v2, Rust, Tokio, serde/serde_json, thiserror, serialport, rumqttc/rumqttd or a scoped broker implementation, axum/tower-http, rusqlite, keyring, TypeScript, Vite, React, Vitest, Testing Library.

---

## Scope Check

The approved design is broad. Implement it in executable slices. Do not attempt all device functions in one commit. The first working milestone must launch the app, load coverage contracts, manage local profiles, and expose a mocked device console. Later chunks add native transports, servers, bridge/hub command models, collection, event recording, and video.

Reference spec: `gui/docs/superpowers/specs/2026-05-11-mmwk-desktop-gui-design.md`.

## File Structure

Create these top-level paths under `gui/`:

- `gui/package.json`: frontend scripts and dependencies.
- `gui/vite.config.ts`: Vite configuration.
- `gui/index.html`: app shell entry.
- `gui/src/main.tsx`: React entrypoint.
- `gui/src/App.tsx`: top-level layout and route selection.
- `gui/src/app/`: layout, navigation, app state, Tauri client wrappers.
- `gui/src/devices/`: device list, profile forms, capability badges, device console.
- `gui/src/servers/`: embedded server profile and status views.
- `gui/src/radar/`: radar firmware/raw/diag controls.
- `gui/src/collection/`: live collection and artifacts UI.
- `gui/src/hub/`: scene, sidecar, hub event live/playback UI.
- `gui/src/video/`: optional video configuration and placeholder panel.
- `gui/src-tauri/Cargo.toml`: Rust dependencies.
- `gui/src-tauri/tauri.conf.json`: Tauri app config.
- `gui/src-tauri/src/main.rs`: app bootstrap.
- `gui/src-tauri/src/lib.rs`: module exports and command registration.
- `gui/src-tauri/src/error.rs`: shared backend error/envelope types.
- `gui/src-tauri/src/contracts/`: coverage/capability contract loading.
- `gui/src-tauri/src/protocol/`: CLIv1 schema, request/response, command model, topic derivation.
- `gui/src-tauri/src/store/`: SQLite schema and repositories.
- `gui/src-tauri/src/transport/`: serial and MQTT client transports.
- `gui/src-tauri/src/services/`: local MQTT/HTTP server lifecycle.
- `gui/src-tauri/src/commands/`: Tauri command handlers.
- `gui/src-tauri/src/collection/`: raw collection and artifact manifests.
- `gui/src-tauri/src/hub_events/`: hub event decoder, recorder, playback.
- `gui/src-tauri/src/video/`: video configuration model and capture facade.
- `gui/contracts/`: copied contract JSON files used by GUI tests and command-model coverage checks.
- `gui/tests/`: frontend/integration test helpers.

## Chunk 1: Scaffold And Contract Guard

### Task 1: Create Tauri/Vite Skeleton

**Files:**
- Create: `gui/package.json`
- Create: `gui/vite.config.ts`
- Create: `gui/tsconfig.json`
- Create: `gui/index.html`
- Create: `gui/src/main.tsx`
- Create: `gui/src/App.tsx`
- Create: `gui/src-tauri/Cargo.toml`
- Create: `gui/src-tauri/build.rs`
- Create: `gui/src-tauri/tauri.conf.json`
- Create: `gui/src-tauri/src/main.rs`
- Create: `gui/src-tauri/src/lib.rs`

- [ ] **Step 1: Write minimal frontend smoke test**

Create `gui/src/App.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
  it("renders the MMWK desktop shell", () => {
    render(<App />);
    expect(screen.getByText("MMWK Desktop")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Add frontend skeleton**

Use React + Vite with scripts:

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "test": "vitest run",
    "tauri": "tauri"
  }
}
```

- [ ] **Step 3: Run frontend tests**

Run: `cd gui && npm test`
Expected: PASS for `App.test.tsx`.

- [ ] **Step 4: Add Rust Tauri skeleton**

`gui/src-tauri/src/lib.rs` should expose `run()` and register no-op commands initially:

```rust
pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("failed to run MMWK GUI");
}
```

- [ ] **Step 5: Verify Rust build**

Run: `cd gui/src-tauri && cargo test`
Expected: build succeeds with zero tests or simple smoke test.

- [ ] **Step 6: Commit**

```bash
git add gui
git commit -m "feat(gui): scaffold tauri desktop app"
```

### Task 2: Add No-Python Guard

**Files:**
- Create: `gui/scripts/check-no-python.mjs`
- Modify: `gui/package.json`

- [ ] **Step 1: Write failing guard test**

Create a Node script that scans `gui/` for forbidden runtime references:

```js
const forbidden = [/python/i, /\.\.\/mmwk\/cli/, /run\.sh/, /run\.ps1/];
```

Ignore docs and this guard script itself. Fail if production source files reference Python or CLI wrappers.

- [ ] **Step 2: Wire script**

Add `"check:no-python": "node scripts/check-no-python.mjs"` to `gui/package.json`.

- [ ] **Step 3: Run guard**

Run: `cd gui && npm run check:no-python`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add gui/package.json gui/scripts/check-no-python.mjs
git commit -m "test(gui): guard against python cli runtime dependency"
```

### Task 3: Copy And Load Coverage Contracts

**Files:**
- Create: `gui/contracts/protocol_coverage.bridge.json`
- Create: `gui/contracts/protocol_coverage.hub.json`
- Create: `gui/contracts/capability_matrix.json`
- Create: `gui/src-tauri/src/contracts/mod.rs`
- Create: `gui/src-tauri/src/contracts/model.rs`
- Create: `gui/src-tauri/src/contracts/tests.rs`

- [ ] **Step 1: Copy contract JSON**

Copy from SDK sources:

```bash
cp ../mmwk_sdk/projects/mmwk_sensor_bridge/cli/protocol_coverage.json gui/contracts/protocol_coverage.bridge.json
cp ../mmwk_sdk/projects/mmwk_sensor_hub/tests/cli/protocol_coverage.hub.json gui/contracts/protocol_coverage.hub.json
cp ../mmwk_sdk/projects/mmwk_sensor_bridge/cli/capability_matrix.json gui/contracts/capability_matrix.json
```

- [ ] **Step 2: Write Rust tests for loading**

Test that all three files parse and expose bridge/hub entries:

```rust
#[test]
fn loads_bridge_and_hub_coverage() {
    let bridge = load_protocol_coverage("contracts/protocol_coverage.bridge.json").unwrap();
    let hub = load_protocol_coverage("contracts/protocol_coverage.hub.json").unwrap();
    assert!(bridge.entries.iter().any(|e| e.profile == "bridge" && e.service == "node"));
    assert!(hub.entries.iter().any(|e| e.profile == "hub" && e.service == "scene"));
}
```

- [ ] **Step 3: Implement loader**

Use `serde` models with optional `sidecar` and `op`.

- [ ] **Step 4: Run test**

Run: `cd gui/src-tauri && cargo test contracts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gui/contracts gui/src-tauri/src/contracts
git commit -m "feat(gui): load firmware coverage contracts"
```

## Chunk 2: Command Model And Persistence

### Task 4: Build Profile-Aware Command Registry

**Files:**
- Create: `gui/src-tauri/src/protocol/mod.rs`
- Create: `gui/src-tauri/src/protocol/commands.rs`
- Create: `gui/src-tauri/src/protocol/topics.rs`
- Create: `gui/src-tauri/src/protocol/tests.rs`
- Create: `gui/src/devices/capabilities.ts`
- Test: `gui/src/devices/capabilities.test.ts`

- [ ] **Step 1: Write Rust coverage parity test**

For every service/action/op in both protocol coverage files, assert a command descriptor exists.

- [ ] **Step 2: Implement descriptors**

Model descriptors with `profile`, `sidecar`, `service`, `action`, `op`, `destructive`, `restore`, `transports`, and `ui_group`.

- [ ] **Step 3: Add topic derivation tests**

Cover DID fallback, CID precedence, case preservation for claimed route, `raw_cmd` gating, hub inquiry/config, and stream topics.

- [ ] **Step 4: Implement topic derivation**

Return canonical `cmd`, `resp`, `raw_data`, `raw_resp`, `raw_cmd`, `hub_inquiry`, `hub_config`, `stream_in`, and `stream_ack` fields.

- [ ] **Step 5: Run tests**

Run: `cd gui/src-tauri && cargo test protocol`
Expected: PASS.

- [ ] **Step 6: Add frontend gating tests**

Test that bridge hides `scene`, hub shows `scene`, care shows RFCare, and rmaker shows RainMaker extension only.

- [ ] **Step 7: Commit**

```bash
git add gui/src-tauri/src/protocol gui/src/devices
git commit -m "feat(gui): add profile-aware command registry"
```

### Task 5: Add SQLite Store

**Files:**
- Create: `gui/src-tauri/src/store/mod.rs`
- Create: `gui/src-tauri/src/store/schema.rs`
- Create: `gui/src-tauri/src/store/device_profiles.rs`
- Create: `gui/src-tauri/src/store/server_profiles.rs`
- Create: `gui/src-tauri/src/store/runs.rs`
- Create: `gui/src-tauri/src/store/tests.rs`

- [ ] **Step 1: Write repository tests**

Use an in-memory SQLite DB. Cover create/read/update device profile, reusable server profile, and run manifest stub.

- [ ] **Step 2: Implement schema**

Tables: `device_profiles`, `server_profiles`, `artifact_runs`, `run_artifacts`, `command_audit`, `hub_event_runs`, `hub_event_log`, `video_configs`.

- [ ] **Step 3: Implement repositories**

Keep one file per aggregate. Do not let UI command handlers write SQL directly.

- [ ] **Step 4: Run tests**

Run: `cd gui/src-tauri && cargo test store`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gui/src-tauri/src/store
git commit -m "feat(gui): add local profile and run store"
```

## Chunk 3: Backend Commands And Core UI

### Task 6: Expose Profile/Server Tauri Commands

**Files:**
- Create: `gui/src-tauri/src/commands/mod.rs`
- Create: `gui/src-tauri/src/commands/profiles.rs`
- Create: `gui/src-tauri/src/error.rs`
- Modify: `gui/src-tauri/src/lib.rs`
- Create: `gui/src/app/backend.ts`
- Create: `gui/src/devices/DeviceList.tsx`
- Create: `gui/src/devices/DeviceEditor.tsx`
- Create: `gui/src/servers/ServerProfiles.tsx`

- [ ] **Step 1: Write Rust command tests**

Call command handlers directly and assert normalized success/error envelopes.

- [ ] **Step 2: Implement command handlers**

Commands: `list_device_profiles`, `save_device_profile`, `delete_device_profile`, `list_server_profiles`, `save_server_profile`, `delete_server_profile`.

- [ ] **Step 3: Write frontend tests**

Mock Tauri invoke. Verify adding a device can select an existing server profile.

- [ ] **Step 4: Implement UI**

Build dense operational screens. Avoid marketing/landing pages. First screen is the device/server workspace.

- [ ] **Step 5: Run tests**

Run:

```bash
cd gui/src-tauri && cargo test commands
cd ../ && npm test
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add gui/src-tauri/src gui/src
git commit -m "feat(gui): manage local device and server profiles"
```

### Task 7: Add Device Console Skeleton

**Files:**
- Create: `gui/src/devices/DeviceConsole.tsx`
- Create: `gui/src/devices/CommandPanel.tsx`
- Create: `gui/src/radar/RadarWorkspace.tsx`
- Create: `gui/src/hub/HubWorkspace.tsx`
- Create: `gui/src/app/navigation.ts`

- [ ] **Step 1: Write UI tests for profile-gated controls**

Assert bridge shows node/network/radar/raw/record/stream/collect groups. Assert hub shows node inquiry, scene, hub events, and sidecar controls.

- [ ] **Step 2: Implement skeleton panels**

Use command descriptors from the registry. Buttons may call mock backend operations until native transports are implemented.

- [ ] **Step 3: Run UI tests**

Run: `cd gui && npm test`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add gui/src
git commit -m "feat(gui): add profile-gated device console"
```

## Chunk 4: Native Protocol And Transports

### Task 8: Implement CLIv1 Request/Response Core

**Files:**
- Create: `gui/src-tauri/src/protocol/cliv1.rs`
- Create: `gui/src-tauri/src/protocol/envelope.rs`
- Test: `gui/src-tauri/src/protocol/tests.rs`

- [ ] **Step 1: Write golden tests**

Use fixtures for request seq, service/action/args, success response, error response, event frame, startup-prefixed JSON, and key-protected error.

- [ ] **Step 2: Implement parser and serializer**

Handle JSON line framing, startup noise trimming before JSON, response matching by sequence, events without sequence, and text fallback.

- [ ] **Step 3: Run tests**

Run: `cd gui/src-tauri && cargo test protocol::cliv1`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add gui/src-tauri/src/protocol
git commit -m "feat(gui): implement cliv1 protocol core"
```

### Task 9: Implement Serial And MQTT Client Transports

**Files:**
- Create: `gui/src-tauri/src/transport/mod.rs`
- Create: `gui/src-tauri/src/transport/serial.rs`
- Create: `gui/src-tauri/src/transport/mqtt.rs`
- Create: `gui/src-tauri/src/transport/tests.rs`

- [ ] **Step 1: Write mock transport tests**

Test retries, timeout, cancellation, route topics, and response matching.

- [ ] **Step 2: Implement serial transport**

Use `serialport`, support port/baudrate/reset flag, read loop, write queue, timeout, and clean close.

- [ ] **Step 3: Implement MQTT client transport**

Use `rumqttc`, derive command/response topics, publish JSON requests, subscribe responses/events, support `mqtts` later if crate support is ready.

- [ ] **Step 4: Run tests**

Run: `cd gui/src-tauri && cargo test transport`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gui/src-tauri/src/transport
git commit -m "feat(gui): add native device transports"
```

### Task 10: Wire Real Device Commands

**Files:**
- Create: `gui/src-tauri/src/commands/device_control.rs`
- Modify: `gui/src-tauri/src/lib.rs`
- Modify: `gui/src/devices/CommandPanel.tsx`

- [ ] **Step 1: Write backend command tests with mock transport**

Cover `node info`, `network status`, `radar status`, destructive confirmation token required, and raw payload exposure.

- [ ] **Step 2: Implement generic `execute_device_command`**

Input: device profile ID, command descriptor ID, args JSON, transport override. Output: normalized envelope.

- [ ] **Step 3: Update UI**

Bind command buttons/forms to real backend command. Keep unsupported commands disabled.

- [ ] **Step 4: Run tests**

Run:

```bash
cd gui/src-tauri && cargo test commands::device_control
cd ../ && npm test
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gui/src-tauri/src gui/src
git commit -m "feat(gui): execute native device commands"
```

## Chunk 5: Embedded Services

### Task 11: Add Embedded HTTP Server

**Files:**
- Create: `gui/src-tauri/src/services/mod.rs`
- Create: `gui/src-tauri/src/services/http_server.rs`
- Create: `gui/src-tauri/src/commands/local_servers.rs`
- Modify: `gui/src/servers/ServerProfiles.tsx`

- [ ] **Step 1: Write HTTP tests**

Serve a temp firmware file, receive POST upload, reject path traversal, expose status.

- [ ] **Step 2: Implement HTTP server**

Use `axum`. Support serve directory, upload directory, host/port, generated base URL, and lifecycle status.

- [ ] **Step 3: Wire Tauri commands**

Commands: `start_http_server`, `stop_http_server`, `get_http_server_status`.

- [ ] **Step 4: Run tests**

Run: `cd gui/src-tauri && cargo test services::http_server`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gui/src-tauri/src/services gui/src-tauri/src/commands gui/src/servers
git commit -m "feat(gui): embed local http server"
```

### Task 12: Add MMWK-Only MQTT Broker

**Files:**
- Create: `gui/src-tauri/src/services/mqtt_broker.rs`
- Modify: `gui/src-tauri/src/commands/local_servers.rs`
- Modify: `gui/src/servers/ServerProfiles.tsx`

- [ ] **Step 1: Write broker scope tests**

Accept MMWK topics: `+/+/+/device/cmd`, `+/+/+/device/resp`, `+/+/+/raw/data`, `+/+/+/raw/resp`, `+/+/+/hub/inquiry`, `+/+/+/hub/config`, `D/+/+/+/+/event`, `D/+/+/+/+/data_rx` for care. Reject unrelated topics.

- [ ] **Step 2: Implement broker lifecycle**

Prefer a maintained broker crate if it allows topic policy hooks. If not, implement a small scoped broker sufficient for MMWK devices and GUI clients.

- [ ] **Step 3: Wire server UI**

Show bound host, port, active clients, accepted/rejected topic counts, and log snippets.

- [ ] **Step 4: Run tests**

Run: `cd gui/src-tauri && cargo test services::mqtt_broker`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gui/src-tauri/src/services gui/src/servers
git commit -m "feat(gui): embed scoped mmwk mqtt broker"
```

## Chunk 6: Collection, Record, Stream

### Task 13: Implement Raw Collection Engine

**Files:**
- Create: `gui/src-tauri/src/collection/mod.rs`
- Create: `gui/src-tauri/src/collection/raw_capture.rs`
- Create: `gui/src-tauri/src/collection/manifest.rs`
- Create: `gui/src-tauri/src/commands/collection.rs`
- Create: `gui/src/collection/CollectionBench.tsx`

- [ ] **Step 1: Write collection tests**

Simulate `raw/data` and `raw/resp` MQTT payloads. Assert `.sraw`, command log, summary, counters, optional resp behavior, and interrupted manifest.

- [ ] **Step 2: Implement capture engine**

Support multi-device subscribe, strict startup-aware mode, late attach, device reboot trigger, radar restart trigger, and artifact writes.

- [ ] **Step 3: Wire UI**

Show live bytes/messages/rates per device, raw command text preview, start/stop controls, and output paths.

- [ ] **Step 4: Run tests**

Run:

```bash
cd gui/src-tauri && cargo test collection
cd ../ && npm test
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gui/src-tauri/src/collection gui/src-tauri/src/commands gui/src/collection
git commit -m "feat(gui): record multi-device raw collection"
```

### Task 14: Implement Record And Stream Surfaces

**Files:**
- Create: `gui/src-tauri/src/collection/record_upload.rs`
- Create: `gui/src-tauri/src/protocol/stream.rs`
- Modify: `gui/src/radar/RadarWorkspace.tsx`
- Modify: `gui/src/collection/CollectionBench.tsx`

- [ ] **Step 1: Write tests**

Cover `record` start/trigger/stop upload receiver, stream open/status/abort/close, stream frame metadata, and audit records.

- [ ] **Step 2: Implement record upload receiver**

Use HTTP upload path from the embedded server or a run-specific receiver.

- [ ] **Step 3: Implement stream helpers**

Support MQTT binary stream OTA/data-plane frame handling and status tracking.

- [ ] **Step 4: Run tests**

Run: `cd gui/src-tauri && cargo test collection protocol::stream`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gui/src-tauri/src gui/src
git commit -m "feat(gui): add record and stream operations"
```

## Chunk 7: Hub Events And Sidecars

### Task 15: Implement Durable Hub Event Recording

**Files:**
- Create: `gui/src-tauri/src/hub_events/mod.rs`
- Create: `gui/src-tauri/src/hub_events/decoder.rs`
- Create: `gui/src-tauri/src/hub_events/recorder.rs`
- Create: `gui/src-tauri/src/hub_events/playback.rs`
- Create: `gui/src-tauri/src/commands/hub_events.rs`
- Create: `gui/src/hub/HubEventsPanel.tsx`
- Create: `gui/src/hub/HubEventPlayback.tsx`

- [ ] **Step 1: Write decoder tests**

Use RFCare fixture payloads for people location, breath/heart, hot place, stats, gesture, stay-too-long, in/out region, fall/pre-fall, heartbeat, room/scene responses, and unknown payloads.

- [ ] **Step 2: Write recorder tests**

Append events, preserve raw payload, persist decoded fields, reload log, recompute counters, filter by type/topic/device/time.

- [ ] **Step 3: Implement decoder and recorder**

Store raw payload exactly. Decoding failures produce `decode_status=unknown` or `decode_status=error`.

- [ ] **Step 4: Wire live UI**

Show live feed, counters, pause/resume/stop, raw payload drawer, decoded table/JSON view.

- [ ] **Step 5: Wire playback UI**

Load event logs later, filter, recompute counters, export.

- [ ] **Step 6: Run tests**

Run:

```bash
cd gui/src-tauri && cargo test hub_events
cd ../ && npm test
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add gui/src-tauri/src/hub_events gui/src-tauri/src/commands gui/src/hub
git commit -m "feat(gui): record and replay hub events"
```

### Task 16: Implement Hub Scene And Sidecar UI

**Files:**
- Create: `gui/src/hub/HubScenePanel.tsx`
- Create: `gui/src/hub/RfcareWorkspace.tsx`
- Create: `gui/src/hub/RmakerPanel.tsx`
- Modify: `gui/src/devices/DeviceConsole.tsx`
- Modify: `gui/src-tauri/src/protocol/commands.rs`

- [ ] **Step 1: Write UI tests**

Assert `scene` and `node inquiry` appear for hub. Assert care controls appear only for care. Assert rmaker controls appear only for rmaker.

- [ ] **Step 2: Implement scene controls**

Actions: scene read, set, apply, wait; show revision/state and destructive confirmation for set/apply.

- [ ] **Step 3: Implement RFCare controls**

Expose platform handshake/inquiry, transfer enable/disable, room/scene get/set payloads, and event counters.

- [ ] **Step 4: Implement RainMaker panel**

Show extension visibility/claim status and keep controls separate from RFCare.

- [ ] **Step 5: Run tests**

Run: `cd gui && npm test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add gui/src/hub gui/src/devices gui/src-tauri/src/protocol
git commit -m "feat(gui): add hub scene and sidecar controls"
```

## Chunk 8: Video And Artifacts

### Task 17: Add Optional Video Configuration And View

**Files:**
- Create: `gui/src-tauri/src/video/mod.rs`
- Create: `gui/src-tauri/src/video/config.rs`
- Create: `gui/src-tauri/src/video/capture.rs`
- Create: `gui/src/video/VideoConfigPanel.tsx`
- Create: `gui/src/video/VideoView.tsx`
- Modify: `gui/src/collection/CollectionBench.tsx`

- [ ] **Step 1: Write config tests**

Cover absent config hides video UI; present local camera/RTSP/HTTP/file config shows video UI; invalid config returns validation error.

- [ ] **Step 2: Implement video config model**

Do not block radar collection if optional video fails. Support `required_for_run` flag for users who require synchronized video.

- [ ] **Step 3: Implement capture facade**

Start with source metadata and placeholder capture lifecycle. Add actual platform capture only after crate feasibility is verified on Windows, macOS, and Linux.

- [ ] **Step 4: Wire UI**

Show video view only when configured. Link video artifacts and sync markers into run manifest.

- [ ] **Step 5: Run tests**

Run:

```bash
cd gui/src-tauri && cargo test video
cd ../ && npm test
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add gui/src-tauri/src/video gui/src/video gui/src/collection
git commit -m "feat(gui): add optional video recording view"
```

### Task 18: Add Artifact Browser

**Files:**
- Create: `gui/src/collection/ArtifactsBrowser.tsx`
- Create: `gui/src-tauri/src/commands/artifacts.rs`
- Modify: `gui/src-tauri/src/store/runs.rs`

- [ ] **Step 1: Write tests**

Create sample run with raw data, command log, hub event log, video artifact, and upload file. Assert list/detail/filter/export behavior.

- [ ] **Step 2: Implement backend artifact queries**

Return run list, artifact list, event counts, counters, paths, sizes, and export metadata.

- [ ] **Step 3: Implement UI**

Browse by device, run, date, artifact type, event type, and error/interrupted status.

- [ ] **Step 4: Run tests**

Run:

```bash
cd gui/src-tauri && cargo test commands::artifacts
cd ../ && npm test
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gui/src-tauri/src gui/src/collection
git commit -m "feat(gui): browse recorded artifacts and runs"
```

## Chunk 9: Packaging, Docs, Final Parity

### Task 19: Add Full Contract Parity Test

**Files:**
- Create: `gui/src-tauri/tests/coverage_parity.rs`
- Create: `gui/src-tauri/tests/no_python_runtime.rs`
- Modify: `gui/package.json`

- [ ] **Step 1: Write parity tests**

Load `gui/contracts/*.json`, load command registry, assert every service/action/op is modeled and has an associated backend test or explicit deferred marker.

- [ ] **Step 2: Write no-Python integration test**

Scan production files for Python/wrapper dependencies.

- [ ] **Step 3: Add top-level check script**

Add `"check": "npm run check:no-python && npm test && npm run build && cargo test --manifest-path src-tauri/Cargo.toml"` from `gui/`.

- [ ] **Step 4: Run full check**

Run: `cd gui && npm run check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gui
git commit -m "test(gui): enforce protocol coverage parity"
```

### Task 20: Add User Docs And Packaging Notes

**Files:**
- Create: `gui/README.md`
- Create: `gui/docs/development.md`
- Create: `gui/docs/manual-validation.md`
- Modify: `README.md`
- Modify: `README_CN.md` only if public package docs should mention GUI availability now.

- [ ] **Step 1: Document local development**

Include prerequisites: Rust, Node, platform build tools, no Python requirement.

- [ ] **Step 2: Document manual validation boundaries**

State that on-device proof requires flashing/using current-session firmware on mapped hardware. Include bridge/hub/sidecar coverage notes.

- [ ] **Step 3: Add packaging command notes**

Document `npm run tauri build` and target OS expectations.

- [ ] **Step 4: Run checks**

Run: `cd gui && npm run check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gui README.md README_CN.md
git commit -m "docs(gui): document desktop app development"
```

## Execution Notes

- Keep each task independently buildable and committed.
- Do not introduce Python, shell CLI wrapper calls, or `../mmwk/cli` runtime dependencies.
- Keep temporary generated files out of commits.
- Before claiming completion, run `cd gui && npm run check`.
- Do not claim hardware validation unless the GUI actually exercised the selected current-session firmware on mapped physical devices.
