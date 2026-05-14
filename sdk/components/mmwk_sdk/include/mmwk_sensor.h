#ifndef MMWK_SENSOR_H
#define MMWK_SENSOR_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "cJSON.h"
#include "esp_err.h"
#include "mmwk_service.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    MMWK_SENSOR_PROFILE_BRIDGE = 0,
    MMWK_SENSOR_PROFILE_HUB,
} mmwk_sensor_profile_kind_t;

typedef struct {
    mmwk_sensor_profile_kind_t kind;
    const char *name;
    bool is_hub;
} mmwk_sensor_profile_t;

typedef enum {
    MMWK_SENSOR_PROTOCOL_FAMILY_NONE = 0,
    MMWK_SENSOR_PROTOCOL_FAMILY_MCP,
    MMWK_SENSOR_PROTOCOL_FAMILY_CLI,
    MMWK_SENSOR_PROTOCOL_FAMILY_RFCARE,
} mmwk_sensor_protocol_family_id_t;

typedef enum {
    MMWK_SENSOR_BUILTIN_CONTROL_NONE = 0,
    MMWK_SENSOR_BUILTIN_CONTROL_MCP,
    MMWK_SENSOR_BUILTIN_CONTROL_CLI,
} mmwk_sensor_builtin_control_t;

typedef struct {
    mmwk_sensor_protocol_family_id_t product_family;
    mmwk_sensor_builtin_control_t builtin_control;
    const char *product_name;
    const char *builtin_control_name;
} mmwk_sensor_protocol_family_t;

typedef struct {
    bool raw_auto_default;
} mmwk_sensor_startup_policy_t;

typedef struct {
    uint8_t enable_mqtt_agent;
    uint8_t enable_uart_agent;
    uint8_t raw_auto;
    uint8_t single_uart_split;
    uint8_t led_enabled;
    uint32_t disconnect_reboot_ms;
} mmwk_sensor_app_config_t;

typedef void (*mmwk_sensor_device_send_fn_t)(void *source_ctx, const char *msg);

typedef struct {
    int32_t interval;
    char fields[128];
    void *source_ctx;
} mmwk_sensor_device_cfg_t;

typedef struct {
    char prod[64];
    char oid[64];
    char cid[64];
    char did[16];
    char mqtt_client_id[64];
    char mqtt_uri[128];
    char mqtt_user[64];
    char mqtt_pass[64];
    char cmd[128];
    char resp[128];
} mmwk_sensor_network_cfg_t;

typedef struct {
    mmwk_sensor_network_cfg_t mqtt;
    char wifi_ssid[33];
    char wifi_password[65];
} mmwk_sensor_network_direct_cfg_t;

typedef enum {
    MMWK_SENSOR_NETWORK_STATE_INITIALIZING = 0,
    MMWK_SENSOR_NETWORK_STATE_CONNECTING,
    MMWK_SENSOR_NETWORK_STATE_RETRY_BACKOFF,
    MMWK_SENSOR_NETWORK_STATE_CONNECTED,
    MMWK_SENSOR_NETWORK_STATE_PROV_WAITING,
    MMWK_SENSOR_NETWORK_STATE_FAILED,
} mmwk_sensor_network_state_t;

typedef enum {
    MMWK_SENSOR_NETWORK_WIFI_STATE_UNKNOWN = 0,
    MMWK_SENSOR_NETWORK_WIFI_STATE_STA_CONNECTING,
    MMWK_SENSOR_NETWORK_WIFI_STATE_CONNECTED,
    MMWK_SENSOR_NETWORK_WIFI_STATE_PROV_WAITING,
} mmwk_sensor_network_wifi_state_t;

#define MMWK_SENSOR_NETWORK_STA_IP_MAX_LEN 16
#define MMWK_SENSOR_NETWORK_REASON_NAME_MAX_LEN 32
#define MMWK_SENSOR_NETWORK_FAILURE_SOURCE_MAX_LEN 32

