# Radar DATA collection

This guide is the user-facing entry point for collecting radar bytes. Choose
the path that matches where the radar is connected:

1. **Attached host:** UART for MINI/PRO, or native USB CDC for WDR.
2. **Remote device:** MQTT host mode.
3. **Hybrid:** local UART/USB for control and MQTT for DATA.
4. **Application-owned:** attach to an existing MQTT DATA route without taking
   ownership.

All four paths use the same `collect` engine. The POSIX entrypoint is
`./run.sh`; Windows PowerShell uses `./run.ps1`. `collect.sh` and
`collect.ps1` forward the same collection options. The optional
`collect.sh --trigger` helper is an advanced pure-MQTT reconnect workflow.

## Attached host: simplest path

MINI and PRO normally use a parsed control UART at 115200 followed by a raw
DATA UART at 1000000:

```bash
./run.sh collect --transport uart --port /dev/ttyUSB0 \
  --raw-baud 1000000 --duration 30 \
  --data-output ./radar.sraw --resp-output ./radar-cmd.log
```

On Windows, use the same arguments with `./run.ps1` and a `COM` port. The
collector identifies the live device (`did`, then `id`, then `client_id`),
normalizes it to lowercase, and checks `--did` before changing device state.
It reads an explicit `--cfg` before takeover; the summary records its path as
`config_source`, and an explicit config is never persisted by the collector.

The local choreography is parsed control, host start, raw open, optional cfg,
`sensorStart`, DATA capture, `sensorStop`, escape, and restoration. A normal
run rejects an already-active host raw route before mutation. It will not close
another client's route or silently displace a running host session without a
complete restorable config/lifecycle snapshot. Cleanup reports raw close,
radar stop, parsed/config restoration, ownership restoration, and route
restoration separately. The first `Ctrl-C` performs the same cleanup; a second
interrupt prints the one-second escape recovery sequence and exits.

The wire is a merged byte stream, not a framed command/data protocol:
`radar.sraw` can contain parsed command responses interleaved with radar DATA.
The command log contains parsed setup/close acknowledgements. Use split or
MQTT DATA when a DATA-only file is required.

## WDR native USB

Native USB CDC has no physical raw baud. Do not pass `--raw-baud`:

```bash
./run.sh collect --transport usb --port /dev/ttyACM0 --duration 30 \
  --data-output ./wdr.sraw --resp-output ./wdr-cmd.log
```

Use the WDR board identity returned by `node info`, not a `/dev/tty*` name, to
choose the target. A USB result is hardware proof only after the current
artifact has been flashed and the live identity has been checked.

## Remote MQTT host mode

Use MQTT when the device is not directly attached. Host mode owns the radar
lifecycle for the collection window:

```bash
./run.sh collect --transport mqtt --broker mqtt://broker.example:1883 \
  --did DEVICE_ID --duration 30 \
  --data-output ./remote.sraw --resp-output ./remote-cmd.log
```

Host MQTT publishes commands and parsed acknowledgements on `raw/cmd` and
`raw/resp` with QoS 1. High-rate DATA uses `raw/data` with QoS 0 and retain
disabled. MQTT has no cross-topic ordering guarantee: clients correlate
responses by lifecycle phase, tolerate duplicated QoS 1 responses, and never
assume that DATA arrived after a particular response merely because it was
published later. There is no owner token; multiple writers may enqueue bytes,
so each client must correlate its own responses.

Credentials, broker passwords, device keys, and certificate contents are never
written to summaries or event logs. Grant ACL access only to the required
`raw/cmd`, `raw/resp`, and `raw/data` topics.

## Hybrid split: `ctrl=wire,data=mqtt`

When the local UART cannot carry the radar DATA rate, keep control local and
send DATA to MQTT:

```bash
./run.sh collect --ctrl-transport uart --data-transport mqtt \
  --port /dev/ttyUSB0 --broker mqtt://broker.example:1883 \
  --did DEVICE_ID --duration 30 \
  --data-output ./split.sraw --resp-output ./split-cmd.log
```

