"""Compile the actual example-owned key/LED implementation against both SDK ABIs.

Host-only GPIO fakes: this does not validate real board pins or flash hardware.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1] / "presence/main"
SOURCE = ROOT / "presence_ui.c"

ESP = """typedef int esp_err_t;
#define ESP_OK 0
#define ESP_ERR_INVALID_ARG -1
#define ESP_ERR_INVALID_STATE -2
#define ESP_ERR_NOT_SUPPORTED -3
"""
BOARD = """#include <stdint.h>
#define MMWK_BOARD_CONFIG_ABI_VERSION 1U
typedef struct { uint32_t size; uint32_t version; int key_gpio; int led_gpio; } mmwk_board_config_t;
const mmwk_board_config_t *mmwk_board_get_config(void);
"""
GPIO = """#include <stdint.h>
#include "esp_err.h"
typedef struct { uint64_t pin_bit_mask; int mode; int pull_up_en; int pull_down_en; int intr_type; } gpio_config_t;
#define GPIO_MODE_INPUT 1
#define GPIO_MODE_OUTPUT 2
#define GPIO_PULLUP_ENABLE 1
#define GPIO_PULLUP_DISABLE 0
#define GPIO_PULLDOWN_DISABLE 0
#define GPIO_INTR_DISABLE 0
#define GPIO_IS_VALID_GPIO(pin) ((pin)>=0 && (pin)<64)
#define GPIO_IS_VALID_OUTPUT_GPIO(pin) ((pin)>=0 && (pin)<34)
esp_err_t gpio_config(const gpio_config_t *config);
esp_err_t gpio_set_level(int pin, int level);
esp_err_t gpio_reset_pin(int pin);
int gpio_get_level(int pin);
"""


class PresenceUiTests(unittest.TestCase):
    def build(self, *, modern, program):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            (folder / "driver").mkdir()
            (folder / "esp_err.h").write_text(ESP)
            (folder / "mmwk_sensor.h").write_text(
                "#define MMWK_SENSOR_STARTUP_LEGACY_UI_POLICY_V1 1\n" if modern else "")
            (folder / "mmwk_board_config.h").write_text(BOARD)
            (folder / "driver/gpio.h").write_text(GPIO)
            (folder / "test.c").write_text(program)
            exe = folder / "a.out"
            command = ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                       "-I", str(folder), "-I", str(SOURCE.parent),
                       str(SOURCE), str(folder / "test.c"), "-o", str(exe)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_legacy_package_never_claims_pins(self):
        self.build(modern=False, program="""
#include "presence_ui.h"
#include <assert.h>
int main(void) {
  presence_ui_policy_t policy = {0};
  assert(presence_ui_configure(0) == ESP_ERR_INVALID_ARG);
  assert(presence_ui_configure(&policy) == ESP_OK);
  assert(presence_ui_read_key() == -1);
  assert(presence_ui_set_led(true) == ESP_ERR_NOT_SUPPORTED);
  policy.claim_key = true;
  assert(presence_ui_configure(&policy) == ESP_ERR_NOT_SUPPORTED);
  return 0;
}
""")

    def test_new_package_explicit_ownership_and_no_default_gpio(self):
        self.build(modern=True, program="""
#include "presence_ui.h"
#include "mmwk_board_config.h"
#include "driver/gpio.h"
#include <assert.h>
static mmwk_board_config_t board={sizeof(board),1,15,16};
static int configs, levels, resets;
const mmwk_board_config_t *mmwk_board_get_config(void) {return &board;}
esp_err_t gpio_config(const gpio_config_t *cfg){assert(cfg); configs++;return ESP_OK;}
esp_err_t gpio_set_level(int pin,int level){assert(pin==16);assert(level==0||level==1);levels++;return ESP_OK;}
esp_err_t gpio_reset_pin(int pin){(void)pin;resets++;return ESP_OK;}
int gpio_get_level(int pin){assert(pin==15);return 1;}
int main(void) {
  presence_ui_policy_t policy={0};
  assert(presence_ui_configure(&policy)==ESP_OK);
  assert(configs==0 && levels==0);
  assert(presence_ui_read_key()==-1);
  assert(presence_ui_set_led(true)==ESP_ERR_INVALID_STATE);
  policy.claim_key=true;policy.claim_led=true;
  assert(presence_ui_configure(&policy)==ESP_OK);
  assert(configs==2 && levels==1);
  assert(presence_ui_read_key()==1);
  assert(presence_ui_set_led(true)==ESP_OK);
  assert(levels==2 && resets==0);
  assert(presence_ui_configure(&policy)==ESP_ERR_INVALID_STATE);
  return 0;
}
""")

    def test_new_package_rejects_incorrect_board_and_rolls_back_gpio(self):
        self.build(modern=True, program="""
#include "presence_ui.h"
#include "mmwk_board_config.h"
#include "driver/gpio.h"
#include <assert.h>
static mmwk_board_config_t board={sizeof(board),1,15,16};
static int configs,resets,fail_led;
const mmwk_board_config_t *mmwk_board_get_config(void){return &board;}
esp_err_t gpio_config(const gpio_config_t *cfg){configs++;return fail_led && cfg->mode==GPIO_MODE_OUTPUT ? -9 : ESP_OK;}
esp_err_t gpio_set_level(int pin,int level){(void)pin;(void)level;return ESP_OK;}
esp_err_t gpio_reset_pin(int pin){(void)pin;resets++;return ESP_OK;}
int gpio_get_level(int pin){(void)pin;return 0;}
int main(void){
  presence_ui_policy_t p={.claim_key=true,.claim_led=true};
  board.version=999;
  assert(presence_ui_configure(&p)==ESP_ERR_INVALID_ARG);
  board.version=1;board.led_gpio=60;
  assert(presence_ui_configure(&p)==ESP_ERR_INVALID_ARG);
  board.led_gpio=16;fail_led=1;
  assert(presence_ui_configure(&p)==-9);
  assert(resets==1 && presence_ui_read_key()==-1);
  fail_led=0;
  assert(presence_ui_configure(&p)==ESP_OK);
  return 0;
}
""")


if __name__ == "__main__":
    unittest.main()
