# Bridge Factory Flash Guide

## Published Packages You Receive

The published bridge release now ships as two zip files under the versioned release directory:

- `./firmwares/esp/<board>/mmwk_sensor_bridge/v<version>/factory.zip`
- `./firmwares/esp/<board>/mmwk_sensor_bridge/v<version>/ota.zip`

This guide only uses `factory.zip` for the first flash onto a blank or erased board. `ota.zip` is the companion package for later ESP OTA updates and is covered in [Bridge Device OTA Guide](./ota.md).

## Prerequisites

- The commands below assume the current working directory is the `mmwk` project root, which contains `firmwares/` and `mmwk_cli/`.
- You already received the published bridge zip packages for your board and version.
- Choose one flashing path:
  - Local serial erase plus `factory/flash.sh` requires ESP-IDF installed locally and the target device port available as `<port>`.
  - Espressif official `ESP Launchpad` DIY does not require a local ESP-IDF installation.

## Extract `factory.zip`

Use the published `factory.zip` directly, then extract it to a temporary directory before flashing:

```bash
rm -rf /tmp/mmwk_bridge_factory
mkdir -p /tmp/mmwk_bridge_factory
unzip ./firmwares/esp/<board>/mmwk_sensor_bridge/v<version>/factory.zip -d /tmp/mmwk_bridge_factory
```

After extraction, the files you use are:

```text
/tmp/mmwk_bridge_factory/factory/flash.sh
/tmp/mmwk_bridge_factory/factory/mmwk_sensor_bridge_factory_v<version>.bin
```

## Option A: Local Serial Erase + Extracted `factory/flash.sh`

Load an ESP-IDF environment before local erase and flash commands. On this repo, use whichever local export path you actually have installed:

```bash
source ~/esp/esp-idf/export.sh
# or
source ~/esp/esp-adf/esp-idf/export.sh
```

The erase step should use `idf.py` with a throwaway build directory, so the command stays copy-executable without depending on a checked-out ESP-IDF project directory:

```bash
idf.py -B /tmp/mmwk_idf_erase -p <port> erase-flash
```

Then flash from the extracted factory bundle:

```bash
cd /tmp/mmwk_bridge_factory/factory
./flash.sh <port>
```

## Option B: Espressif Official ESP Launchpad DIY

If you want the single-file path in the Espressif official [ESP Launchpad](https://espressif.github.io/esp-launchpad/) UI, choose `DIY`, upload the extracted merged factory image, and write it at address `0x0`.

Use this exact extracted file:

```text
/tmp/mmwk_bridge_factory/factory/mmwk_sensor_bridge_factory_v<version>.bin
```

## Verify Recovery

From the `mmwk` project root, verify runtime identity:

```bash
./mmwk_cli/mmwk_cli.sh device hi --reset -p <port>
```

`device hi` should report the bridge identity. Confirm that `device hi.version` matches the version encoded in the published package path or extracted binary name, for example:

```text
./firmwares/esp/mini/mmwk_sensor_bridge/v1.2.2/factory.zip
/tmp/mmwk_bridge_factory/factory/mmwk_sensor_bridge_factory_v1.2.2.bin
```

## Out of Scope

Out of scope in this guide:

- ESP OTA updates after the first flash
- How to build or publish the zip packages
