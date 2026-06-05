cmake_minimum_required(VERSION 3.16)
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

set(ENV{MMWK_USB_ENABLE_TINYUSB} "${MMWK_PRESENCE_ENABLE_TINYUSB}")

set(COMPONENT_DIRS "$ENV{IDF_PATH}/components" "${CMAKE_CURRENT_LIST_DIR}/main" "${MMWK_USER_SDK_ROOT}/components")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(mmwk_presence_example)

set(MMWK_PUBLIC_RADAR_ROOT "${MMWK_USER_SDK_ROOT}/../firmwares/radar")
set(MMWK_PUBLIC_IWR6843_OOB_DIR "${MMWK_USER_SDK_ROOT}/../firmwares/radar/iwr6843/oob")
set(MMWK_PUBLIC_IWRL6432_PRESENCE_DIR "${MMWK_USER_SDK_ROOT}/../firmwares/radar/iwrl6432/presence")
if(NOT EXISTS "${MMWK_PUBLIC_RADAR_ROOT}")
    get_filename_component(MMWK_PRIVATE_REPO_ROOT "${MMWK_USER_SDK_ROOT}/../.." ABSOLUTE)
    set(MMWK_PUBLIC_RADAR_ROOT "${MMWK_PRIVATE_REPO_ROOT}/../mmwk/firmwares/radar")
    set(MMWK_PUBLIC_IWR6843_OOB_DIR "${MMWK_PUBLIC_RADAR_ROOT}/iwr6843/oob")
    set(MMWK_PUBLIC_IWRL6432_PRESENCE_DIR "${MMWK_PUBLIC_RADAR_ROOT}/iwrl6432/presence")
endif()

set(PRESENCE_RADAR_ASSET_DIR "${CMAKE_BINARY_DIR}/presence_assets")
file(MAKE_DIRECTORY "${PRESENCE_RADAR_ASSET_DIR}")

if(CONFIG_RADAR_BOARD_WDR)
    set(PRESENCE_RADAR_FW_SRC "${MMWK_PUBLIC_IWRL6432_PRESENCE_DIR}/presence.appimage")
    set(PRESENCE_RADAR_CFG_SRC "${MMWK_PUBLIC_IWRL6432_PRESENCE_DIR}/presence.cfg")
    set(PRESENCE_RADAR_FW_NAME "presence.appimage")
    set(PRESENCE_RADAR_CFG_NAME "presence.cfg")
    set(PRESENCE_RADAR_VERSION "xWRL6432 MMW Demo 05.05.03.00")
    set(PRESENCE_RADAR_FID 1)
else()
    set(PRESENCE_RADAR_FW_SRC "${MMWK_PUBLIC_IWR6843_OOB_DIR}/out_of_box_6843_aop.bin")
    set(PRESENCE_RADAR_CFG_SRC "${MMWK_PUBLIC_IWR6843_OOB_DIR}/out_of_box_6843_aop.cfg")
    set(PRESENCE_RADAR_FW_NAME "out_of_box_6843_aop.bin")
    set(PRESENCE_RADAR_CFG_NAME "out_of_box_6843_aop.cfg")
    set(PRESENCE_RADAR_VERSION "03.06.00.00")
    set(PRESENCE_RADAR_FID 2)
endif()

if(NOT EXISTS "${PRESENCE_RADAR_FW_SRC}")
    message(FATAL_ERROR "Presence radar firmware asset not found: ${PRESENCE_RADAR_FW_SRC}")
endif()
if(NOT EXISTS "${PRESENCE_RADAR_CFG_SRC}")
    message(FATAL_ERROR "Presence radar config asset not found: ${PRESENCE_RADAR_CFG_SRC}")
endif()

file(COPY "${PRESENCE_RADAR_FW_SRC}" DESTINATION "${PRESENCE_RADAR_ASSET_DIR}")
file(COPY "${PRESENCE_RADAR_CFG_SRC}" DESTINATION "${PRESENCE_RADAR_ASSET_DIR}")
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
