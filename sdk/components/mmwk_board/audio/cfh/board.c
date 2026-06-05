#include "esp_log.h"
#include "board.h"
#include "audio_mem.h"
#include "periph_sdcard.h"
#include "periph_button.h"

static const char *TAG = CONFIG_RADAR_BOARD_NAME;

static audio_board_handle_t board_handle = 0;

audio_board_handle_t audio_board_init(void)
{
    if (board_handle) {
        ESP_LOGW(TAG, "The board has already been initialized!");
        return board_handle;
    }
    board_handle = (audio_board_handle_t) audio_calloc(1, sizeof(struct audio_board_handle));
    AUDIO_MEM_CHECK(TAG, board_handle, return NULL);
    board_handle->audio_hal = audio_board_codec_init();
    board_handle->adc_hal = audio_board_adc_init();
    return board_handle;
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
        .gpio_mask = (1ULL << MMWK_IO_KEY) | (1ULL << MMWK_IO_KEY_SECOND), //REC BTN & MODE BTN
    };
    esp_periph_handle_t button_handle = periph_button_init(&btn_cfg);
    AUDIO_NULL_CHECK(TAG, button_handle, return ESP_ERR_ADF_MEMORY_LACK);
    return esp_periph_start(set, button_handle);
}


audio_hal_handle_t audio_board_adc_init(void)
{
    audio_hal_codec_config_t audio_codec_cfg = AUDIO_CODEC_DEFAULT_CONFIG();
    audio_codec_cfg.codec_mode = AUDIO_HAL_CODEC_MODE_ENCODE;
    audio_hal_handle_t adc_hal = NULL;
    adc_hal = audio_hal_init(&audio_codec_cfg, &AUDIO_CODEC_ES7210_DEFAULT_HANDLE);
    AUDIO_NULL_CHECK(TAG, adc_hal, return NULL);
    return adc_hal;
}

audio_hal_handle_t audio_board_codec_init(void)
{
    audio_hal_codec_config_t audio_codec_cfg = AUDIO_CODEC_DEFAULT_CONFIG();
    audio_hal_handle_t codec_hal = audio_hal_init(&audio_codec_cfg, &AUDIO_CODEC_ES8311_DEFAULT_HANDLE);
    AUDIO_NULL_CHECK(TAG, codec_hal, return NULL);
    return codec_hal;
}


audio_board_handle_t audio_board_get_handle(void)
{
    return board_handle;
}

esp_err_t audio_board_deinit(audio_board_handle_t audio_board)
{
    esp_err_t ret = ESP_OK;
    ret |= audio_hal_deinit(audio_board->audio_hal);
    ret |= audio_hal_deinit(audio_board->adc_hal);
    audio_free(audio_board);
    board_handle = NULL;
    return ret;
}

void *audio_board_lcd_init(esp_periph_set_handle_t set, void *cb) 
{
    return NULL;
}
