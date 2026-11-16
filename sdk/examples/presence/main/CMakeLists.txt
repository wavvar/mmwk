# The same presence_state.c business logic is shared by the old Bridge app and
# the new isolated offline RAW app. Never compile two app_main definitions.
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
