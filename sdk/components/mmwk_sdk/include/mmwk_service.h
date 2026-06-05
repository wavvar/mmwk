#ifndef __MMWK_SERVICE_H__
#define __MMWK_SERVICE_H__

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "esp_err.h"
#include "sdkconfig.h"
#if !CONFIG_MMWK_SDK_RAW_ONLY
#include "radar_frame_proc.h"
#else
typedef void radar_frame_proc_handle_base_t;
#endif
#include "mmwk_driver.h"
#include "mmwk_sensor_raw.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ============================================================================
 * Data Types and Configurations
 * ============================================================================ */

/**
 * @brief Opaque handle for radar sensor service
 */
typedef struct mmwk_service* mmwk_service_handle_t;

/**
 * @brief Radar service state
 */
typedef enum {
    MMWK_SERVICE_STATE_STOPPED = 0,    /**< Stopped */
    MMWK_SERVICE_STATE_STARTING,       /**< Starting */
    MMWK_SERVICE_STATE_RUNNING,        /**< Running */
    MMWK_SERVICE_STATE_UPDATING,       /**< Updating firmware */
    MMWK_SERVICE_STATE_ERROR,          /**< Error state */
} mmwk_service_state_t;

/**
 * @brief Service start mode
 */
typedef enum {
    MMWK_SERVICE_START_AUTO = 0,   /**< Auto mode: check version, flash if needed */
    MMWK_SERVICE_START_HOST,       /**< Host mode: start directly, no flash */
} mmwk_service_start_mode_t;

/**
 * @brief Service error codes
 */
typedef enum {
    MMWK_SERVICE_OK = 0,
    MMWK_SERVICE_ERR_INVALID_ARG = -1,
    MMWK_SERVICE_ERR_NO_MEM = -2,
    MMWK_SERVICE_ERR_BOOT_FAIL = -3,
    MMWK_SERVICE_ERR_VERSION_READ = -4,
    MMWK_SERVICE_ERR_FLASH_FAIL = -5,
    MMWK_SERVICE_ERR_CONFIG_FAIL = -6,
    MMWK_SERVICE_ERR_FW_NOT_FOUND = -7,
    MMWK_SERVICE_ERR_FW_DOWNLOAD = -8,
    MMWK_SERVICE_ERR_FW_STORAGE = -9,
    MMWK_SERVICE_ERR_FW_DEL_DEFAULT = -10,
    MMWK_SERVICE_ERR_FW_DEL_FACTORY = -11,
    MMWK_SERVICE_ERR_FW_INVALID_IDX = -12,
    MMWK_SERVICE_ERR_NVS = -13,
    MMWK_SERVICE_ERR_FS = -14,
    MMWK_SERVICE_ERR_ALREADY_RUNNING = -15,
    MMWK_SERVICE_ERR_NOT_RUNNING = -16,
    MMWK_SERVICE_ERR_NOT_SUPPORTED = -17,
    MMWK_SERVICE_ERR_FAIL = -99,
} mmwk_service_err_t;

/**
 * @brief Startup parameters owned by the caller and consumed by mmwk_service.
 */
typedef struct {
    uint8_t single_uart_split;      /**< Split single-UART radar data after sensorStart (0/1) */
} mmwk_service_startup_cfg_t;

/**
 * @brief Radar sensor service configuration
 *
 * Sensor enable/disable is controlled by the processor handle,
 * not by this configuration structure.
 */
typedef struct mmwk_service_cfg {
    radar_board_cfg_t board_cfg;    /**< Radar board configuration */
    int task_priority;              /**< RTOS task priority for the service */
    int task_core;                  /**< Optional task core affinity; use tskNO_AFFINITY for no pinning */
    mmwk_driver_config_fn_t config_cb; /**< Optional config provider callback */
    void* config_ctx;               /**< Context for config_cb */
    mmwk_service_startup_cfg_t startup; /**< Caller-owned startup configuration */
} mmwk_service_cfg_t;

