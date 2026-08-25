# Collect Trigger Helper

`collect.sh --trigger` is an advanced pure-MQTT helper for workflows that keep
both control and capture off UART. Normal local, remote, split, and attach
workflows should use the shared `run.sh collect` engine.

The helper runs directly under Python; `collect.ps1 --trigger` does not require
Bash. Run it from the published `cli` directory:

```bash
./collect.sh --trigger none --broker mqtt://broker.example:1883 --did DEVICE_ID
```

It supports `none`, `radar-restart`, and `device-reboot` triggers. It subscribes
to `raw/data` and, for host-owned flows, `raw/resp`; DATA and response bytes are
preserved, but MQTT payload boundaries are not encoded in the files. MQTT
credentials and device keys are not printed into summaries or event logs.

## No-reboot host collection

```bash
./collect.sh --trigger none \
  --broker mqtt://broker.example:1883 --did DEVICE_ID \
  --data-output ./data.sraw --resp-output ./resp.log
```

This compatibility trigger delegates to the owned host MQTT engine; it is not
an attach window, and responses are required. For an application-owned DATA-only
route, use `run.sh collect --transport mqtt --mode auto --attach`. The legacy
`--resp-optional` behavior is rejected rather than treating missing lifecycle
responses as success.

## Reconnect-triggered capture

```bash
./collect.sh --trigger device-reboot \
  --broker mqtt://broker.example:1883 --did DEVICE_ID \
  --data-output ./data.sraw --resp-output ./resp.log
```

The helper subscribes before arming `mode=reconnect`, waits for the structured
acknowledgement, requests the reboot, and accepts DATA only after the new device
generation has consumed the arm. The one-shot arm is consumed once; a second
reboot requires a new arm. `radar-restart` is retained as a compatibility name
for the shared owned host lifecycle collection; it does not use the reconnect
arm or reboot the device.

## Options and safety

- `--did`, or `--prod --oid --cid`, selects the MQTT route; environment fallbacks
  are `MMWK_DID`, `MMWK_PROD`, `MMWK_OID`, and `MMWK_CID`.
- `--raw-data` and `--raw-resp` override topics when needed; the live DID or
  claimed CID must remain an exact topic segment. Prefer explicit ACLs for
  `raw/cmd`, `raw/resp`, and `raw/data`.
- A full `mqtts://` broker URI, including URI credentials when used, is reused
  by both control and raw connections without rendering its password.
- `--duration` defaults to 10 seconds; `--timeout` defaults to 10 seconds.
- `--server-state-dir` may provide a local broker URI from `server.env`.
- Reserve distinct output paths before the device is changed; use
  `--overwrite` only when replacing an existing set is intentional.

For host-local UART/USB collection, use the [Radar DATA collection guide](data-collection.md)
instead. It documents identity checks, route ownership, cleanup, QoS, and rate
limits.
