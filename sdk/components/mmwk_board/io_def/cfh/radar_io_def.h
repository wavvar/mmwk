#ifndef __MMWK_IO_DEF_H__
#define __MMWK_IO_DEF_H__

/** 
 * CFH Radar Board Definitions
 * 
 * This file defines all possible functions that for a radar application board. It serves as a 
 * template for defining a new radar board by using default value -1 and then forces the application
 * code to check its availibility. 
 *  
 */

/**
 * User Interaction
 */
#define MMWK_IO_KEY                     (2)
#define MMWK_IO_KEY_SECOND              (40)
#define MMWK_IO_LED                     (47)
#define MMWK_IO_LED_SECOND              (-1)
#define MMWK_IO_KEY_ACTIVE_LEVEL        (0)
#define MMWK_IO_KEY_SECOND_ACTIVE_LEVEL (0)


/*
 * CLI UART
 */
#define MMWK_CLI_UART_NUM              (0)
#define MMWK_IO_CLI_UART_TX            (43)
#define MMWK_IO_CLI_UART_RX            (44)


/*
* Radar
*/
#define MMWK_RADAR_UART_CMD          (1)
#define MMWK_RADAR_UART_DATA         (2)
#define MMWK_IO_RADAR_SPI_MISO       (-1)
#define MMWK_IO_RADAR_SPI_MOSI       (-1)
#define MMWK_IO_RADAR_SPI_CLK        (-1)
#define MMWK_IO_RADAR_SPI_CS         (-1)
#define MMWK_IO_RADAR_SPI_INT        (-1)
#define MMWK_IO_RADAR_FLASH_PWR      (-1)
#define MMWK_IO_RADAR_PWR_EN         (-1)
#define MMWK_IO_RADAR_NRESET         (-1)
#define MMWK_IO_RADAR_CMD_TX         (-1)
#define MMWK_IO_RADAR_CMD_RX         (-1)
#define MMWK_IO_RADAR_DATA_TX        (-1)
#define MMWK_IO_RADAR_DATA_RX        (-1)
#define MMWK_IO_RADAR_BOOT_CTL       (-1)
#define MMWK_IO_RADAR_SOP_REVERSED   (0)


/*
* Audio 
*/
#define MMWK_IO_AUD_I2S_DOUT (10)
#define MMWK_IO_AUD_I2S_DIN  (8)
#define MMWK_IO_AUD_I2S_LRCK (45)
#define MMWK_IO_AUD_I2S_SCLK (9)
#define MMWK_IO_AUD_I2S_MCLK (16)
#define MMWK_IO_AUD_PA_CTL   (48)


/*
* USB for 4G modules
*/
#define MMWK_IO_IOT_PWR_CTL  (21)
#define MMWK_IO_IOT_UART_TX  (39)
#define MMWK_IO_IOT_UART_RX  (38)
#define MMWK_IO_IOT_USB_DM   (19)
#define MMWK_IO_IOT_USB_DP   (20)
#define MMWK_IO_IOT_RESET    (12)


/*
* Sensor
*/
#define MMWK_IO_I2C_SDA      (17)
#define MMWK_IO_I2C_SCL      (18)
#define MMWK_IO_VEML6030_INT (-1)
#define MMWK_IO_BMI160_INT   (-1)
#endif /* __MMWK_IO_DEF_H__ */