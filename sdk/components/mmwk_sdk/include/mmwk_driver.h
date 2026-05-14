#ifndef __MMWK_DRIVER_H__
#define __MMWK_DRIVER_H__

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include "radar_io_def.h"

#ifdef __cplusplus
extern "C" {
#endif

#define MMWK_DRIVER_VERSION    ("1.1.0")

/* ============== Board Configuration ============== */

typedef struct {
    int sop;                /* GPIO pin for controlling the radar boot mode */
    int power;              /* GPIO pin for powering the radar */
    int flash;              /* GPIO pin for controlling the radar flash power */
    int sop_reversed;       /* Whether the SOP pin's voltage level is reversed, 0 for normal, 1 for reversed */
} radar_board_ctrl_io_cfg_t;

typedef struct {
    int txd;     /* GPIO pin for UART TX */
    int rxd;     /* GPIO pin for UART RX */
    int rts;     /* GPIO pin for UART RTS */
    int cts;     /* GPIO pin for UART CTS */
} radar_board_uart_io_cfg_t;

typedef struct {
    int cs;      /* GPIO pin for SPI CS */
    int miso;    /* GPIO pin for SPI MISO */
    int mosi;    /* GPIO pin for SPI MOSI */
    int clk;     /* GPIO pin for SPI CLK */
    int irq;     /* GPIO pin for SPI IRQ */
} radar_board_spi_io_cfg_t;

#define RADAR_CHIP_XWR6843      6843
#define RADAR_CHIP_XWR1843      1843
#define RADAR_CHIP_XWRL6432     6432

/**
 * @brief ESP32 platform board configuration structure
 */
typedef struct {
    radar_board_ctrl_io_cfg_t   ctrl_io;            /* Radar Control IO configuration */
    radar_board_spi_io_cfg_t    spi_io;             /* SPI IO configuration */
    int                         cmd_uart_num;       /* Command UART port number (0, 1, 2), -1 to disable */
    int                         cmd_baudrate;       /* Command UART baudrate, e.g. 115200 */
    radar_board_uart_io_cfg_t   cmd_uart_io;        /* Command UART IO configuration */
    int                         data_uart_num;      /* Data UART port number (0, 1, 2), -1 to disable */
    int                         data_baudrate;      /* Data UART baudrate, e.g. 921600 */
    radar_board_uart_io_cfg_t   data_uart_io;       /* Data UART IO configuration */
    const char*                 board;              /* The radar board name */
    int                         radar_chip;         /* Radar chip type */
} radar_board_cfg_t;

/**
 * @brief Default radar board configuration macro
 * Uses Kconfig values from radar_io_def.h
 */
#define DEFAULT_RADAR_BOARD_CFG() { \
    .ctrl_io = { \
        .sop   =  MMWK_IO_RADAR_BOOT_CTL,          /* GPIO pin for SOP control */ \
        .power =  MMWK_IO_RADAR_PWR_EN,            /* GPIO pin for power control */ \
        .flash =  MMWK_IO_RADAR_FLASH_PWR,         /* GPIO pin for flash control */ \
        .sop_reversed = MMWK_IO_RADAR_SOP_REVERSED /* SOP pin is not reversed */ \
    }, \
    .spi_io = { \
        .cs =   MMWK_IO_RADAR_SPI_CS,       /* SPI CS pin, -1 if not used */ \
        .miso = MMWK_IO_RADAR_SPI_MISO,     /* SPI MISO pin, -1 if not used */ \
        .mosi = MMWK_IO_RADAR_SPI_MOSI,     /* SPI MOSI pin, -1 if not used */ \
        .clk =  MMWK_IO_RADAR_SPI_CLK,      /* SPI CLK pin, -1 if not used */ \
        .irq =  MMWK_IO_RADAR_SPI_INT       /* SPI IRQ pin, -1 if not used */ \
    }, \
    .cmd_uart_num = MMWK_RADAR_UART_CMD,    /* Command UART port number */ \
    .cmd_baudrate = 115200,                 /* Command UART baudrate */ \
    .cmd_uart_io = { \
        .txd = MMWK_IO_RADAR_CMD_TX,         /* Command UART TX pin */ \
        .rxd = MMWK_IO_RADAR_CMD_RX,         /* Command UART RX pin */ \
        .rts = -1,                           /* Command UART RTS pin, -1 if not used */ \
        .cts = -1                            /* Command UART CTS pin, -1 if not used */ \
    }, \
    .data_uart_num = MMWK_RADAR_UART_DATA,   /* Data UART port number */ \
    .data_baudrate = 921600,                 /* Data UART baudrate */ \
    .data_uart_io = { \
        .txd = MMWK_IO_RADAR_DATA_TX,        /* Data UART TX pin */ \
        .rxd = MMWK_IO_RADAR_DATA_RX,        /* Data UART RX pin */ \
        .rts = -1,                           /* Data UART RTS pin, -1 if not used */ \
        .cts = -1                            /* Data UART CTS pin, -1 if not used */ \
    }, \
    .board = CONFIG_RADAR_BOARD_NAME,                /* Board name */ \
    .radar_chip = CONFIG_RADAR_BOARD_RADAR_CHIP      /* Radar chip type */ \
}

