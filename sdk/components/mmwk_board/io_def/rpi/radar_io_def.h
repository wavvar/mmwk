#ifndef __MMWK_IO_DEF_H__
#define __MMWK_IO_DEF_H__

/** 
 * RPI Radar Board Definitions
 * 
 * This file defines all possible functions that for a radar application board. It serves as a 
 * template for defining a new radar board by using default value -1 and then forces the application
 * code to check its availibility. 
 *  
 */


/**
 * User Interaction
 */
#define MMWK_IO_KEY                     (40)
#define MMWK_IO_KEY_SECOND              (-1)
#define MMWK_IO_LED                     (0)
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
#define MMWK_RADAR_UART_DATA         (-1)
#define MMWK_IO_RADAR_SPI_MISO       (13)
#define MMWK_IO_RADAR_SPI_MOSI       (11)
#define MMWK_IO_RADAR_SPI_CLK        (14)
#define MMWK_IO_RADAR_SPI_CS         (15)
#define MMWK_IO_RADAR_SPI_INT        (0)
#define MMWK_IO_RADAR_FLASH_PWR      (45)
#define MMWK_IO_RADAR_PWR_EN         (10)
#define MMWK_IO_RADAR_CMD_TX         (9)
#define MMWK_IO_RADAR_CMD_RX         (8)
#define MMWK_IO_RADAR_DATA_RX        (-1)
#define MMWK_IO_RADAR_DATA_TX        (-1)
#define MMWK_IO_RADAR_BOOT_CTL       (38)
#define MMWK_IO_RADAR_SOP_REVERSED   (1)


/*
* Audio
*/
#define MMWK_IO_AUD_I2S_DOUT (3)
#define MMWK_IO_AUD_I2S_DIN  (4)
#define MMWK_IO_AUD_I2S_LRCK (5)
#define MMWK_IO_AUD_I2S_SCLK (6)
#define MMWK_IO_AUD_I2S_MCLK (7)
#define MMWK_IO_AUD_PA_CTL   (17)


/*
* USB for 4G modules
*/
#define MMWK_IO_IOT_PWR_CTL  (-1)
#define MMWK_IO_IOT_UART_TX  (-1)
#define MMWK_IO_IOT_UART_RX  (-1)
#define MMWK_IO_IOT_USB_DM   (19)
#define MMWK_IO_IOT_USB_DP   (20)
#define MMWK_IO_IOT_RESET    (-1)


/*
* Sensor
*/
#define MMWK_IO_I2C_SDA      (2)
#define MMWK_IO_I2C_SCL      (1)
#define MMWK_IO_VEML6030_INT (-1)
#define MMWK_IO_BMI160_INT   (-1)

#endif /* __MMWK_IO_DEF_H__ */