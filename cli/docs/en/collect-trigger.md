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
to `raw/data` and, for host-triggered flows, `raw/resp`; DATA is binary and the
response file preserves MQTT payload boundaries. MQTT credentials and device
keys are not printed into summaries or event logs.

## Late attach

```bash
./collect.sh --trigger none \
  --broker mqtt://broker.example:1883 --did DEVICE_ID \
  --data-output ./data.sraw --resp-output ./resp.log --resp-optional
```

`--resp-optional` is valid only for this steady-state observation window. It is
not startup or welcome proof, and it never takes ownership of an application
route.

## Reconnect-triggered capture

```bash
./collect.sh --trigger device-reboot \
  --broker mqtt://broker.example:1883 --did DEVICE_ID \
  --data-output ./data.sraw --resp-output ./resp.log
```

The helper subscribes before arming `mode=reconnect`, waits for the structured
acknowledgement, requests the reboot, and accepts DATA only after the new MQTT
generation. The one-shot arm is consumed once; a second reboot requires a new
arm. `radar-restart` follows the same subscribe-before-control rule without a
device reboot.

## Options and safety

- `--did`, or `--prod --oid --cid`, selects the MQTT route; environment fallbacks
  are `MMWK_DID`, `MMWK_PROD`, `MMWK_OID`, and `MMWK_CID`.
- `--raw-data` and `--raw-resp` override topics when a broker uses non-default
  ACL names. Prefer explicit ACLs for `raw/cmd`, `raw/resp`, and `raw/data`.
- `--duration` defaults to 10 seconds; `--timeout` defaults to 10 seconds.
- `--server-state-dir` may provide a local broker URI from `server.env`.
- Reserve distinct output paths before the device is changed; use
  `--overwrite` only when replacing an existing set is intentional.

For host-local UART/USB collection, use the [Radar DATA collection guide](data-collection.md)
instead. It documents identity checks, route ownership, cleanup, QoS, and rate
limits.
