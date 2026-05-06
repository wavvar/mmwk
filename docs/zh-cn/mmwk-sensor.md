# mmWave Sensor Development Kit

MMWK 是面向雷达固件开发、原始数据采集、联网控制和产品化验证的 mmWave Sensor Development Kit。只要固件基于 `mmwk_sensor` 栈构建，同一套平台行为就适用于受支持的雷达与主控组合，包括 IWR6843 / IWRL6432，以及 ESP / ESP32-S3 系列板卡。

旧文档中描述的 bridge 能力是平台能力，不只是某一个固件模式。`mmwk_sensor_bridge` 是基于该平台的基础透传 profile；`mmwk_sensor_hub` 等其他 profile 同样保留共享 sensor 能力，并在其上增加自己的高层 profile 语义。

## 1. 概览

如果你属于以下任一情况，请从这里开始：

- 你正在第一次 bring-up 一块 MMWK 板卡
- 设备已经运行某个 `mmwk_sensor` 固件 profile，并且你想跑通第一次端到端雷达刷写加数据采集
- 你需要快速选择出厂刷机、OTA、采集或参考文档入口
- 你想区分哪些行为属于共享 sensor 平台，哪些行为属于某个具体固件 profile

如果你已经知道自己要走哪条路径，只是需要深入查看技术语义，请直接跳到 [mmWave Sensor Development Kit 参考](./mmwk-sensor-reference.md)。

## 2. 支持的固件 Profile

### 2.1 mmwk_sensor_bridge

`mmwk_sensor_bridge` 是基础透明透传固件 profile。它提供共享的 `mmwk_sensor` 平台行为，重点用于雷达固件开发、刷写、配置、调参、raw 数据采集和主机侧验证。

它不定义更高层的 sensor hub 产品面。如果当前目标是打通主机、ESP、雷达固件、雷达配置和原始雷达数据流之间的链路，请优先使用它。

### 2.2 mmwk_sensor_hub

`mmwk_sensor_hub` 是另一个基于同一 `mmwk_sensor` 平台的固件 profile。它同样具备共享 sensor 能力，并在此基础上增加 sensor hub profile 的定义与实现。

本文档只把 hub 作为 profile 示例使用。Hub 内部模块、算法和具体产品行为不属于这份公开文档的范围。

## 3. 共享平台能力

### 3.1 CLI 控制

平台通过 UART 和 MQTT 暴露标准 CLI JSON 控制面。主机侧推荐在 macOS 或 Linux 上使用 `./cli/run.sh` 作为统一入口。

### 3.2 Wi-Fi 配网

出厂态或未配置设备会暴露 AP 配网流程。用户可以通过浏览器门户配置 Wi-Fi，也可以通过 UART 上的 CLI 命令配置。

### 3.3 MQTT 传输

网络配置完成后，MQTT 是推荐的远程控制和数据通道。设备命令/响应 topic 以及原始雷达 topic 都从设备 MQTT 身份派生。

### 3.4 4G / 网络优先级

具备蜂窝硬件的板卡可以保存 4G 配置，并选择 Wi-Fi 或 4G 作为优先网络。如果优先网络无法上线，设备可以临时使用可用 fallback，同时保留已保存的优先级。

### 3.5 OTA 与固件管理

平台支持 ESP OTA，用于设备固件维护；也支持雷达固件和配置管理，用于雷达侧开发与验证。

### 3.6 原始雷达透传

raw 透传是共享 `mmwk_sensor` 能力。它会把雷达 DATA 字节和启动 trim 后的命令口输出转发到主机可见的 raw 通道。在 host 模式下，平台还可以暴露 raw 命令输入。

### 3.7 KEY 与 LED 交互

