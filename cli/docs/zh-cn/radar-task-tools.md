# Radar Task Tools

这组 task-oriented wrapper 挂在 `run.sh` 之外，现在收敛成两条本地雷达工作流：

- `config.sh`：统一入口，包含 `init`、`update` 和 `list`
- `collect.sh`：基于设备注册表的 MQTT raw 采集

本文示例使用 POSIX shell 写法。Windows PowerShell 下，在 `cli` 目录使用可用的 `.\config.ps1` 和 `.\collect.ps1`。其中 `config.ps1` 为了保持完整 registry-task parity，会转调 `config.sh`，因此需要 Bash，例如 Git Bash。`collect.ps1` 在有 Bash 时会转调 `collect.sh`；没有 Bash 时仍支持 pure-MQTT 的 `--trigger` 模式，以及受限的非 trigger registry 采集 fallback。

设备注册表文件固定为 `<working>/device.yml`。默认 `<working>` 的解析顺序是：

1. 当前工作目录下已经存在的 `./collect`
2. 已经存在的 `~/.mmwk/collect`
3. 如果上面都不存在，就创建并使用当前工作目录下的 `./collect`

如果你希望使用别的位置，请显式传 `--working DIR`。

`device.yml` 里的每条设备记录都会保存后续 wrapper 需要复用的传输端点信息：

- `device_id`
- `mqtt_server` / `mqtt_port` / `mqtt_uri`
- `http_server` / `http_port` / `http_base_url`
- 可选的 `ssid`
- `updated_at`

## 1. 初始化 UART 接入设备

当板子仍然通过 UART 接入，而你希望把它写入 `<working>/device.yml` 时，使用 `config.sh init`：

```bash
./config.sh init --port /dev/ttyUSB1
```

如果还需要同时下发 Wi-Fi 凭据，就显式加上：

```bash
./config.sh init \
  --port /dev/ttyUSB1 \
  --ssid YOUR_WIFI \
  --password YOUR_PASSWORD \
  --working ./collect-lab
```

当 `--mqtt-server` 和 `--http-server` 都未传入时，脚本会通过 `server.sh` 解析本机地址。

当 bridge 处在 provisioning AP 上时，加上 `--ap-link`，让 `init` 先准备主机 Wi-Fi 网口，再解析本地 server 端点：

```bash
./config.sh init \
  --port /dev/ttyUSB1 \
  --ap-link \
  --ssid YOUR_WIFI \
  --password YOUR_PASSWORD \
  --working ./collect-lab
```

`--ap-link` 是 bridge AP 网段准备动作，不是 Ethernet 选择器。Linux 和 WSL 上，如果 Wi-Fi 网口还没有 `192.168.4.x/24` 地址，它会执行 `sudo ip addr add 192.168.4.2/24 dev <wifi-iface>`。macOS 上使用 `sudo ifconfig <wifi-iface> alias 192.168.4.2 netmask 255.255.255.0`。如果自动发现选错或找不到 Wi-Fi，可以传 `--ap-iface IFACE`；实验环境地址不是默认值时，传 `--ap-cidr CIDR`。完整的 Linux、WSL 和 macOS 行为见 [配置助手](config.md)。

成功后脚本会打印：

- 检测到的 device id
- 实际使用的 MQTT URI
- 实际使用的 HTTP base URL
- `<working>` 路径
- `device.yml` 路径
- 可直接复制的 `config.sh update` 与 `collect.sh` 命令

只有当 UART 配置、重启以及 MQTT ready 校验全部成功后，`config.sh init` 才会更新 `device.yml`。

## 2. 更新雷达固件或运行时 Cfg

当设备已经注册进 `device.yml` 后，使用 `config.sh update`。

固件 OTA：

```bash
./config.sh update \
  --device-id 0123456789ab \
  --fw ../firmwares/radar/iwr6843/oob/out_of_box_6843_aop.bin \
  --cfg ../firmwares/radar/iwr6843/oob/out_of_box_6843_aop.cfg \
  --working ./collect-lab
```

只更新运行时 cfg：

```bash
./config.sh update \
  --device-id 0123456789ab \
  --cfg ./runtime.cfg \
  --working ./collect-lab
```

`config.sh update` 会从 `device.yml` 解析 MQTT / HTTP 信息。带 `--fw` 时走 `radar fw ota`；只传 `--cfg` 时走 `radar config apply`。

## 3. 列出已注册设备

使用 `config.sh list` 查看当前注册表：

```bash
./config.sh list --working ./collect-lab
```

输出至少包含：

- `device_id`
- MQTT URI
- HTTP base URL

用它可以确认后续 `config.sh update` 和 `collect.sh` 实际会读取哪条 registry 记录。

## 4. 采集 Raw 数据

当设备已经注册完成，而你需要 late-attach 的 MQTT 采集窗口时，使用 `collect.sh`：

```bash
./collect.sh \
  --device-id 0123456789ab \
  --duration 10 \
  --working ./collect-lab
```

如果你希望 helper 在订阅 ready 和打开 raw forwarding 后立即重启 radar service，以便把启动期 `raw_resp` 一起采下来，就加上 `--reboot`：

```bash
./collect.sh \
  --device-id 0123456789ab \
  --duration 20 \
  --reboot \
  --working ./collect-lab
```

如果不传 `--duration`，脚本会持续运行，直到你按下 `Ctrl-C`：

```bash
./collect.sh \
  --device-id 0123456789ab \
  --working ./collect-lab
```

每次采集都会把产物写入 `<working>/data/<device-id>/`，并带上开始时间戳前缀，例如：

- `20260424-153000_raw_data.sraw`
- `20260424-153000_raw_data.log`
- `20260424-153000_summary.json`
- `20260424-153000_state_events.log`

helper 会打印高层状态，例如 MQTT 已连接、收到命令口流量、收到 raw 数据、设备断开、设备重连，以及停止采集。

只有当你明确希望 `collect.sh` 在订阅 ready 后主动重启 radar service，并把同一窗口里的 startup `raw_resp` 一起采下来时，才加 `--reboot`。

如果你要看一份面向公开发布路径的 6843 / 6432 选板和 wrapper 使用顺序说明，请直接阅读 [通过 Bridge 开发雷达](bridge-ti-radar-debug.md)。
