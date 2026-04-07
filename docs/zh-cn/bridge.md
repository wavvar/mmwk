# MMWK Bridge 模式

MMWK Bridge 是默认运行模式。本文现在是 bridge 模式的规范起步入口：先判断设备当前所处状态，再跳转到正确的下一份操作文档。

## 本指南适合谁

如果你属于以下任一情况，请从这里开始：

- 你正在第一次把 MMWK 板卡带到 bridge 模式
- 设备已经在运行 bridge 固件，但你想跑通第一次端到端雷达刷写加数据采集
- 设备已经在运行 bridge 固件，你只想先确定下一步该看哪份文档

如果你已经知道自己要走哪条路径，只是需要查看更深入的技术语义，请直接跳到 [MMWK Sensor BRIDGE 参考](./bridge-reference.md)。

## 开始前先确认

- 硬件：请先看[模组产品总览](../../modules/README_CN.md)，再按板型进入 [RPX 模块使用指南](../../modules/rpx_cn.md) 或 [ML6432Ax 系列介绍](../../modules/ml6432ax_cn.md)
- 主机环境：推荐 macOS 或 Linux，并具备 `bash`
- 工具：Python 3.10+
- 本地接入：先确认设备串口，再执行 CLI
- 决策点：先判断板卡是空片/已擦除、已运行 bridge，还是已运行 bridge 且只需要 ESP OTA

## 路径 A：空片 / 被擦除板卡 -> 出厂刷机

如果 ESP 还是空片、已擦除，或尚未运行 bridge 固件，请走这条路径。

- 直接阅读 [Bridge 出厂烧录指南](./flash.md)
- 当前对外交付的 bridge 发布包是 `factory.zip` 加 `ota.zip`；首次烧录只使用 `factory.zip`
- 出厂刷机成功后，再回到这里继续走路径 B，或者在后续维护时走路径 C

## 路径 B：Bridge 已运行 -> 雷达刷写 + 数据采集

如果 `device hi` 已经能返回 bridge 身份信息，而你要跑通第一次 bridge 端到端 bring-up，请走这条路径。

推荐顺序：

1. 用 `./mmwk_cli/mmwk_cli.sh device hi -p <port>` 确认设备可通过 UART 访问
2. 如果 Wi-Fi 和 MQTT 还没配置好，按 [本地 `server.sh` + `mmwk_cli.sh` Wi-Fi 刷机与 5 分钟采集示例](./collect.md) 里的 bring-up 主线继续
3. 用 [本地 `server.sh` + `mmwk_cli.sh` Wi-Fi 刷机与 5 分钟采集示例](./collect.md) 完成经过验证的雷达刷写加 5 分钟数据采集流程

[本地 `server.sh` + `mmwk_cli.sh` Wi-Fi 刷机与 5 分钟采集示例](./collect.md) 负责完整的详细步骤。若你需要查看刷机参数契约、`meta.json`、welcome/version 语义、topic split 或 raw capture 细节，请再读 [MMWK Sensor BRIDGE 参考](./bridge-reference.md)。

## 路径 C：仅做 ESP OTA

如果设备已经在运行 bridge 固件，而你只需要更新 ESP 固件本身，请直接走这条路径。

- 直接阅读 [Bridge 设备 OTA 指南](./ota.md)
- 这是已运行 bridge 设备的维护路径，不需要再走完整的 bridge bring-up 流程

## 接下来读什么

- [Bridge 出厂烧录指南](./flash.md)：空片或擦除板卡的首次刷机
- [本地 `server.sh` + `mmwk_cli.sh` Wi-Fi 刷机与 5 分钟采集示例](./collect.md)：完整的 bridge bring-up、雷达刷写和数据采集
- [Bridge 设备 OTA 指南](./ota.md)：已运行 bridge 设备的 ESP OTA
- [MMWK Sensor BRIDGE 参考](./bridge-reference.md)：原始语义、topic 分工、welcome/version 处理和运行态确认细节
- [CLI README](../../mmwk_cli/docs/zh-cn/README.md)：完整 CLI 参考