ESP 侧 KEY 与 LED 行为默认在所有受支持板型上一致。完整行为表见 [3. 用户交互参考](./mmwk-sensor-reference.md#3-用户交互参考)。

## 4. 启动模式

sensor 文档和 CLI 统一采用以下含义：

- `mode` 表示由雷达状态面暴露的、当前保存/配置的默认模式。
- `modes` 表示当前固件 profile 暴露的能力列表。
- `fw.boot_mode` 表示当前运行态真实使用的雷达 boot path（`flash`、`host`、`uart`、`spi`）。
- `auto` 表示由 ESP 接管雷达 bring-up。
- `host` 表示由主机接管雷达 bring-up。
- `raw_auto` 只控制 raw 平面的自动启动，不决定由谁负责雷达启动。

运行时上请区分：

- `radar start --mode auto|host` 会先持久化新的默认模式，再按该模式启动或重启当前雷达服务。
- 不带 `--mode` 的 `radar start` 会按已保存的 `mode` 启动。
- `radar stop` 只停止当前雷达服务，不会改写 `mode`。
- `radar status` 现在是只读查询，不再接受 `--set`。

## 5. 生产 / 售后一页式 SOP

目标读者：生产测试、售后和现场部署人员。
目标：以最短路径完成上电、Wi-Fi 配网、MQTT 连接、原始数据转发，以及录制/上传验证。

### 5.1 SOP 前置条件

- 固件：某个 `mmwk_sensor` 固件 profile。当前公开基础 profile 下，`node info.name` 通常会返回 `mmwk_sensor_bridge`。
- 串口：`UART0 / 115200 baud`。
- 可连接设备 AP 的手机或电脑。
- 可访问的 MQTT broker（优先局域网）。
- 可访问的 HTTP 上传端点（用于 `record` 验证）。

### 5.2 路径 A：空片 / 被擦除板卡 -> 出厂刷机

如果 ESP 还是空片、已擦除，或尚未运行当前公开的 `mmwk_sensor_bridge` 固件包，请走这条路径。

- 直接阅读 [出厂刷机指南](./flash.md)。
- 当前公开基础版本以 `factory.zip` 加 `ota.zip` 交付；`flash.md` 说明首次烧录如何使用 `factory.zip`。
- 出厂刷机成功后，再回到这里继续走路径 B，或者在后续维护时走路径 C。

### 5.3 路径 B：Sensor 固件已运行 -> 雷达刷写 + 数据采集

如果 `node info` 已经能返回可访问的 `mmwk_sensor` 固件 profile，而你要跑通第一次端到端流程，请走这条路径。

推荐顺序：

1. 用 `./cli/run.sh node info -p <port>` 确认设备可通过 UART 访问。
2. 如果 Wi-Fi 和 MQTT 还没配置好，按 [本地 `server.sh` + `run.sh` Wi-Fi 刷机与 5 分钟采集示例](./collect.md) 里的 bring-up 主线继续。
3. 用 [本地 `server.sh` + `run.sh` Wi-Fi 刷机与 5 分钟采集示例](./collect.md) 完成经过验证的雷达刷写加 5 分钟数据采集流程。

`collect.md` 负责完整的详细步骤。若你需要查看参数契约、welcome/version 语义、topic split、raw capture 细节或启动模式边界，请再读 [mmWave Sensor Development Kit 参考](./mmwk-sensor-reference.md)。

### 5.4 路径 C：仅做 ESP OTA

如果设备已经运行当前公开的 `mmwk_sensor_bridge` 包，而你只需要更新 ESP 固件本身，请直接走这条路径。

- 直接阅读 [设备 OTA 指南](./ota.md)。
- 这是已运行设备的维护路径，不需要再走完整 bring-up 流程。

### 5.5 上电用户交互

上电后按 [3. 用户交互参考](./mmwk-sensor-reference.md#3-用户交互参考) 确认 LED 和 KEY 行为。长按按钮 10 秒可清除 NVS 并重启（恢复出厂设置）。

### 5.6 配置 Wi-Fi

无 Wi-Fi 配置或连接失败时：

1. 扫描并连接 AP：`MMWK_XXXX`（开放网络，XXXX 为 MAC 后 4 位）。
2. 在浏览器打开 `http://192.168.4.1/`。
3. 输入 Wi-Fi SSID 和密码并提交。
4. 设备切换到 STA 模式并直接连接，不会自动重启。

也可以通过 UART 上的 CLI 配置：

```bash
./cli/run.sh network wifi --ssid "YOUR_SSID" --pass "YOUR_PASSWORD" -p /dev/cu.usbserial-0001
./cli/run.sh node reboot -p /dev/cu.usbserial-0001
```

### 5.7 配置 MQTT 与 raw 透传

fresh `mmwk_sensor_bridge` 设备在 agent key 缺失时默认 `mqtt=1`、`raw_auto=1`。其他 profile 可以选择不同的 profile 默认值，但保持相同的平台控制面。

```bash
./cli/run.sh node agent --mqtt 1 --raw-auto 1 -p /dev/cu.usbserial-0001
./cli/run.sh network mqtt --uri mqtt://192.168.1.100:1883 -p /dev/cu.usbserial-0001
./cli/run.sh node reboot -p /dev/cu.usbserial-0001
```

重启后验证：

```bash
./cli/run.sh network status -p /dev/cu.usbserial-0001
./cli/run.sh radar raw status -p /dev/cu.usbserial-0001
```

网络 ready 以 `network status` 的 `state=connected && ready=true` 为准；MQTT 相关流程以 `mqtt_state=connected` 为准。

### 5.8 设备身份检查

```bash
./cli/run.sh node info -p /dev/cu.usbserial-0001
```

`name` / `version` 描述当前运行在 MMWK 板子上的 ESP 固件身份；`radar_fw` / `radar_fw_version` / `radar_cfg` 描述的是 ESP 侧当前选择/默认的雷达元信息条目，不是直刷/OTA 后雷达芯片实时运行镜像的最终判据。要确认运行态，请结合 `radar fw version` 与 `radar status`。

### 5.9 主机侧采集冒烟测试

```bash
./cli/run.sh collect --duration 12 \
  --data-output ./data_resp.sraw \
  --resp-output ./cmd_resp.log \
  -p /dev/cu.usbserial-0001
```

最小通过标准：

- `Resp topic frames (CMD UART / startup-trimmed command-port text) > 0`
- `Data topic frames (DATA UART / binary) > 0`
- `data_resp.sraw` 非空
- `cmd_resp.log` 非空
- `cmd_resp.log` 从第一个 printable ASCII 字节开始，用户看到的是启动 trim 后的命令口文本

这里的 `Resp topic frames` 和 `Data topic frames` 统计的是 MQTT 消息条数，不是毫米波 TLV 帧数。对开启 `single_uart_split=1` 的单 UART `WDR/xWRL6432` 来说，`resp_topic` 里只有少量启动或命令响应分片是正常现象，持续运行期 payload 应主要出现在 `data_topic`。

### 5.10 录制与上传验证

启动录制（`uri` 必须是可访问的 HTTP URL）：

```bash
./cli/run.sh raw record start --uri "http://192.168.1.100:8080/upload" -p /dev/cu.usbserial-0001
```

触发一个 30 秒事件片段：

```bash
./cli/run.sh raw record trigger --event "factory_test" --duration 30 -p /dev/cu.usbserial-0001
```

停止录制：

```bash
./cli/run.sh raw record stop -p /dev/cu.usbserial-0001
```

## 6. 常见故障速查

| 现象 | 处理方式 |
|---|---|
| 看不到设备 AP | 给设备重新上电；如果仍无 AP，长按按钮 10 秒清除 NVS。 |
| MQTT 一直连不上 | 检查 `uri`、局域网连通性、防火墙规则和 topic ACL。 |
| `raw_auto` 不生效 | 确认 MQTT 已启用且 MQTT 传输已连接。 |
| `record` 无法上传 | 检查 `start` 指定的 URI 是否可达，以及 HTTP 服务端状态。 |
| Wi-Fi 已连接但没有 IP | 检查目标网络 DHCP，必要时更换 SSID 测试。 |
| `collect` 命令超时 | 确保设备和主机都能访问同一个 MQTT broker。 |
| 雷达配置文件已经发出，但始终没有数据返回 | 大概率是 `.cfg` 和当前运行的雷达固件不匹配，导致雷达固件在应用配置后进入异常/死机状态。请重新核对固件 demo、板型/AOP 变体、CLI 指令是否匹配，并且先在雷达开发板上确认同一份固件 + 配置本身能够正确跑起来。 |

## 7. 相关文档

- [出厂刷机指南](./flash.md)
- [本地 `server.sh` + `run.sh` Wi-Fi 刷机与 5 分钟采集示例](./collect.md)
- [设备 OTA 指南](./ota.md)
- [mmWave Sensor Development Kit 参考](./mmwk-sensor-reference.md)
- [CLI README](../../cli/docs/zh-cn/README.md)
- [Radar Task Tools](../../cli/docs/zh-cn/radar-task-tools.md)
- [通过 Bridge 开发雷达](../../cli/docs/zh-cn/bridge-ti-radar-debug.md)
- [模组产品总览](../../modules/README_CN.md)