/* ============== Firmware Stream Interface ============== */

/**
 * @brief Firmware stream interface for reading firmware data
 */
typedef struct {
    void*  ctx;             /**< User context */
    size_t total_size;      /**< Total size of firmware (Required) */
    /** Read data from stream. Returns bytes read. */
    size_t (*read)(void* ctx, void* buf, size_t size);
    /** Close/cleanup the stream */
    void   (*close)(void* ctx);
} mmwk_driver_fw_stream_t;

/**
 * @brief Callback to generate configuration data in memory
 * @param ctx User context passed as configure_ctx
 * @param size Output variable for the size of generated configuration
 * @return Pointer to the configuration buffer (must remain valid until driver init completes), or NULL on error
 */
typedef const char* (*mmwk_driver_config_fn_t)(void* ctx, uint32_t* size);

/**
 * @brief Helper function to load config from file (used by MMWK_DRIVER_CONFIG_FROM_FILE macro)
 * @param ctx File path cast to void*
 * @param size Output variable for the size of config data
 * @return Pointer to allocated config buffer, or NULL on error. Caller must free.
 */
const char* mmwk_driver_config_from_file(void* ctx, uint32_t* size);

/**
 * @brief Macro to create a file-based config source
 * @param path Path to the config file
 *
 * Usage: .configure = MMWK_DRIVER_CONFIG_FROM_FILE("/spiffs/radar.cfg")
 */
#define MMWK_DRIVER_CONFIG_FROM_FILE(path) \
    mmwk_driver_config_from_file, (void*)(path)

/**
 * @brief Firmware configuration structure
 */
typedef struct {
    bool            welcome;        /* whether boot should wait for startup/welcome text from the firmware */
    bool            verify_version; /* when true, require version substring to appear in welcome text */
    const char*     version;        /* version substring / firmware identifier, optional unless verify_version=true */
    mmwk_driver_config_fn_t configure; /* callback to generate config in memory, NULL = no config */
    void*           configure_ctx;  /* context passed to configure callback */
    const char*     prompt;         /* command response end marker (prompt), NULL to use default */

    /** Open a firmware stream. Called by driver when firmware data is needed.
     * @param ctx stream_ctx provided below
     * @param out Output stream structure to populate
     * @return true on success, false on failure
     */
    bool (*open_stream)(void* ctx, mmwk_driver_fw_stream_t* out);
    void* stream_ctx;               /**< Context passed to open_stream */
} mmwk_driver_fw_cfg_t;

typedef struct {
    bool cmd_bytes_seen;                  /**< true once any command-port bytes were observed during boot */
    uint32_t cmd_bytes_total;             /**< total command-port bytes observed during boot */
    bool welcome_seen;                    /**< true once any printable startup text was observed on the command UART */
    uint32_t leading_noise_bytes;         /**< leading non-printable, non-whitespace startup bytes before printable text */
    bool welcome_preview_truncated;       /**< true if the printable startup preview was truncated */
    char welcome_preview[64];             /**< printable startup preview captured from command-UART ingress */
} mmwk_driver_boot_observation_t;

