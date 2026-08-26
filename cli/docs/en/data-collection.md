# Radar DATA collection

## Collection options

The protocol column describes the user-facing control or integration protocol.
The collected radar DATA is stored in `radar.sraw`. “All” means MINI, PRO, WDR,
and WSR.[^bridge-devices]

### Bridge collection

| Option | Devices | Protocol | Advantages | Limitations |
| --- | --- | --- | --- | --- |
| UART | All | JSON | Local; no network required | Physical connection and UART rate limit |
| USB | WDR, WSR | JSON | Local high-rate path; no network required | Limited device range |
| MQTT | All | MQTT | Remote and multi-device collection | Requires network access |
| UART + MQTT | All | JSON + MQTT | Local control and remote DATA | Requires both UART and MQTT |
| MQTT attach | All | MQTT | Does not take over existing application state | Requires an active MQTT DATA route |

[^bridge-devices]: WSR uses the PRO UART/radar behavior and the WDR-style native
Type-C USB path. WDR external UART is a lossy diagnostic path; use USB, MQTT, or
split for lossless DATA collection.

### Custom collection

| Option | Devices | Protocol | Advantages | Limitations |
| --- | --- | --- | --- | --- |
| Application MQTT DATA subscriber | All | MQTT | Fits existing systems | Application owns routing and files |
| Recorder | Devices with recorder support | JSON + HTTP | Event-oriented clips | Not a continuous real-time stream |

An application that subscribes to `raw/data` directly must manage radar
ownership, the DATA route, and files. Use Bridge `--attach` when the requirement
is only to observe an existing route. Recorder is controlled independently with
`radar record`; availability is determined by the live device response.

UART, USB, MQTT, split, and attach use the shared collection engine. POSIX users
run `./run.sh` or `./collect.sh`; Windows PowerShell users run `./run.ps1` or
`./collect.ps1` with the same core options. Recorder is independent.

### Protocol and DATA boundary

JSON over UART/USB and MQTT are control or integration protocols; `radar.sraw`
contains raw radar DATA. Tail DATA may still be present on the same physical
channel during raw/parsed transitions, so do not parse every received byte as
JSON or a text response. Use the collector to separate the streams, and judge a
run by DATA magic, valid bytes, drop/CRC evidence, and cleanup restoration.

## 1. MINI/PRO/WSR attached UART

MINI, PRO, and WSR use the same local UART collection behavior. Parsed control
starts at 115200, radar DATA is nominally 921600, and host raw UART uses at most
1000000:

```bash
./run.sh collect --transport uart --port /dev/ttyUSB0 \
  --raw-baud 1000000 --duration 30
```

On Windows, the equivalent shape is:

```powershell
.\run.ps1 collect --transport uart --port COM5 --raw-baud 1000000 --duration 30
```

Local UART collection does not configure or wait for Wi-Fi or MQTT. Before any
mutation, the collector reads `node info`, selects `did` then legacy `id` or
`client_id`, normalizes it to lowercase, and checks an optional `--did`. A
mismatch fails before outputs are opened or device state is changed.

The collector snapshots raw routing, ownership, running state, and the current
radar cfg. Pass `--cfg FILE` to use another cfg for this run. It is validated
before takeover, is not persisted, and its path appears as `config_source` in
the summary. Without `--cfg`, the source is `device:radar.config`.

When the target firmware and config are already running in host mode, use
`--mode host --attach`. This path opens only a temporary raw route and captures
the existing DATA; it does not send cfg or run sensorStart/sensorStop. Cleanup
closes the route it opened and verifies that the original host lifecycle is
still running. `--attach` cannot be combined with `--cfg` and cannot take over
an already-open local raw route.

The lifecycle commands are taken from the selected cfg, including profile
arguments such as WDR's `sensorStop 0` and `sensorStart 0 0 0 0`. WDR's
`baudRate` line is a boot-time setting and is not replayed through the runtime
collection window; replaying it would change the radar UART without changing
the bridge-side UART.

## 2. WDR/WSR attached native USB

WDR DATA is 1250000 baud, so native USB CDC is its attached lossless path. WSR
uses the same class of native Type-C USB path:

```bash
./run.sh collect --transport usb --port <native-usb-port> --duration 30
```

Native USB has no physical raw baud; do not pass `--raw-baud`. Select the board
from the live `node info` identity, not from a `/dev/tty*` name or USB descriptor.

## 3. Remote MQTT host collection

Use MQTT when the device is not directly attached:

```bash
./run.sh collect --transport mqtt \
  --broker mqtt://broker.example:1883 --did DEVICE_ID --duration 30
```

For authenticated TLS:

