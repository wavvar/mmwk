# Repository Agent Guide

## Scope

These instructions apply to the entire repository. Keep changes self-contained in this repository and base implementation decisions on the files and documentation that are present here.

## Repository Map

- `cli/` contains the Python host CLI and the POSIX and PowerShell wrappers used for device control, local services, configuration, and radar data collection.
- `sdk/` contains the public ESP-IDF component boundary, prebuilt board libraries, board support code, and the presence example.
- `docs/` contains protocol, platform, flashing, OTA, bridge, and sensor documentation in English and Chinese.
- `modules/` contains board and product documentation, generally as English/Chinese pairs, plus hardware images.
- `firmwares/` contains published ESP packages and radar firmware/configuration pairs.
- `downloads/` contains the module PDF generator and its unit tests.
- `.github/workflows/` defines the repository's automated smoke and release checks.

Start with `README.md`, then read the README or guide nearest to the area being changed.

## General Working Rules

- Keep edits focused on the requested behavior. Do not reformat or rewrite unrelated files.
- Preserve user changes and untracked files. Inspect `git status` before and after editing.
- Do not commit local or generated output such as `build_output/`, `cli/build_output/`, `cli/venv/`, `downloads/.venv/`, `sdk/examples/build/`, `dist/`, `output/`, or `__pycache__/`.
- Treat committed `.bin`, `.appimage`, `.zip`, and `.a` files as opaque release artifacts. Do not regenerate, replace, or normalize them unless the task explicitly requires it.
- Never place credentials, Wi-Fi passwords, access keys, device identities, or local network details in source or documentation examples.
- Use repository-relative paths in documentation and verify links after moving or renaming files.
- Prefer the smallest relevant validation set. If a required toolchain or device is unavailable, report the skipped check instead of claiming success.

## CLI and Protocol Changes

- The CLI requires Python 3.10 or newer. Follow the existing Python style: four-space indentation, descriptive snake_case names, type hints where they improve public or non-trivial interfaces, and focused helper functions.
- `cli/run.sh` and `cli/run.ps1` are the primary entry points. `server`, `config`, and `collect` also have POSIX and PowerShell wrappers. Preserve cross-platform behavior where both wrappers expose the same workflow, and document intentional parity limits.
- Wrapper-relative file arguments are resolved from the caller's working directory. Preserve that behavior when changing path handling.
- Canonical CLI JSON (CLIv1) is the default control protocol. MCPv1 is an explicitly selected compatibility path; do not make compatibility behavior the default.
- Keep transport behavior distinct for UART, native USB, and MQTT. Do not assume hardware discovery, broker availability, or a connected device in unit-level code.
- When changing commands, options, topics, response fields, or protocol behavior, update the applicable protocol specification and the matching English and Chinese CLI documentation.
- Keep command help usable without attached hardware. Hardware-free `--help` checks are part of the smoke surface.

## SDK Changes

- `sdk/components/mmwk_sdk/include/` is the exposed header surface. Keep declarations compatible with the board-selected prebuilt libraries under `sdk/components/mmwk_sdk/lib/`.
- Supported example build targets are `mini`, `pro`, and `wdr`; `sdk/examples/build.sh` selects the correct ESP-IDF target and board defaults.
- Keep `CONFIG_COMPILER_OPTIMIZATION_SIZE=y` in SDK projects because the prebuilt SDK libraries use size optimization.
- Preserve board-specific definitions and do not silently substitute one board's GPIO, audio, firmware, or configuration values for another board.
- The presence example is intentionally minimal. A raw radar frame only refreshes its demonstration state; do not describe that heuristic as production presence detection.
- Build only the affected board when possible. Build all boards when changing shared SDK headers, components, CMake logic, or example code.

## Documentation and Release Assets

- Keep user-facing English and Chinese documentation aligned when behavior changes. Common pairs include `README.md` and `README_CN.md`, `docs/en/` and `docs/zh-cn/`, `cli/docs/en/` and `cli/docs/zh-cn/`, and English module files with their `*_cn.md` counterparts.
- Keep CLIv1 terminology canonical and describe MCPv1 only as compatibility behavior where applicable.
- Verify board names, firmware/configuration pairings, serial transports, and relative paths against repository files before documenting them.
- Do not edit generated PDFs. Change their Markdown sources or `downloads/generate_module_pdfs.py`, then regenerate only for explicit release validation.
- PDF generation requires `pandoc`; the Python dependencies are installed into `downloads/.venv/` by `downloads/generate.sh`.

## Development and Validation Commands

Run commands from the repository root unless a command changes directories explicitly.

### Fast hardware-free checks

```bash
git diff --check
python3 -m py_compile cli/mmwk/server.py cli/mmwk/server_runtime.py
python3 -m compileall -q cli/mmwk downloads
bash -n cli/run.sh cli/server.sh cli/config.sh cli/collect.sh
bash -n downloads/generate.sh sdk/examples/build.sh
(
  cd cli
  ./run.sh -h >/dev/null
  ./server.sh -h >/dev/null
  ./config.sh -h >/dev/null
  ./collect.sh -h >/dev/null
)
```

The POSIX wrapper creates `cli/venv/` and installs `cli/requirements.txt` automatically for commands that need the Python runtime. On Windows, install the requirements into the active Python 3.10+ environment before using the PowerShell wrappers.

### PDF generator tests

```bash
python3 -m venv downloads/.venv
downloads/.venv/bin/python -m pip install reportlab pypdf
downloads/.venv/bin/python -m unittest discover -s downloads/tests -v
```

For an explicit release-generation check with `pandoc` installed:

```bash
bash downloads/generate.sh pdfs \
  --version v0.0.0 \
  --built-date 2000-01-01 \
  --out-dir dist/release/pdfs
```

### SDK example builds

These commands require an initialized ESP-IDF environment with `idf.py` on `PATH`:

```bash
cd sdk/examples
./build.sh presence mini
./build.sh presence pro
./build.sh presence wdr
./build.sh presence all
```

Use one board command for board-specific changes and `./build.sh presence all` for shared SDK changes.

## Hardware-Dependent Validation

Device discovery, serial communication, firmware flashing, OTA, MQTT collection, and live server workflows require suitable hardware or network services. Run them only when the task calls for integration validation and the required environment is available. Never flash or reset a device merely as a generic smoke test. When live validation is required, use the documented CLI wrappers and record the board, transport, command, and observed result.

## Final Review

- Review `git diff` for accidental binary, generated, or unrelated changes.
- Run `git diff --check` and the checks relevant to the files changed.
- Confirm documentation examples use placeholders rather than real secrets or device data.
- Summarize changed behavior, validations run, and any checks skipped because hardware or toolchains were unavailable.
