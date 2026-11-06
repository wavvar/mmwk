#!/usr/bin/env bash
# Native public SDK host regressions only: no real idf.py, hardware or CI.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$root"
for executable in python3 cc cmake git; do
    command -v "$executable" >/dev/null 2>&1 || {
        echo "MMWK host tests require $executable" >&2
        exit 2
    }
done
unset MMWK_STAGE1_PRESET MMWK_STAGE1_BOARD MMWK_STAGE1_ABI
unset MMWK_STAGE1_LOCK_FILE MMWK_USB_ENABLE_TINYUSB
export PYTHONDONTWRITEBYTECODE=1
python3 -B -m unittest discover -s sdk/examples/tests -p 'test_*.py' -v
printf '%s\n' 'PASS: public SDK host/source tests only.'
printf '%s\n' 'NOT target builds, 12 real consumer binaries, hardware or release.'
