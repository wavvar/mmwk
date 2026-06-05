#include "presence_cli.h"

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "cJSON.h"
#include "mmwk_sensor.h"

static cJSON *presence_cli_config_to_json(const presence_state_t *state)
{
    cJSON *root;

    if (!state) {
        return NULL;
    }

    root = cJSON_CreateObject();
    if (!root) {
        return NULL;
    }

    if (!cJSON_AddNumberToObject(root, "timeout_ms", state->timeout_ms)) {
        cJSON_Delete(root);
        return NULL;
    }

    return root;
}

static bool presence_cli_parse_timeout_ms(const cJSON *args, uint32_t *out_timeout_ms)
{
    cJSON *item;
    uint32_t timeout_ms;

    if (!args || !out_timeout_ms) {
        return false;
    }

    item = cJSON_GetObjectItem(args, "timeout_ms");
    if (!cJSON_IsNumber(item) ||
        item->valuedouble < 0.0 ||
        item->valuedouble > 60000.0) {
        return false;
    }

    timeout_ms = (uint32_t)item->valuedouble;
    if ((double)timeout_ms != item->valuedouble) {
        return false;
    }

    *out_timeout_ms = timeout_ms;
    return true;
}

static mmwk_sensor_cli_status_t presence_cli_handle(const mmwk_sensor_cli_request_t *req,
                                                    cJSON **out_result,
                                                    void *user_ctx)
{
    presence_state_t *state = (presence_state_t *)user_ctx;

    if (!out_result) {
        return MMWK_SENSOR_CLI_STATUS_INVALID_ARG;
    }
    *out_result = NULL;

    if (!req || !req->action || !state) {
        return MMWK_SENSOR_CLI_STATUS_INVALID_ARG;
    }

    if (strcmp(req->action, "status") == 0) {
        presence_state_refresh(state);
        *out_result = presence_state_to_json(state);
        return *out_result ? MMWK_SENSOR_CLI_STATUS_OK : MMWK_SENSOR_CLI_STATUS_NO_MEMORY;
    }

    if (strcmp(req->action, "config_get") == 0) {
        *out_result = presence_cli_config_to_json(state);
        return *out_result ? MMWK_SENSOR_CLI_STATUS_OK : MMWK_SENSOR_CLI_STATUS_NO_MEMORY;
    }

    if (strcmp(req->action, "config_set") == 0) {
        uint32_t timeout_ms;

        if (!presence_cli_parse_timeout_ms(req->args, &timeout_ms) ||
            !presence_state_set_timeout(state, timeout_ms)) {
            return MMWK_SENSOR_CLI_STATUS_INVALID_ARG;
        }

        *out_result = presence_cli_config_to_json(state);
        return *out_result ? MMWK_SENSOR_CLI_STATUS_OK : MMWK_SENSOR_CLI_STATUS_NO_MEMORY;
    }

    return MMWK_SENSOR_CLI_STATUS_NOT_FOUND;
}

esp_err_t presence_cli_register(presence_state_t *state)
{
    if (!state) {
        return ESP_ERR_INVALID_ARG;
    }

    return mmwk_sensor_register_cli_service("presence", presence_cli_handle, state);
}
