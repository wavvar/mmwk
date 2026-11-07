cmake_minimum_required(VERSION 3.16)
# Stage1 preset selection must be fixed before IDF component discovery.
# Never trust cached sdkconfig from another capability configuration.
if(DEFINED MMWK_STAGE1_PRESET AND DEFINED ENV{MMWK_STAGE1_PRESET} AND
   NOT "$ENV{MMWK_STAGE1_PRESET}" STREQUAL "" AND
   NOT "${MMWK_STAGE1_PRESET}" STREQUAL "$ENV{MMWK_STAGE1_PRESET}")
    message(FATAL_ERROR "presence: conflicting early/normal Stage1 preset")
endif()
if(NOT DEFINED MMWK_STAGE1_PRESET AND DEFINED ENV{MMWK_STAGE1_PRESET} AND
   NOT "$ENV{MMWK_STAGE1_PRESET}" STREQUAL "")
    set(MMWK_STAGE1_PRESET "$ENV{MMWK_STAGE1_PRESET}" CACHE STRING "Stage1 public capability preset")
endif()
if(DEFINED MMWK_STAGE1_PRESET AND
   NOT MMWK_STAGE1_PRESET MATCHES "^(offline|local-control|wifi-data|default)$")
    message(FATAL_ERROR "presence: unsupported Stage1 preset")
endif()

