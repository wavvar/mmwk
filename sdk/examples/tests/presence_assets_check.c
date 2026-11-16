#include "presence_radar_assets.h"
#include <assert.h>
#include <string.h>
int main(void) {
    const presence_radar_asset_pair_t *p = (const presence_radar_asset_pair_t *)1;
    assert(presence_radar_assets_select("MINI","esp32",6843,"radar68xx",&p)==0);
    assert(p && strcmp(p->firmware_path,"/assets/out_of_box_6843_aop.bin")==0);
    assert(presence_radar_assets_select("PRO","esp32s3",6843,"radar68xx",&p)==0);
    assert(p && strcmp(p->config_path,"/assets/out_of_box_6843_aop.cfg")==0);
    assert(presence_radar_assets_select("WDR","esp32s3",6432,"radarl64xx",&p)==0);
    assert(p && strcmp(p->firmware_path,"/assets/presence.appimage")==0);
    assert(presence_radar_assets_select("WDR","esp32s3",6843,"radarl64xx",&p)!=0 && !p);
    assert(presence_radar_assets_select("WDR","esp32",6432,"radarl64xx",&p)!=0 && !p);
    assert(presence_radar_assets_select("PRO","esp32s3",6843,"radarl64xx",&p)!=0 && !p);
    assert(presence_radar_assets_select("UNKNOWN","esp32s3",6843,"radar68xx",&p)!=0 && !p);
    assert(presence_radar_assets_select(NULL,"esp32",6843,"radar68xx",&p)!=0 && !p);
    assert(presence_radar_assets_select("PRO","esp32s3",6843,"radar68xx",NULL)!=0);
#ifdef EXPECT_INVALID
    assert(presence_radar_assets_current() == NULL);
    assert(presence_radar_firmware_path() == NULL);
    assert(presence_radar_config_path() == NULL);
#else
    p = presence_radar_assets_current();
    assert(p);
    assert(presence_radar_firmware_path()==p->firmware_path);
    assert(presence_radar_config_path()==p->config_path);
#if CONFIG_RADAR_BOARD_RADAR_CHIP == 6432
    assert(strcmp(p->firmware_path, "/assets/presence.appimage")==0);
#else
    assert(strcmp(p->firmware_path,"/assets/out_of_box_6843_aop.bin")==0);
#endif
#endif
    return 0;
}
