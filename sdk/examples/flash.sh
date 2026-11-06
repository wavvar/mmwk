#!/usr/bin/env bash
# Flash/monitor a previously built presence example without the MMWK host CLI.
# Hardware selection is explicit; do not infer a board from a serial port name.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat >&2 <<'USAGE'
Usage:
  ./flash.sh presence mini|pro|wdr --port <device-port> [--preset default] [--monitor]
  ./flash.sh presence mini|pro|wdr --port <device-port> [--preset default] --monitor-only

Build first with ./build.sh presence <board> [--preset default].
A flash checks the board/target configuration and the generated asset image.
The --monitor option monitors immediately after flashing; --monitor-only never flashes.
Non-default presets stay disabled until aggregate SDK and source migration pass target validation.
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
case "$preset" in
    default) ;;
    offline|local-control|wifi-data)
        die "preset '$preset' is not enabled until the aggregate archive and actual target builds are verified" ;;
    *) die "unknown preset: $preset" ;;
esac

project_dir="$SCRIPT_DIR/presence"
build_dir="$SCRIPT_DIR/build/presence/$board"
if ((explicit_preset)); then build_dir="$build_dir/$preset"; fi
[[ -d "$project_dir" ]] || die "presence project missing"
[[ -d "$build_dir" ]] || die "build not found for board=$board preset=$preset: run build.sh first"
command -v idf.py >/dev/null 2>&1 || die "idf.py unavailable: initialize the pinned ESP-IDF environment"
command -v python3 >/dev/null 2>&1 || die "python3 unavailable"

python3 "$SCRIPT_DIR/tools/verify_presence_flash.py" \
    --build-dir "$build_dir" --board "$board" --action "$action" || exit 2

case "$action" in
    flash)
        (cd "$project_dir"; idf.py -B "$build_dir" -p "$port" flash) ;;
    flash-monitor)
        (cd "$project_dir"; idf.py -B "$build_dir" -p "$port" flash monitor) ;;
    monitor)
        (cd "$project_dir"; idf.py -B "$build_dir" -p "$port" monitor) ;;
esac
