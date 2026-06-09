# Determine source files and include directories based on board type
set(BOARD_SRCS "")
set(BOARD_INCLUDE_DIRS "")

# Always set include directories so board.h can be found
if (CONFIG_RADAR_BOARD_MINI)
    set(BOARD_INCLUDE_DIRS "./mini")
    if(CONFIG_RADAR_BOARD_AUDIO_ENABLED)
        set(BOARD_SRCS
                "./mini/board.c"
                "./mini/board_pins_config.c"
        )
    endif()
endif()

if (CONFIG_RADAR_BOARD_RPI)
    set(BOARD_INCLUDE_DIRS "./rpi")
    if(CONFIG_RADAR_BOARD_AUDIO_ENABLED)
        set(BOARD_SRCS
                "./rpi/board.c"
                "./rpi/board_pins_config.c"
        )
    endif()
endif()

if (CONFIG_RADAR_BOARD_PRO)
    set(BOARD_INCLUDE_DIRS "./pro")
    if(CONFIG_RADAR_BOARD_AUDIO_ENABLED)
        set(BOARD_SRCS
                "./pro/board.c"
                "./pro/board_pins_config.c"
        )
    endif()
endif()

if (CONFIG_RADAR_BOARD_CFH)
    set(BOARD_INCLUDE_DIRS "./cfh")
    if(CONFIG_RADAR_BOARD_AUDIO_ENABLED)
        set(BOARD_SRCS
                "./cfh/board.c"
                "./cfh/board_pins_config.c"
        )
    endif()
endif()

if (CONFIG_RADAR_BOARD_WDR)
    set(BOARD_INCLUDE_DIRS "./wdr")
    if(CONFIG_RADAR_BOARD_AUDIO_ENABLED)
        set(BOARD_SRCS
                "./wdr/board.c"
                "./wdr/board_pins_config.c"
        )
    endif()
endif()

# Always register the component with board.h available to all components
# The INCLUDE_DIRS are public and available to all components that depend on this one
if(CONFIG_RADAR_BOARD_AUDIO_ENABLED)
    # Register with full audio dependencies and source files
    idf_component_register(
        SRCS ${BOARD_SRCS}
        INCLUDE_DIRS ${BOARD_INCLUDE_DIRS}
        REQUIRES mmwk_board audio_hal audio_sal audio_board esp_peripherals
        PRIV_REQUIRES esp_dispatcher display_service esp_lcd_ili9341
    )
else()
    # Register with minimal dependencies, just to provide board.h to other components
    # Still need audio_hal because board.h includes audio_hal.h
    idf_component_register(
        INCLUDE_DIRS ${BOARD_INCLUDE_DIRS}
        REQUIRES mmwk_board audio_hal audio_sal audio_board esp_peripherals
    )
endif()

# Make sure the board include directory is available to esp_peripherals component
# This is needed because esp_peripherals tries to include "board.h"
target_include_directories(${COMPONENT_LIB} INTERFACE ${BOARD_INCLUDE_DIRS})

# Link ADF components that include "board.h" to this component, so they inherit our include dirs
# This avoids having to modify top-level CMakeLists or ADF components
set(_audio_dep_components esp_peripherals audio_hal display_service dueros_service input_key_service)
foreach(_dep ${_audio_dep_components})
    idf_component_get_property(_dep_lib ${_dep} COMPONENT_LIB)
    if(_dep_lib)
        target_link_libraries(${_dep_lib} PRIVATE ${COMPONENT_LIB})
    endif()
endforeach()
