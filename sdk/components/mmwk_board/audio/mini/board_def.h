#ifndef _BOARD_DEF_H_
#define _BOARD_DEF_H_

#include "driver/i2s.h"
#include "audio_hal.h"

/* I2S port and GPIOs - placeholder values for MINI board */
#define I2S_NUM         (0)
#define I2S_MCK_IO      (GPIO_NUM_0)
#define I2S_BCK_IO      (GPIO_NUM_4)
#define I2S_WS_IO       (GPIO_NUM_5)
#define I2S_DO_IO       (GPIO_NUM_18)
#define I2S_DI_IO       (GPIO_NUM_19)

/* PA */
#define GPIO_PA_EN      (GPIO_NUM_21)
#define GPIO_SEL_PA_EN  (1ULL << GPIO_PA_EN)

/* Press button */
#define GPIO_SEL_REC    (1ULL << GPIO_NUM_36)
#define GPIO_SEL_MODE   (1ULL << GPIO_NUM_39)
#define GPIO_REC        (GPIO_NUM_36)
#define GPIO_MODE       (GPIO_NUM_39)
#define GPIO_SET_REC    (GPIO_NUM_36)
#define GPIO_SET_MODE   (GPIO_NUM_39)

/* Board PA gain */
#define BOARD_PA_GAIN   (0)

extern audio_hal_func_t AUDIO_CODEC_DEFAULT_CONFIG;

#define AUDIO_CODEC_DEFAULT_CONFIG {                   \
        .init = audio_board_codec_init,                \
        .deinit = audio_board_codec_deinit,            \
        .ctrl = audio_board_codec_ctrl,                \
        .config_iface = audio_board_codec_config_iface,\
        .config_volume = audio_board_codec_set_volume, \
        .set_volume = audio_board_codec_set_volume,    \
        .get_volume = audio_board_codec_get_volume,    \
        .set_mute = audio_board_codec_set_voice_mute,  \
        .set_mic_gain = audio_board_codec_set_mic_gain,\
        .set_mic_mute = audio_board_codec_set_voice_mute,\
        .pa_enable = audio_board_pa_enable,            \
        .codec_enable = audio_board_codec_enable,      \
        .get_codec_mode = audio_board_get_active_codec_mode,\
        .lock = audio_board_codec_mutex_lock,          \
        .unlock = audio_board_codec_mutex_unlock,      \
        .read_raw = audio_board_codec_get_read_data,   \
        .samples = AUDIO_HAL_48K_SAMPLES,              \
        .bits = AUDIO_HAL_BIT_LENGTH_16BITS,           \
    },                                                 \
};

/*
 * Camera Function Definition (no camera on MINI by default)
 */
#define FUNC_CAMERA_EN              (-1)
#define CAM_PIN_PWDN                -1
#define CAM_PIN_RESET               -1
#define CAM_PIN_XCLK                -1
#define CAM_PIN_SIOD                -1
#define CAM_PIN_SIOC                -1
#define CAM_PIN_D7                  -1
#define CAM_PIN_D6                  -1
#define CAM_PIN_D5                  -1
#define CAM_PIN_D4                  -1
#define CAM_PIN_D3                  -1
#define CAM_PIN_D2                  -1
#define CAM_PIN_D1                  -1
#define CAM_PIN_D0                  -1
#define CAM_PIN_VSYNC               -1
#define CAM_PIN_HREF                -1
#define CAM_PIN_PCLK                -1

/* SD Card pins (not supported on MINI) */
#define ESP_SD_PIN_CLK               (-1)
#define ESP_SD_PIN_CMD               (-1)
#define ESP_SD_PIN_D0                (-1)
#define ESP_SD_PIN_D1                (-1)
#define ESP_SD_PIN_D2                (-1)
#define ESP_SD_PIN_D3                (-1)
#define ESP_SD_PIN_D4                (-1)
#define ESP_SD_PIN_D5                (-1)
#define ESP_SD_PIN_D6                (-1)
#define ESP_SD_PIN_D7                (-1)
#define ESP_SD_PIN_CD                (-1)
#define ESP_SD_PIN_WP                (-1)

/* Audio codec configuration (MINI board has no real codec) */
#define CODEC_ADC_I2S_PORT           (I2S_NUM)
#define CODEC_ADC_BITS_PER_SAMPLE    (16)
#define CODEC_ADC_SAMPLE_RATE        (48000)

/* common config rest of  audio codec  */
#define FUNC_AUDIO_CODEC_EN       (1)

#endif