#ifdef CONFIG_RADAR_SINGLE_UART_SPLIT_DEFAULT
#define MMWK_SERVICE_DEFAULT_SINGLE_UART_SPLIT 1U
#else
#define MMWK_SERVICE_DEFAULT_SINGLE_UART_SPLIT 0U
#endif

/**
 * @brief Default radar sensor service configuration macro
 */
#define DEFAULT_MMWK_SERVICE_CFG() { \
    .board_cfg = DEFAULT_RADAR_BOARD_CFG(), \
    .task_priority = 5, \
    .task_core = tskNO_AFFINITY, \
    .config_cb = NULL, \
    .config_ctx = NULL, \
    .startup = { \
        .single_uart_split = MMWK_SERVICE_DEFAULT_SINGLE_UART_SPLIT \
    } \
}

/**
 * @brief Application operations interface (for callback injection)
 *
 * Application layer sets these to connect mmwk_service with
 * the app layer (e.g. radar_hub) without compile-time dependency.
 */
typedef struct mmwk_service_fw_switch_caps mmwk_service_fw_switch_caps_t;

typedef struct {
    /**
     * @brief Query firmware switch capability flags for current app profile.
     * @param ctx User context
     * @param out_caps Output capability flags
     * @return true when out_caps is filled; false to use service defaults
     */
    bool (*get_fw_switch_caps)(void* ctx, mmwk_service_fw_switch_caps_t* out_caps);

    /**
     * @brief Get application-specific help string to append to help response.
     * @param ctx User context
     * @return Const string containing application help commands (e.g. "hub, device")
     */
    const char* (*get_help_string)(void* ctx);
} radar_app_cb_t;

typedef struct {
    esp_err_t (*enter)(void *ctx, const char *reason, uint32_t timeout_ms);
    void (*leave)(void *ctx, const char *reason);
} mmwk_service_maintenance_guard_t;


/* ============================================================================
 * Lifecycle Functions: Init -> Start -> Stop -> Deinit
 * ============================================================================ */

/**
 * @brief Initialize the radar sensor hub
 *
 * This function initializes the radar system with the specified configuration.
 * If config is NULL, all sensors will be enabled by default but board handle
 * must still be provided.
 * The board handle must be externally created and managed by the caller.
 *
 * @param handle Output handle pointer
 * @param proc_handle Processor handle created by the radar frame processor init path or similar
 * @param config Sensor enable/disable configuration (NULL for all enabled, but board must be provided)
 * @return 0 on success, negative error code on failure
 */
int mmwk_service_init(mmwk_service_handle_t* handle, radar_frame_proc_handle_base_t* proc_handle, const mmwk_service_cfg_t* config);

    /**
     * @brief Register application operations (callback injection from application layer)
     *
     * Must be called after mmwk_service_init() and before starting agents.
     *
     * @param handle Service handle
     * @param app_cb Application operations vtable
     * @param ctx Context pointer passed to app_cb functions
     */
    void mmwk_service_register_app(mmwk_service_handle_t handle, const radar_app_cb_t* app_cb, void* ctx);

void mmwk_service_set_maintenance_guard(mmwk_service_handle_t handle,
                                     const mmwk_service_maintenance_guard_t *guard,
                                     void *ctx);

/**
 * @brief Start the radar sensor hub task
 *
 * This function creates a task to run the radar sensor hub's main loop.
 * The task will run until mmwk_service_stop() is called from another thread.
 *
 * Task management is handled internally:
 * - Creates a task with recommended stack size (8KB)
 * - Task will automatically delete itself when stopped
 * - Task handle is stored internally in the hub handle
 *
 * @param handle Radar sensor hub handle (from mmwk_service_init)
 * @param mode Start mode for the service
 * @return MMWK_SERVICE_OK on success, error code otherwise
 */
mmwk_service_err_t mmwk_service_start(mmwk_service_handle_t handle, mmwk_service_start_mode_t mode);

