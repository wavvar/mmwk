#include "presence_ui.h"
#include "mmwk_sensor.h"

#ifdef MMWK_SENSOR_STARTUP_LEGACY_UI_POLICY_V1
#include "mmwk_board_config.h"
#include "driver/gpio.h"
#endif

/* This is intentionally not a default key task, debounce policy, LED
 * animation, or network button gesture. The application decides whether and
 * how to poll the claimed key or drive its LED. */
#ifdef MMWK_SENSOR_STARTUP_LEGACY_UI_POLICY_V1
static int s_owned_key = -1;
static int s_owned_led = -1;
#endif

esp_err_t presence_ui_configure(const presence_ui_policy_t *policy)
{
    if (!policy) {
        return ESP_ERR_INVALID_ARG;
    }
#ifdef MMWK_SENSOR_STARTUP_LEGACY_UI_POLICY_V1
    if (s_owned_key >= 0 || s_owned_led >= 0) {
        return ESP_ERR_INVALID_STATE;
    }
    if (!policy->claim_key && !policy->claim_led) {
        return ESP_OK;
    }
    const mmwk_board_config_t *board = mmwk_board_get_config();
    if (!board || board->size != sizeof(*board) ||
        board->version != MMWK_BOARD_CONFIG_ABI_VERSION) {
        return ESP_ERR_INVALID_ARG;
    }
    if ((policy->claim_key && !GPIO_IS_VALID_GPIO(board->key_gpio)) ||
        (policy->claim_led && !GPIO_IS_VALID_OUTPUT_GPIO(board->led_gpio)) ||
        (policy->claim_key && policy->claim_led &&
         board->key_gpio == board->led_gpio)) {
        return ESP_ERR_INVALID_ARG;
    }
    esp_err_t err;
    if (policy->claim_key) {
        const gpio_config_t config = {
            .pin_bit_mask = 1ULL << board->key_gpio,
            .mode = GPIO_MODE_INPUT,
            .pull_up_en = GPIO_PULLUP_ENABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };
        err = gpio_config(&config);
        if (err != ESP_OK) {
            return err;
        }
        s_owned_key = board->key_gpio;
    }
    if (policy->claim_led) {
        const gpio_config_t config = {
            .pin_bit_mask = 1ULL << board->led_gpio,
            .mode = GPIO_MODE_OUTPUT,
            .pull_up_en = GPIO_PULLUP_DISABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };
        err = gpio_config(&config);
        if (err != ESP_OK) {
            if (s_owned_key >= 0) {
                (void)gpio_reset_pin(s_owned_key);
                s_owned_key = -1;
            }
            return err;
        }
        err = gpio_set_level(board->led_gpio, policy->led_initially_on ? 1 : 0);
        if (err != ESP_OK) {
            (void)gpio_reset_pin(board->led_gpio);
            if (s_owned_key >= 0) {
                (void)gpio_reset_pin(s_owned_key);
                s_owned_key = -1;
            }
            return err;
        }
        s_owned_led = board->led_gpio;
    }
    return ESP_OK;
#else
    if (policy->claim_key || policy->claim_led) {
        return ESP_ERR_NOT_SUPPORTED; /* Old SDK still owns its legacy IO. */
    }
    return ESP_OK;
#endif
}

int presence_ui_read_key(void)
{
#ifdef MMWK_SENSOR_STARTUP_LEGACY_UI_POLICY_V1
    return s_owned_key >= 0 ? gpio_get_level(s_owned_key) : -1;
#else
    return -1;
#endif
}

esp_err_t presence_ui_set_led(bool on)
{
#ifdef MMWK_SENSOR_STARTUP_LEGACY_UI_POLICY_V1
    if (s_owned_led < 0) {
        return ESP_ERR_INVALID_STATE;
    }
    return gpio_set_level(s_owned_led, on ? 1 : 0);
#else
    (void)on;
    return ESP_ERR_NOT_SUPPORTED;
#endif
}
