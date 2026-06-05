#ifndef __MMWK_SENSOR_RAW_H__
#define __MMWK_SENSOR_RAW_H__

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @file mmwk_sensor_raw.h
 * @brief Raw data listener interface.
 */

typedef struct {
    bool enabled;
    const char* uri;
    const char* username;
    const char* password;
    const char* data_topic;
    const char* resp_topic;
    const char* cmd_topic;
    void* client_handle;
} mmwk_sensor_raw_cfg_t;

typedef enum {
    RAW_SENSOR_EVENT_CONNECTED,
    RAW_SENSOR_EVENT_DISCONNECTED,
    RAW_SENSOR_EVENT_CMD_RECEIVED,
    RAW_SENSOR_EVENT_DATA,
} raw_sensor_event_type_t;

typedef enum {
    RAW_SENSOR_STREAM_NONE = 0,
    RAW_SENSOR_STREAM_CMD,
    RAW_SENSOR_STREAM_DATA,
} raw_sensor_stream_t;

typedef struct {
    raw_sensor_event_type_t type;
    raw_sensor_stream_t stream;
    union {
        struct {
            const char* cmd_data;
            size_t cmd_len;
        } cmd;
        struct {
            const void* data;
            size_t len;
        } data;
    };
} mmwk_sensor_raw_event_t;

typedef void (*mmwk_sensor_raw_callback_t)(const mmwk_sensor_raw_event_t* event, void* ctx);

#ifdef __cplusplus
}
#endif

#endif /* __MMWK_SENSOR_RAW_H__ */
