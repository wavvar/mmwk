# MMWK User SDK

This tree is the canonical source for the public MMWK user SDK before it is
published into the sibling distribution repository. Keep examples and SDK-facing
content here independent from private checkout paths so the published SDK can
build from its own `sdk/` directory.

The board-specific archive layout below describes the **legacy/default
release**, not an already completed Stage1 aggregate. The `arch_v2`
development candidate aims for one ESP32 archive (MINI) and one shared
ESP32-S3 archive (PRO/WDR), with board-config ABI v2 and explicit capability
presets. Final Xtensa ELF pruning, all 12 consumer builds and full device
acceptance are still **unverified**. See
[Stage1 preview](../docs/en/sdk-arch-v2-preview.md) for transition gates.

The published SDK boundary is:

- `components/mmwk_board/` is published as source and provides board IO
  definitions needed by public examples.
- `components/mmwk_sdk/` is published as headers plus one board-selected static
  library:

  ```text
  components/mmwk_sdk/
    CMakeLists.txt
    include/
      mmwk_sensor.h
      mmwk_service.h
      mmwk_sensor_raw.h
      mmwk_driver.h
      mmwk_cat1.h
    lib/
      mini/libmmwk_sdk.a
      pro/libmmwk_sdk.a
      wdr/libmmwk_sdk.a
  ```

- `examples/` contains standalone ESP-IDF projects that use only the published
  SDK component boundary.
- Private firmware projects, local validation helpers, build output, caches,
  and unpublished component source are not part of the public SDK surface.

## Build The Presence Example

From `sdk/examples` after publish, or from `projects/mmwk_user_sdk/examples` in
this checkout, run:

```bash
./build.sh presence mini
./build.sh presence pro
./build.sh presence wdr
./build.sh presence all
./build.sh all
```

The example build script selects the ESP-IDF target for each board and writes
board-specific output under `build/presence/<board>`.

The presence example depends on `mmwk_sdk`, `mmwk_board`, and ESP-IDF public
components only. It does not depend on private component source from this
checkout. Its presence state is intentionally a minimal demonstration: raw
radar frames only refresh an example status flag. Real products should decode
radar frames and derive presence from targets, point clouds, tracks, or another
application-specific signal before reporting a presence result.

## Direct ESP-IDF flash and monitor (no host CLI)

The supported presence project includes a radar `assets` SPIFFS image via
`spiffs_create_partition_image(... FLASH_IN_PROJECT)`. After building,
identify the **actual physical board** and use its own serial port:

```sh
cd sdk/examples
./build.sh presence mini
bash flash.sh presence mini --port /dev/ttyUSB0 --monitor
# Monitor only (does not flash):
bash flash.sh presence mini --port /dev/ttyUSB0 --monitor-only
```

The flash preflight checks the selected board/ESP target, size optimization,
`flasher_args.json`, application image and `assets.bin`; it refuses an
incomplete first-flash partition set. With an aggregate SDK installed, **both
default and offline** flashes recheck the exact board/preset/ABI manifest lock
and build CMake cache. Returning to a legacy package does not permit flashing
an old aggregate-built image. For an explicit `--preset default`
build, repeat the same preset when flashing. Other new presets remain
unavailable until the aggregate SDK is verified. Details:
[stage1 preview](../docs/en/sdk-arch-v2-preview.md).

## Offline host regression (no IDF target or hardware)

From the `arch_v2` repository root:

```sh
bash sdk/examples/tests/run_host_checks.sh
```

The host suite exercises the public example's C/CMake source, firmware/config
pairing, consumer package locks, and direct-flash preflight with a simulated
`idf.py`. It never flashes hardware, runs a target build, invokes CI or
publishes to another branch. Software and device acceptance are tracked in
`mmwk_sdk` PR #70.

### RAW callback and CLI concurrency

The native presence sample now shares the same lock-protected presence state
as the SDK's legacy/internal host example. The RAW worker updates counters
under a FreeRTOS spinlock; CLI readers obtain a consistent snapshot before
formatting JSON. `test_presence_state_concurrency.py` executes the actual
public C source with host pthreads and validates that untrusted timeout
values (NaN, fractions, out-of-range) are rejected. This is a host concurrency
contract, **not** ESP target timing or hardware acceptance.

In aggregate mode, presence flashes only the SDK-managed `assets/radar68xx`
or `assets/radarl64xx` firmware/config pair. Legacy/default mode continues
to use its native `firmwares/radar` tree. A missing package asset never falls
back to another native firmware image.
