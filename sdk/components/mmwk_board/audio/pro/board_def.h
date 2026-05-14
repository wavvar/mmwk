#ifndef _AUDIO_BOARD_DEFINITION_H_
#define _AUDIO_BOARD_DEFINITION_H_

#include <radar_io_def.h>

/**
 * @brief Audio Codec Chip Function Definition
 */

/**
 * Config RECORD_HARDWARE_AEC of audio codec
 *
 * It's used in the AEC module of esp-sr module and should be tested
 * with the Emergency Call example.
 */

#define RECORD_HARDWARE_AEC       (false)

/** enable this when we have video and lcd support */
//RADAR_BOARD_CAP_VIDEO
/**
 * Configure RADAR_BOARD_CAP_VIDEO (the video support)
 *
 * If this is defined, the video function in voip will be enabled. Just ignore
 * this if no
 *
 */

 #define AUDIO_ADC_INPUT_CH_FORMAT "MR"
/* config AUDIO_CODEC_DEFAULT_CONFIG of audio codec */

#define AUDIO_CODEC_DEFAULT_CONFIG(){               \
    .adc_input  = AUDIO_HAL_ADC_INPUT_LINE1,        \
    .dac_output = AUDIO_HAL_DAC_OUTPUT_LINE1,       \
    .codec_mode = AUDIO_HAL_CODEC_MODE_BOTH,        \
    .i2s_iface = {                                  \
        .mode = AUDIO_HAL_MODE_SLAVE,               \
        .fmt = AUDIO_HAL_I2S_NORMAL,                \
        .samples = AUDIO_HAL_48K_SAMPLES,           \
        .bits = AUDIO_HAL_BIT_LENGTH_16BITS,        \
    },                                              \
};

/*
 * Camera Function Definition (no camera on PRO by default)
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



/* common config rest of  audio codec  */
#define FUNC_AUDIO_CODEC_EN       (1)
#define AUXIN_DETECT_GPIO         (-1)
#define HEADPHONE_DETECT          (-1)
#define PA_ENABLE_GPIO            MMWK_IO_AUD_PA_CTL
#define CODEC_ADC_I2S_PORT        ((i2s_port_t)0)
#define CODEC_ADC_BITS_PER_SAMPLE ((i2s_data_bit_width_t)16) /* 16bit */
#define CODEC_ADC_SAMPLE_RATE     (48000)
#define BOARD_PA_GAIN             (6) /* Power amplifier gain defined by board (dB) */
extern audio_hal_func_t            AUDIO_CODEC_ES8388_DEFAULT_HANDLE;


/**
 * @brief  SDCARD Function Definition
 */
#define FUNC_SDCARD_EN               (-1)
#define SDCARD_OPEN_FILE_NUM_MAX     (5)
#define SDCARD_INTR_GPIO             (-1)
#define SDCARD_PWR_CTRL              (-1)

// In order to coexist with ESP host, slot0 is required and matrix will not be used,
// so all default configurations are set to 0
#define ESP_SD_PIN_CLK               (0)
#define ESP_SD_PIN_CMD               (0)
#define ESP_SD_PIN_D0                (0)
#define ESP_SD_PIN_D1                (0)
#define ESP_SD_PIN_D2                (0)
#define ESP_SD_PIN_D3                (0)
#define ESP_SD_PIN_D4                (0)
#define ESP_SD_PIN_D5                (0)
#define ESP_SD_PIN_D6                (0)
#define ESP_SD_PIN_D7                (0)
#define ESP_SD_PIN_CD                (-1)
#define ESP_SD_PIN_WP                (-1)

#endif  /* _AUDIO_BOARD_DEFINITION_H_ */