typedef struct {
    mmwk_sensor_network_state_t state;
    char sta_ip[MMWK_SENSOR_NETWORK_STA_IP_MAX_LEN];
    bool ip_ready;
    uint32_t provisioning_wait_sec;
    int32_t prov_wait_remaining_sec;
    int32_t retry_count;
    int32_t max_retry;
    int32_t retry_backoff_ms;
    int32_t last_disconnect_reason_code;
    char last_disconnect_reason_name[MMWK_SENSOR_NETWORK_REASON_NAME_MAX_LEN];
    bool terminal_failure;
    char failure_source[MMWK_SENSOR_NETWORK_FAILURE_SOURCE_MAX_LEN];
} mmwk_sensor_network_snapshot_t;

typedef struct {
    char server[128];
    int32_t tz_offset;
    int32_t interval;
} mmwk_sensor_time_cfg_t;

typedef struct {
    const char *contract_id;
    const char *builtin_protocol;
    const char *builtin_spec;
    bool builtin_enabled;
    const char *product_name;
    bool product_enabled;
    const char *product_mode;
} mmwk_sensor_protocol_surface_meta_t;

typedef struct {
    uint32_t seq;
    const char *service;
    const char *action;
    cJSON *args;
    void *source_ctx;
} mmwk_sensor_cli_request_t;

typedef enum {
    MMWK_SENSOR_CLI_STATUS_OK = 0,
    MMWK_SENSOR_CLI_STATUS_INVALID_ARG = -1,
    MMWK_SENSOR_CLI_STATUS_NOT_FOUND = -2,
    MMWK_SENSOR_CLI_STATUS_NO_MEMORY = -3,
    MMWK_SENSOR_CLI_STATUS_ERROR = -99,
} mmwk_sensor_cli_status_t;

typedef mmwk_sensor_cli_status_t (*mmwk_sensor_cli_service_handler_t)(
    const mmwk_sensor_cli_request_t *req,
    cJSON **out_result,
    void *user_ctx);

typedef void (*mmwk_sensor_service_hook_t)(mmwk_service_handle_t svc,
                                                 void *user_ctx);

mmwk_sensor_profile_t mmwk_sensor_load_profile(void);
mmwk_sensor_protocol_family_t mmwk_sensor_load_protocol_family(void);
mmwk_sensor_startup_policy_t mmwk_sensor_load_startup_policy(
    const mmwk_sensor_profile_t *profile,
    const mmwk_sensor_protocol_family_t *proto_cfg);

void mmwk_sensor_app_config_init(mmwk_sensor_app_config_t *out_cfg);
int mmwk_sensor_app_process_agent_cmd(cJSON *root, char **out_resp);

esp_err_t mmwk_sensor_device_init(void *hub, void *send_cb);
void mmwk_sensor_device_set_send_cb(mmwk_sensor_device_send_fn_t send_cb);
void mmwk_sensor_device_set_service_handle(mmwk_service_handle_t svc);
cJSON *mmwk_sensor_device_get_hi_data(void);
const char *mmwk_sensor_device_identity_name(void);
const char *mmwk_sensor_device_identity_version(void);
esp_err_t mmwk_sensor_device_config_heartbeat(int32_t interval, const char *fields);
esp_err_t mmwk_sensor_device_config_startup(mmwk_service_start_mode_t mode);
mmwk_service_start_mode_t mmwk_sensor_device_get_startup_mode(void);
bool mmwk_sensor_device_get_active_start_mode(mmwk_service_start_mode_t *out_mode);
const char *mmwk_sensor_device_startup_mode_name(mmwk_service_start_mode_t mode);
bool mmwk_sensor_device_profile_supports_startup_mode(mmwk_service_start_mode_t mode);
const char *const *mmwk_sensor_device_supported_startup_mode_names(size_t *out_count);
bool mmwk_sensor_device_raw_cmd_ingress_enabled(void);
void mmwk_sensor_device_build_raw_topics(char *data_topic,
                                         size_t data_topic_len,
                                         char *resp_topic,
                                         size_t resp_topic_len,
                                         char *cmd_topic,
                                         size_t cmd_topic_len);
