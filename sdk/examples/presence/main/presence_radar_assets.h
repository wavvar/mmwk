#ifndef PRESENCE_RADAR_ASSETS_H
#define PRESENCE_RADAR_ASSETS_H

/* This asset/board mapping is application-owned, not part of libmmwk_sdk.a.
 * A mismatched board/target/chip/family cannot silently load another firmware.
 * Returned descriptors have static lifetime; no allocation or mutation. */
typedef struct {
    const char *board;
    const char *target;
    int radar_chip;
    const char *family;
    const char *firmware_path;
    const char *config_path;
} presence_radar_asset_pair_t;

/* Return 0 only for a complete and explicitly approved selection. */
int presence_radar_assets_select(const char *board, const char *target,
                                 int radar_chip, const char *family,
                                 const presence_radar_asset_pair_t **out);
const presence_radar_asset_pair_t *presence_radar_assets_current(void);

/* Legacy helpers still used by the published presence demo. */
const char *presence_radar_firmware_path(void);
const char *presence_radar_config_path(void);

#endif