/**
 * @brief Stop the radar sensor hub
 *
 * This function signals the radar sensor hub to stop. It should be called
 * from a different thread than the one running mmwk_service_start().
 * After calling this function, the caller should wait for the mmwk_service_start()
 * thread to complete (e.g., using vTaskDelete or pthread_join).
 *
 * Thread cleanup is the caller's responsibility:
 * - Call this function to signal stop
 * - Wait for mmwk_service_start() thread to exit
 * - Delete/join the thread
 *
 * @param handle Radar sensor hub handle
 * @return 0 on success, negative error code on failure
 */
int mmwk_service_stop(mmwk_service_handle_t handle);

/**
 * @brief Deinitialize the radar core
 *
 * This function cleans up and deinitializes the radar system.
 *
 * @return 0 on success, negative error code on failure
 */
int mmwk_service_deinit(mmwk_service_handle_t handle);


/* ============================================================================
 * State and Status Accessors
 * ============================================================================ */

/**
 * @brief Get radar service state
 */
mmwk_service_state_t mmwk_service_get_state(mmwk_service_handle_t handle);

/**
 * @brief Get the current radar service start mode cache.
 */
mmwk_service_start_mode_t mmwk_service_get_start_mode(mmwk_service_handle_t handle);

/**
 * @brief Structured status details for the latest radar startup/run failure.
 */
typedef struct {
    bool present;                           /**< true if details contain a valid failure record */
    char kind[32];                          /**< Stable machine-readable category, e.g. startup_failed */
    char stage[32];                         /**< Failure stage, e.g. welcome/config/driver/init */
    char message[160];                      /**< Human-readable explanation for operators */
    int error_code;                         /**< Underlying mmwk_driver error code */
    char error_name[40];                    /**< Underlying mmwk_driver symbolic error name */
    bool expected_welcome;                  /**< Whether startup welcome text was expected */
    char expected_version[64];              /**< Expected version substring, if any */
    bool cmd_bytes_seen;                    /**< Whether command-port bytes were observed during boot */
    uint32_t cmd_bytes_total;               /**< Total command-port bytes observed during boot */
    uint32_t leading_noise_bytes;           /**< Count of leading non-printable startup bytes */
    bool welcome_seen;                      /**< Whether non-empty startup output was observed */
    bool welcome_preview_truncated;         /**< Whether welcome_preview was truncated */
    char welcome_preview[64];               /**< Printable startup preview, if any */
    char config_command[MMWK_DRIVER_CONFIG_ERROR_COMMAND_SIZE];   /**< Config command that failed, if known */
    char config_response[MMWK_DRIVER_CONFIG_ERROR_RESPONSE_SIZE]; /**< Fatal config response preview, if known */
} mmwk_service_status_details_t;

/**
 * @brief Snapshot returned by radar status queries.
 */
typedef struct {
    mmwk_service_state_t state;                /**< Current service state */
    mmwk_service_status_details_t details;     /**< Present only when state=error */
} mmwk_service_status_snapshot_t;

/**
 * @brief Query the current radar service status snapshot.
 *
 * @param handle Service handle.
 * @param out_status Output snapshot buffer.
 * @return MMWK_SERVICE_OK on success; error code otherwise.
 */
mmwk_service_err_t mmwk_service_get_status_snapshot(mmwk_service_handle_t handle,
                                              mmwk_service_status_snapshot_t* out_status);

/**
 * @brief Default firmware metadata from firmware manager.
 */
typedef struct {
    char name[32];
    char version[32];
    char config_name[32];
} mmwk_service_fw_meta_t;

struct mmwk_service_fw_switch_caps {
    bool persist;
    bool temp;
};

typedef struct {
    char source[16];
    int index;
    char name[32];
    char version[32];
    char config[32];
} mmwk_service_fw_entry_state_t;

typedef struct {
    mmwk_service_fw_entry_state_t fw_default;
    mmwk_service_fw_entry_state_t fw_running;
    mmwk_service_fw_switch_caps_t fw_switch;
    char fw_mode[16];
    bool running_is_default;
} mmwk_service_fw_runtime_state_t;

