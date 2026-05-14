#include "esp_log.h"
#include "board.h"
#include "audio_mem.h"

static const char *TAG = "AUDIO_BOARD";

static audio_board_handle_t audio_board = NULL;

audio_board_handle_t audio_board_init(void)
{
    return NULL;
}

audio_board_handle_t audio_board_get_handle(void)
{
    return audio_board;
}

esp_err_t audio_board_deinit(audio_board_handle_t audio_board)
{
    return 0;
}

/* MINI board LCD stub */
esp_lcd_panel_handle_t audio_board_lcd_init(esp_periph_set_handle_t set, void *cb)
{
    (void)set;
    (void)cb;
    return NULL;
}

/* Audio codec functions - empty implementations for MINI board */
audio_hal_handle_t audio_board_codec_init(void)
{
    return NULL;
}

esp_err_t audio_board_codec_deinit(audio_hal_handle_t audio_hal)
{
    (void)audio_hal;
    return ESP_OK;
}

esp_err_t audio_board_codec_ctrl(audio_hal_handle_t audio_hal, audio_hal_codec_mode_t mode, audio_hal_ctrl_t ctrl_state)
{
    (void)audio_hal;
    (void)mode;
    (void)ctrl_state;
    return ESP_OK;
}

esp_err_t audio_board_codec_config_iface(audio_hal_handle_t audio_hal, audio_hal_codec_mode_t mode, audio_hal_codec_i2s_iface_t *iface)
{
    (void)audio_hal;
    (void)mode;
    (void)iface;
    return ESP_OK;
}

esp_err_t audio_board_codec_set_volume(audio_hal_handle_t audio_hal, int volume)
{
    (void)audio_hal;
    (void)volume;
    return ESP_OK;
}

esp_err_t audio_board_codec_get_volume(audio_hal_handle_t audio_hal, int *volume)
{
    (void)audio_hal;
    if (volume) *volume = 0;
    return ESP_OK;
}

esp_err_t audio_board_codec_set_voice_mute(audio_hal_handle_t audio_hal, bool enable)
{
    (void)audio_hal;
    (void)enable;
    return ESP_OK;
}

esp_err_t audio_board_codec_set_mic_gain(audio_hal_handle_t audio_hal, audio_hal_codec_mode_t mode, int gain)
{
    (void)audio_hal;
    (void)mode;
    (void)gain;
    return ESP_OK;
}

esp_err_t audio_board_pa_enable(bool enable)
{
    (void)enable;
    return ESP_OK;
}

esp_err_t audio_board_codec_enable(audio_hal_handle_t audio_hal, bool enable)
{
    (void)audio_hal;
    (void)enable;
    return ESP_OK;
}

audio_hal_codec_mode_t audio_board_get_active_codec_mode(void)
{
    return AUDIO_HAL_CODEC_MODE_BOTH;
}

esp_err_t audio_board_codec_mutex_lock(audio_hal_handle_t audio_hal)
{
    (void)audio_hal;
    return ESP_OK;
}

esp_err_t audio_board_codec_mutex_unlock(audio_hal_handle_t audio_hal)
{
    (void)audio_hal;
    return ESP_OK;
}

esp_err_t audio_board_codec_get_read_data(audio_hal_handle_t audio_hal, uint8_t *data, int len)
{
    (void)audio_hal;
    (void)data;
    (void)len;
    return ESP_OK;
}
