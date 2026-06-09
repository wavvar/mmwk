set(mmwk_sdk_board "")
set(mmwk_sdk_enable_tinyusb 0)
set(mmwk_sdk_requires
    mmwk_board
    json
    mqtt
    mbedtls
    app_update
    nvs_flash
    spiffs
    esp_timer
    esp_wifi
    esp_app_format
    esp_http_client
    esp_http_server
    esp_event
    esp_netif
    lwip
    driver
    esp_driver_gpio
    esp_driver_ledc
    esp_driver_uart
    esp_driver_spi
    esp_ringbuf
    usb
    freertos
    log
    espressif__led_indicator
    espressif__mdns
)

if("$ENV{MMWK_USB_ENABLE_TINYUSB}" STREQUAL "1")
    set(mmwk_sdk_enable_tinyusb 1)
endif()

if(CMAKE_BUILD_EARLY_EXPANSION)
    set(mmwk_sdk_config_paths "")

    idf_build_get_property(mmwk_sdk_sdkconfig SDKCONFIG)
    if(EXISTS "${mmwk_sdk_sdkconfig}")
        list(APPEND mmwk_sdk_config_paths "${mmwk_sdk_sdkconfig}")
    endif()

    idf_build_get_property(mmwk_sdk_sdkconfig_defaults SDKCONFIG_DEFAULTS)
    foreach(mmwk_sdk_sdkconfig_default IN LISTS mmwk_sdk_sdkconfig_defaults)
        if(EXISTS "${mmwk_sdk_sdkconfig_default}")
            list(APPEND mmwk_sdk_config_paths "${mmwk_sdk_sdkconfig_default}")
        endif()
    endforeach()

    foreach(mmwk_sdk_config_path IN LISTS mmwk_sdk_config_paths)
        if(EXISTS "${mmwk_sdk_config_path}")
            file(STRINGS "${mmwk_sdk_config_path}" mmwk_sdk_board_lines
                REGEX "^CONFIG_RADAR_BOARD_(MINI|PRO|WDR)=y$")
            foreach(mmwk_sdk_board_line IN LISTS mmwk_sdk_board_lines)
                if("${mmwk_sdk_board_line}" STREQUAL "CONFIG_RADAR_BOARD_MINI=y")
                    set(mmwk_sdk_board "mini")
                elseif("${mmwk_sdk_board_line}" STREQUAL "CONFIG_RADAR_BOARD_PRO=y")
                    set(mmwk_sdk_board "pro")
                elseif("${mmwk_sdk_board_line}" STREQUAL "CONFIG_RADAR_BOARD_WDR=y")
                    set(mmwk_sdk_board "wdr")
                endif()
            endforeach()
        endif()
    endforeach()
else()
    if(CONFIG_RADAR_BOARD_MINI)
        set(mmwk_sdk_board "mini")
    elseif(CONFIG_RADAR_BOARD_PRO)
        set(mmwk_sdk_board "pro")
    elseif(CONFIG_RADAR_BOARD_WDR)
        set(mmwk_sdk_board "wdr")
    endif()
endif()

if(NOT mmwk_sdk_board)
    message(FATAL_ERROR "mmwk_sdk: unsupported SDK board selection")
endif()

if("${mmwk_sdk_board}" STREQUAL "wdr" AND mmwk_sdk_enable_tinyusb)
    list(APPEND mmwk_sdk_requires espressif__esp_tinyusb)
endif()

set(mmwk_sdk_library "${CMAKE_CURRENT_LIST_DIR}/lib/${mmwk_sdk_board}/libmmwk_sdk.a")
if(NOT EXISTS "${mmwk_sdk_library}")
    message(FATAL_ERROR "mmwk_sdk: missing SDK library: ${mmwk_sdk_library}")
endif()

idf_component_register(
    INCLUDE_DIRS "include"
    REQUIRES ${mmwk_sdk_requires}
)

target_compile_definitions(${COMPONENT_LIB} INTERFACE
    CONFIG_MMWK_SDK_RAW_ONLY=1
)

add_prebuilt_library(mmwk_sdk_prebuilt "${mmwk_sdk_library}" PRIV_REQUIRES ${mmwk_sdk_requires})

set(mmwk_sdk_link_group
    "-Wl,--start-group"
    mmwk_sdk_prebuilt
    idf::mmwk_board
    idf::json
    idf::mqtt
    idf::mbedtls
    idf::app_update
    idf::nvs_flash
    idf::spiffs
    idf::esp_timer
    idf::esp_wifi
    idf::esp_app_format
    idf::esp_http_client
    idf::esp_http_server
    idf::esp_event
    idf::esp_netif
    idf::lwip
    idf::driver
    idf::esp_driver_gpio
    idf::esp_driver_ledc
    idf::esp_driver_uart
    idf::esp_driver_spi
    idf::esp_ringbuf
    idf::usb
    idf::freertos
    idf::log
    idf::espressif__led_indicator
    idf::espressif__mdns
)

if("${mmwk_sdk_board}" STREQUAL "wdr" AND mmwk_sdk_enable_tinyusb)
    list(APPEND mmwk_sdk_link_group idf::espressif__esp_tinyusb)
endif()

list(APPEND mmwk_sdk_link_group "-Wl,--end-group")

target_link_libraries(${COMPONENT_LIB} INTERFACE ${mmwk_sdk_link_group})