typedef struct {
    int index;
    char name[32];
    char version[32];
    char config_name[32];
    char source[16];
    char path[128];
    size_t size;
    bool is_default;
    bool is_running;
} mmwk_service_fw_catalog_entry_t;

typedef struct {
    bool packets_enabled;
    bool frames_enabled;
    uint64_t raw_bytes_in;
    uint64_t record_bytes_in;
    uint64_t raw_packets_in;
    uint64_t record_packets_in;
    uint64_t raw_frames_in;
} mmwk_service_debug_snapshot_t;

/**
 * @brief Query current default firmware metadata.
 *
 * @param out_meta Output metadata buffer.
 * @return MMWK_SERVICE_OK on success; error code otherwise.
 */
mmwk_service_err_t mmwk_service_get_default_fw_meta(mmwk_service_fw_meta_t* out_meta);

/**
 * @brief Query current default/running firmware runtime state.
 *
 * @param handle Service handle.
 * @param out_state Output runtime state buffer.
 * @return MMWK_SERVICE_OK on success; error code otherwise.
 */
mmwk_service_err_t mmwk_service_get_fw_runtime_state(mmwk_service_handle_t handle,
                                               mmwk_service_fw_runtime_state_t* out_state);

/**
 * @brief Query one firmware catalog entry by stable position.
 *
 * @param handle Service handle used to resolve default/running flags.
 * @param position Stable catalog position.
 * @param out_entry Output entry buffer.
 * @return MMWK_SERVICE_OK on success; MMWK_SERVICE_ERR_FW_NOT_FOUND when position is exhausted.
 */
mmwk_service_err_t mmwk_service_get_fw_catalog_entry_by_position(mmwk_service_handle_t handle,
                                                           size_t position,
                                                           mmwk_service_fw_catalog_entry_t* out_entry);

/**
 * @brief Query current radar debug switches and counters.
 *
 * @param handle Service handle.
 * @param out_snapshot Output snapshot buffer.
 * @return MMWK_SERVICE_OK on success; error code otherwise.
 */
mmwk_service_err_t mmwk_service_get_debug_snapshot(mmwk_service_handle_t handle,
                                             mmwk_service_debug_snapshot_t* out_snapshot);

/**
 * @brief Reset accumulated radar debug counters.
 *
 * @param handle Service handle.
 * @return MMWK_SERVICE_OK on success; error code otherwise.
 */
mmwk_service_err_t mmwk_service_reset_debug_snapshot(mmwk_service_handle_t handle);



/* ============================================================================
 * Firmware Update Subsystem
 * ============================================================================ */


/**
 * @brief Radar update event types
 */
typedef enum {
    /* Download phase events */
    RADAR_UPDATE_EVENT_DOWNLOAD_START,      /**< Firmware download started */
    RADAR_UPDATE_EVENT_DOWNLOAD_PROGRESS,   /**< Download in progress */
    RADAR_UPDATE_EVENT_DOWNLOAD_SUCCESS,    /**< Download completed successfully */
    RADAR_UPDATE_EVENT_DOWNLOAD_FAILED,     /**< Download failed */

    /* Flash/Update phase events */
    RADAR_UPDATE_EVENT_FLASH_START,         /**< Firmware flash/update started */
    RADAR_UPDATE_EVENT_FLASH_PROGRESS,      /**< Flash in progress */
    RADAR_UPDATE_EVENT_FLASH_SUCCESS,       /**< Flash completed successfully */
    RADAR_UPDATE_EVENT_FLASH_FAILED,        /**< Flash failed */
} radar_update_event_type_t;

/**
 * @brief Radar update event data
 */
typedef struct {
    radar_update_event_type_t event_type;   /**< Event type */
    size_t bytes_processed;                  /**< Bytes downloaded/written */
    size_t total_bytes;                      /**< Total bytes (0 if unknown) */
    int error_code;                          /**< Error code (0 if no error) */
    const char* error_message;               /**< Error message (NULL if no error) */
    const char* uri;                         /**< Source URI */
} radar_update_event_t;

/**
 * @brief Radar firmware update configuration

 */