typedef struct {
    uint64_t read_bytes;                  /**< total bytes returned by uart_read_bytes() */
    uint64_t fifo_overflows;              /**< UART FIFO overflow events reported by the driver */
    uint64_t buffer_full_events;          /**< UART ring-buffer full events reported by the driver */
    uint64_t frame_errors;                /**< UART frame error events reported by the driver */
    uint64_t parity_errors;               /**< UART parity error events reported by the driver */
    uint32_t buffered_bytes_high_water;   /**< largest buffered-byte snapshot seen while draining this UART */
} mmwk_driver_uart_port_diag_t;

typedef struct {
    mmwk_driver_uart_port_diag_t cmd_uart;
    mmwk_driver_uart_port_diag_t data_uart;
} mmwk_driver_uart_diag_t;

#define MMWK_DRIVER_CONFIG_ERROR_COMMAND_SIZE 96
#define MMWK_DRIVER_CONFIG_ERROR_RESPONSE_SIZE 160

typedef struct {
    bool present;                                               /**< true when the latest config failure captured command context */
    char command[MMWK_DRIVER_CONFIG_ERROR_COMMAND_SIZE];       /**< Config command that received the fatal response */
    char response[MMWK_DRIVER_CONFIG_ERROR_RESPONSE_SIZE];     /**< Fatal response preview returned by the radar */
} mmwk_driver_config_error_t;

/* ============== Driver API ============== */

typedef struct mmwk_driver* mmwk_driver_handle;

typedef enum {
    MMWK_DRIVER_ERR_NONE       = 0,    /**< No error */
    MMWK_DRIVER_ERR_PARAM      = -1,   /**< Invalid parameter */
    MMWK_DRIVER_ERR_MEMORY     = -2,   /**< Memory allocation failed */
    MMWK_DRIVER_ERR_BOARD      = -3,   /**< Board operation failed */
    MMWK_DRIVER_ERR_FIRMWARE   = -4,   /**< Firmware loading failed */
    MMWK_DRIVER_ERR_CMD        = -5,   /**< Radar command execution failed (reported from radar)*/
    MMWK_DRIVER_ERR_TIMEOUT    = -6,   /**< Timeout when interacting with the radar */
    MMWK_DRIVER_ERR_FLASH      = -7,   /**< Flash operation failed */
    MMWK_DRIVER_ERR_STATE      = -8,   /**< Internal state error */
    MMWK_DRIVER_ERR_VERSION    = -9,   /**< Version error */
    MMWK_DRIVER_ERR_DATA       = -10,  /**< Data error */
    MMWK_DRIVER_ERR_FRAME      = -11,  /**< Frame error */
} mmwk_driver_err_t;

/**
 * @brief Progress callback status for flash operations
 */
typedef enum {
    MMWK_DRIVER_PROGRESS_CONTINUE = 0,  /**< Continue the operation */
    MMWK_DRIVER_PROGRESS_ABORT = 1      /**< Abort the operation */
} mmwk_driver_progress_status_t;

/**
 * @brief Convert radar driver error code to string
 * @param err Error code
 * @return String representation of the error code
 */
#define mmwk_driver_err_to_str(err) \
    ((err) == MMWK_DRIVER_ERR_NONE     ? "No error" : \
     (err) == MMWK_DRIVER_ERR_PARAM    ? "Invalid parameter" : \
     (err) == MMWK_DRIVER_ERR_MEMORY   ? "Memory allocation failed" : \
     (err) == MMWK_DRIVER_ERR_BOARD    ? "Board operation failed" : \
     (err) == MMWK_DRIVER_ERR_FIRMWARE ? "Firmware loading failed" : \
     (err) == MMWK_DRIVER_ERR_CMD      ? "Radar command execution failed" : \
     (err) == MMWK_DRIVER_ERR_TIMEOUT  ? "Timeout when interacting with the radar" : \
     (err) == MMWK_DRIVER_ERR_FLASH    ? "Flash operation failed" : \
     (err) == MMWK_DRIVER_ERR_STATE    ? "Internal state error" : \
     (err) == MMWK_DRIVER_ERR_VERSION  ? "Version error" : \
     (err) == MMWK_DRIVER_ERR_DATA     ? "Data error" : \
     (err) == MMWK_DRIVER_ERR_FRAME    ? "Frame error" : \
     "Undefined error")

