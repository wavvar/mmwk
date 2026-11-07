"""Execute the real offline presence lifecycle with fake public SDK services.

All service/driver operations are controlled host shims; no network, ESP target,
board or live radar is exercised. The actual app_main/stop bodies are compiled.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "sdk/examples/presence/main"

HEADER = r"""
#ifndef STAGE1_OFFLINE_TEST_SDK
#define STAGE1_OFFLINE_TEST_SDK
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define ESP_OK 0
#define MMWK_SERVICE_OK 0
#define MMWK_SERVICE_START_HOST 1
#define MMWK_DRIVER_ERR_NONE 0
#define MMWK_DRIVER_SPI_BACKEND_ABI_V1 1
#define MMWK_BOARD_CONFIG_ABI_VERSION 2U
#define tskNO_AFFINITY (-1)
typedef int esp_err_t;
typedef int mmwk_service_err_t;
typedef uint32_t mmwk_service_raw_subscription_t;
typedef struct { unsigned abi_version; int radar_chip; } mmwk_driver_spi_backend_v1_t;
extern const mmwk_driver_spi_backend_v1_t mmwk_driver_spi_backend_xwrl6432;
typedef struct { uint32_t size, version; const char *target; int radar_chip; } mmwk_board_config_t;
typedef struct { int marker; } mmwk_driver_cfg_t;
typedef struct {int live;} fake_service_t;
typedef fake_service_t *mmwk_service_handle_t;
typedef struct {
    int task_priority, task_core;
    bool disable_external_raw_commands;
    const mmwk_driver_spi_backend_v1_t *spi_backend;
    mmwk_driver_cfg_t board_cfg;
} mmwk_service_cfg_t;
typedef enum {MMWK_SERVICE_RAW_EVENT_CMD_OUTPUT, MMWK_SERVICE_RAW_EVENT_DATA_OUTPUT}
    mmwk_service_raw_event_type_t;
typedef struct {mmwk_service_raw_event_type_t type; const void *data; size_t len;}
    mmwk_service_raw_event_t;
typedef void (*mmwk_service_raw_callback_t)(const mmwk_service_raw_event_t *,void *);
const mmwk_board_config_t *mmwk_board_get_config(void);
int mmwk_driver_board_cfg_from_profile(
    const mmwk_board_config_t *, const char *, int, const char *, mmwk_driver_cfg_t *);
int mmwk_service_init(mmwk_service_handle_t *, void *, const mmwk_service_cfg_t *);
int mmwk_service_raw_subscribe(mmwk_service_handle_t, mmwk_service_raw_callback_t,
                               void *, mmwk_service_raw_subscription_t *);
int mmwk_service_start(mmwk_service_handle_t, int);
int mmwk_service_stop(mmwk_service_handle_t);
int mmwk_service_raw_unsubscribe(mmwk_service_handle_t, mmwk_service_raw_subscription_t);
int mmwk_service_deinit(mmwk_service_handle_t);
#endif
"""
C_TEST = r"""
#include "mock_sdk.h"
#include "presence_state.h"
#include "presence_radar_assets.h"
#include <assert.h>
#include <string.h>

static fake_service_t service;
static mmwk_board_config_t board={sizeof(board),MMWK_BOARD_CONFIG_ABI_VERSION,
                                  "esp32s3",6432};
