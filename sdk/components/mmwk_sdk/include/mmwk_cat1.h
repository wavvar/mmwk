#pragma once

#include <stdbool.h>

#include "esp_err.h"
#include "esp_event.h"
#include "esp_netif.h"
#include <sdkconfig.h>

#ifdef __cplusplus
extern "C" {
#endif

ESP_EVENT_DECLARE_BASE(MMWK_CAT1_EVENT);

typedef enum {
    MMWK_CAT1_EVENT_DIALING = 0,
    MMWK_CAT1_EVENT_CONNECTED,
    MMWK_CAT1_EVENT_DISCONNECTED,
} mmwk_cat1_event_t;

typedef enum {
    MMWK_CAT1_STATE_UNINIT = 0,
    MMWK_CAT1_STATE_INITED,
    MMWK_CAT1_STATE_STARTING,
    MMWK_CAT1_STATE_RUNNING,
    MMWK_CAT1_STATE_STOPPING,
    MMWK_CAT1_STATE_ERROR,
} mmwk_cat1_state_t;

typedef enum {
    MMWK_CAT1_DISCONNECT_REASON_USER_STOP = 0,
    MMWK_CAT1_DISCONNECT_REASON_USB_DETACHED = 1,
    MMWK_CAT1_DISCONNECT_REASON_CONNECT_TIMEOUT = 2,
    MMWK_CAT1_DISCONNECT_REASON_PPP_NEGOTIATION_FAILED = 3,
    MMWK_CAT1_DISCONNECT_REASON_MODEM_ERROR = 4,
    MMWK_CAT1_DISCONNECT_REASON_INTERNAL_ERROR = 5,
    MMWK_CAT1_DISCONNECT_REASON_SIM_NOT_READY = 6,
    MMWK_CAT1_DISCONNECT_REASON_REGISTRATION_DENIED = 7,
    MMWK_CAT1_DISCONNECT_REASON_REGISTRATION_SEARCH_TIMEOUT = 8,
} mmwk_cat1_disconnect_reason_t;

typedef struct {
    int connect_timeout_ms;
    int stop_timeout_ms;
} mmwk_cat1_config_t;

typedef struct {
    const char *apn;
    const char *username;
    const char *password;
} mmwk_cat1_start_config_t;

typedef struct {
    esp_netif_t *netif;
} mmwk_cat1_connected_event_t;

typedef struct {
    mmwk_cat1_disconnect_reason_t reason;
    esp_err_t last_err;
} mmwk_cat1_disconnected_event_t;

#define MMWK_CAT1_DEFAULT_CONNECT_TIMEOUT_MS CONFIG_MMWK_CAT1_CONNECT_TIMEOUT_MS
#define MMWK_CAT1_DEFAULT_STOP_TIMEOUT_MS CONFIG_MMWK_CAT1_STOP_TIMEOUT_MS

#define MMWK_CAT1_DEFAULT_CONFIG() ((mmwk_cat1_config_t) { \
    .connect_timeout_ms = MMWK_CAT1_DEFAULT_CONNECT_TIMEOUT_MS, \
    .stop_timeout_ms = MMWK_CAT1_DEFAULT_STOP_TIMEOUT_MS, \
})

#define MMWK_CAT1_DEFAULT_START_CONFIG() ((mmwk_cat1_start_config_t) { \
    .apn = NULL, \
    .username = NULL, \
    .password = NULL, \
})

esp_err_t mmwk_cat1_init(const mmwk_cat1_config_t *config);
esp_err_t mmwk_cat1_start(const mmwk_cat1_start_config_t *config);
esp_err_t mmwk_cat1_stop(void);
esp_err_t mmwk_cat1_deinit(void);
mmwk_cat1_state_t mmwk_cat1_get_state(void);
esp_netif_t *mmwk_cat1_get_netif(void);
bool mmwk_cat1_is_ready(void);

#ifdef __cplusplus
}
#endif
