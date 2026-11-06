# The same presence_state.c business logic is shared by the old Bridge app and
# the new isolated offline RAW app. Never compile two app_main definitions.
# Reject unsupported mode selection even when idf.py is invoked directly:
# build.sh's gate is not a substitute for an actual component-level guard.
if(DEFINED MMWK_STAGE1_PRESET AND
   MMWK_STAGE1_PRESET MATCHES "^(local-control|wifi-data)$")
    message(FATAL_ERROR
        "presence: ${MMWK_STAGE1_PRESET} source adapter is not implemented; "
        "refusing to build the legacy Bridge as another capability mode")
endif()
if(DEFINED MMWK_STAGE1_PRESET AND MMWK_STAGE1_PRESET STREQUAL "offline")
    idf_component_register(
        SRCS "presence_offline.c" "presence_state.c" "presence_radar_assets.c"
        REQUIRES mmwk_sdk mmwk_board json esp_timer)
else()
    idf_component_register(
        SRCS "main.c" "presence_state.c" "presence_cli.c"
             "presence_radar_assets.c" "presence_ui.c"
        REQUIRES mmwk_sdk mmwk_board json esp_driver_gpio)
endif()
