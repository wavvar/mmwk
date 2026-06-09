#include "esp_log.h"
#include "board.h"
#include "audio_mem.h"

#include "periph_sdcard.h"
#include "led_indicator.h"
#include "periph_button.h"
#include "i2c_bus.h"


static audio_board_handle_t audio_board = 0;
static const char *TAG = CONFIG_RADAR_BOARD_NAME;


static audio_hal_handle_t audio_board_codec_init(void)
{
    audio_hal_codec_config_t audio_codec_cfg = AUDIO_CODEC_DEFAULT_CONFIG();
    audio_hal_handle_t codec_hal = audio_hal_init(&audio_codec_cfg, &AUDIO_CODEC_ES8388_DEFAULT_HANDLE);
    AUDIO_NULL_CHECK(TAG, codec_hal, return NULL);
    return codec_hal;
}

audio_board_handle_t audio_board_init(void)
{
    if (audio_board) {
        ESP_LOGW(TAG, "The board has already been initialized!");
        return audio_board;
    }

    audio_board = (audio_board_handle_t) audio_calloc(1, sizeof(struct audio_board_handle));
    AUDIO_MEM_CHECK(TAG, audio_board, return NULL);

    audio_board->audio_hal = audio_board_codec_init();
    AUDIO_NULL_CHECK(TAG, audio_board->audio_hal, return NULL);

    return audio_board;
}

/**
 * @brief Initialize key peripheral
 *
 * @param set The handle of esp_periph_set_handle_t
 *
 * @return
 *     - ESP_OK, success
 *     - Others, fail
 */
esp_err_t audio_board_key_init(esp_periph_set_handle_t set)
{
    periph_button_cfg_t btn_cfg = {
        .gpio_mask = (1ULL << MMWK_IO_KEY), //REC BTN
    };
    esp_periph_handle_t button_handle = periph_button_init(&btn_cfg);
    AUDIO_NULL_CHECK(TAG, button_handle, return ESP_ERR_ADF_MEMORY_LACK);
    return esp_periph_start(set, button_handle);
}

/**
 * @brief Query audio_board_handle
 *
 * @return The audio board handle
 */
audio_board_handle_t audio_board_get_handle(void) {
    return audio_board;
}


esp_err_t audio_board_deinit(audio_board_handle_t audio_board)
{
    esp_err_t ret = ESP_OK;
    ret = audio_hal_deinit(audio_board->audio_hal);
    audio_free(audio_board);
    audio_board = NULL;
    return ret;
}


/* PRO board currently has no LCD, provide stub to satisfy av_stream */
esp_lcd_panel_handle_t audio_board_lcd_init(esp_periph_set_handle_t set, void *cb)
{
    (void)set;
    (void)cb;
    return NULL;
}