## Bridge 启动模式

bridge 相关文档和 CLI 统一采用以下含义：

- `startup_mode` 表示保存/配置的默认模式。
- `supported_modes` 表示当前 profile 暴露的能力列表。
- bridge 会报告 `supported_modes: ["auto", "host"]`。
- `auto` 表示由 ESP 接管雷达 bring-up。
- `host` 表示由主机接管雷达 bring-up。
- `raw_auto` 只控制 raw 平面的自动启动，不决定由谁负责雷达启动。

运行时上请区分：

- `device startup --mode auto|host` 会持久化默认启动策略。
- `radar status --set start --mode auto|host` 只是当前雷达服务的一次性启动请求。
- 在 bridge `host` 下，ESP 仍然暴露 raw 传输面，但不会在启动期自动下发雷达配置。

## 生产 / 售后一页式 SOP

目标读者：生产测试、售后和现场部署人员。
目标：以最短路径完成上电、WiFi 配网、MQTT 连接、原始数据转发，以及录制/上传验证。

### 0. SOP 前置条件

- 固件：bridge 固件，**BRIDGE** 模式。`device hi.name` 通常会返回 `mmwk_sensor_bridge`
- 串口：`UART0 / 115200 baud`
- 可连接设备 AP 的手机或电脑
- 可访问的 MQTT broker（优先局域网）
- 可访问的 HTTP 上传端点（用于 `record` 验证）

### 1. 上电 LED 状态

- **WiFi 未连接**：快闪（约 100ms）
- **MQTT 已连接**：常亮约 30 秒
- **MQTT 未连接**：1 秒亮 / 1 秒灭循环

长按按钮 10 秒可清除 NVS 并重启（恢复出厂设置）。

### 2. WiFi 配网（无 WiFi 或连接失败时）

1. 扫描并连接 AP：`MMWK_XXXX`（开放网络，XXXX 为 MAC 后 4 位）
2. 在浏览器打开 `http://192.168.4.1/`
3. 输入 WiFi SSID 和密码并提交
4. 设备切换到 STA 模式并直接连接，不会自动重启

也可以通过 CLI（UART）配置：

```bash
./mmwk_cli/mmwk_cli.sh network config --ssid "YOUR_SSID" --password "YOUR_PASSWORD" -p /dev/cu.usbserial-0001
./mmwk_cli/mmwk_cli.sh device reboot -p /dev/cu.usbserial-0001
```

### 3. 最小命令集合（通过 UART 的 CLI）

#### 3.1 查看或覆盖当前 Agent 设置

fresh bridge 在缺 key 时已经默认 `mqtt_en=1`、`raw_auto=1`。产测或排障时，如果你要检查持久化状态，或手动覆盖旧设置，再执行下面的命令：

```bash
./mmwk_cli/mmwk_cli.sh device agent --mqtt-en 1 --raw-auto 1 -p /dev/cu.usbserial-0001
```

> **说明**：`mqtt_en`、`uart_en`、`raw_auto` 和 `single_uart_split` 会持久化到 NVS。缺失 bridge agent key 时，默认 `mqtt_en=1`、`raw_auto=1`；缺失 hub agent key 时，默认 `mqtt_en=0`、`raw_auto=1`。修改持久化值后建议重启设备，再确认最终状态。
>
> 对单 UART 的 `WDR/xWRL6432` 板卡，`single_uart_split` 用来控制运行期原始字节的去向：
> - `0`：保持 legacy 语义，运行期字节仍主要出现在 `raw_resp`
> - `1`：`sensorStart` 成功后把运行期字节切到 `raw_data`；运行中临时命令的响应窗口仍回到 `raw_resp`

#### 3.2 配置 MQTT 参数