typedef struct {
    char base[256];           /**< Base URI (protocol://host:port) */
    char firmware[256];       /**< Firmware path relative to base */
    char config[256];         /**< Config path relative to base (optional, only if config update needed) */
    bool welcome;             /**< Whether target firmware emits welcome/startup text */
    bool welcome_set;         /**< Whether welcome was explicitly provided by caller */
    bool verify;              /**< Whether to verify version substring inside welcome text */
    char version[64];         /**< Version substring / target version (optional unless verify=true) */
    char cert_url[256];       /**< Certificate URL for HTTPS/MQTTS (optional, if mutual auth/custom CA needed) */
    char fw_topic[128];       /**< MQTT firmware topic (optional, defaults to standard topic) */
    char cfg_topic[128];      /**< MQTT config topic (optional, defaults to standard topic) */
    bool force;               /**< Force update even if version matches */

    /* UART mode specific fields (used when base = "uart://") */
    size_t firmware_size;     /**< Firmware size in bytes (required for UART mode) */
    size_t config_size;       /**< Config size in bytes (0 if no config, required for UART mode if config specified) */
    size_t chunk_size;        /**< Chunk size in bytes (optional, default 4096) */
    int prog_intvl;           /**< Progress report interval in seconds (0 = fast/no interval) */
} radar_update_config_t;


/**
 * @brief Initialize UART firmware update
 * 
 * @param handle Service handle
 * @param config Update configuration
 * @return 0 on success, negative error code on failure
 */
int mmwk_service_update_uart_init(mmwk_service_handle_t handle, const radar_update_config_t* config);

/**
 * @brief Receive data chunk for UART firmware update
 * 
 * @param handle Service handle
 * @param file_type Type of file being updated ("firmware" or "config")
 * @param seq Sequence number
 * @param b64_data Base64 encoded payload
 * @return 0 on success, negative error code on failure
 */
int mmwk_service_update_uart_data(mmwk_service_handle_t handle, const char* file_type, uint32_t seq, const char* b64_data);

/**
 * @brief Finish UART firmware update and trigger flashing
 * 
 * @param handle Service handle
 * @return 0 on success, negative error code on failure
 */
int mmwk_service_update_uart_complete(mmwk_service_handle_t handle);

/**
 * @brief Cancel ongoing UART firmware update
 * 
 * @param handle Service handle
 * @return 0 on success, negative error code on failure
 */
int mmwk_service_update_uart_cancel(mmwk_service_handle_t handle);

int mmwk_service_update_stream_prepare_local_storage(mmwk_service_handle_t handle,
                                                  const char* local_path,
                                                  size_t required_bytes);
size_t mmwk_service_update_stream_write_all(FILE* fp, const void* data, size_t len);
int mmwk_service_begin_stream_update_staging(mmwk_service_handle_t handle);
void mmwk_service_end_stream_update_staging(mmwk_service_handle_t handle);

/* ============================================================================
 * Common Async Command Interface
 * ============================================================================ */

/**
 * @brief Command IDs for asynchronous radar service execution
 */
typedef enum {
    MMWK_SERVICE_CMD_START = 0,
    MMWK_SERVICE_CMD_STOP,
    MMWK_SERVICE_CMD_GET_VERSION,
    MMWK_SERVICE_CMD_GET_STATUS,
    
    /* Data / Raw Data Agent */
    MMWK_SERVICE_CMD_GET_CFG,
    MMWK_SERVICE_CMD_GET_DATA_CFG,
    MMWK_SERVICE_CMD_SET_DATA_CFG,
    MMWK_SERVICE_CMD_DEBUG_SET,
    MMWK_SERVICE_CMD_DEBUG_GET,
    MMWK_SERVICE_CMD_DEBUG_SNAPSHOT,
    MMWK_SERVICE_CMD_DEBUG_RESET,
    
    /* Record Operations */
    MMWK_SERVICE_CMD_RECORD_START,
    MMWK_SERVICE_CMD_RECORD_STOP,
    MMWK_SERVICE_CMD_RECORD_TRIGGER,
    
    /* OTA Update */
    MMWK_SERVICE_CMD_UPDATE_OTA,
    MMWK_SERVICE_CMD_UPDATE_FLASH,
    MMWK_SERVICE_CMD_RECONF_BEGIN,
    MMWK_SERVICE_CMD_RECONF_COMPLETE,
    MMWK_SERVICE_CMD_UPDATE_UART_DATA,
    MMWK_SERVICE_CMD_UPDATE_UART_COMPLETE,
    MMWK_SERVICE_CMD_UPDATE_UART_CANCEL,
    
    /* Firmware Manager */
    MMWK_SERVICE_CMD_FW_INFO,
    MMWK_SERVICE_CMD_FW_LIST,
    MMWK_SERVICE_CMD_FW_SWITCH,
    MMWK_SERVICE_CMD_FW_SET,
    MMWK_SERVICE_CMD_FW_DEL,
    MMWK_SERVICE_CMD_FW_DOWNLOAD,
} mmwk_service_cmd_id_t;

