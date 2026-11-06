#include "presence_state.h"

#include "cJSON.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/portmacro.h"

#define PRESENCE_STATE_DEFAULT_TIMEOUT_MS 5000U
#define PRESENCE_STATE_MIN_TIMEOUT_MS 1000U
#define PRESENCE_STATE_MAX_TIMEOUT_MS 60000U

/* Internal RAM is required for the ESP spinlock used in critical sections.
 * One example-wide lock covers the RAW callback and CLI task's shared states. */
static portMUX_TYPE s_presence_lock = portMUX_INITIALIZER_UNLOCKED;

static uint32_t presence_state_now_ms(void)
{
    return (uint32_t)(esp_timer_get_time() / 1000);
}

void presence_state_init(presence_state_t *state)
{
    if (!state) {
        return;
    }

    portENTER_CRITICAL(&s_presence_lock);
    state->occupied = false;
    state->timeout_ms = PRESENCE_STATE_DEFAULT_TIMEOUT_MS;
    state->last_seen_ms = 0;
    state->raw_packets = 0;
    state->raw_bytes = 0;
    portEXIT_CRITICAL(&s_presence_lock);
}

void presence_state_update_raw(presence_state_t *state, const uint8_t *data, size_t len)
{
    if (!state || !data || len == 0) {
        return;
    }

    /*
     * This is an example-only raw frame heuristic: any nonempty callback refreshes
     * the occupied state. Product code should decode radar frames first and
     * derive presence from target, point cloud, or track data instead.
     */
    portENTER_CRITICAL(&s_presence_lock);
    state->occupied = true;
    state->last_seen_ms = presence_state_now_ms();
    state->raw_packets++;
    state->raw_bytes += (uint64_t)len;
    portEXIT_CRITICAL(&s_presence_lock);
}

/* Caller holds s_presence_lock. No allocation or service calls in this helper. */
static void presence_state_refresh_locked(presence_state_t *state)
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

void presence_state_refresh(presence_state_t *state)
{
    if (!state) {
        return;
    }
    portENTER_CRITICAL(&s_presence_lock);
    presence_state_refresh_locked(state);
    portEXIT_CRITICAL(&s_presence_lock);
}

bool presence_state_snapshot(const presence_state_t *state, presence_state_t *snapshot)
{
    if (!state || !snapshot || state == snapshot) {
        return false;
    }
    portENTER_CRITICAL(&s_presence_lock);
    *snapshot = *state;
    portEXIT_CRITICAL(&s_presence_lock);
    return true;
}

cJSON *presence_state_to_json(presence_state_t *state)
{
    cJSON *root;
    presence_state_t snapshot;

    if (!state) {
        return NULL;
    }
    portENTER_CRITICAL(&s_presence_lock);
    presence_state_refresh_locked(state);
    snapshot = *state;
    portEXIT_CRITICAL(&s_presence_lock);

    root = cJSON_CreateObject();
    if (!root) {
        return NULL;
    }

    if (!cJSON_AddBoolToObject(root, "occupied", snapshot.occupied) ||
        !cJSON_AddNumberToObject(root, "timeout_ms", snapshot.timeout_ms) ||
        !cJSON_AddNumberToObject(root, "raw_packets", (double)snapshot.raw_packets) ||
        !cJSON_AddNumberToObject(root, "raw_bytes", (double)snapshot.raw_bytes) ||
        !cJSON_AddNumberToObject(root, "last_seen_ms", snapshot.last_seen_ms)) {
        cJSON_Delete(root);
        return NULL;
    }

    return root;
}

bool presence_state_set_timeout(presence_state_t *state, uint32_t timeout_ms)
{
    if (!state || timeout_ms < PRESENCE_STATE_MIN_TIMEOUT_MS ||
        timeout_ms > PRESENCE_STATE_MAX_TIMEOUT_MS) {
        return false;
    }

    portENTER_CRITICAL(&s_presence_lock);
    state->timeout_ms = timeout_ms;
    presence_state_refresh_locked(state);
    portEXIT_CRITICAL(&s_presence_lock);
    return true;
}
