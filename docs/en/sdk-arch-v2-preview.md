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