```bash
./mmwk_cli/mmwk_cli.sh network mqtt --mqtt-uri mqtt://192.168.1.100:1883 -p /dev/cu.usbserial-0001
```

`network mqtt` 会配置设备 MQTT 身份以及 MCP 交互通道 `mmwk/{mac}/device/cmd` 和 `mmwk/{mac}/device/resp`。这是推荐的远程应用/控制路径。

配置完成后请重启设备，再继续验证。

#### 3.3 验证原始数据转发

启用原始数据转发。bridge/auto 模式下，默认会按 MQTT client ID 派生 `mmwk/{mac}/raw/data`、`mmwk/{mac}/raw/resp`；host 模式下还会额外派生 `mmwk/{mac}/raw/cmd`：

```bash
# 启用原始转发
./mmwk_cli/mmwk_cli.sh radar raw --enable -p /dev/cu.usbserial-0001

# 查询原始转发状态
./mmwk_cli/mmwk_cli.sh radar raw -p /dev/cu.usbserial-0001
```

各 topic 的含义如下：

- `raw_data`：雷达 DATA UART 透传字节（`data_resp`，二进制采集）
- `raw_resp`：雷达 CMD UART 启动 trim 后的命令口输出（`cmd_resp`，来源 `on_cmd_data`）
- `raw_cmd`：可选的雷达 CMD UART 输入通道，仅在 host 模式下可用，与 MCP 的 `mmwk/{mac}/device/cmd` 不同

如果 `startup_mode=host` 且 `raw_auto=1`，bridge 自动启动时也会一起派生 `mmwk/{mac}/raw/cmd`，与 `mmwk/{mac}/raw/data`、`mmwk/{mac}/raw/resp` 同时生效。

对于单 UART 的 `WDR/xWRL6432`，并不存在物理 DATA UART。这时：
- `single_uart_split=0` 时，运行期原始字节继续留在 `raw_resp`
- `single_uart_split=1` 时，驱动会在 `sensorStart` 成功后把运行期字节切到 `raw_data`，只有命令响应窗口仍发布到 `raw_resp`

#### 3.4 设备身份检查

```bash
./mmwk_cli/mmwk_cli.sh device hi -p /dev/cu.usbserial-0001
```

返回字段包括：`name`、`board`、`version`、`id`、`ip`、`mqtt_uri`、`client_id`、`cmd_topic`、`resp_topic`、`mqtt_en`、`uart_en`、`raw_auto`、`single_uart_split`、`radar_fw`、`radar_fw_version`、`radar_cfg`、`raw_data_topic`、`raw_resp_topic`，以及 host 模式下的 `raw_cmd_topic`。

其中 `name` / `version` 描述当前运行在 MMWK 板子上的 ESP 固件身份；`radar_fw` / `radar_fw_version` / `radar_cfg` 描述的是 ESP 侧当前选择/默认的雷达元信息条目，不是直刷/OTA 后雷达芯片实时运行镜像的最终判据。要确认运行态，请结合 `radar version` 与 `radar status`。
`startup_mode` 返回当前保存的默认启动策略，`supported_modes` 返回 bridge 能力列表 `["auto", "host"]`。

#### 3.5 IoT 实体与能力注册表（可选）

查询设备动态能力（entities、adapters、scenes、policies）：

```bash
./mmwk_cli/mmwk_cli.sh entity list --json -p /dev/cu.usbserial-0001
```

#### 3.6 主机侧采集冒烟测试

```bash
./mmwk_cli/mmwk_cli.sh collect --duration 12 \
  --data-output ./data_resp.sraw \
  --resp-output ./cmd_resp.log \
  -p /dev/cu.usbserial-0001
```

如果你已经拿到了可用的 MQTT 控制，并且明确要求主机侧采集全程不碰 UART，请继续把 `collect` 视为这条 checklist 的官方命令，同时改用 `mmwk_cli` 目录下的外挂 helper `./tools/mmwk_raw.sh`。这个 helper 只走 pure MQTT，支持 `trigger=none`、`trigger=radar-restart` 和 `trigger=device-reboot`。如果你还需要先下发 Wi-Fi / MQTT 设置，或者要把设备改指到本地 `server.sh` broker，请先运行 `./tools/mmwk_cfg.sh`。

