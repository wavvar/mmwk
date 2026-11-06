"""Exercise the public presence-state C implementation with real pthreads.

The RAW callback can run on an ESP worker while a local CLI reads/sets status.
Host pthread locks model the FreeRTOS spinlock; no ESP, network or hardware.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "presence/main"
CJSON = r"""
#pragma once
#include <stdlib.h>
typedef struct cJSON {int dummy;} cJSON;
static inline cJSON *cJSON_CreateObject(void) { return calloc(1, sizeof(cJSON)); }
static inline int cJSON_AddBoolToObject(cJSON *obj, const char *key, int value)
{ (void)key; (void)value; return obj != NULL; }
static inline int cJSON_AddNumberToObject(cJSON *obj, const char *key, double value)
{ (void)key; (void)value; return obj != NULL; }
static inline void cJSON_Delete(cJSON *obj) { free(obj); }
"""
FREERTOS = r"""
#pragma once
#include <pthread.h>
typedef pthread_mutex_t portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED PTHREAD_MUTEX_INITIALIZER
#define portENTER_CRITICAL(mux) ((void)pthread_mutex_lock((mux)))
#define portEXIT_CRITICAL(mux) ((void)pthread_mutex_unlock((mux)))
"""
PROGRAM = r"""
#include "presence_state.h"
#include "cJSON.h"
#include <assert.h>
#include <pthread.h>
#include <stdint.h>
static presence_state_t state;
static int64_t microseconds = 1000000;
int64_t esp_timer_get_time(void) {
    return __atomic_add_fetch(&microseconds, 1000, __ATOMIC_RELAXED);
}
static void *writer(void *unused) {
    (void)unused;
    const uint8_t bytes[4] = {1, 2, 3, 4};
    for (int i = 0; i < 12000; ++i)
        presence_state_update_raw(&state, bytes, sizeof(bytes));
    return NULL;
}
static void *reader(void *unused) {
    (void)unused;
    for (int i = 0; i < 12000; ++i) {
        presence_state_t snapshot = {0};
        assert(presence_state_snapshot(&state, &snapshot));
        assert(snapshot.raw_bytes == snapshot.raw_packets * 4);
        assert(snapshot.timeout_ms >= 1000 && snapshot.timeout_ms <= 60000);
        presence_state_refresh(&state);
    }
    return NULL;
}
int main(void) {
    presence_state_init(&state);
    assert(!presence_state_snapshot(&state, &state));
    assert(!presence_state_snapshot(NULL, &state));
    assert(!presence_state_set_timeout(&state, 999));
    assert(!presence_state_set_timeout(&state, 60001));
    assert(presence_state_set_timeout(&state, 1000));
    pthread_t write_task, read_task;
    assert(pthread_create(&write_task, NULL, writer, NULL) == 0);
    assert(pthread_create(&read_task, NULL, reader, NULL) == 0);
    assert(pthread_join(write_task, NULL) == 0);
    assert(pthread_join(read_task, NULL) == 0);
    presence_state_t snapshot;
    assert(presence_state_snapshot(&state, &snapshot));
    assert(snapshot.raw_packets == 12000);
    assert(snapshot.raw_bytes == 48000);
    cJSON *encoded = presence_state_to_json(&state);
    assert(encoded != NULL);
    cJSON_Delete(encoded);
    return 0;
}
"""


class PresenceStateConcurrencyTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("cc"), "host C compiler missing")
    def test_real_production_c_source_atomic_snapshot_across_raw_callback_and_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "freertos").mkdir()
            (root / "freertos/FreeRTOS.h").write_text(FREERTOS)
            (root / "freertos/portmacro.h").write_text('#include "FreeRTOS.h"\n')
            (root / "esp_timer.h").write_text(
                "#pragma once\n#include <stdint.h>\n"
                "int64_t esp_timer_get_time(void);\n")
            (root / "cJSON.h").write_text(CJSON)
            (root / "main.c").write_text(PROGRAM)
            executable = root / "presence_state_host"
            command = [
                "cc", "-std=c11", "-O2", "-pthread",
                "-Wall", "-Wextra", "-Werror", "-I", str(root),
                "-I", str(SOURCE), str(SOURCE / "presence_state.c"),
                str(root / "main.c"), "-o", str(executable),
            ]
            build = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            executed = subprocess.run([str(executable)], text=True, capture_output=True)
            self.assertEqual(executed.returncode, 0, executed.stderr)

    def test_public_cli_rejects_nan_fraction_and_uses_consistent_snapshot(self):
        code = (SOURCE / "presence_cli.c").read_text()
        self.assertIn("presence_state_snapshot(state, &snapshot)", code)
        self.assertIn("isfinite(item->valuedouble)", code)
        self.assertIn("cJSON_GetObjectItemCaseSensitive", code)
        self.assertIn("item->valuedouble < 1000.0", code)
        self.assertIn("(double)timeout_ms != item->valuedouble", code)


if __name__ == "__main__":
    unittest.main()
