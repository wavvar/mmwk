# 通过 Bridge 开发雷达

这份文档面向一条最常见、最可重复的开发路径：通过 `mmwk_sensor_bridge` 完成 TI 雷达开发。

这里的“通过 bridge 开发雷达”指的是把 bridge 当作公开可复用的开发载体，持续执行下面这条主循环：

- 通过 UART 完成 bridge 配置
- 通过网络更新雷达固件或运行时 cfg
- 通过 MQTT 采集原始数据和启动期输出
- 围绕这条链路反复迭代，并为不同雷达系列选择合适的公开 bridge 板型

下面的例子默认你的当前工作目录是已发布 `mmwk` 包里的 `mmwk_cli` 目录，示例路径只使用公开包结构。

## 先选对 Bridge 板子

| 雷达系列 | 推荐 bridge 板子 | 公开固件形态 | 说明 |
|---|---|---|---|
| `IWR6843` / `IWR6843AOP` | `mini` 或 `pro` | `../firmwares/radar/iwr6843/...` 下的 `.bin` + `.cfg` | 标准 68xx bridge 开发路径 |
| `IWRL6432` | `wdr` | `../firmwares/radar/iwrl6432/...` 下的 `.appimage` + `.cfg` | bridge 侧是单 UART 雷达开发路径 |

两条路径都使用同一组 wrapper：`config.sh init|update|list` 加 `collect.sh`。真正不同的是板型选择、雷达固件配对，以及运行期采集预期。

## 主体步骤

1. 先用 `server.sh` 启动本地 MQTT + HTTP helper。
2. `server.sh --serve-dir` 指向你计划 OTA 的那组雷达固件目录。
3. 用 `config.sh init` 通过 UART 下发 Wi-Fi / MQTT 设置。脚本会自动重启设备、验证 MQTT 可达，并把设备信息写入 `<working>/device.yml`。
4. 用 `config.sh update` 通过 MQTT 做雷达 OTA 或运行时 cfg 更新。脚本会从 `device.yml` 解析设备传输信息。
5. 用 `collect.sh` 通过 MQTT 采集 `raw_data` 和 `raw_resp`。脚本会从 `device.yml` 读取设备配置，并把采集产物放到 `<working>/data/<device-id>/`。

推荐先起本地服务：

```bash
./server.sh start --serve-dir <radar-artifact-dir>
eval "$(./server.sh env)"
```

默认情况下，`server.sh` 会自动检测本机可用 IP。只有当自动选择的网卡不对时，才需要显式传 `--host-ip <your-host-ip>`。

如果你希望把设备注册表放到别的位置，请在 `config.sh` 和 `collect.sh` 上持续使用同一个 `--working <dir>`。

这些 wrapper 还会带来几条稳定约定：

- `config.sh list` 会把 `<working>/device.yml` 里的 `device_id`、MQTT URI 和 HTTP base URL 直接打印出来。
- `collect.sh` 会把带时间戳前缀的产物写入 `<working>/data/<device-id>/`：`*_raw_data.sraw`、`*_raw_data.log`、`*_summary.json`、`*_state_events.log`。
- 只有当你明确希望 helper 在订阅 ready 之后主动重启 radar service，并把同一窗口里的 startup `raw_resp` 一起采下来时，才给 `collect.sh` 加 `--reboot`。

## 6843 系列

`mini` 和 `pro` 都适合 6843 开发。命令面是一样的，只是你接入的 bridge 板子不同。

下面例子使用公开 OOB 固件对。若你换成自己的 6843 固件，请保证 `.bin` 和 `.cfg` 是同一套配对产物。

