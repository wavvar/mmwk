#ifndef _AUDIO_BOARD_H_
#define _AUDIO_BOARD_H_

#include "audio_hal.h"
#include "board_def.h"
#include "board_pins_config.h"
#include "esp_peripherals.h"
#include "display_service.h"
#include "periph_sdcard.h"
#include "esp_lcd_panel_ops.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Audio board handle, which is required by the audio stream layer.
 */
struct audio_board_handle {
    audio_hal_handle_t audio_hal;                   /*! audio hardware abstract layer handle */
};

typedef struct audio_board_handle *audio_board_handle_t;

/**
 * @brief Initialize audio board
 *
 * @return The audio board handle
 */
audio_board_handle_t audio_board_init(void);

/**
 * @brief Query audio_board_handle
 *
 * @return The audio board handle
 */
audio_board_handle_t audio_board_get_handle(void);

/**
 * @brief Uninitialize the audio board
 *
 * @param audio_board The handle of audio board
 *
 * @return  0       success,
 *          others  fail
 */
esp_err_t audio_board_deinit(audio_board_handle_t audio_board);

/**
 * Optional: Initialize LCD panel for this board (stubbed for RPI)
 */
esp_lcd_panel_handle_t audio_board_lcd_init(esp_periph_set_handle_t set, void *cb);

/* Audio codec function declarations */
audio_hal_handle_t audio_board_codec_init(void);
esp_err_t audio_board_codec_deinit(audio_hal_handle_t audio_hal);
esp_err_t audio_board_codec_ctrl(audio_hal_handle_t audio_hal, audio_hal_codec_mode_t mode, audio_hal_ctrl_t ctrl_state);
esp_err_t audio_board_codec_config_iface(audio_hal_handle_t audio_hal, audio_hal_codec_mode_t mode, audio_hal_codec_i2s_iface_t *iface);
esp_err_t audio_board_codec_set_volume(audio_hal_handle_t audio_hal, int volume);
esp_err_t audio_board_codec_get_volume(audio_hal_handle_t audio_hal, int *volume);
esp_err_t audio_board_codec_set_voice_mute(audio_hal_handle_t audio_hal, bool enable);
esp_err_t audio_board_codec_set_mic_gain(audio_hal_handle_t audio_hal, audio_hal_codec_mode_t mode, int gain);
esp_err_t audio_board_pa_enable(bool enable);
esp_err_t audio_board_codec_enable(audio_hal_handle_t audio_hal, bool enable);
audio_hal_codec_mode_t audio_board_get_active_codec_mode(void);
esp_err_t audio_board_codec_mutex_lock(audio_hal_handle_t audio_hal);
esp_err_t audio_board_codec_mutex_unlock(audio_hal_handle_t audio_hal);
esp_err_t audio_board_codec_get_read_data(audio_hal_handle_t audio_hal, uint8_t *data, int len);

#ifdef __cplusplus
}
#endif

#endif
