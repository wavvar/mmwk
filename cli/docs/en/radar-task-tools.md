# Radar Task Tools

These task-oriented wrappers stay outside `run.sh` and provide registry/config
helpers around the shared collection engine:

- `config.sh`: one registry-backed entrypoint with `init`, `update`, and `list`
- `collect.sh`: forwards collection options to `run.sh collect`; its optional
  `--trigger` form is the advanced pure-MQTT helper

Examples in this guide use POSIX shell syntax. On Windows PowerShell, use
`.\config.ps1` and `.\collect.ps1` from the `cli` directory where available.
`config.ps1` still requires Bash for its registry/config helper; `collect.ps1`
invokes the Python collection engine directly and does not require Bash.

The registry file is `<working>/device.yml`. The default `<working>` resolution is:

1. `./collect` if it already exists under your current working directory
2. `~/.mmwk/collect` if it already exists
3. otherwise create and use `./collect`

Pass `--working DIR` on either wrapper when you want a different location.

Each device record in `device.yml` stores the resolved transport endpoints that the wrappers need later:

- `did`
- `mqtt_server` / `mqtt_port` / `mqtt_uri`
- `http_server` / `http_port` / `http_base_url`
- optional `ssid`
- `updated_at`

## 1. Initialize A UART-Connected Device

Use `config.sh init` when the board is still on UART and you want to store its server binding into `<working>/device.yml`:

```bash
./config.sh init --port /dev/ttyUSB1
```

If Wi-Fi credentials still need to be provisioned, add them explicitly:

```bash
./config.sh init \
  --port /dev/ttyUSB1 \
  --ssid YOUR_WIFI \
  --password YOUR_PASSWORD \
  --working ./collect-lab
```

If `--mqtt-server` and `--http-server` are omitted, the tool resolves the local machine through `server.sh`.

When the bridge is on its provisioning AP, add `--ap-link` so `init` prepares the host Wi-Fi interface before resolving local server endpoints:

```bash
./config.sh init \
  --port /dev/ttyUSB1 \
  --ap-link \
  --ssid YOUR_WIFI \
  --password YOUR_PASSWORD \
  --working ./collect-lab
```

`--ap-link` is bridge AP-subnet preparation, not an Ethernet selector. On Linux and WSL it adds the AP address with `sudo ip addr add 192.168.4.2/24 dev <wifi-iface>` when the Wi-Fi interface does not already have a `192.168.4.x/24` address. On macOS it uses `sudo ifconfig <wifi-iface> alias 192.168.4.2 netmask 255.255.255.0`. If auto-detection picks the wrong interface or cannot find Wi-Fi, pass `--ap-iface IFACE`; for non-default lab addressing, pass `--ap-cidr CIDR`. See [Config Helper](config.md) for the full Linux, WSL, and macOS behavior.

On success the script prints:

- the detected DID
- the resolved MQTT URI
- the resolved HTTP base URL
- the `<working>` path
- the `device.yml` path
- copy-paste-ready `config.sh update` and `collect.sh` commands

`config.sh init` writes `device.yml` only after UART configuration, reboot, and MQTT readiness verification all succeed.

## 2. Update Radar Firmware Or Runtime Cfg

Use `config.sh update` after the device is already registered in `device.yml`.

Firmware OTA:

```bash
./config.sh update \
  --did 0123456789ab \
  --fw ../firmwares/radar/iwr6843/oob/out_of_box_6843_aop.bin \
  --cfg ../firmwares/radar/iwr6843/oob/out_of_box_6843_aop.cfg \
  --working ./collect-lab
```

Runtime cfg only:

```bash
./config.sh update \
  --did 0123456789ab \
  --cfg ./runtime.cfg \
  --working ./collect-lab
```

`config.sh update` resolves MQTT and HTTP endpoints from `device.yml`. With `--fw`, it uses `radar fw ota`; with cfg-only updates, it uses `radar config apply`.

## 3. List Registered Devices

Use `config.sh list` to inspect the current registry:

```bash
./config.sh list --working ./collect-lab
```

The output includes:

- `did`
- MQTT URI
- HTTP base URL

Use this to confirm which registry entry `config.sh update` will consume. Pass
the resulting `did` and broker URI explicitly to `run.sh collect`.

## 4. Collect Raw Data

Use `collect.sh` as a thin wrapper around the shared engine. For a late-attach
MQTT window after the device has been registered:

```bash
./collect.sh --transport mqtt --mode auto --attach \
  --did 0123456789ab --broker mqtt://broker.example:1883 \
  --duration 10 --data-output ./data.sraw --resp-output ./resp.log
```

The application must already own the radar and expose the auto MQTT DATA route;
attach observes it and does not create it.

For host-owned MQTT collection, omit `--mode auto --attach` and use
`--transport mqtt`; for attached UART/USB or split collection, see the
[Radar DATA collection guide](data-collection.md). The shared engine reserves
all outputs before mutation and reports cleanup failures separately.

The engine writes the requested `.sraw`, response log, optional wire audit, and
summary paths. It prints high-level connection, capture, and cleanup states.

If you need a publication-safe 6843 vs 6432 board-selection walkthrough built around these wrappers, start with [Develop Radar With Bridge](bridge-ti-radar-debug.md).
