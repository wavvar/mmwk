#include "presence_radar_assets.h"
#include "sdkconfig.h"

#include <stddef.h>
#include <string.h>

/* One consumer-side registry. The firmware and config paths are an atomic
 * pair; an SDK archive has no knowledge of the installation's SPIFFS path.
 * These are the existing legacy filenames, deliberately unchanged. */
static const presence_radar_asset_pair_t s_pairs[] = {
    {"MINI", "esp32", 6843, "radar68xx",
     "/assets/out_of_box_6843_aop.bin", "/assets/out_of_box_6843_aop.cfg"},
    {"PRO", "esp32s3", 6843, "radar68xx",
     "/assets/out_of_box_6843_aop.bin", "/assets/out_of_box_6843_aop.cfg"},
    {"WDR", "esp32s3", 6432, "radarl64xx",
     "/assets/presence.appimage", "/assets/presence.cfg"},
};

int presence_radar_assets_select(const char *board, const char *target,
                                 int radar_chip, const char *family,
                                 const presence_radar_asset_pair_t **out)
{
    if (!out) return -1;
    *out = NULL;
    if (!board || !target || !family) return -1;
    for (size_t i = 0; i < sizeof(s_pairs)/sizeof(s_pairs[0]); ++i) {
        const presence_radar_asset_pair_t *pair = &s_pairs[i];
        if (strcmp(board, pair->board) != 0) continue;
        if (strcmp(target, pair->target) != 0 ||
            radar_chip != pair->radar_chip ||
            strcmp(family, pair->family) != 0 ||
            !pair->firmware_path || !pair->config_path ||
            strcmp(pair->firmware_path, pair->config_path) == 0) {
            return -1;
        }
        *out = pair;
        return 0;
    }
    return -1;
}

const presence_radar_asset_pair_t *presence_radar_assets_current(void)
{
    const presence_radar_asset_pair_t *selected = NULL;
#if defined(CONFIG_IDF_TARGET_ESP32S3)
    const char *target = "esp32s3";
#elif defined(CONFIG_IDF_TARGET_ESP32)
    const char *target = "esp32";
#else
    const char *target = NULL;
#endif
#if CONFIG_RADAR_BOARD_RADAR_CHIP == 6432
    const char *family = "radarl64xx";
#elif CONFIG_RADAR_BOARD_RADAR_CHIP == 6843
    const char *family = "radar68xx";
#else
    const char *family = NULL;
#endif
    if (!target || !family) return NULL;
    if (presence_radar_assets_select(CONFIG_RADAR_BOARD_NAME, target,
                                     CONFIG_RADAR_BOARD_RADAR_CHIP,
                                     family, &selected) != 0) return NULL;
    return selected;
}

const char *presence_radar_firmware_path(void)
{
    const presence_radar_asset_pair_t *pair = presence_radar_assets_current();
    return pair ? pair->firmware_path : NULL;
}

const char *presence_radar_config_path(void)
{
    const presence_radar_asset_pair_t *pair = presence_radar_assets_current();
    return pair ? pair->config_path : NULL;
}
