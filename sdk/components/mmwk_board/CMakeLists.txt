# components/mmwk_board/CMakeLists.txt
# Provides IO definitions for different radar boards

# Select IO definition directory based on configured radar board
if (CONFIG_RADAR_BOARD_MINI)
    set(IODEF_DIR ${CMAKE_CURRENT_LIST_DIR}/io_def/mini)
elseif (CONFIG_RADAR_BOARD_RPI)
    set(IODEF_DIR ${CMAKE_CURRENT_LIST_DIR}/io_def/rpi)
elseif (CONFIG_RADAR_BOARD_PRO)
    set(IODEF_DIR ${CMAKE_CURRENT_LIST_DIR}/io_def/pro)
elseif (CONFIG_RADAR_BOARD_CFH)
    set(IODEF_DIR ${CMAKE_CURRENT_LIST_DIR}/io_def/cfh)
elseif (CONFIG_RADAR_BOARD_IOT)
    set(IODEF_DIR ${CMAKE_CURRENT_LIST_DIR}/io_def/iot)
elseif (CONFIG_RADAR_BOARD_WDR)
    set(IODEF_DIR ${CMAKE_CURRENT_LIST_DIR}/io_def/wdr)
endif()

idf_component_register(
    INCLUDE_DIRS
        "${IODEF_DIR}"
        "include"
)
