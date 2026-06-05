#ifndef __MMWK_IO_DEF_H__
#define __MMWK_IO_DEF_H__

/** 
 * MINI Radar Board Definitions
 * 
 * This file defines all possible functions that for a radar application board. It serves as a 
 * template for defining a new radar board by using default value -1 and then forces the application
 * code to check its availibility. 
 *  
 */


/**
 * User Interaction
 */
#define MMWK_IO_KEY                     (37)
#define MMWK_IO_KEY_SECOND              (-1)
#define MMWK_IO_LED                     (22)
#define MMWK_IO_LED_SECOND              (-1)
#define MMWK_IO_KEY_ACTIVE_LEVEL        (0)
#define MMWK_IO_KEY_SECOND_ACTIVE_LEVEL (0)


/*
 * CLI UART
 */
#define MMWK_CLI_UART_NUM              (0)
#define MMWK_IO_CLI_UART_TX            (1)
#define MMWK_IO_CLI_UART_RX            (3)


/*
* Radar
*/
#define MMWK_RADAR_UART_CMD          (1)
#define MMWK_RADAR_UART_DATA         (2)
#define MMWK_IO_RADAR_SPI_MISO       (12)
#define MMWK_IO_RADAR_SPI_MOSI       (13)
#define MMWK_IO_RADAR_SPI_CLK        (14)
#define MMWK_IO_RADAR_SPI_CS         (15)
#define MMWK_IO_RADAR_SPI_INT        (39)
#define MMWK_IO_RADAR_FLASH_PWR      (33)
#define MMWK_IO_RADAR_PWR_EN         (27)
#define MMWK_IO_RADAR_CMD_TX         (4)
#define MMWK_IO_RADAR_CMD_RX         (19)
#define MMWK_IO_RADAR_DATA_RX        (32)
#define MMWK_IO_RADAR_DATA_TX        (-1)
#define MMWK_IO_RADAR_BOOT_CTL       (2)
#define MMWK_IO_RADAR_SOP_REVERSED   (0)


/*
* Audio 
*/
#define MMWK_IO_AUD_I2S_DOUT (-1)
#define MMWK_IO_AUD_I2S_DIN  (-1)
#define MMWK_IO_AUD_I2S_LRCK (-1)
#define MMWK_IO_AUD_I2S_SCLK (-1)
#define MMWK_IO_AUD_I2S_MCLK (-1)
#define MMWK_IO_AUD_PA_CTL   (-1)


/*
* USB for 4G modules
*/
#define MMWK_IO_IOT_PWR_CTL  (-1)
#define MMWK_IO_IOT_UART_TX  (-1)
#define MMWK_IO_IOT_UART_RX  (-1)
#define MMWK_IO_IOT_USB_DM   (-1)
#define MMWK_IO_IOT_USB_DP   (-1)
#define MMWK_IO_IOT_RESET    (-1)


/*
* Sensor
*/
#define MMWK_IO_I2C_SDA      (18)
#define MMWK_IO_I2C_SCL      (23)
#define MMWK_IO_VEML6030_INT (36)
#define MMWK_IO_BMI160_INT   (38)
#endif /* __MMWK_IO_DEF_H__ */