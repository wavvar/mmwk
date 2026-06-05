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
 * @brief Initialize key peripheral
 *
 * @param set The handle of esp_periph_set_handle_t
 *
 * @return
 *     - ESP_OK, success
 *     - Others, fail
 */
esp_err_t audio_board_key_init(esp_periph_set_handle_t set);


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

/**
 * Optional: Initialize LCD panel for this board (stubbed for PRO)
 */
esp_lcd_panel_handle_t audio_board_lcd_init(esp_periph_set_handle_t set, void *cb);

esp_err_t audio_board_deinit(audio_board_handle_t audio_board);

#ifdef __cplusplus
}
#endif

#endif
