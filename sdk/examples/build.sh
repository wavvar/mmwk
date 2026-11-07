#!/usr/bin/env bash
# Consumer-owned presence build. Legacy default remains unchanged when no v2
# manifest exists; other presets never silently fall back to full legacy.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat >&2 <<'EOF'
Usage:
  ./build.sh presence mini|pro|wdr|all [--preset default|offline|local-control|wifi-data]
  ./build.sh all
Legacy default works without a v2 bundle. For v2, set MMWK_STAGE1_ABI and
create one board+preset lock per selection, or set MMWK_STAGE1_LOCK_FILE.
EOF
}

idf_target_for_board() {
    case "$1" in
        mini) echo esp32 ;;
        pro|wdr) echo esp32s3 ;;
        *) return 1 ;;
    esac
}

require_preset_ready() {
    local board="$1" preset="$2"
    local sdk_root="${SCRIPT_DIR}/.."
    MMWK_STAGE1_BUILD_MODE=legacy
    MMWK_STAGE1_SELECTED_LOCK=""
    local manifest="$sdk_root/release-manifest.json"
    local libs="$sdk_root/components/mmwk_sdk/lib"
    if [[ -L "$manifest" || ( -e "$manifest" && ! -f "$manifest" ) ]]; then
        echo "Invalid SDK release manifest; refusing an implicit legacy fallback." >&2
        return 2
    fi
    if [[ ! -f "$manifest" ]]; then
        # An incomplete aggregate package must never be treated as a valid
        # legacy SDK just because its release-manifest.json disappeared.
        if [[ -e "$libs/esp32" || -L "$libs/esp32" ||
              -e "$libs/esp32s3" || -L "$libs/esp32s3" ]]; then
            echo "Aggregate SDK archives require a verified release manifest." >&2
            return 2
        fi
        if [[ "$preset" = default ]]; then return 0; fi
        echo "Stage1 '$preset' requires a verified aggregate package, not legacy archives." >&2
        return 2
    fi
    if [[ "$preset" = local-control || "$preset" = wifi-data ]]; then
        echo "Stage1 '$preset' presence adapter is not ready; refusing a false build." >&2
        return 2
    fi
    if [[ "$preset" = offline && ! -f "${SCRIPT_DIR}/presence/main/presence_offline.c" ]]; then
        echo "Stage1 offline RAW consumer source is missing." >&2
        return 2
    fi
    if [[ -z "${MMWK_STAGE1_ABI:-}" ]]; then
        echo "Set MMWK_STAGE1_ABI to the verified archive ABI in release-manifest.json." >&2
        return 2
    fi
    local lock="${MMWK_STAGE1_LOCK_FILE:-${SCRIPT_DIR}/../../mmwk-sdk.${board}.${preset}.lock.json}"
    if [[ "$lock" != /* || ! -f "$lock" || -L "$lock" ]]; then
        echo "Missing absolute lock: $lock. Create it using sdk/examples/tools/mmwk_sdk_bundle.py." >&2
        return 2
    fi
    if ! python3 "${SCRIPT_DIR}/tools/mmwk_sdk_bundle.py" \
        --sdk-root "$sdk_root" --board "$board" --preset "$preset" \
        --abi "$MMWK_STAGE1_ABI" --check-lock "$lock"; then
        echo "Stage1 aggregate manifest/ABI/asset/lock preflight rejected the build." >&2
        return 2
    fi
    MMWK_STAGE1_BUILD_MODE=aggregate
    # Keep the caller lock override intact for multi-board selection.
    MMWK_STAGE1_SELECTED_LOCK="$lock"
    export MMWK_STAGE1_PRESET="$preset"
    export MMWK_STAGE1_BOARD="$board"
}

preflight_presence_cache() {
    local board="$1" preset="$2" explicit="$3"
    local build_dir="${SCRIPT_DIR}/build/presence/$board"
    if [[ "$explicit" = 1 ]]; then build_dir="$build_dir/$preset"; fi
    local cache="$build_dir/CMakeCache.txt"
    if [[ -L "$build_dir" || -L "$cache" ]]; then
        echo "Refusing linked presence build directory or CMake cache." >&2
        return 2
    fi
    # An old bundle cannot silently reuse a cached aggregate board/ABI/lock.
    if [[ "$MMWK_STAGE1_BUILD_MODE" = legacy && -f "$cache" ]] &&
       grep -Eq '^MMWK_STAGE1_(BOARD|ABI|LOCK_FILE):[^=]*=|^MMWK_STAGE1_PRESET:[^=]*=(offline|local-control|wifi-data)$' "$cache"; then
        echo "Legacy SDK cannot reuse aggregate Stage1 CMake cache; select a fresh output directory." >&2
        return 2
    fi
    if [[ "$MMWK_STAGE1_BUILD_MODE" = aggregate && -f "$cache" ]]; then
        # Reuse the exact flash-side cache contract before idf.py can rewrite
        # a prior aggregate build (preset/board/ABI/lock are all immutable).
        if ! python3 -B -c '
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from verify_presence_flash import check_stage1_cache
check_stage1_cache(Path(sys.argv[2]), sys.argv[3], sys.argv[4],
                   sys.argv[5], Path(sys.argv[6]))
' "$SCRIPT_DIR/tools" "$build_dir" "$board" "$preset" \
  "$MMWK_STAGE1_ABI" "$MMWK_STAGE1_SELECTED_LOCK"; then
            echo "Aggregate SDK build cache differs from selected board/preset/ABI/lock; use a fresh output directory." >&2
            return 2
        fi
    fi
}

build_presence_board() {
    local board="$1" preset="$2" explicit="$3" target
    target="$(idf_target_for_board "$board")" || {
        echo "Unsupported board: $board" >&2
        return 1
    }
    require_preset_ready "$board" "$preset" || return $?
    local project_dir="${SCRIPT_DIR}/presence"
    local build_dir="${SCRIPT_DIR}/build/presence/$board"
    if [[ "$explicit" = 1 ]]; then build_dir="$build_dir/$preset"; fi
    local sdkconfig_path="$build_dir/sdkconfig"
    local sdkconfig_defaults="sdkconfig.defaults;sdkconfig.defaults.$board"
    preflight_presence_cache "$board" "$preset" "$explicit" || return $?
    (
        cd "$project_dir"
        local -a stage1_args=()
        if [[ "$MMWK_STAGE1_BUILD_MODE" = aggregate ]]; then
            export MMWK_STAGE1_LOCK_FILE="$MMWK_STAGE1_SELECTED_LOCK"
            stage1_args=(-D "MMWK_STAGE1_PRESET=$preset"
                         -D "MMWK_STAGE1_BOARD=$board"
                         -D "MMWK_STAGE1_ABI=$MMWK_STAGE1_ABI"
                         -D "MMWK_STAGE1_LOCK_FILE=$MMWK_STAGE1_SELECTED_LOCK")
        else
            # Isolate legacy from inherited aggregate selections.
            export MMWK_STAGE1_PRESET=default
            unset MMWK_STAGE1_BOARD MMWK_STAGE1_LOCK_FILE MMWK_STAGE1_ABI
            stage1_args=(-D "MMWK_STAGE1_PRESET=default")
        fi
        idf.py -B "$build_dir" \
            -D "SDKCONFIG=$sdkconfig_path" \
            -D "SDKCONFIG_DEFAULTS=$sdkconfig_defaults" \
            "${stage1_args[@]}" set-target "$target" build
    )
}

build_presence() {
    local board="$1" preset="$2" explicit="$3"
    case "$board" in
        mini|pro|wdr) build_presence_board "$board" "$preset" "$explicit" ;;
        all)
            for check_board in mini pro wdr; do
                require_preset_ready "$check_board" "$preset" || return $?
                preflight_presence_cache "$check_board" "$preset" "$explicit" || return $?
            done
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