get_filename_component(MMWK_USER_SDK_ROOT "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)

set(MMWK_PRESENCE_ENABLE_TINYUSB 0)
set(MMWK_PRESENCE_WDR_ENABLED 0)
set(MMWK_PRESENCE_TINYUSB_CDC_ENABLED 0)
if(DEFINED SDKCONFIG_DEFAULTS)
    foreach(mmwk_presence_default ${SDKCONFIG_DEFAULTS})
        set(mmwk_presence_default_path "${mmwk_presence_default}")
        if(NOT IS_ABSOLUTE "${mmwk_presence_default_path}")
            get_filename_component(mmwk_presence_default_path
                                   "${CMAKE_CURRENT_LIST_DIR}/${mmwk_presence_default}"
                                   ABSOLUTE)
        endif()

        if(EXISTS "${mmwk_presence_default_path}")
            file(STRINGS "${mmwk_presence_default_path}"
                 mmwk_presence_wdr_lines
                 REGEX "^CONFIG_RADAR_BOARD_WDR=y$")
            if(mmwk_presence_wdr_lines)
                set(MMWK_PRESENCE_WDR_ENABLED 1)
            endif()

            file(STRINGS "${mmwk_presence_default_path}"
                 mmwk_presence_tinyusb_cdc_lines
                 REGEX "^CONFIG_TINYUSB_CDC_ENABLED=y$")
            if(mmwk_presence_tinyusb_cdc_lines)
                set(MMWK_PRESENCE_TINYUSB_CDC_ENABLED 1)
            endif()
        endif()
    endforeach()
endif()

if(MMWK_PRESENCE_WDR_ENABLED AND MMWK_PRESENCE_TINYUSB_CDC_ENABLED)
    set(MMWK_PRESENCE_ENABLE_TINYUSB 1)
endif()

# Offline mode must not implicitly claim WDR USB, modem or network resources.
if(DEFINED MMWK_STAGE1_PRESET AND MMWK_STAGE1_PRESET STREQUAL "offline")
    set(MMWK_PRESENCE_ENABLE_TINYUSB 0)
endif()
set(ENV{MMWK_USB_ENABLE_TINYUSB} "${MMWK_PRESENCE_ENABLE_TINYUSB}")

set(COMPONENT_DIRS "$ENV{IDF_PATH}/components" "${CMAKE_CURRENT_LIST_DIR}/main" "${MMWK_USER_SDK_ROOT}/components")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(mmwk_presence_example)

# Firmware/config pairing is consumer-owned; the shipped SDK cannot
# infer the radar chip or choose a build from a neighboring checkout.
# An aggregate package already verifies its own SHA256-managed assets.
# It must not accidentally flash a different native firmware checkout.
set(MMWK_PRESENCE_AGGREGATE_ASSETS OFF)
set(_presence_manifest "${MMWK_USER_SDK_ROOT}/release-manifest.json")
if(IS_SYMLINK "${_presence_manifest}")
    message(FATAL_ERROR "presence: linked aggregate SDK manifest is forbidden")
elseif(EXISTS "${_presence_manifest}")
    set(MMWK_PRESENCE_AGGREGATE_ASSETS ON)
    set(MMWK_PUBLIC_RADAR_ROOT "${MMWK_USER_SDK_ROOT}/assets")
else()
    if(DEFINED MMWK_STAGE1_PRESET AND NOT MMWK_STAGE1_PRESET STREQUAL "default")
        message(FATAL_ERROR "presence: non-default capability requires a verified aggregate SDK")
    endif()
    set(MMWK_PUBLIC_RADAR_ROOT "${MMWK_USER_SDK_ROOT}/../firmwares/radar")
endif()
include("${CMAKE_CURRENT_LIST_DIR}/presence_asset_profiles.cmake")
presence_resolve_asset_profile("${MMWK_PUBLIC_RADAR_ROOT}")

# Never silently reuse stale SPIFFS sources from an earlier board/preset.
# Different source bytes use different output paths, with no destructive
# cleanup of previous firmware build evidence.
presence_resolve_asset_staging_dir(
    "${CMAKE_BINARY_DIR}" "${PRESENCE_RADAR_FAMILY}"
    "${PRESENCE_RADAR_FW_SRC}" "${PRESENCE_RADAR_CFG_SRC}"
    PRESENCE_RADAR_ASSET_DIR)
if(IS_SYMLINK "${CMAKE_BINARY_DIR}/presence_assets" OR
   IS_SYMLINK "${CMAKE_BINARY_DIR}/presence_assets/${PRESENCE_RADAR_FAMILY}" OR
   IS_SYMLINK "${PRESENCE_RADAR_ASSET_DIR}")
    message(FATAL_ERROR "presence: linked generated asset staging directory forbidden")
endif()
file(MAKE_DIRECTORY "${PRESENCE_RADAR_ASSET_DIR}")
presence_validate_asset_staging(
    "${PRESENCE_RADAR_ASSET_DIR}"
    "${PRESENCE_RADAR_FW_NAME}"
    "${PRESENCE_RADAR_CFG_NAME}")
file(COPY "${PRESENCE_RADAR_FW_SRC}" DESTINATION "${PRESENCE_RADAR_ASSET_DIR}")
file(COPY "${PRESENCE_RADAR_CFG_SRC}" DESTINATION "${PRESENCE_RADAR_ASSET_DIR}")
# file(COPY) uses timestamp heuristics; verify actual staged bytes.
file(SHA256 "${PRESENCE_RADAR_FW_SRC}" _source_fw_sha)
file(SHA256 "${PRESENCE_RADAR_ASSET_DIR}/${PRESENCE_RADAR_FW_NAME}" _staged_fw_sha)
file(SHA256 "${PRESENCE_RADAR_CFG_SRC}" _source_cfg_sha)
file(SHA256 "${PRESENCE_RADAR_ASSET_DIR}/${PRESENCE_RADAR_CFG_NAME}" _staged_cfg_sha)
if(NOT _source_fw_sha STREQUAL _staged_fw_sha OR
   NOT _source_cfg_sha STREQUAL _staged_cfg_sha)
    message(FATAL_ERROR "presence: SPIFFS staging does not match locked source firmware/config")
endif()
file(WRITE "${PRESENCE_RADAR_ASSET_DIR}/meta.json"
    "{\n"
    "  \"idx\": ${PRESENCE_RADAR_FID},\n"
    "  \"fws\": [\n"
    "    {\n"
    "      \"fid\": ${PRESENCE_RADAR_FID},\n"
    "      \"firmware\": \"${PRESENCE_RADAR_FW_NAME}\",\n"
    "      \"version\": \"${PRESENCE_RADAR_VERSION}\",\n"
    "      \"config\": \"${PRESENCE_RADAR_CFG_NAME}\",\n"
    "      \"wait\": true,\n"
    "      \"welcome\": true\n"
    "    }\n"
    "  ]\n"
    "}\n")

spiffs_create_partition_image(assets "${PRESENCE_RADAR_ASSET_DIR}" FLASH_IN_PROJECT)
