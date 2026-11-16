#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat >&2 <<'EOF'
Usage:
  ./build.sh presence mini|pro|wdr|all [--preset default|offline|local-control|wifi-data]
  ./build.sh all
Legacy invocation without --preset remains supported.
EOF
}

idf_target_for_board() {
    case "$1" in
        mini) echo "esp32" ;;
        pro|wdr) echo "esp32s3" ;;
        *) return 1 ;;
    esac
}

require_preset_ready() {
    local preset="$1"
    if [[ "$preset" = default ]]; then
        return 0
    fi
    # Do NOT silently build a full legacy image under an 'offline' label.
    # The current public package still contains per-board archives and its
    # presence source does not yet implement static feature assembly.
    if [[ ! -f "${SCRIPT_DIR}/../release-manifest.json" ||
          ! -f "${SCRIPT_DIR}/presence/main/presence_stage1.c" ]]; then
        echo "Preset '$preset' requires a verified arch_v2 aggregate package and migrated presence sources; this checkout still has legacy SDK assets." >&2
        return 2
    fi
    # When the v2 package and migrated presence exist, a full independent
    # manifest/lock preflight will be required before this is enabled.
    echo "Preset '$preset' is not enabled until the v2 manifest/lock and 12 build proofs are integrated." >&2
    return 2
}

build_presence_board() {
    local board="$1" preset="$2" explicit="$3"
    local target
    target="$(idf_target_for_board "$board")" || {
        echo "Unsupported board: $board" >&2
        return 1
    }
    require_preset_ready "$preset" || return $?

    local project_dir="${SCRIPT_DIR}/presence"
    local build_dir="${SCRIPT_DIR}/build/presence/$board"
    if [[ "$explicit" = 1 ]]; then
        build_dir="$build_dir/$preset"
    fi
    local sdkconfig_path="$build_dir/sdkconfig"
    local sdkconfig_defaults="sdkconfig.defaults;sdkconfig.defaults.$board"

    (
        cd "$project_dir"
        idf.py -B "$build_dir" \
            -D "SDKCONFIG=$sdkconfig_path" \
            -D "SDKCONFIG_DEFAULTS=$sdkconfig_defaults" \
            set-target "$target" build
    )
}

build_presence() {
    local board="$1" preset="$2" explicit="$3"
    case "$board" in
        mini|pro|wdr) build_presence_board "$board" "$preset" "$explicit" ;;
        all)
            build_presence_board mini "$preset" "$explicit"
            build_presence_board pro "$preset" "$explicit"
            build_presence_board wdr "$preset" "$explicit"
            ;;
        *) echo "Unsupported presence target: $board" >&2; usage; return 1 ;;
    esac
}

main() {
    local example="${1:-}" target="${2:-}" preset=default explicit=0
    if [[ "$example" = all && $# -eq 1 ]]; then
        build_presence all default 0
        return
    fi
    if [[ "$example" != presence || -z "$target" ]]; then
        usage
        return 1
    fi
    if [[ $# -eq 4 && "$3" = --preset ]]; then
        preset="$4"
        explicit=1
    elif [[ $# -ne 2 ]]; then
        usage
        return 1
    fi
    case "$preset" in
        default|offline|local-control|wifi-data) ;;
        *) echo "Unknown preset: $preset" >&2; usage; return 1 ;;
    esac
    build_presence "$target" "$preset" "$explicit"
}

main "$@"