/* Command argument structures */

typedef struct {
    bool set;                      /* true = write, false = read */
    mmwk_service_start_mode_t mode;   /* only used if set == true */
} mmwk_service_cmd_status_args_t;

typedef struct {
    bool enabled;
    char uri[128];
    char data_topic[128];
    char resp_topic[128];
    char cmd_topic[128];
    void* client_handle;       /**< External MQTT client handle (NULL = create new from uri) */
} mmwk_service_cmd_data_cfg_t;

typedef struct {
    uint64_t data_listener_packets_in;
    uint64_t data_listener_bytes_in;
    uint64_t data_mqtt_attempts;
    uint64_t data_mqtt_failures;
    /* WDR single-UART diagnostics need to distinguish "broker disconnected"
     * from "publish still failed even though MQTT looked connected" so we can
     * tell transport stalls apart from ingress/routing bugs. */
    uint64_t data_mqtt_failures_while_connected;
    uint64_t data_mqtt_failures_while_disconnected;
    uint64_t data_mqtt_bytes;
    uint64_t data_mqtt_failed_bytes;
    int32_t data_mqtt_last_publish_result;
    int32_t data_mqtt_last_failure_result;
    uint64_t resp_listener_packets_in;
    uint64_t resp_listener_bytes_in;
    uint64_t resp_mqtt_attempts;
    uint64_t resp_mqtt_failures;
    uint64_t resp_mqtt_bytes;
    uint64_t resp_mqtt_failed_bytes;
    uint64_t data_backpressure_warnings;
    /* Track MQTT edge transitions explicitly so raw-capture regressions can be
     * diagnosed from one status snapshot instead of relying on log timing. */
    uint64_t mqtt_connected_events;
    uint64_t mqtt_disconnected_events;
    uint8_t mqtt_connected;
    /* Surface whether the async raw-data pool really landed in external RAM so
     * single-UART capture diagnostics can separate allocator placement from
     * UART-ingress loss. */
    uint8_t data_pool_external_ram;
    /* WDR 200 Hz loss now looks like partial sync damage rather than queue
     * exhaustion, so publish the lower-level UART driver counters beside the
     * MQTT stats to prove whether bytes were already being dropped at ingress. */
    uint64_t cmd_uart_read_bytes;
    uint64_t cmd_uart_fifo_overflows;
    uint64_t cmd_uart_buffer_full_events;
    uint64_t cmd_uart_frame_errors;
    uint64_t cmd_uart_parity_errors;
    int32_t cmd_uart_buffered_bytes_high_water;
    uint64_t data_uart_read_bytes;
    uint64_t data_uart_fifo_overflows;
    uint64_t data_uart_buffer_full_events;
    uint64_t data_uart_frame_errors;
    uint64_t data_uart_parity_errors;
    int32_t data_uart_buffered_bytes_high_water;
    int32_t mqtt_outbox_last_bytes;
    int32_t mqtt_outbox_high_water_bytes;
} mmwk_service_raw_diag_t;