The collector verifies the DID across both transports before mutation,
subscribes to MQTT before opening raw, and keeps DATA off the wire. Explicit
split routing is different from `channel=both`: `both` broadcasts to both
physical adapters and is never interpreted as a split session.

## Application-owned DATA and safe attach

An application can expose a read-only MQTT DATA route:

```bash
./run.sh radar raw runtime --channel mqtt \
  --transport mqtt --did DEVICE_ID
./run.sh collect --transport mqtt --mode auto --attach \
  --broker mqtt://broker.example:1883 --did DEVICE_ID --duration 30
```

`--attach` requires the requested DATA route to already be active. It records
the route as borrowed and never changes ownership, sends cfg, starts or stops
the radar, closes another owner's route, or restores state it did not mutate.
Auto mode is DATA-only: it does not expect command or parsed response topics.
If the route is not active, attach fails before mutation.

To arm one MQTT DATA window after the next reconnect:

```bash
./run.sh radar raw reconnect --channel mqtt \
  --transport mqtt --did DEVICE_ID
```

Subscribe before arming. The structured acknowledgement must arrive before the
reboot. The one-shot arm is consumed by the next MQTT generation; a second
reboot does not restart collection until it is armed again.

## Raw route control

The unified radar command has two sibling actions: `raw` and `record`.

```bash
./run.sh radar raw status -p /dev/ttyUSB0
./run.sh radar raw runtime --channel wire --baud 1000000 --escape +++ -p /dev/ttyUSB0
./run.sh radar raw runtime --ctrl wire --data mqtt --escape +++ \
  --transport uart --port /dev/ttyUSB0 --broker mqtt://broker.example:1883 \
  --did DEVICE_ID
./run.sh radar raw off --channel both --transport mqtt --did DEVICE_ID
```

Raw and parsed traffic are mutually exclusive only on the same physical
channel. A second parsed control channel may remain active. The default escape
is `+++`: keep the wire silent for one second, send the printable sequence with
no newline, then keep it silent for one second. `--escape` accepts a custom
1–16-character printable sequence; the guard time remains one second.

## Outputs, overwrite, and recovery

The default outputs are `data_resp.sraw` and `cmd_resp.log`. Set explicit paths
with `--data-output`, `--resp-output`, optional `--wire-output`, and
`--summary-output`. The complete output set is checked for collisions before
the device is changed; a collision fails the whole run unless `--overwrite` is
explicit. Paths must be distinct. Summary JSON includes identity, transport,
config provenance, source/destination byte counts, queue high-water data when
available, warnings, and separate cleanup results.

The collector never claims a general command/DATA demultiplex on a merged wire;
runtime writes may interleave. If cleanup reports a failed config, running-state,
route, or ownership restoration, follow the reported item before reconnecting
the radar. For a hard wire recovery, keep the line silent, send the configured
escape (default `+++`) with one-second guards, and return to parsed 115200.

## Rate policy

- External UART DATA is capped at 1000000 baud.
- MINI/PRO radar DATA is nominally 921600; 1000000 has an 8.5% margin and the
  summary warns that sustained drop-counter testing is required.
- WDR DATA is 1250000; the default external UART path refuses it as lossless.
  Use native USB, MQTT, or split routing. `--allow-lossy` is an explicit
  diagnostic exception and disqualifies the result from lossless acceptance.
- There is no default 2 Mbaud setting.

Build/test output proves source and artifact validity only. Hardware proof
requires flashing the current artifact, checking the live identity, and running
the matching board suite; no software-only collection result is hardware proof.

## Recording

Recording is independent of raw forwarding:

```bash
./run.sh radar record status -p /dev/ttyUSB0
./run.sh radar record config get -p /dev/ttyUSB0
./run.sh radar record config set --json '{"auto_upload":true}' -p /dev/ttyUSB0
./run.sh radar record start --uri file://recording -p /dev/ttyUSB0
./run.sh radar record trigger --event manual --duration-s 10 -p /dev/ttyUSB0
./run.sh radar record stop -p /dev/ttyUSB0
```

`config set` accepts `config`, not a patch alias. Recording does not open a raw
route, and changing a raw route does not change recorder configuration.
