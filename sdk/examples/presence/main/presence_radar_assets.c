#include "presence_radar_assets.h"

#include "sdkconfig.h"

const char *presence_radar_firmware_path(void)
{
#if CONFIG_RADAR_BOARD_WDR
    return "/assets/presence.appimage";
#else
    return "/assets/out_of_box_6843_aop.bin";
#endif
}

const char *presence_radar_config_path(void)
{
#if CONFIG_RADAR_BOARD_WDR
    return "/assets/presence.cfg";
#else
    return "/assets/out_of_box_6843_aop.cfg";
#endif
}