typedef struct {
    bool packets_enabled;          /* include packet counters in debug snapshot */
    bool frames_enabled;           /* include frame counters in debug snapshot */
} mmwk_service_cmd_debug_cfg_t;

typedef enum {
    MMWK_SERVICE_CFG_READ_FILE = 0,
    MMWK_SERVICE_CFG_READ_GENERATED,
} mmwk_service_cfg_read_mode_t;

typedef struct {
    bool gen;
} mmwk_service_cmd_cfg_args_t;

/**
 * @brief Read the current raw forwarding configuration synchronously.
 */
mmwk_service_err_t mmwk_service_get_raw_config(mmwk_service_handle_t handle,
                                         mmwk_service_cmd_data_cfg_t* out_cfg);

/**
 * @brief Read current raw forwarding diagnostics synchronously.
 */
mmwk_service_err_t mmwk_service_get_raw_diag(mmwk_service_handle_t handle,
                                       mmwk_service_raw_diag_t* out_diag);

/**
 * @brief Apply the raw forwarding configuration synchronously.
 */
int mmwk_service_set_raw_config(mmwk_service_handle_t handle,
                             const mmwk_service_cmd_data_cfg_t* cfg);

/**
 * @brief Read the current runtime debug switch configuration synchronously.
 */
mmwk_service_err_t mmwk_service_get_debug_config(mmwk_service_handle_t handle,
                                           mmwk_service_cmd_debug_cfg_t* out_cfg);

/**
 * @brief Read radar cfg text synchronously.
 *
 * Caller owns the returned buffer and must release it with mmwk_service_free_cfg().
 */
mmwk_service_err_t mmwk_service_read_cfg(mmwk_service_handle_t handle,
                                   mmwk_service_cfg_read_mode_t mode,
                                   char** out_cfg,
                                   size_t* out_size);

/**
 * @brief Free cfg text returned by mmwk_service_read_cfg().
 */
void mmwk_service_free_cfg(char* cfg);

typedef struct {
    char uri[128];
} mmwk_service_cmd_record_start_t;

typedef struct {
    char event[64];
    int duration_sec;
} mmwk_service_cmd_record_trigger_t;

/**
 * @brief Start the raw recorder synchronously.
 */
int mmwk_service_record_start(mmwk_service_handle_t handle, const char* uri);

/**
 * @brief Stop the raw recorder synchronously.
 */
int mmwk_service_record_stop(mmwk_service_handle_t handle);

/**
 * @brief Trigger a recorder capture window synchronously.
 */
int mmwk_service_record_trigger(mmwk_service_handle_t handle,
                             const char* event,
                             int duration_sec);

typedef struct {
    int index;
} mmwk_service_cmd_fw_index_t;

typedef struct {
    uint8_t index;
    bool persist;
} mmwk_service_cmd_fw_switch_args_t;

typedef struct {
    bool changed;
    uint8_t index;
    bool persist;
} mmwk_service_fw_switch_result_t;

typedef struct {
    char source[32];
    char name[64];
    char version[64];
    size_t size;
} mmwk_service_cmd_fw_download_t;

typedef enum {
    MMWK_SERVICE_CFG_ACTION_KEEP = 0,
    MMWK_SERVICE_CFG_ACTION_REPLACE,
    MMWK_SERVICE_CFG_ACTION_CLEAR,
} mmwk_service_cfg_action_t;

typedef struct {
    bool welcome;
    bool verify;
    char version[64];
    mmwk_service_cfg_action_t cfg_action;
    size_t config_size;
    size_t chunk_size;
} mmwk_service_cmd_reconf_args_t;

typedef struct {
    char file_type[16];
    uint32_t seq;
    const char* b64_data; /* Pointer to chunk data to prevent stack overflow */
} mmwk_service_cmd_uart_data_t;

/**
 * @brief Unified asynchronous command structure
 */