```bash
./run.sh collect --transport mqtt \
  --broker mqtts://broker.example:8883 --mqtt-user USER \
  --mqtt-password PASSWORD --mqtt-ca ./broker-ca.pem \
  --did DEVICE_ID --duration 30
```

Host MQTT uses `raw/cmd` QoS 1 for commands, `raw/resp` QoS 1 for responses,
and `raw/data` QoS 0 for high-rate DATA. Publishes set retain=false; retained
incoming raw payloads are ignored. There is no QoS 0 offline DATA outbox.

MQTT does not order different topics. The collector correlates responses by
protocol phase, preserves duplicated QoS 1 response bytes for audit, and never
lets a duplicate advance a phase twice. The raw service has no owner token:
multiple writers can share its FIFO, so every client must serialize its own
commands and correlate its own responses.

Limit broker ACLs to the required `raw/cmd`, `raw/resp`, and `raw/data` topics.
Broker passwords, MQTT credentials, device keys, and certificate contents are
never written to summaries or event logs.

## 4. Split wire control and MQTT DATA

Use split routing when a local UART is convenient for command/response traffic
but should not carry high-rate DATA:

```bash
./run.sh collect --ctrl-transport uart --data-transport mqtt \
  --port /dev/ttyUSB0 --broker mqtt://broker.example:1883 \
  --did DEVICE_ID --duration 30
```

The collector verifies the live wire identity against the MQTT topic identity
before mutation and subscribes to DATA before opening raw. Commands and
responses stay on wire; DATA stays off that wire and is written from MQTT.
Explicit split routing is not `channel=both`: `both` broadcasts the selected
plane to both adapters.

Raw and parsed traffic are mutually exclusive only on the same physical
channel. A second UART, native USB, or MQTT control channel can remain parsed
while another channel is raw.

## 5. Application-owned DATA and reconnect capture

Application-owned auto mode is MQTT DATA-only. The application firmware must
already own the radar and expose an active MQTT DATA route; the host command
does not create that route:

```bash
./run.sh collect --transport mqtt --mode auto --attach \
  --broker mqtt://broker.example:1883 --did DEVICE_ID --duration 30
```

`--attach` marks the route as borrowed. It does not change ownership, send cfg,
start or stop the radar, close the route, or restore state it never mutated.
If the route is absent or its ownership does not match, attach fails before
mutation. An advanced `--mode host --attach` can observe an existing host MQTT
DATA route under the same non-ownership rules.

For a one-shot capture across a device reboot, use the reconnect helper. It
subscribes first, arms `mode=reconnect`, requires the structured acknowledgement,
then reboots and waits for the arm to become a runtime route in the new device
generation:

```bash
./collect.sh --trigger device-reboot \
  --broker mqtt://broker.example:1883 --did DEVICE_ID --duration 30
```

PowerShell uses `./collect.ps1 --trigger device-reboot` with the same arguments.
The arm is consumed at most once. A second reboot cannot restart DATA unless a
new reconnect arm is acknowledged.

## 6. Outputs and success criteria

When output paths are omitted, the engine creates one identity-scoped set:

```text
collections/<did>/<UTC timestamp>/radar.sraw
collections/<did>/<UTC timestamp>/commands.log
collections/<did>/<UTC timestamp>/summary.json
collections/<did>/<UTC timestamp>/events.jsonl
```

If you set explicit outputs, pass `--data-output` and `--resp-output` together.
You may also set `--summary-output`, `--events-output`, and `--wire-output`.
Every path must be distinct. The complete set is reserved before mutation; one
collision fails the run without truncating anything. `--overwrite` writes
same-directory temporary files and atomically replaces each destination only at
finalization.

`radar.sraw` contains validated DATA beginning at radar magic
`02 01 04 03 06 05 08 07`. `commands.log` contains collection command responses.
The optional wire audit is a complete merged sequence of observed raw-transport
payloads, including outgoing commands and incoming response/DATA chunks. It has
no direction or frame delimiters, so runtime interleaving cannot be generally
demultiplexed after the fact.

A successful owned run has all of these properties:

- DATA magic was observed before the duration timer started;
- `data_bytes` is positive and `duration_s` excludes setup and cleanup;
- source/destination, CRC, queue high-water, and drop counters are reviewed when
  the firmware reports them;
- `cleanup.state_restored` is true, with config, lifecycle, route, and ownership
  restoration also reported separately.

For attach, also require `borrowed_route=true`; success means the borrowed route
remained available, not that the collector owned or restored it.

## 7. Cleanup and manual recovery

