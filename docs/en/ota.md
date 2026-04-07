# Bridge Device OTA Guide

Use this guide only for OTA updates on devices that are already running bridge firmware.

## Scope

- OTA-only flow for already-running bridge devices.
- Uses prebuilt artifacts from `../firmwares/esp/<board>/`.
- Out of scope: factory flashing and package build instructions.

For blank/erased devices, see [Factory Flash Guide](./flash.md).

## Prerequisites

- Device is reachable on UART and already running bridge firmware.
- Bridge OTA artifact exists at `../firmwares/esp/<board>/mmwk_sensor_bridge_full.bin`.
- Optional version sidecar exists at `../firmwares/esp/<board>/mmwk_sensor_bridge.version`.

## Start Local Publish Helper

Use the helper mode `server.sh --device-ota --device-ota-board <board>` to publish bridge OTA artifacts.

```bash
cd ./mmwk_cli
./server.sh run --device-ota --device-ota-board <board> --host-ip <host_ip>
```

Then in another terminal:

```bash
cd ./mmwk_cli
./server.sh env
```

Check:

- `MMWK_SERVER_DEVICE_OTA_URL` points to `mmwk_sensor_bridge_full.bin`.
- `MMWK_SERVER_DEVICE_OTA_VERSION` matches `mmwk_sensor_bridge.version` when the sidecar exists.

## Trigger OTA and Verify

```bash
cd ..
./mmwk_cli/mmwk_cli.sh device ota --url "$MMWK_SERVER_DEVICE_OTA_URL" -p <port>
./mmwk_cli/mmwk_cli.sh device hi -p <port>
```

Success criteria:

- OTA command succeeds and device reconnects.
- Post-OTA `device hi.version` equals the expected value from `mmwk_sensor_bridge.version`.
