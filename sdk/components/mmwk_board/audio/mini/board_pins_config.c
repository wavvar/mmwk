#include "esp_log.h"
#include "driver/gpio.h"
#include "board.h"
#include "board_pins_config.h"
#include "periph_sdcard.h"

static const char *TAG = "BOARD_PINS_CONFIG";

esp_err_t audio_board_sdcard_init(esp_periph_set_handle_t set, periph_sdcard_mode_t mode)
{
    (void)set;
    (void)mode;
    ESP_LOGW(TAG, "MINI board: SD card not supported");
    return ESP_FAIL;
}

esp_err_t audio_board_key_init(esp_periph_set_handle_t set)
{
    (void)set;
    ESP_LOGW(TAG, "MINI board: Keys not configured");
    return ESP_OK;
}

esp_err_t audio_board_init_led(void)
{
    ESP_LOGW(TAG, "MINI board: LEDs not configured");
    return ESP_OK;
}

esp_err_t audio_board_led_indicator(int idx, bool on_off)
{
    (void)idx;
    (void)on_off;
    ESP_LOGW(TAG, "MINI board: LEDs not configured");
    return ESP_OK;
}