const mmwk_driver_spi_backend_v1_t mmwk_driver_spi_backend_xwrl6432={1,6432};
static const presence_radar_asset_pair_t assets={
    "wdr","esp32s3",6432,"radarl64xx","firmware","config"
};
static int ninit,nstart,nstop,nsub,nunsub,ndeinit;
static int fail_init,fail_start,fail_stop,fail_sub,fail_unsub,fail_deinit;
const mmwk_board_config_t *mmwk_board_get_config(void){return &board;}
const presence_radar_asset_pair_t *presence_radar_assets_current(void){return &assets;}
void presence_state_init(presence_state_t *state){memset(state,0,sizeof(*state));}
void presence_state_update_raw(presence_state_t *state,const uint8_t *d,size_t n)
{if(state && d && n)state->raw_bytes += n;}
int mmwk_driver_board_cfg_from_profile(const mmwk_board_config_t *b,
    const char *target, int chip,const char *family,mmwk_driver_cfg_t *out)
{
  assert(b && target && family && out); assert(chip==6432);
  out->marker=1;return 0;
}
int mmwk_service_init(mmwk_service_handle_t *out,void *processor,
                      const mmwk_service_cfg_t *cfg)
{
  assert(processor==0 && cfg->disable_external_raw_commands);
  assert(cfg->spi_backend==&mmwk_driver_spi_backend_xwrl6432);
  ++ninit; if(fail_init)return -9;
  service.live=1;*out=&service;return 0;
}
int mmwk_service_raw_subscribe(mmwk_service_handle_t h,mmwk_service_raw_callback_t cb,
                                void *ctx,mmwk_service_raw_subscription_t *out)
{
  assert(h && h->live && cb && ctx && out);
  ++nsub; if(fail_sub)return -10;
  *out=1234;return 0;
}
int mmwk_service_start(mmwk_service_handle_t h,int mode)
{
  assert(h && h->live && mode==MMWK_SERVICE_START_HOST);
  ++nstart;return fail_start?-11:0;
}
int mmwk_service_stop(mmwk_service_handle_t h)
{
  assert(h && h->live);++nstop;return fail_stop?-12:0;
}
int mmwk_service_raw_unsubscribe(mmwk_service_handle_t h,mmwk_service_raw_subscription_t token)
{
  assert(h && h->live && token==1234);++nunsub;return fail_unsub?-13:0;
}
int mmwk_service_deinit(mmwk_service_handle_t h)
{
  assert(h && h->live);++ndeinit;
  if(fail_deinit)return -14;
  h->live=0;return 0;
}
void app_main(void);
int presence_offline_stop(void);
static void reset_failures(void)
{fail_init=fail_start=fail_stop=fail_sub=fail_unsub=fail_deinit=0;}
int main(void)
{
  reset_failures();
  /* Normal start, failed stop, successful retry, idempotent cleanup. */
  app_main();assert(ninit==1 && nsub==1 && nstart==1 && service.live);
  fail_stop=1;
  assert(presence_offline_stop()==-12 && nstop==1 && nunsub==0 && ndeinit==0);
  reset_failures();
  assert(presence_offline_stop()==0 && nstop==2 && nunsub==1 && ndeinit==1);
  assert(presence_offline_stop()==0 && nstop==2);
  /* Failed subscribe followed by failed deinit must retain the live handle. */
  fail_sub=1;fail_deinit=1;
  app_main();assert(ninit==2 && nsub==2 && nstart==1 && service.live);
  app_main();assert(ninit==2); /* refuse overwrite */
  reset_failures();
  assert(presence_offline_stop()==0 && nstop==2 && nunsub==1 && ndeinit==3);
  /* Failed start, failed unsubscribe; retry must not call stop. */
  fail_start=1;fail_unsub=1;
  app_main();assert(ninit==3 && nstart==2 && nunsub==2 && service.live);
  reset_failures();
  assert(presence_offline_stop()==0 && nstop==2 && nunsub==3 && ndeinit==4);
  /* Once stopped, do not re-stop if unsubscribe or deinit must retry. */
  app_main();assert(nstart==3);
  fail_deinit=1;
  assert(presence_offline_stop()==-14);
  assert(nstop==3 && nunsub==4 && ndeinit==5);
  reset_failures();
  assert(presence_offline_stop()==0);
  assert(nstop==3 && nunsub==4 && ndeinit==6 && !service.live);
  return 0;
}
"""

class OfflinePresenceCleanupTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("cc"), "host C compiler required")
    def test_actual_presence_offline_start_stop_retry(self):
        with tempfile.TemporaryDirectory() as d:
            temp=Path(d)
            (temp / "freertos").mkdir()
            for name in ("mmwk_board_config.h","mmwk_driver_board_adapter.h",
                         "mmwk_service.h","mmwk_service_raw.h"):
                (temp/name).write_text('#include "mock_sdk.h"\n')
            (temp/"mock_sdk.h").write_text(HEADER)
            (temp/"esp_log.h").write_text(
                '#define ESP_LOGE(tag, ...) do {(void)(tag);}while(0)\n'
                '#define ESP_LOGI(tag, ...) do {(void)(tag);}while(0)\n')
            (temp/"freertos/FreeRTOS.h").write_text("#define portMAX_DELAY 0\n")
            (temp/"freertos/task.h").write_text("#define tskNO_AFFINITY (-1)\n")
            (temp/"test.c").write_text(C_TEST)
            # This relocates only the target translation unit to ensure
            # quote-includes resolve to controlled host ESP/SDK headers.
            (temp/"offline.c").write_bytes((APP/"presence_offline.c").read_bytes())
            binary=temp/"offline"
            result=subprocess.run([
                "cc","-std=c11","-Wall","-Wextra","-Werror",
                "-DCONFIG_RADAR_BOARD_RADAR_CHIP=6432",
                "-I",str(temp),"-I",str(APP),
                str(temp/"offline.c"),str(temp/"test.c"),"-o",str(binary)],
                capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            run=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

if __name__=="__main__":
    unittest.main()
