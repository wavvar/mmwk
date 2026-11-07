# Develop Radar With Bridge

This guide covers the public bridge development loop: configure over UART,
update a matched radar artifact pair, then collect with the shared host/MQTT
engine. Windows uses `server.ps1`, `run.ps1`, `collect.ps1`, and (for registry
configuration) `config.ps1`; the collection PowerShell wrapper does not require
Bash.

## Choose the bridge board

| Radar family | Bridge | Artifact pair |
| --- | --- | --- |
| `IWR6843` / `IWR6843AOP` | `mini`, `pro`, or `wsr` | `.bin` + `.cfg` under `firmwares/radar/iwr6843/` |
| `IWRL6432` | `wdr` | `.appimage` + `.cfg` under `firmwares/radar/iwrl6432/` |

Keep the firmware and cfg from the same release. WDR high-rate DATA should use
native USB, MQTT, or split routing; an external 1000000-baud UART is not a
lossless path for its 1250000-baud radar output.

## Common loop

```bash
./server.sh start --serve-dir <radar-artifact-dir>
eval "$(./server.sh env)"
./config.sh init --port <control-port> --working ./collect-lab
./config.sh update --did <DID> --fw <radar.bin> --cfg <radar.cfg> --working ./collect-lab
./run.sh radar status --transport mqtt --broker "$MMWK_SERVER_HOST_IP" --did <DID>
```

Use `config.sh list` to confirm the DID and broker URI. Do not infer board type
from a `/dev/tty*` name; use live `node info` identity.

## Collect

Attached MINI/PRO/WSR UART:

```bash
./collect.sh --transport uart --port <control-port> --raw-baud 1000000 \
  --duration 30 --data-output ./radar.sraw --resp-output ./radar-cmd.log
```

Attached WDR/WSR USB:

```bash
./collect.sh --transport usb --port <native-usb-port> --duration 30
```

Remote MQTT host or application-owned attach:

```bash
./collect.sh --transport mqtt --broker mqtt://broker.example:1883 \
  --did <DID> --duration 30
./collect.sh --transport mqtt --mode auto --attach \
  --broker mqtt://broker.example:1883 --did <DID> --duration 30
```

Hybrid control/DATA split:

```bash
./collect.sh --ctrl-transport uart --data-transport mqtt \
  --port <control-port> --broker mqtt://broker.example:1883 --did <DID>
```

The engine verifies identity before mutation, reserves outputs, subscribes
before opening MQTT DATA, and reports route/config/running/ownership cleanup
separately. A normal run rejects a pre-existing host raw route; `--attach`
borrows an existing application DATA route and performs no lifecycle mutation.
The application, not the attach command, must create that auto route first.

For the full QoS, topic ACL, reconnect, output, cleanup, and baud contract see
[Radar DATA collection](data-collection.md). Build/test output is software
evidence only; hardware proof requires flashing the current artifact and
checking the live identity.
