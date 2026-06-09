#include "presence_state.h"

#include "cJSON.h"
#include "esp_timer.h"

#define PRESENCE_STATE_DEFAULT_TIMEOUT_MS 5000U
#define PRESENCE_STATE_MIN_TIMEOUT_MS 1000U
#define PRESENCE_STATE_MAX_TIMEOUT_MS 60000U

static uint32_t presence_state_now_ms(void)
{
    return (uint32_t)(esp_timer_get_time() / 1000);
}

void presence_state_init(presence_state_t *state)
{
    if (!state) {
        return;
    }

    state->occupied = false;
    state->timeout_ms = PRESENCE_STATE_DEFAULT_TIMEOUT_MS;
    state->last_seen_ms = 0;
    state->raw_packets = 0;
    state->raw_bytes = 0;
}

void presence_state_update_raw(presence_state_t *state, const uint8_t *data, size_t len)
{
    if (!state || !data || len == 0) {
        return;
    }

    /*
     * This is an example-only raw frame heuristic: any radar frame refreshes
     * the occupied state. Product code should decode radar frames first and
     * derive presence from target, point cloud, or track data instead.
     */
    state->occupied = true;
    state->last_seen_ms = presence_state_now_ms();
    state->raw_packets++;
    state->raw_bytes += (uint64_t)len;
}

void presence_state_refresh(presence_state_t *state)
{
    uint32_t elapsed_ms;

    if (!state || !state->occupied) {
        return;
    }

    elapsed_ms = presence_state_now_ms() - state->last_seen_ms;
    if (elapsed_ms >= state->timeout_ms) {
        state->occupied = false;
    }
}

cJSON *presence_state_to_json(const presence_state_t *state)
{
    cJSON *root;

    if (!state) {
        return NULL;
    }

    root = cJSON_CreateObject();
    if (!root) {
        return NULL;
    }

    cJSON_AddBoolToObject(root, "occupied", state->occupied);
    cJSON_AddNumberToObject(root, "timeout_ms", state->timeout_ms);
    cJSON_AddNumberToObject(root, "raw_packets", (double)state->raw_packets);
    cJSON_AddNumberToObject(root, "raw_bytes", (double)state->raw_bytes);
    cJSON_AddNumberToObject(root, "last_seen_ms", state->last_seen_ms);

    return root;
}

bool presence_state_set_timeout(presence_state_t *state, uint32_t timeout_ms)
{
    if (!state || timeout_ms < PRESENCE_STATE_MIN_TIMEOUT_MS ||
        timeout_ms > PRESENCE_STATE_MAX_TIMEOUT_MS) {
        return false;
    }

    state->timeout_ms = timeout_ms;
    presence_state_refresh(state);
    return true;
}
