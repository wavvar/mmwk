#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat >&2 <<'EOF'
Usage:
  ./build.sh presence mini
  ./build.sh presence pro
  ./build.sh presence wdr
  ./build.sh presence all
  ./build.sh all
EOF
}

idf_target_for_board() {
    case "$1" in
        mini) echo "esp32" ;;
        pro|wdr) echo "esp32s3" ;;
        *) return 1 ;;
    esac
}

build_presence_board() {
    local board="$1"
    local target
    target="$(idf_target_for_board "${board}")" || {
        echo "Unsupported board: ${board}" >&2
        return 1
    }

    local project_dir="${SCRIPT_DIR}/presence"
    local build_dir="${SCRIPT_DIR}/build/presence/${board}"
    local sdkconfig_path="${build_dir}/sdkconfig"
    local sdkconfig_defaults="sdkconfig.defaults;sdkconfig.defaults.${board}"

    (
        cd "${project_dir}"
        idf.py \
            -B "${build_dir}" \
            -D "SDKCONFIG=${sdkconfig_path}" \
            -D "SDKCONFIG_DEFAULTS=${sdkconfig_defaults}" \
            set-target "${target}" \
            build
    )
}

build_presence() {
    case "$1" in
        mini|pro|wdr)
            build_presence_board "$1"
            ;;
        all)
            build_presence_board mini
            build_presence_board pro
            build_presence_board wdr
            ;;
        *)
            echo "Unsupported presence target: $1" >&2
            usage
            return 1
            ;;
    esac
}

main() {
    local example="${1:-}"
    local target="${2:-}"

    case "${example}" in
        presence)
            if [[ -z "${target}" ]]; then
                usage
                return 1
            fi
            build_presence "${target}"
            ;;
        all)
            if [[ -n "${target}" ]]; then
                usage
                return 1
            fi
            build_presence all
            ;;
        *)
            usage
            return 1
            ;;
    esac
}

main "$@"
