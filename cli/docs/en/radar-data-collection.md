# Radar data collection

The public interface has one radar tool:

- `radar raw` controls byte routing.
- `radar record` controls the recorder.

There is no boot-time raw setting, separate raw tool, or separate `bridge` command.

## Choose a mode

Use host mode when the radar is connected to the collection computer. It works
over UART or native USB and does not require Wi‑Fi, MQTT, or provisioning. The
host sends configuration, `sensorStart`, runtime commands, and `sensorStop`.

Use auto mode when application firmware must keep ownership of radar setup and
lifecycle. Auto raw is read-only MQTT DATA; it never exposes command or parsed
responses.

Use MQTT host mode when the device is remote. If both links are available, split
their jobs, for example `ctrl=wire, data=mqtt`: use the local UART/USB for
commands and MQTT for the high-rate DATA stream.

## Local host collection

The short path is:

```bash
./run.sh collect --transport uart --port /dev/ttyUSB0 \
  --raw-baud 1000000 --duration 30 \
  --data-output ./radar.sraw --resp-output ./radar-cmd.log
```

Windows uses the same command through `run.ps1` and a `COM` port. The initial
parsed control baud remains `115200`; `--raw-baud` is only the later raw DATA
rate. Native WDR USB CDC has no physical baud, so omit `--raw-baud`:

```bash
./run.sh collect --transport usb --port /dev/ttyACM0 --duration 30
```

The host collection flow identifies the device (`did`, then `id`, then
`client_id`), checks the optional `--did`, enters host mode, opens wire raw, and
starts the capture window immediately after sending `sensorStart`. It restores
parsed control on normal exit or one `Ctrl-C`.

The local host wire has no separate command/data framing, so `radar.sraw` is the
merged raw wire stream: radar command responses can appear before or after DATA
chunks. `radar-cmd.log` contains the parsed setup/close acknowledgements. If a
DATA-only file is required, use auto MQTT or the split `data=mqtt` collection
shown below.

Raw and parsed output are mutually exclusive on one physical channel. Parsed
JSON may be visible before raw opens; once raw is active, that channel carries
raw bytes only. A separate MQTT or USB/UART route may still carry commands.

The unified collector also supports the recommended split route directly:

```bash
./run.sh collect --ctrl-transport uart --data-transport mqtt \
  --port /dev/ttyUSB0 --broker mqtt://192.168.1.100:1883 --did DEVICE_ID \
  --duration 30 --data-output ./radar.sraw --resp-output ./radar-cmd.log
```

`--transport` and the explicit split options are mutually exclusive. The split
collector subscribes to MQTT DATA before opening wire raw, so high-rate DATA is
not mirrored onto the external UART; its `data-output` file contains MQTT DATA
payloads only and its `resp-output` file contains the local wire responses.

## Raw route commands

Query the route:

```bash
./run.sh radar raw status -p /dev/ttyUSB0
```

Open or close a route:

```bash
./run.sh radar raw runtime --channel wire --baud 1000000 --escape +++ -p /dev/ttyUSB0
./run.sh radar raw runtime --ctrl wire --data mqtt --escape +++ \
  --transport uart --port /dev/ttyUSB0 --broker mqtt://192.168.1.100:1883 --did DEVICE_ID
./run.sh radar raw reconnect --channel mqtt --transport mqtt --did DEVICE_ID
./run.sh radar raw off --channel both --transport mqtt --did DEVICE_ID
```

`channel=wire|mqtt|both` is a full-duplex shorthand. Explicit `ctrl` and
`data` split command/response from radar DATA. Multiple writers are allowed;
the service FIFO preserves enqueue order, but the protocol does not provide
command ownership or response correlation.

The default wire escape is `+++`: keep the wire silent for one second, send the
three bytes without a newline, then keep it silent for another second. A custom
printable sequence may be supplied with `--escape`; the guard time is fixed at
one second. Escape closes only the wire route and leaves an independent MQTT
route running.

## Auto DATA collection

Auto mode is application-owned and MQTT DATA-only:

```bash
./run.sh radar raw runtime --channel mqtt --transport mqtt --did DEVICE_ID
./run.sh collect --transport mqtt --mode auto --attach --did DEVICE_ID \
  --broker mqtt://192.168.1.100:1883 --duration 30
```

To arm one collection after the next MQTT reconnect:

```bash
./run.sh radar raw reconnect --channel mqtt --transport mqtt --did DEVICE_ID
```

Auto raw publishes only `raw/data`. It does not publish `raw/cmd`, `raw/resp`,
CLI JSON, logs, or parsed frames. `mode=reconnect` is one-shot and is cleared
after it is consumed; it is not a permanent boot flag.

## MQTT and QoS

Host MQTT uses `raw/cmd` and `raw/resp` at QoS 1, and `raw/data` at QoS 0 with
retain disabled. Auto MQTT uses only `raw/data` at QoS 0. MQTT payload boundaries
are transport chunks, not radar frame boundaries; concatenate DATA payloads in
arrival order before parsing.

## Baud limits

- MINI/PRO radar DATA is nominally `921600`; external UART `1000000` has little
  margin and requires sustained hardware drop testing.
- WDR radar DATA is `1250000`; the current CP2102 `1000000` path is not lossless.
- Prefer native USB CDC or MQTT for WDR high-speed DATA.
- A WDR UART path needs a validated 2–3 Mbaud adapter. The bridge never defaults
  to 2 Mbaud; current external UART validation is capped at 1 Mbaud.

Use `--allow-lossy` only for an explicitly diagnostic WDR UART capture. Its
summary is not a lossless result.

## Recording

Recording is separate from raw forwarding:

```bash
./run.sh radar record status -p /dev/ttyUSB0
./run.sh radar record config get -p /dev/ttyUSB0
./run.sh radar record config set --json '{"auto_upload":true}' -p /dev/ttyUSB0
./run.sh radar record start --uri file://recording -p /dev/ttyUSB0
./run.sh radar record trigger --event manual --duration-s 10 -p /dev/ttyUSB0
./run.sh radar record stop -p /dev/ttyUSB0
```

Recording does not open a raw route and changing a raw route does not change
recorder configuration.
