#ifndef PRESENCE_STATE_H
#define PRESENCE_STATE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct cJSON cJSON;

typedef struct {
    bool occupied;
    uint32_t timeout_ms;
    uint32_t last_seen_ms;
    uint64_t raw_packets;
    uint64_t raw_bytes;
} presence_state_t;

void presence_state_init(presence_state_t *state);
void presence_state_update_raw(presence_state_t *state, const uint8_t *data, size_t len);
void presence_state_refresh(presence_state_t *state);
cJSON *presence_state_to_json(const presence_state_t *state);
bool presence_state_set_timeout(presence_state_t *state, uint32_t timeout_ms);

#endif