int32_t mmwk_sensor_device_get_heartbeat_interval_sec(void);
void mmwk_sensor_device_get_heartbeat_fields(char *buf, size_t buf_len);
bool mmwk_sensor_device_is_ota_running(void);
esp_err_t mmwk_sensor_device_start_ota(const char *url);
esp_err_t mmwk_sensor_register_cli_service(const char *service,
                                           mmwk_sensor_cli_service_handler_t handler,
                                           void *user_ctx);
esp_err_t mmwk_sensor_register_service_hook(mmwk_sensor_service_hook_t hook,
                                                  void *user_ctx);

void mmwk_sensor_network_init(mmwk_sensor_network_cfg_t *out_cfg);
int mmwk_sensor_network_process_json_cmd(const char *action, cJSON *root, char **out_resp);
esp_err_t mmwk_sensor_network_load_direct_cfg(mmwk_sensor_network_direct_cfg_t *out_cfg);
esp_err_t mmwk_sensor_network_save_direct_cfg(const mmwk_sensor_network_direct_cfg_t *cfg);
void mmwk_sensor_network_start(void);
void mmwk_sensor_network_set_state(mmwk_sensor_network_state_t state);
mmwk_sensor_network_state_t mmwk_sensor_network_get_state(void);
const char *mmwk_sensor_network_state_name(mmwk_sensor_network_state_t state);
void mmwk_sensor_network_set_sta_ip(const char *ip);
void mmwk_sensor_network_set_retry_diag(int32_t retry_count,
                                        int32_t max_retry,
                                        int32_t retry_backoff_ms,
                                        int32_t last_disconnect_reason_code,
                                        const char *last_disconnect_reason_name,
                                        bool terminal_failure,
                                        const char *failure_source);
void mmwk_sensor_network_clear_retry_diag(void);
void mmwk_sensor_network_get_snapshot(mmwk_sensor_network_snapshot_t *out_snapshot);
void mmwk_sensor_network_set_wifi_state(mmwk_sensor_network_wifi_state_t state);
void mmwk_sensor_network_set_provisioning_wait(bool active, uint32_t wait_sec);
mmwk_sensor_network_wifi_state_t mmwk_sensor_network_get_wifi_state(void);
int32_t mmwk_sensor_network_get_prov_wait_remaining_sec(void);
uint32_t mmwk_sensor_network_get_provisioning_wait_sec(void);

esp_err_t mmwk_sensor_time_init(void);
esp_err_t mmwk_sensor_time_config(const mmwk_sensor_time_cfg_t *cfg);
int64_t mmwk_sensor_time_get_world_time(void);

bool mmwk_sensor_protocol_surface_meta_load(mmwk_sensor_protocol_surface_meta_t *out_meta);
cJSON *mmwk_sensor_protocol_surface_meta_build_control_object(
    const mmwk_sensor_protocol_surface_meta_t *meta);
bool mmwk_sensor_protocol_surface_meta_describe_protocol(
    const mmwk_sensor_protocol_surface_meta_t *meta,
    const char *protocol,
    const char **out_surface,
    bool *out_reference);

void mmwk_sensor_bridge_run(const mmwk_sensor_profile_t *profile,
                            const mmwk_sensor_protocol_family_t *proto_cfg,
                            const mmwk_sensor_startup_policy_t *startup);
void mmwk_sensor_hub_run(const mmwk_sensor_profile_t *profile,
                         const mmwk_sensor_protocol_family_t *proto_cfg,
                         const mmwk_sensor_startup_policy_t *startup);

#ifdef __cplusplus
}
#endif

#endif /* MMWK_SENSOR_H */
