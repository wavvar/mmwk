#include "presence_cli.h"
#include "presence_radar_assets.h"
#include "presence_state.h"
#include "presence_ui.h"

#include <stdint.h>

#include "esp_err.h"
#include "esp_log.h"
#include "mmwk_sensor.h"
#include "mmwk_sensor_raw.h"
#include "mmwk_service.h"

static const char *TAG = "presence_main";
static presence_state_t s_presence_state;

/* Application UI is opt-in and fully editable. This example does not install
 * a default key/LED task. For custom IO set claim_key/claim_led to true and
 * use presence_ui_read_key()/presence_ui_set_led() in your own app logic.
 * Old SDK packages retain their original internal key/LED ownership. */
static const presence_ui_policy_t s_ui_policy = {
    .claim_key = false,
    .claim_led = false,
    .led_initially_on = false,
};

static void presence_raw_event_callback(const mmwk_sensor_raw_event_t *event,
                                        void *ctx)
{
    presence_state_t *state = (presence_state_t *)ctx;

    if (!event || !state) {
        return;
    }

    if (event->type == RAW_SENSOR_EVENT_DATA &&
        event->data.data &&
        event->data.len > 0) {
        /*
         * The demo keeps the radar payload opaque and only counts raw frames.
         * Replace this with parser-specific decoding before exposing a real
         * presence decision to your own CLI protocol.
         */
        presence_state_update_raw(state,
                                  (const uint8_t *)event->data.data,
                                  event->data.len);
        return;
    }

    if (event->type == RAW_SENSOR_EVENT_CMD_RECEIVED &&
        event->cmd.cmd_data &&
        event->cmd.cmd_len > 0) {
        ESP_LOGD(TAG, "raw command bytes received: %u", (unsigned)event->cmd.cmd_len);
    }
}

static void presence_service_ready(mmwk_service_handle_t svc, void *user_ctx)
{
    if (!svc) {
        ESP_LOGW(TAG, "service hook received null handle");
        return;
    }

    mmwk_service_set_raw_event_callback(svc, presence_raw_event_callback, user_ctx);
}

void app_main(void)
{
    mmwk_sensor_profile_t profile;
    mmwk_sensor_protocol_family_t proto_cfg;
    mmwk_sensor_startup_policy_t startup;
    const presence_radar_asset_pair_t *assets = presence_radar_assets_current();
    if (!assets) {
        /* Never try to boot 6432 firmware with 6843 pins/assets, or vice versa. */
        ESP_LOGE(TAG, "Unsupported or mismatched board/target/radar asset pair");
        return;
    }
    const char *firmware_path = assets->firmware_path;
    const char *config_path = assets->config_path;

    presence_state_init(&s_presence_state);

    ESP_LOGI(TAG,
             "presence radar assets firmware=%s config=%s",
             firmware_path ? firmware_path : "(null)",
             config_path ? config_path : "(null)");

    ESP_ERROR_CHECK(presence_cli_register(&s_presence_state));
    ESP_ERROR_CHECK(mmwk_sensor_register_service_hook(presence_service_ready,
                                                      &s_presence_state));

    profile = mmwk_sensor_load_profile();
    proto_cfg = mmwk_sensor_load_protocol_family();
    startup = mmwk_sensor_load_startup_policy(&profile, &proto_cfg);
#ifdef MMWK_SENSOR_STARTUP_SPI_BACKEND_POLICY_V1
    /* Keep one consumer-owned static linker root, never both descriptors.
     * The SDK runtime may only use SPI when the caller chooses SPI mode;
     * default/host paths retain their existing behavior. */
#if CONFIG_RADAR_BOARD_RADAR_CHIP == 6432
    startup.spi_backend = &mmwk_driver_spi_backend_xwrl6432;
#elif CONFIG_RADAR_BOARD_RADAR_CHIP == 6843
    startup.spi_backend = &mmwk_driver_spi_backend_xwr6843;
#else
#error "Presence example requires one approved radar SPI backend"
#endif
#endif
    ESP_ERROR_CHECK(presence_ui_configure(&s_ui_policy));
    /* The new aggregate SDK lets the application own key/LED GPIOs. The
     * current legacy SDK has no such policy fields and retains its original
     * behavior, so the same native presence source remains buildable there. */
#ifdef MMWK_SENSOR_STARTUP_LEGACY_UI_POLICY_V1
    startup.disable_legacy_key = true;
    startup.disable_legacy_led = true;
#endif

    mmwk_sensor_bridge_run(&profile, &proto_cfg, &startup);
}
