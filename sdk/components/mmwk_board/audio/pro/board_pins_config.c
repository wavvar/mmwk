#include "esp_log.h"
#include "driver/gpio.h"
#include <string.h>
#include "board.h"
#include "audio_error.h"
#include "audio_mem.h"
#include "soc/io_mux_reg.h"
#include "soc/soc_caps.h"

static const char *TAG = "RADAR_BOARD";

esp_err_t get_i2c_pins(i2c_port_t port, i2c_config_t *i2c_config)
{
    AUDIO_NULL_CHECK(TAG, i2c_config, return ESP_FAIL);
    if (port == I2C_NUM_0 || port == I2C_NUM_1) {
        i2c_config->sda_io_num = MMWK_IO_I2C_SDA;
        i2c_config->scl_io_num = MMWK_IO_I2C_SCL;
    } else {
        i2c_config->sda_io_num = -1;
        i2c_config->scl_io_num = -1;
        ESP_LOGE(TAG, "i2c port %d is not supported", port);
        return ESP_FAIL;
    }
    return ESP_OK;
}

esp_err_t get_i2s_pins(int port, board_i2s_pin_t *i2s_config)
{
    AUDIO_NULL_CHECK(TAG, i2s_config, return ESP_FAIL);
    if (port == 0 || port == 1) {
        i2s_config->bck_io_num   = MMWK_IO_AUD_I2S_SCLK;
        i2s_config->ws_io_num    = MMWK_IO_AUD_I2S_LRCK;
        i2s_config->data_out_num = MMWK_IO_AUD_I2S_DIN;
        i2s_config->data_in_num  = MMWK_IO_AUD_I2S_DOUT;
        i2s_config->mck_io_num   = MMWK_IO_AUD_I2S_MCLK;
    } else {
        memset(i2s_config, -1, sizeof(board_i2s_pin_t));
        ESP_LOGE(TAG, "i2s port %d is not supported", port);
        return ESP_FAIL;
    }

    return ESP_OK;
}

esp_err_t get_spi_pins(spi_bus_config_t *spi_config, spi_device_interface_config_t *spi_device_interface_config)
{
    AUDIO_NULL_CHECK(TAG, spi_config, return ESP_FAIL);
    AUDIO_NULL_CHECK(TAG, spi_device_interface_config, return ESP_FAIL);

    spi_config->mosi_io_num = -1;
    spi_config->miso_io_num = -1;
    spi_config->sclk_io_num = -1;
    spi_config->quadwp_io_num = -1;
    spi_config->quadhd_io_num = -1;

    spi_device_interface_config->spics_io_num = -1;

    ESP_LOGW(TAG, "SPI interface is not supported");
    return ESP_OK;
}


// input-output pins

int8_t get_headphone_detect_gpio(void)
{
    return HEADPHONE_DETECT;
}

int8_t get_input_rec_id(void)
{
    return MMWK_IO_KEY;
}

int8_t get_input_mode_id(void)
{
    return MMWK_IO_KEY_SECOND;
}

int8_t get_pa_enable_gpio(void)
{
    return MMWK_IO_AUD_PA_CTL;
}