A normal owned run rejects an already-open runtime raw route instead of closing
another client's session. It also refuses to replace a running host session
unless it has a complete restorable config and lifecycle snapshot. Every
successful mutation is recorded before the next step, and cleanup reverses only
mutations owned by this run.

During a normal close, the collector keeps reading through both escape guard
windows. This drains final WDR/WSR DATA and prevents native USB backpressure
while host ingress remains silent.

The first `Ctrl-C` runs normal cleanup. If cleanup itself is interrupted, keep
the wire silent for one second, send the configured printable escape with no
newline, then keep it silent for one second and reopen parsed control at 115200.
The default escape is `+++`; `--escape` accepts 1–16 printable characters, but
the one-second guards are fixed.

If any summary item says config, lifecycle, route, ownership, parsed state, or
baud restoration failed, recover that item explicitly before starting another
session.

## 8. UART limits and evidence

- External raw UART is capped at 1000000; there is no default 2 Mbaud mode.
- MINI/PRO/WSR DATA is nominally 921600. The 1000000 setting has only an 8.5%
  adapter margin, so the warning and drop counters are mandatory acceptance
  evidence.
- WDR DATA is 1250000. External UART is refused as lossless by default; use
  native USB, MQTT, or split routing. `--allow-lossy` is diagnostic-only and
  explicitly disqualifies the result from lossless acceptance.

## 9. Local MQTT/HTTP end-to-end collection example

This section covers the complete local-development path from a fresh bridge to
a five-minute MQTT DATA capture. The host runs a local aMQTT broker and HTTP
file server through `server.sh`; both the device and host collector connect to
that broker. “Local” means that the broker runs on the development host. The
device must use an address of that host reachable from the device network, not
`mqtt://localhost:1883` in the device MQTT configuration.

Run these commands from the project root that contains both `cli/` and
`firmwares/`. On Windows PowerShell, use the corresponding `server.ps1`,
`run.ps1`, and `collect.ps1` wrappers and a Windows port such as `COM3`.

### 9.1 Example parameters

Replace these values for the local environment:

- `<artifact-dir>`: directory containing the radar firmware and cfg, for
  example `./firmwares/radar/iwr6843/vital_signs`;
- `<output-dir>`: directory for logs and collection output;
- `<port>`: device UART, for example `/dev/ttyUSB0`;
- `<host-ip>`: host address reachable by the device, for example
  `192.168.4.9`;
- `<device-id>`: the device `did` before claim, or preferably its `cid` after
  claim;
- MQTT URI: `mqtt://<host-ip>:1883`;
- HTTP base URL: `http://<host-ip>:8380/`.

Default topics are derived from device identity:

```text
mmwk/mmwk/<device-id>/device/cmd
mmwk/mmwk/<device-id>/device/resp
mmwk/mmwk/<device-id>/raw/cmd
mmwk/mmwk/<device-id>/raw/resp
mmwk/mmwk/<device-id>/raw/data
```

Do not copy the example identity literally. After the device reconnects to
MQTT, use the `prod`, `oid`, `cid`, `did`, `cmd`, `resp`, `raw_cmd`, `raw_resp`,
and `raw_data` values returned by `node info`.

### 9.2 Start local MQTT and HTTP

Run the services in terminal A:

```bash
./cli/server.sh run \
  --state-dir <output-dir>/local_server \
  --serve-dir <artifact-dir> \
  --host-ip <host-ip> \
  --mqtt-port 1883 \
  --http-port 8380
```

Use `start` instead for detached operation. Inspect the same state directory:

```bash
./cli/server.sh status --state-dir <output-dir>/local_server
./cli/server.sh env --state-dir <output-dir>/local_server
```

Before continuing, confirm:

- `MQTT Up   : yes`;
- `HTTP Up   : yes`;
- `MMWK_SERVER_MQTT_URI=mqtt://<host-ip>:1883`;
- `MMWK_SERVER_HTTP_BASE_URL=http://<host-ip>:8380/`.

### 9.3 Configure device networking and the local broker

Read the baseline and write Wi-Fi and MQTT settings over UART:

```bash
./cli/run.sh node info --reset -p <port>
./cli/run.sh network status --reset -p <port>
./cli/run.sh network wifi --ssid <ssid> --pass <password> -p <port>
./cli/run.sh network mqtt --uri mqtt://<host-ip>:1883 -p <port>
./cli/run.sh node reboot -p <port>
```

A fresh bridge normally has the MQTT agent and automatic raw DATA enabled. Run
this before reboot only when the device carries older persisted settings or
troubleshooting confirms that the MQTT agent is disabled:

```bash
./cli/run.sh node agent --mqtt 1 --uart 1 --raw-auto 1 --reset -p <port>
```

After reboot, handshake through the local broker:

```bash
./cli/run.sh node info \
  --transport mqtt \
  --broker mqtt://<host-ip>:1883 \
  --did <device-id>

./cli/run.sh network status \
  --transport mqtt \
  --broker mqtt://<host-ip>:1883 \
  --did <device-id>
```

Before continuing, `network status` should satisfy
`state=connected && ready=true`, and MQTT state should be `connected`. For a
claimed device, also pass its actual `--prod`, `--oid`, and `--cid`.

### 9.4 Optional: update radar firmware and config over local HTTP

If the target radar firmware and cfg are not already running, let the device
download them from the local HTTP service:

```bash
./cli/run.sh radar fw ota \
  --fw <artifact-dir>/<radar-firmware>.bin \
  --cfg <artifact-dir>/<radar-config>.cfg \
  --welcome \
  --no-verify \
  --ota-timeout 300 \
  --progress-interval 5 \
  --raw-resp-output <output-dir>/ota_cmd_resp.log \
  --transport mqtt \
  --broker mqtt://<host-ip>:1883 \
  --did <device-id> \
  --base-url http://<host-ip>:8380/
```

`<artifact-dir>` must identify the same files served by
`server.sh --serve-dir`. Successful firmware and cfg `GET` requests should
appear in the HTTP log. An OTA command timeout does not prove that flashing
failed. Do not immediately retry the flash; continue polling over MQTT:

```bash
./cli/run.sh radar status \
  --transport mqtt \
  --broker mqtt://<host-ip>:1883 \
  --did <device-id>
```

After `radar fw ota`, `radar fw flash`, `radar config apply`, and the first boot
after recovery, repeat the query until it returns `state=running`; do not
replace this ready gate with a fixed sleep. `--raw-resp-output` is a best-effort
startup window and may remain empty. Reliable readiness evidence is
`radar status=running`, followed by startup output observed in a later
`raw_resp` capture.

### 9.5 Capture 300 seconds of MQTT DATA

Use the live identity and topics for host-owned MQTT collection:

```bash
./cli/run.sh collect \
  --transport mqtt \
  --duration 300 \
  --broker mqtt://<host-ip>:1883 \
  --did <device-id> \
  --data-topic mmwk/mmwk/<device-id>/raw/data \
  --resp-topic mmwk/mmwk/<device-id>/raw/resp \
  --data-output <output-dir>/radar_300s.sraw \
  --resp-output <output-dir>/commands_300s.log \
  --summary-output <output-dir>/summary.json \
  --events-output <output-dir>/events.jsonl
```

If the application already owns an auto MQTT DATA route and the collector must
only observe it, use:

```bash
./cli/collect.sh \
  --transport mqtt \
  --mode auto \
  --attach \
  --duration 300 \
  --broker mqtt://<host-ip>:1883 \
  --did <device-id> \
  --data-output <output-dir>/radar_300s.sraw \
  --resp-output <output-dir>/commands_300s.log
```

For one capture window across a device reboot, use the
`./cli/collect.sh --trigger device-reboot` flow from Section 5. `collect.sh` can
reuse the broker URI exported by `server.sh` through
`--server-state-dir <output-dir>/local_server`.

High-rate DATA still uses QoS 0 with a local MQTT broker, so “local broker” does
not make the network path inherently lossless. At minimum, confirm:

- `radar.sraw` begins at DATA magic and `data_bytes > 0`;
- the 300-second timer starts after DATA ready and excludes setup and cleanup;
- summary drop, CRC, and queue metrics meet the target requirements;
- `cleanup.state_restored=true`;
- `radar status` remains `running` after collection.

### 9.6 Logs, troubleshooting, and shutdown

Retain the collection files, summary, events, and these main service artifacts:

```text
<output-dir>/local_server/mqtt.log
<output-dir>/local_server/http.log
<output-dir>/ota_cmd_resp.log
```

Common problems:

- The device cannot connect to the local broker: verify that the MQTT URI uses
  a host address reachable by the device, the firewall allows `1883`, and the
  network routes between device and host.
- MQTT topic identity mismatch: read `node info` again; do not mix an old `did`
  with the `cid` used after claim.
- Corrupt UART JSON immediately after reboot: runtime logs may overlap command
  responses. Do not access one UART concurrently; retry with `--reset` or move
  to MQTT after it becomes available.
- OTA remains `updating`: keep using the `radar status` ready gate; do not
  immediately reflash because one CLI call timed out.
- Short `raw_resp`: a partial banner is normal, but a startup-proof capture
  should still contain non-empty printable command-port output.

Stop the local services when finished:

```bash
./cli/server.sh stop --state-dir <output-dir>/local_server
```