最小通过标准：

- `Resp topic frames (CMD UART / startup-trimmed command-port text) > 0`
- `Data topic frames (DATA UART / binary) > 0`
- `data_resp.sraw` 非空
- `cmd_resp.log` 非空
- `cmd_resp.log` 从第一个 printable ASCII 字节开始，用户看到的是启动 trim 后的命令口文本

这里的 `Resp topic frames` 和 `Data topic frames` 统计的是 MQTT 消息条数，不是毫米波 TLV 帧数。对开启 `single_uart_split=1` 的单 UART `WDR/xWRL6432` 来说，`resp_topic` 里只有少量启动或命令响应分片是正常现象，持续运行期 payload 应主要出现在 `data_topic`。

### 4. 录制与上传验证（可选但推荐）

启动录制（`uri` 必须是可访问的 HTTP URL）：

```bash
./mmwk_cli/mmwk_cli.sh raw record start --uri "http://192.168.1.100:8080/upload" -p /dev/cu.usbserial-0001
```

触发一个 30 秒事件片段：

```bash
./mmwk_cli/mmwk_cli.sh raw record trigger --event "factory_test" --duration 30 -p /dev/cu.usbserial-0001
```

停止录制：

```bash
./mmwk_cli/mmwk_cli.sh raw record stop -p /dev/cu.usbserial-0001
```

### 5. 出厂验收标准（最低通过线）

- 设备 AP 配网页面可访问，且目标 WiFi 可成功连接
- `network mqtt` 配置已生效，设备重启后可连接 MQTT
- `radar raw` 的启停可正常工作，且 MQTT broker 能收到 `raw_data` 与 `raw_resp`
- 主机侧 `collect` 能同时验证 `data_resp.sraw` 与 `cmd_resp.log`
- `record start + trigger` 能让上传服务器收到 HTTP POST
- 长按按钮 10 秒可触发恢复出厂设置（设备回到未配网状态）
- `device hi` 返回完整的身份信息载荷，所有预期字段均已填充

### 6. 常见故障速查

| 现象 | 处理方式 |
|---|---|
| 看不到设备 AP | 给设备重新上电；如果仍无 AP，长按按钮 10 秒清除 NVS |
| MQTT 一直连不上 | 检查 `mqtt_uri`、局域网连通性、防火墙规则和 topic ACL |
| `raw_auto` 不生效 | 确认 `mqtt_en=1` 且 MQTT 传输已连接 |
| `record` 无法上传 | 检查 `start` 指定的 URI 是否可达，以及 HTTP 服务端状态 |
| WiFi 已连接但没有 IP | 检查目标网络 DHCP，必要时更换 SSID 测试 |
| `collect` 命令超时 | 确保设备和主机都能访问同一个 MQTT broker |
| 雷达配置文件已经发出，但始终没有数据返回 | 大概率是 `.cfg` 和当前运行的雷达固件不匹配，导致雷达固件在应用配置后进入异常/死机状态。请重新核对固件 demo、板型/AOP 变体、CLI 指令是否匹配，并且先在雷达开发板上确认同一份固件 + 配置本身能够正确跑起来。 |

## 故障排查 / 参考链接

- [Bridge 出厂烧录指南](./flash.md)
- [本地 `server.sh` + `mmwk_cli.sh` Wi-Fi 刷机与 5 分钟采集示例](./collect.md)
- [Bridge 设备 OTA 指南](./ota.md)
- [MMWK Sensor BRIDGE 参考](./bridge-reference.md)
- [CLI README](../../mmwk_cli/docs/zh-cn/README.md)
- [模组产品总览](../../modules/README_CN.md)
