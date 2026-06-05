#include "presence_cli.h"
#include "presence_radar_assets.h"
#include "presence_state.h"

#include <stdint.h>

#include "esp_err.h"
#include "esp_log.h"
#include "mmwk_sensor.h"
#include "mmwk_sensor_raw.h"
#include "mmwk_service.h"

static const char *TAG = "presence_main";
static presence_state_t s_presence_state;

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
    const char *firmware_path = presence_radar_firmware_path();
    const char *config_path = presence_radar_config_path();

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

    mmwk_sensor_bridge_run(&profile, &proto_cfg, &startup);
}