/* Raw Data Listener. Data from the command port or data port are dispatched as they are received. */
typedef struct {
    /* raw command response data, every byte received from the radar will be dispatched by this callback */
    void (*on_cmd_data)(const uint8_t* data, uint32_t len, void* ctx);

    /* raw radar data, every byte received from the radar will be dispatched by this callback */
    void (*on_radar_data)(const uint8_t* data, uint32_t len, void* ctx);
} mmwk_driver_raw_data_listener_t;

/* Application Data listener for running your own logics */
typedef struct {
    /* there are multiple reponses for a radar command and every response will be dispatched by this callback */
    void (*on_cmd_resp)(const uint8_t* data, uint32_t len, void* ctx);

    /* a complete frame of radar data */
    void (*on_radar_frame)(const uint8_t* data, uint32_t len, void* ctx);

    /* Called before sending command. Allows modification of command text and size. */
    void (*on_cmd_sending)(uint8_t** sending_text, uint8_t* sending_text_size, void* cmd, void* ctx);

    /* Called after command has been sent to UART */
    void (*on_cmd_sent)(void* ctx);
} mmwk_driver_app_data_listener_t;

/* Driver events callbacks */
typedef struct {
    /* Notification callback called before firmware flashing starts.
     * This is for notification only - the driver manages firmware state internally.
     * Parameters:
     *   - fid: Firmware ID that will be flashed
     *   - version_str: Firmware version string (can be NULL)
     *   - ctx: User context
     */
    void (*on_flash_prepare)(int fid, const char* version_str, void* ctx);

    /* Flash progress callback. Return MMWK_DRIVER_PROGRESS_CONTINUE to continue,
     * or MMWK_DRIVER_PROGRESS_ABORT to cancel the flash operation. */
    mmwk_driver_progress_status_t (*on_flash_progress)(uint32_t sent, uint32_t total, void* ctx);

    /* Notification callback called after firmware flashing completes.
     * This is for notification only - the driver manages firmware state internally.
     * Parameters:
     *   - fid: Firmware ID that was flashed
     *   - version_str: Firmware version string (can be NULL)
     *   - success: true if flash succeeded, false if failed
     *   - ctx: User context
     */
    void (*on_flash_done)(int fid, const char* version_str, bool success, void* ctx);

    /* Notification callback called after radar firmware has been successfully booted.
     * Parameters:
     *   - fid: Firmware ID that was booted
     *   - version_str: Firmware version string (can be NULL)
     *   - ctx: User context
     */
    void (*on_firmware_booted)(int fid, const char* version_str, void* ctx);

    /* Error callback during the driver execution (the driver keeps running) */
    void (*on_run_error)(mmwk_driver_err_t err, void* ctx);

    /* Notification callback called when boot retry occurs.
     * Parameters:
     *   - attempt: Current attempt number (1-based)
     *   - max_attempts: Total attempts configured
     *   - last_error: Error from previous attempt
     *   - ctx: User context
     */
    void (*on_boot_retry)(uint8_t attempt, uint8_t max_attempts, mmwk_driver_err_t last_error, void* ctx);
} mmwk_driver_event_listener_t;

typedef enum {
    MMWK_DRIVER_SINGLE_UART_ROUTE_LEGACY_CMD = 0,
    MMWK_DRIVER_SINGLE_UART_ROUTE_SPLIT_AFTER_SENSOR_START = 1,
} mmwk_driver_single_uart_route_policy_t;

typedef enum {
    MMWK_DRIVER_BOOT_DEFAULT = 0,  /* default boot mode: boot directly without flashing */
    MMWK_DRIVER_BOOT_UPDATE  = 1,  /* UART flash + one-shot exit after update flow */
    MMWK_DRIVER_BOOT_HOST    = 2,  /* host mode: power on + init uart, skip firmware/config, receive data directly (a firmware should be already flashed into radar) */
    MMWK_DRIVER_BOOT_SPI     = 3,  /* SPI load for current runtime session, then continue receive loop */
} mmwk_driver_boot_mode_t;

