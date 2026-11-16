# Stage1 aggregate SDK migration preview (not a released feature)

This document is **only for the `arch_v2` development branch** associated with [SDK PR #70](https://github.com/wavvar/mmwk_sdk/pull/70). The SDK in `mmwk/dev` and `main` remains the current per-board release. New presets and a common S3 archive have **not** passed target builds or hardware acceptance.

The intended developer boundary is two public components: `mmwk_board` contains consumer-compiled board facts, while `mmwk_sdk` exposes one aggregate `libmmwk_sdk.a` for each verified ESP target/ABI group. The consumer explicitly selects one 6843 or 6432 radar backend, its matching firmware/config and optional capabilities *before* ESP-IDF's component dependency expansion.

The stage1 presets are `offline` (radar only), `local-control` (radar + local control), `wifi-data` (radar + Wi-Fi, no management control), and `default` (supported compatibility features). Key/LED interpretation belongs to the application. No preset may cause unwanted Wi-Fi/MQTT/HTTP dependencies or legacy UI tasks.

## What works in the current arch_v2 public branch

The original, legacy form is preserved:

```sh
cd sdk/examples
./build.sh presence mini
./build.sh presence pro
./build.sh presence wdr
./build.sh all
```

`./build.sh presence pro --preset default` also accepts an explicitly isolated `build/presence/pro/default` output directory. Other preset names are recognized but **fail with an explanation**, rather than quietly building the legacy full-featured image. There is currently no validated four-preset package to consume.

## Required before enabling the new combinations

The schema-3 manifest must carry an exact `file_sha256` map for **all** managed files, not only the selected board archive; verification covers board configuration sources, public CMake, both chip asset families, `NOTICE`, licenses and patches. The manifest's own SHA256 is pinned by `mmwk-sdk.lock.json`. Missing or tampered unselected files must also fail. The new package must include a verified schema-3 `release-manifest.json`, matched public headers and board source, a compatible `libmmwk_sdk.a`, paired firmware/config and a consumer lock that pins all relevant SHA256 values and target/ABI. The presence sources must use the RAW subscription API without legacy UI, bind exactly one radar backend, and separate network/control objects. Three boards × four presets must actually compile and link using the final candidate. The last acceptance phase tests **every in-use physical device and revision**.

The host CLI is optional for offline applications. After the new package has passed target builds, the published instructions will provide the exact first-flash asset partition procedure and `idf.py -B <build-dir> -p <port> flash monitor` commands. Do not infer a device's board from its changing serial-port name.

**The current production publisher writes `mmwk/dev`; it must not be used during this branch's pre-merge work.** New native sources and docs are committed only on `mmwk/arch_v2`. A merge does not authorize a formal release.

## CLI flash-session compatibility

The host CLI on `mmwk/arch_v2` now recognizes both legacy `err=-2` and current SDK `err=-3415` inactive radar UART update responses, and avoids treating unrelated `err=-20` or `err=-34150` as the same error. The change preserves the previous bounded retry/reopen behavior; it is validated by host fake-transport tests only, **not** an actual firmware flash or OTA. The public CLI remains independent of the SDK candidate overlay.

## Application-owned key and LED

The new aggregate SDK adds `startup.disable_legacy_key` and
`startup.disable_legacy_led` to the existing startup policy, without
adding a new exported API. Set both **before** calling
`mmwk_sensor_bridge_run()`. This prevents the legacy button GPIO/task
and LED driver/delayed-task initialization; the application may then
configure those pins with its own policy. These flags do **not** disable
Wi-Fi provisioning or the network runtime; those capabilities require
separate build selection. Internal legacy firmware keeps its old behavior
when the policy fields are zero.

The native presence source uses
`#ifdef MMWK_SENSOR_STARTUP_LEGACY_UI_POLICY_V1` to set these flags only
when consuming the new header/archive. On the still-published old per-board
SDK it builds without accessing absent fields. This source-path opt-out is
not a substitute for the eventual aggregate SDK target build or physical
key/LED ownership test.

## Flash, monitor and first-flash radar assets without host CLI

Build with the matching ESP-IDF environment activated, then identify the
**physical** board (do not choose MINI/PRO/WDR from a changing USB port name).
The following commands use only ESP-IDF, Python and the public SDK files:

```sh
cd sdk/examples
./build.sh presence mini
./flash.sh presence mini --port /dev/ttyUSB0 --monitor
# Subsequent serial monitoring only, with no flash:
./flash.sh presence mini --port /dev/ttyUSB0 --monitor-only

# Explicit default uses an isolated output directory:
./build.sh presence wdr --preset default
./flash.sh presence wdr --preset default --port /dev/ttyACM0 --monitor
```

The flash wrapper refuses an unknown board, missing explicit `--port`,
incompatible `sdkconfig` board/ESP target/size-optimization setting, missing
`flasher_args.json` or missing app and `assets.bin` image. The presence
project already calls `spiffs_create_partition_image(assets ... FLASH_IN_PROJECT)`,
so `idf.py flash` includes the approved paired radar firmware, configuration
and `meta.json` **on initial flash**. It refuses incomplete images rather
than silently flashing only the ESP application. `--monitor-only` never flashes.
Real flashing and serial/device behavior remain subject to S6 acceptance.

For an independent ESP-IDF application, include only the delivered
`sdk/components` directory as a component root, link `mmwk_sdk` from
your app's `main/CMakeLists.txt`, choose its matching board-specific
`sdkconfig.defaults` and keep `CONFIG_COMPILER_OPTIMIZATION_SIZE=y`.
Prepare your own `assets` SPIFFS partition from the paired radar firmware,
config and catalog (with `FLASH_IN_PROJECT`); do not silently take assets
from another board or a sibling source checkout. When the new aggregate
package is ready, validate its entire `release-manifest.json` and lock
before selecting backend/preset. The current legacy binary only supports
the existing default profile.

Use a Windows COM port when appropriate. No host MMWK CLI or prior device
configuration is required for the ESP image and radar-resource partition flash.

## Custom key/LED policy in the native presence application

Edit `sdk/examples/presence/main/main.c`:

```c
static const presence_ui_policy_t s_ui_policy = {
    .claim_key = false,  // set true only when your app will read the key
    .claim_led = false,  // set true only when your app will drive the LED
    .led_initially_on = false,
};
```

`presence_ui_configure(&s_ui_policy)` runs **before**
`mmwk_sensor_bridge_run()`. With both fields false, the application configures
no GPIO and creates no UI task. A new aggregate SDK exposes
`mmwk_board_get_config()` and supports explicit application key/LED
ownership; `presence_ui_read_key()` and `presence_ui_set_led()` then provide
the read/write primitives. The application implements its own debounce,
events and light states; the example creates **no** background button,
gesture or LED animation task. The PRO/WDR/MINI physical pin behavior must
be checked during S6. A legacy per-board SDK cannot safely transfer those
GPIOs and therefore returns `ESP_ERR_NOT_SUPPORTED` when asked to claim
one; with the default all-false policy, the old example remains functional.

## Optional external RAW command ingress

The new SDK supports an independent, application-chosen startup flag,
`startup.disable_external_raw_commands = true` (guarded by
`MMWK_SENSOR_STARTUP_RAW_COMMAND_POLICY_V1`). It prevents the external
RAW command worker, queues and copied-payload pool from being allocated.
Internal radar startup/config commands and RAW output subscribers remain
available. The default is **false**, preserving existing host-control,
Bridge and Hub workflows. Only enable the opt-out when the application
does not require external UART/MQTT RAW commands. It is not a global
radio/network shutdown switch. New target firmware and concurrent stop/
restart behavior still require validation; older published SDKs do not
provide this flag.

## Consumer-owned radar firmware and configuration pairs

`sdk/examples/presence/main/presence_radar_assets.c` now owns the explicit
MINI/ESP32/6843, PRO/ESP32-S3/6843 and WDR/ESP32-S3/6432 descriptors.
Each descriptor binds one firmware and one configuration file, including its
resource family. Mismatched or unknown profiles fail **before** the presence
SDK runtime starts; legacy `presence_radar_firmware_path()` and
`presence_radar_config_path()` remain for compatibility.

The matching build-time selection is in
`sdk/examples/presence/presence_asset_profiles.cmake`; it checks chip,
board, IDF target and both native firmware/config files. It does **not** use
a sibling private checkout as an implicit fallback. These files are
application-maintained; the aggregate library must not choose the product's
firmware or embedded asset partition. Host GCC and CMake test cases cover
the three valid profiles, mismatches and missing resources. Actual firmware
contents, target linkage and initial flash remain separate verification
requirements.

## Stage1 radar-only presence source mode

The native presence application now has two mutually exclusive entry sources.
Existing default/legacy builds keep `main.c` with the current Bridge and host
CLI behavior. The new, **not yet enabled for normal users**, `offline`
source mode selects `presence_offline.c` plus the same `presence_state.c`
business logic. It uses `mmwk_service_init`, a generation-protected
`mmwk_service_raw_subscribe` token and a consumer-selected 6432/6843 backend,
with `disable_external_raw_commands=true`. It has no Bridge network runtime,
MQTT, portal, CLI, or key/LED initialization in its application source.

It starts in `MMWK_SERVICE_START_HOST`: the radar itself must already have
approved firmware. Shipping an ESP resource partition alone does **not**
prove that the radar has been updated. The optional
`presence_offline_stop()` is an external-thread lifecycle example and must
not be called from a RAW callback. The current `build.sh` deliberately
refuses non-default presets until the actual v2 aggregate/lock and target
builds have passed; the source and mock-CMake tests do not lift that gate.