typedef struct {
    mmwk_service_cmd_id_t id;
    uint32_t msg_id;               /**< Application-provided message ID, returned in event */
    void* source_ctx;              /**< Opaque application context (e.g., origin channel), returned in event */
    
    union {
        mmwk_service_cmd_status_args_t status;
        mmwk_service_cmd_cfg_args_t cfg;
        mmwk_service_cmd_data_cfg_t data_cfg;
        mmwk_service_cmd_debug_cfg_t debug_cfg;
        mmwk_service_cmd_record_start_t record_start;
        mmwk_service_cmd_record_trigger_t record_trigger;
        radar_update_config_t update;
        mmwk_service_cmd_reconf_args_t reconf;
        mmwk_service_cmd_fw_index_t fw_idx;
        mmwk_service_cmd_fw_switch_args_t fw_switch;
        mmwk_service_cmd_fw_download_t fw_download;
        mmwk_service_cmd_uart_data_t uart_data;
        /* custom sensor command payload could be placed here if needed, or mmwk_driver passes through */
    } args;
} mmwk_service_cmd_t;

/**
 * @brief Response/Event types emitted by the service
 */
typedef enum {
    MMWK_SERVICE_EVT_CMD_RESPONSE = 0,  /**< Response to a mmwk_service_execute_command */
    MMWK_SERVICE_EVT_UPDATE_PROGRESS,   /**< Firmware update progress event */
    MMWK_SERVICE_EVT_SENSOR_DATA,       /**< Raw sensor data JSON emitted by the service (if internal formatting used) */
} mmwk_service_event_type_t;

/**
 * @brief Unified event structure returned via application callback
 */
typedef struct {
    mmwk_service_event_type_t type;
    mmwk_service_err_t status;          /**< MMWK_SERVICE_OK on success, negative error code on failure */
    uint32_t msg_id;                 /**< msg_id from the original command (if type == RESPONSE) */
    void* source_ctx;                /**< source_ctx from the original command (if type == RESPONSE) */
    const char* error_msg;           /**< String description if status != OK */
    
    union {
        /* Valid if type == CMD_RESPONSE */
        struct {
            mmwk_service_cmd_id_t cmd_id;
            const void* resp_data;   /**< Callback-scoped pointer to command-specific response data; copy if needed after callback returns */
            size_t resp_len;
        } response;
        
        /* Valid if type == UPDATE_PROGRESS */
        const radar_update_event_t* update;
        
        /* Valid if type == SENSOR_DATA (raw data output from sensor) */
        struct {
            const uint8_t* payload;
            size_t len;
        } sensor_data;
    } data;
} mmwk_service_event_t;

/**
 * @brief Asynchronous event callback signature
 */
typedef void (*mmwk_service_event_cb_t)(mmwk_service_handle_t handle, const mmwk_service_event_t* event, void* user_ctx);

/**
 * @brief Execute a radar service command asynchronously
 *
 * Validates arguments and places the command in the service's internal queue.
 * The caller will receive the execution result via the registered mmwk_service_event_cb_t.
 * For MMWK_SERVICE_EVT_CMD_RESPONSE, event response pointers are callback-scoped and
 * must be copied by consumers that need to retain data after callback return.
 *
 * @param handle Service handle
 * @param cmd Structured command
 * @return MMWK_SERVICE_OK if successfully enqueued, error code if submission fails.
 */
mmwk_service_err_t mmwk_service_execute_command(mmwk_service_handle_t handle, const mmwk_service_cmd_t* cmd);

/**
 * @brief Register the global event callback for asynchronous responses
 *
 * @param handle Service handle
 * @param cb Callback function pointer
 * @param user_ctx Opaque context passed to the callback
 */
void mmwk_service_set_event_callback(mmwk_service_handle_t handle, mmwk_service_event_cb_t cb, void* user_ctx);

/**
 * @brief Register a raw listener callback for command/data-port bytes.
 *
 * The callback is independent from MQTT raw forwarding configuration and is
 * emitted by the raw route whenever raw listener bytes arrive.
 */
void mmwk_service_set_raw_event_callback(mmwk_service_handle_t handle,
                                      mmwk_sensor_raw_callback_t cb,
                                      void* user_ctx);

#ifdef __cplusplus
}
#endif

#endif