typedef struct {
    radar_board_cfg_t                   board_cfg;          /**< board configuration (driver manages board lifecycle internally) */
    mmwk_driver_boot_mode_t            mode;               /* boot mode */
    mmwk_driver_single_uart_route_policy_t single_uart_route_policy; /* runtime routing policy for single-UART boards */
    bool                                disable_cmd_startup_trim; /* disable command-UART startup prefix trim; zero-init keeps trim enabled */
    bool                                skip_erase;         /* Skip flash erase during UART flashing (experimental, may fail) */
    uint8_t                             retry_count;        /**< Number of retries on boot failure (0 = no retry, default) */
    mmwk_driver_fw_cfg_t               firmware;           /**< firmware configuration */
    mmwk_driver_raw_data_listener_t    raw_data_listener;  /**< raw data listener */
    mmwk_driver_app_data_listener_t    app_data_listener;  /**< application data listener */
    mmwk_driver_event_listener_t       driver_listener;    /**< driver listener */
    void*                               user_ctx;           /**< user's context object */
} mmwk_driver_cfg_t;

/**
 * @brief Initialize the radar driver
 * @param cfg
 * @param out
 * @return  0 on success, other value on error
 */
mmwk_driver_err_t mmwk_driver_init(mmwk_driver_cfg_t* cfg, mmwk_driver_handle* out);

/**
 * @brief Run the radar driver in the current thread's context. The function should be runned in a dedicated thread.
 * @return  0 on success, other value on error
 */
mmwk_driver_err_t mmwk_driver_run(mmwk_driver_handle handle);

/**
 * @brief Send a command to the radar, this is only valid when the driver is running and configured as hosted config mode.
 * @param handle The radar driver handle
 * @param cmd The command buffer (does not need to be null-terminated)
 * @param cmd_len The length of the command in bytes
 * @return  0 on success, other value on error
 */
mmwk_driver_err_t mmwk_driver_send_cmd(mmwk_driver_handle handle, const uint8_t* cmd, size_t cmd_len);

/**
 * @brief Stop the radar driver.
 * @return  0 on success, other value on error
 */
mmwk_driver_err_t mmwk_driver_stop(mmwk_driver_handle handle);

/**
 * @brief Enable or disable runtime frame parsing for bytes arriving on the radar data path.
 *
 * Raw byte forwarding remains active regardless of this flag. Disabling parsing is intended for
 * high-rate raw capture modes where the caller wants to preserve UART ingress budget and does not
 * need frame-layer callbacks during that window.
 *
 * @param handle Driver handle
 * @param enabled true to keep runtime frame parsing enabled, false to bypass it
 */
void mmwk_driver_set_runtime_frame_parse_enabled(mmwk_driver_handle handle, bool enabled);

/**
 * @brief Deinitialize the radar driver
 * @return  0 on success, other value on error
 */
mmwk_driver_err_t mmwk_driver_deinit(mmwk_driver_handle handle);

/**
 * @brief Return the latest boot observation snapshot collected by the driver.
 * @param handle Driver handle
 * @param out Observation snapshot output
 * @return 0 on success, other value on error
 */
mmwk_driver_err_t mmwk_driver_get_boot_observation(mmwk_driver_handle handle,
                                                     mmwk_driver_boot_observation_t* out);

/**
 * @brief Return the latest radar config command failure context.
 * @param handle Driver handle
 * @param out Config failure context output
 * @return 0 on success, other value on error
 */
mmwk_driver_err_t mmwk_driver_get_config_error(mmwk_driver_handle handle,
                                                 mmwk_driver_config_error_t* out);

/**
 * @brief Return the latest UART ingress diagnostics for the driver.
 * @param handle Driver handle
 * @param out UART diagnostics output
 * @return 0 on success, other value on error
 */
mmwk_driver_err_t mmwk_driver_get_uart_diag(mmwk_driver_handle handle,
                                              mmwk_driver_uart_diag_t* out);


#ifdef __cplusplus
}
#endif

#endif
