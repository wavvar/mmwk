# Bridge Device OTA Guide

Use this guide only for OTA updates on devices that are already running bridge firmware.

## Scope

- OTA-only flow for already-running bridge devices.
- Uses published bridge artifacts from `../firmwares/esp/<board>/`.
- Out of scope: factory flashing and package build instructions.

For blank/erased devices, see [Factory Flash Guide](./flash.md).

## Prerequisites

- Device is reachable on UART and already running bridge firmware.
- Published OTA package exists at `../firmwares/esp/<board>/mmwk_sensor_bridge/v<version>/ota.zip`.
- `server.sh --device-ota --device-ota-board <board>` can also consume the legacy top-level `mmwk_sensor_bridge_full.bin` when it exists.

## Start Local Publish Helper

Use the helper mode `server.sh --device-ota --device-ota-board <board>` to publish bridge OTA artifacts.

```bash
cd ./cli
./server.sh run --device-ota --device-ota-board <board> --host-ip <host_ip>
```

Then in another terminal:

```bash
cd ./cli
./server.sh env
```

Check:

- `MMWK_SERVER_DEVICE_OTA_PATH` points to the resolved OTA `.bin` that `server.sh` will publish.
- `MMWK_SERVER_DEVICE_OTA_URL` points to the same resolved OTA payload.
- `MMWK_SERVER_DEVICE_OTA_VERSION` reports the resolved version when `server.sh` selected a published `ota.zip`.

Resolution behavior:

- `server.sh` first checks the legacy top-level `firmwares/esp/<board>/mmwk_sensor_bridge_full.bin`.
- If that file is absent, it automatically falls back to the latest published `firmwares/esp/<board>/mmwk_sensor_bridge/v*/ota.zip`, extracts the OTA `.bin`, and serves that extracted payload instead.

## Trigger OTA and Verify

```bash
cd ..
./cli/run.sh node ota --url "$MMWK_SERVER_DEVICE_OTA_URL" -p <port>
./cli/run.sh node info -p <port>
```

Success criteria:

- OTA command succeeds and device reconnects.
- Post-OTA `node info.version` equals the expected version.
- When `MMWK_SERVER_DEVICE_OTA_VERSION` is non-empty, it should match `node info.version`.
