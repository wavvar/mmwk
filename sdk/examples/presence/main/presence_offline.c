/* Stage1 radar-only presence consumer. Selected only with the new aggregate
 * SDK offline preset. Reuses presence_state.c; does not initialize the legacy
 * sensor Bridge, MQTT, Wi-Fi, portal, key/LED, or host CLI.
 * A radar firmware must already be installed (HOST start mode). */
#include "presence_state.h"
#include "presence_radar_assets.h"

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mmwk_board_config.h"
#include "mmwk_driver_board_adapter.h"
#include "mmwk_service.h"
#include "mmwk_service_raw.h"

static const char *TAG = "presence_offline";
static presence_state_t s_presence_state;
static mmwk_service_handle_t s_service;
static mmwk_service_raw_subscription_t s_subscription;
static bool s_started;

#if CONFIG_RADAR_BOARD_RADAR_CHIP == 6432
static const mmwk_driver_spi_backend_v1_t *const s_backend =
    &mmwk_driver_spi_backend_xwrl6432;
#elif CONFIG_RADAR_BOARD_RADAR_CHIP == 6843
static const mmwk_driver_spi_backend_v1_t *const s_backend =
    &mmwk_driver_spi_backend_xwr6843;
#else
#error "offline presence only supports approved 6432/6843 static backends"
#endif

static void presence_offline_raw_callback(
    const mmwk_service_raw_event_t *event, void *user_ctx)
{
    presence_state_t *state = (presence_state_t *)user_ctx;
    if (!event || !state || event->type != MMWK_SERVICE_RAW_EVENT_DATA_OUTPUT ||
        !event->data || !event->len) {
        return;
    }
    /* The RAW callback's bytes are only valid inside this function.
     * The state module updates counters and does not retain their address.
     * A RAW callback represents a chunk, not necessarily a full radar frame. */
    presence_state_update_raw(state, (const uint8_t *)event->data, event->len);
}

/* Keep ownership until every cleanup step has returned success. In
 * particular, deinit can reject a busy runtime: never discard a still-live
 * service pointer or subscription token merely to make an error path quiet. */
static int presence_offline_release_service(void)
{
    if (!s_service) return MMWK_SERVICE_OK;
    if (s_subscription != 0U) {
        int unsub = mmwk_service_raw_unsubscribe(s_service, s_subscription);
        if (unsub != MMWK_SERVICE_OK) return unsub;
        s_subscription = 0U;
    }
    int done = mmwk_service_deinit(s_service);
    if (done == MMWK_SERVICE_OK) {
        s_service = NULL;
        s_started = false;
    }
    return done;
}

/* Optional app-owned external shutdown entry. Never invoke synchronously
 * from the service or a RAW callback: the service rejects self-wait.
 * A failed stop, unsubscribe or deinit can be retried without losing the
 * handle. Stop is not repeated after it has already succeeded. */
int presence_offline_stop(void)
{
    if (!s_service) return MMWK_SERVICE_OK;
    if (s_started) {
        int stopped = mmwk_service_stop(s_service);
        if (stopped != MMWK_SERVICE_OK) return stopped;
        s_started = false;
    }
    return presence_offline_release_service();
}

void app_main(void)
{
    /* Avoid overwriting a handle retained after a previous cleanup error. */
    if (s_service) {
        ESP_LOGE(TAG, "Previous RAW service still owned; stop/retry before restart");
        return;
    }
    const mmwk_board_config_t *board = mmwk_board_get_config();
    const presence_radar_asset_pair_t *assets = presence_radar_assets_current();
    if (!board || !assets || s_backend->abi_version != MMWK_DRIVER_SPI_BACKEND_ABI_V1 ||
        s_backend->radar_chip != assets->radar_chip) {
        ESP_LOGE(TAG, "Invalid board/backend/asset contract");
        return;
    }

    mmwk_service_cfg_t cfg = {
        .task_priority = 5,
        .task_core = tskNO_AFFINITY,
        .disable_external_raw_commands = true,
        .spi_backend = s_backend,
    };
    if (mmwk_driver_board_cfg_from_profile(
            board, board->target, s_backend->radar_chip, assets->family,
            &cfg.board_cfg) != MMWK_DRIVER_ERR_NONE) {
        ESP_LOGE(TAG, "Rejected board, target, chip, or resource pair");
        return;
    }

    presence_state_init(&s_presence_state);
    if (mmwk_service_init(&s_service, NULL, &cfg) != MMWK_SERVICE_OK) {
        ESP_LOGE(TAG, "Unable to initialize RAW radar service");
        s_service = NULL;
        return;
    }
    if (mmwk_service_raw_subscribe(s_service, presence_offline_raw_callback,
                                   &s_presence_state, &s_subscription) != MMWK_SERVICE_OK) {
        ESP_LOGE(TAG, "Unable to subscribe to RAW radar output");
        int cleanup = presence_offline_release_service();
        if (cleanup != MMWK_SERVICE_OK) {
            ESP_LOGE(TAG, "RAW service cleanup deferred after subscribe failure: %d", cleanup);
        }
        return;
    }

    if (mmwk_service_start(s_service, MMWK_SERVICE_START_HOST) != MMWK_SERVICE_OK) {
        ESP_LOGE(TAG, "Unable to start radar in host-only mode");
        int cleanup = presence_offline_release_service();
        if (cleanup != MMWK_SERVICE_OK) {
            ESP_LOGE(TAG, "RAW service cleanup deferred after start failure: %d", cleanup);
        }
        return;
    }
    s_started = true;
    ESP_LOGI(TAG, "Radar-only consumer started; no network or legacy UI");
}
