#!/usr/bin/env bash
# Flash/monitor a previously built presence example without the MMWK host CLI.
# Hardware selection is explicit; do not infer a board from a serial port name.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat >&2 <<'USAGE'
Usage:
  ./flash.sh presence mini|pro|wdr --port <device-port> [--preset default|offline] [--monitor]
  ./flash.sh presence mini|pro|wdr --port <device-port> [--preset default|offline] --monitor-only

Build first with ./build.sh presence <board> [--preset default|offline].
A flash checks the board/target configuration and the generated asset image.
The --monitor option monitors immediately after flashing; --monitor-only never flashes.
For both default and offline aggregate builds, flashing requires the matching
SDK manifest, board/preset/ABI lock and the exact first-config CMake cache.
Legacy default builds remain supported without an aggregate manifest.
Local-control and wifi-data remain disabled pending their source adapters.
USAGE
}

die() { echo "flash.sh: $*" >&2; exit 2; }

board=""; port=""; preset="default"; explicit_preset=0; action="flash"
if [[ "${1:-}" != presence || $# -lt 2 ]]; then usage; exit 2; fi
board="$2"; shift 2
case "$board" in mini|pro|wdr) ;; *) die "unsupported board: $board" ;; esac

while (($#)); do
    case "$1" in
        --port)
            (($# >= 2)) || die "--port requires a value"
            [[ -n "$2" && "$2" != -* ]] || die "invalid --port"
            [[ -z "$port" ]] || die "duplicate --port"
            port="$2"; shift 2 ;;
        --preset)
            (($# >= 2)) || die "--preset requires a value"
            ((explicit_preset == 0)) || die "duplicate --preset"
            preset="$2"; explicit_preset=1; shift 2 ;;
        --monitor)
            [[ "$action" == flash ]] || die "--monitor and --monitor-only are mutually exclusive"
            action="flash-monitor"; shift ;;
        --monitor-only)
            [[ "$action" == flash ]] || die "--monitor and --monitor-only are mutually exclusive"
            action="monitor"; shift ;;
        *) die "unknown argument: $1" ;;
    esac
done

[[ -n "$port" ]] || die "--port is mandatory; do not guess a serial device"
aggregate_manifest="$SCRIPT_DIR/../release-manifest.json"
aggregate_selected=0
aggregate_libs="$SCRIPT_DIR/../components/mmwk_sdk/lib"
if [[ ! -e "$aggregate_manifest" && ! -L "$aggregate_manifest" &&
      ( -e "$aggregate_libs/esp32" || -L "$aggregate_libs/esp32" ||
        -e "$aggregate_libs/esp32s3" || -L "$aggregate_libs/esp32s3" ) ]]; then
    die "aggregate SDK archives require a verified release manifest"
fi
if [[ -e "$aggregate_manifest" || -L "$aggregate_manifest" ]]; then
    [[ -f "$aggregate_manifest" && ! -L "$aggregate_manifest" ]] ||
        die "aggregate SDK manifest must be a regular file"
    aggregate_selected=1
fi
case "$preset" in
    default) ;;
    offline)
        [[ "$aggregate_selected" = 1 &&
           -f "$SCRIPT_DIR/presence/main/presence_offline.c" ]] ||
            die "preset 'offline' is not enabled without an aggregate SDK and native RAW consumer"
        ;;
    local-control|wifi-data)
        die "preset '$preset' is not enabled until the aggregate source adapter and actual target builds are verified" ;;
    *) die "unknown preset: $preset" ;;
esac

project_dir="$SCRIPT_DIR/presence"
build_dir="$SCRIPT_DIR/build/presence/$board"
if ((explicit_preset)); then build_dir="$build_dir/$preset"; fi
[[ -d "$project_dir" ]] || die "presence project missing"
[[ -d "$build_dir" ]] || die "build not found for board=$board preset=$preset: run build.sh first"
command -v idf.py >/dev/null 2>&1 || die "idf.py unavailable: initialize the pinned ESP-IDF environment"
command -v python3 >/dev/null 2>&1 || die "python3 unavailable"

stage1_args=()
if ((aggregate_selected)); then
    [[ -n "${MMWK_STAGE1_ABI:-}" ]] ||
        die "aggregate '$preset' flash requires MMWK_STAGE1_ABI"
    stage1_lock="${MMWK_STAGE1_LOCK_FILE:-$SCRIPT_DIR/../../mmwk-sdk.$board.$preset.lock.json}"
    [[ "$stage1_lock" = /* && -f "$stage1_lock" && ! -L "$stage1_lock" ]] ||
        die "aggregate '$preset' flash requires an existing absolute SDK lock"
    python3 "$SCRIPT_DIR/tools/mmwk_sdk_bundle.py" \
        --sdk-root "$SCRIPT_DIR/.." --board "$board" --preset "$preset" \
        --abi "$MMWK_STAGE1_ABI" --check-lock "$stage1_lock" ||
        die "aggregate SDK/asset/ABI lock invalid; refusing flash"
    stage1_args=(--stage1-preset "$preset" --stage1-abi "$MMWK_STAGE1_ABI"
                 --stage1-lock "$stage1_lock")
fi
python3 "$SCRIPT_DIR/tools/verify_presence_flash.py" \
    --build-dir "$build_dir" --board "$board" --action "$action" \
    "${stage1_args[@]}" || exit 2

case "$action" in
    flash)
        (cd "$project_dir"; idf.py -B "$build_dir" -p "$port" flash) ;;
    flash-monitor)
        (cd "$project_dir"; idf.py -B "$build_dir" -p "$port" flash monitor) ;;
    monitor)
        (cd "$project_dir"; idf.py -B "$build_dir" -p "$port" monitor) ;;
esac
