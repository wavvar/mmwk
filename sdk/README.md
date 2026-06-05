# MMWK User SDK

This tree is the canonical source for the public MMWK user SDK before it is
published into the sibling distribution repository. Keep examples and SDK-facing
content here independent from private checkout paths so the published SDK can
build from its own `sdk/` directory.

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
