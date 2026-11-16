#ifndef PRESENCE_UI_H
#define PRESENCE_UI_H

#include <stdbool.h>
#include "esp_err.h"

/* Application-owned IO policy. Default (all false) touches no GPIO or tasks.
 * Must be installed before starting the SDK sensor runtime. */
typedef struct {
    bool claim_key;
    bool claim_led;
    bool led_initially_on;
} presence_ui_policy_t;

esp_err_t presence_ui_configure(const presence_ui_policy_t *policy);
/* Release application-owned GPIO when the sensor runtime exits.
 * No-op on the legacy SDK or when no GPIO was claimed. On a GPIO reset
 * failure the failed pin remains owned, allowing the application to retry. */
esp_err_t presence_ui_release(void);
/* Returns -1 when key GPIO is not claimed by this application. */
int presence_ui_read_key(void);
/* Returns ESP_ERR_INVALID_STATE when LED GPIO has not been claimed. */
esp_err_t presence_ui_set_led(bool on);

#endif /* PRESENCE_UI_H */
