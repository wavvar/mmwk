#ifndef PRESENCE_CLI_H
#define PRESENCE_CLI_H

#include "esp_err.h"
#include "presence_state.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t presence_cli_register(presence_state_t *state);

#ifdef __cplusplus
}
#endif

#endif