```bash
cd mmwk_cli

PORT=<serial-port>
SSID=<wifi-ssid>
PASSWORD=<wifi-password>
FW_DIR=../firmwares/radar/iwr6843/oob

./server.sh start --serve-dir "$FW_DIR"
eval "$(./server.sh env)"

WORKING=./collect-lab

./tools/config.sh init \
  --port "$PORT" \
  --ssid "$SSID" \
  --password "$PASSWORD" \
  --working "$WORKING"

DEVICE_ID=<由 config.sh 打印出来的 id>

./tools/config.sh update \
  --device-id "$DEVICE_ID" \
  --fw "$FW_DIR/out_of_box_6843_aop.bin" \
  --cfg "$FW_DIR/out_of_box_6843_aop.cfg" \
  --working "$WORKING"

./mmwk_cli.sh radar status \
  --transport mqtt \
  --device-id "$DEVICE_ID" \
  --broker "$MMWK_SERVER_HOST_IP"

./mmwk_cli.sh radar fw version \
  --transport mqtt \
  --device-id "$DEVICE_ID" \
  --broker "$MMWK_SERVER_HOST_IP"

./tools/collect.sh \
  --device-id "$DEVICE_ID" \
  --duration 30 \
  --working "$WORKING"
```

正常预期：

- `config.sh init` 成功意味着 bridge 已经能访问目标 MQTT server，并且 `device.yml` 已经更新。
- `config.sh update` 会等到 `radar status` 回到 `running`。
- `collect.sh` 会把带时间戳前缀的采集文件写入 `<working>/data/<device-id>/`。

## 6432 系列

6432 系列建议直接使用 `wdr`。

下面例子使用公开的 `presence` 固件对：

```bash
cd mmwk_cli

PORT=<serial-port>
SSID=<wifi-ssid>
PASSWORD=<wifi-password>
FW_DIR=../firmwares/radar/iwrl6432/presence

./server.sh start --serve-dir "$FW_DIR"
eval "$(./server.sh env)"

WORKING=./collect-lab

./tools/config.sh init \
  --port "$PORT" \
  --ssid "$SSID" \
  --password "$PASSWORD" \
  --working "$WORKING"

DEVICE_ID=<由 config.sh 打印出来的 id>

./tools/config.sh update \
  --device-id "$DEVICE_ID" \
  --fw "$FW_DIR/presence.appimage" \
  --cfg "$FW_DIR/presence.cfg" \
  --working "$WORKING"

./mmwk_cli.sh radar status \
  --transport mqtt \
  --device-id "$DEVICE_ID" \
  --broker "$MMWK_SERVER_HOST_IP"

./mmwk_cli.sh radar fw version \
  --transport mqtt \
  --device-id "$DEVICE_ID" \
  --broker "$MMWK_SERVER_HOST_IP"

./tools/collect.sh \
  --device-id "$DEVICE_ID" \
  --duration 30 \
  --working "$WORKING"
```

6432 相关注意点：

- bridge 侧的雷达链路是单 UART。
- 当 `uart_split=1` 时，稳定运行期的 raw 字节主要会进入 `raw_data.sraw`。
- 带时间戳前缀的 `*_raw_data.log` 仍然主要用于看启动文本和命令响应窗口。

所以，不要只看 `*_raw_data.log` 来判断 6432 是否采集成功，要同时检查 `*_raw_data.sraw` 和 `*_summary.json`。

## 实际排查时怎么判断

- `config.sh init` 打印出 device id 和后续命令，说明 UART bring-up 已经完成。
- `config.sh update` 成功退出，说明它已经完成 OTA 或运行时 cfg 更新，并验证了运行态恢复。
- 如果你要手动复查运行态，先看 `./mmwk_cli.sh radar status`，把 `state=running` 当成硬门槛。
- 如果设备重启后串口号变化了，先重新识别串口，再重复 UART 命令。

## 什么时候用 `collect.sh`，什么时候用 `collect -p`

`collect.sh` 是一个任务导向的 MQTT helper，更适合网络已经就绪之后的 late-attach raw 采集窗口。它会从 `device.yml` 读取 MQTT 配置，并把带时间戳前缀的输出写到 `<working>/data/<device-id>/`。

如果你要抓同一次 reboot、flash 或 radar restart 窗口里的启动期命令口输出，应改用官方的 UART 辅助采集命令：

```bash
./mmwk_cli.sh collect -p <serial-port> --duration 12
```

当雷达已经联网并且你只是想更简单地做 MQTT 采集时，再使用 `collect.sh`。
