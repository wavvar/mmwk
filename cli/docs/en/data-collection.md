# Radar DATA collection

Choose the workflow by where the device is and who owns the radar:

| Scenario | Use this path |
| --- | --- |
| Attached MINI/PRO | Host UART; no network is required |
| Attached WDR | Host native USB CDC; no network is required |
| Remote device | Host MQTT |
| Local control, remote DATA | Split `ctrl=wire,data=mqtt` |
| Application already owns the radar | MQTT DATA-only `--mode auto --attach` |

All paths use the same collection engine. POSIX users run `./run.sh` or
`./collect.sh`; Windows PowerShell users run `./run.ps1` or `./collect.ps1`
with the same core options.

## 1. MINI/PRO attached UART

This is the simplest MINI/PRO workflow. The parsed control UART starts at
115200; raw DATA uses at most 1000000:

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

## 2. WDR attached native USB

WDR DATA is 1250000 baud, so native USB CDC is the attached lossless path:

```bash
./run.sh collect --transport usb --port /dev/ttyACM0 --duration 30
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
- MINI/PRO DATA is nominally 921600. The 1000000 setting has only an 8.5%
  adapter margin, so the warning and drop counters are mandatory acceptance
  evidence.
- WDR DATA is 1250000. External UART is refused as lossless by default; use
  native USB, MQTT, or split routing. `--allow-lossy` is diagnostic-only and
  explicitly disqualifies the result from lossless acceptance.

Code inspection, unit tests, and local builds are software evidence. Hardware
proof requires flashing the artifact built or selected in the current session,
checking the live DID/board, and running the matching physical-device suite.
