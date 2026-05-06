# mmWave Sensor Development Kit

MMWK 是面向雷达固件开发、原始数据采集、联网控制和产品化验证的 mmWave Sensor Development Kit。只要固件基于 `mmwk_sensor` 栈构建，同一套平台行为就适用于受支持的雷达与主控组合，包括 IWR6843 / IWRL6432，以及 ESP / ESP32-S3 系列板卡。

旧文档中描述的 bridge 能力是平台能力，不只是某一个固件模式。`mmwk_sensor_bridge` 是基于该平台的基础透传 profile；`mmwk_sensor_hub` 等其他 profile 同样保留共享 sensor 能力，并在其上增加自己的高层 profile 语义。

## 1. 概览

如果你属于以下任一情况，请从这里开始：

- 你正在第一次 bring-up 一块 MMWK 板卡
- 设备已经运行某个 `mmwk_sensor` 固件 profile，并且你想跑通第一次端到端雷达刷写加数据采集
- 你需要快速选择出厂刷机、OTA、采集或参考文档入口
- 你想区分哪些行为属于共享 sensor 平台，哪些行为属于某个具体固件 profile

执行命令前请注意：

- 请从 `./cli` 目录执行下面的 shell 示例，这样 `./run.sh` 和 `../firmwares/...` 这些参考路径才能按文档原样生效。
- 把 `PORT=/dev/cu.usbserial-0001` 替换成你自己机器上的真实 UART 串口。
- 本文档默认你先执行 `./run.sh device hi -p "$PORT"` 或 `./run.sh node info -p "$PORT"`，并且返回某个 `mmwk_sensor` 固件 profile，例如 `mmwk_sensor_bridge`。
- `run.sh` 默认走标准 CLI JSON。如果旧调用方还依赖 MCP，请显式加上 `--protocol mcp` 作为兼容回退。
- 本文档不替代 Wi-Fi / MQTT bring-up。执行 `collect` 之前，设备运行时网络应已经可用，例如 `ip` 不应还是 `0.0.0.0`；依赖 MQTT 的流程应看到 `mqtt_state=connected`。
- 如果你刚执行过 `radar flash`、`radar ota`、`radar reconf`，或者刚走完 factory / baseline 恢复路径后的第一次上电，请先等 `radar status` 返回 `running`，再去使用任何 late-attach 的 `collect` 流程。

下面这组 shell 变量可直接复用到后续命令：

```bash
cd ./cli
export PORT=/dev/cu.usbserial-0001
export FW=../firmwares/radar/iwr6843/vital_signs/vital_signs_tracking_6843AOP_demo.bin
export CFG=../firmwares/radar/iwr6843/vital_signs/vital_signs_AOP_2m.cfg
```

## 2. 平台模型

### 2.1 mmwk_sensor 共享能力层

`mmwk_sensor` 是面向受支持 MMWK 板卡的共享固件平台。它提供固件 profile 共同使用的控制、联网、OTA、雷达固件管理、raw 透传、启动验证和用户交互能力。

这些能力不绑定某一个雷达芯片家族或某一代 ESP。只要当前固件 profile 基于 `mmwk_sensor`，它们就适用于受支持的 6843 / 6432 与 ESP / ESP32-S3 组合。

### 2.2 固件 Profile

固件 profile 定义共享平台层之上的产品面。

- `mmwk_sensor_bridge` 是基础透明透传 profile。
- `mmwk_sensor_hub` 是在保留共享平台行为的基础上，增加雷达传感器 sensor hub profile 的 profile。公开示例包括心率、呼吸、睡眠和体动等传感器面。

### 2.3 Bridge 能力与 mmwk_sensor_bridge Profile

Bridge 能力表示平台可以通过主机可见的控制和 raw 传输通道暴露雷达侧命令/数据流。它包括 CLI 控制、MQTT 传输、raw topic 派生、启动观测，以及可选的 host 模式 raw 命令输入。

`mmwk_sensor_bridge` 是公开的基础 profile，重点使用这类能力，并且不叠加更高层的 sensor hub 产品面。它适合雷达固件开发、刷写、配置、调参、raw 数据采集和主机侧验证。

### 2.4 Hub Profile 边界

本文档只把 `mmwk_sensor_hub` 作为有边界的 profile 示例。它同样具备共享 `mmwk_sensor` sensor 能力，并在共享层之上增加雷达传感器 sensor hub 语义，同时仍保留 raw 雷达数据、点云实时显示等 bridge 能力。

Hub 内部实现、算法、私有模块和具体产品行为不属于这份公开文档范围。

## 3. 快速开始

目标读者：生产测试、售后、现场部署和雷达固件开发人员。
目标：以最短路径完成上电、Wi-Fi 配网、MQTT 连接、雷达刷写、原始数据转发，以及录制/上传验证。

### 3.1 路径 A：空片 / 被擦除板卡 -> 出厂刷机

如果 ESP 还是空片、已擦除，或尚未运行当前公开的 `mmwk_sensor_bridge` 固件包，请走这条路径。

- 直接阅读 [出厂刷机指南](./flash.md)。
- 当前公开基础版本以 `factory.zip` 加 `ota.zip` 交付；`flash.md` 说明首次烧录如何使用 `factory.zip`。
- 出厂刷机成功后，再回到这里继续走路径 B，或者在后续维护时走路径 C。

### 3.2 路径 B：Sensor 固件已运行 -> 雷达刷写 + 数据采集

如果 `node info` 已经能返回可访问的 `mmwk_sensor` 固件 profile，而你要跑通第一次端到端流程，请走这条路径。

推荐顺序：

1. 用 `./cli/run.sh node info -p <port>` 确认设备可通过 UART 访问。
2. 如果 Wi-Fi 和 MQTT 还没配置好，按 [本地 `server.sh` + `run.sh` Wi-Fi 刷机与 5 分钟采集示例](./collect.md) 里的 bring-up 主线继续。
3. 用 [本地 `server.sh` + `run.sh` Wi-Fi 刷机与 5 分钟采集示例](./collect.md) 完成经过验证的雷达刷写加 5 分钟数据采集流程。

`collect.md` 负责完整的详细步骤。参数契约、welcome/version 语义、topic split、raw capture 细节和启动模式边界都已并入本文后续章节。

### 3.3 路径 C：仅做 ESP OTA

如果设备已经运行当前公开的 `mmwk_sensor_bridge` 包，而你只需要更新 ESP 固件本身，请直接走这条路径。

- 直接阅读 [设备 OTA 指南](./ota.md)。
- 这是已运行设备的维护路径，不需要再走完整 bring-up 流程。

## 4. 共享平台能力

### 4.1 CLI 控制

平台通过 UART 和 MQTT 暴露标准 CLI JSON 控制面。主机侧推荐在 macOS 或 Linux 上使用 `./cli/run.sh` 作为统一入口。

### 4.2 Wi-Fi 配网

出厂态或未配置设备会暴露 AP 配网流程。用户可以通过浏览器门户配置 Wi-Fi，也可以通过 UART 上的 CLI 命令配置。

### 4.3 MQTT 传输

网络配置完成后，MQTT 是推荐的远程控制和数据通道。设备命令/响应 topic 以及原始雷达 topic 都从设备 MQTT 身份派生。

### 4.4 4G / 网络优先级

具备蜂窝硬件的板卡可以保存 4G 配置，并选择 Wi-Fi 或 4G 作为优先网络。如果优先网络无法上线，设备可以临时使用可用 fallback，同时保留已保存的优先级。

### 4.5 OTA 与固件管理

平台支持 ESP OTA，用于设备固件维护；也支持雷达固件和配置管理，用于雷达侧开发与验证。

### 4.6 原始雷达透传

raw 透传是共享 `mmwk_sensor` 能力。它会把雷达 DATA 字节和启动 trim 后的命令口输出转发到主机可见的 raw 通道。在 host 模式下，平台还可以暴露 raw 命令输入。

### 4.7 KEY 与 LED 交互

ESP 侧 KEY 与 LED 行为默认在所有受支持板型上一致。详细行为见 [5. 用户交互](#5-用户交互)。

## 5. 用户交互

### 5.1 LED 行为

ESP 侧 LED 行为默认在受支持的 `mmwk_sensor` 板卡上一致。各板具体 LED 位置和 GPIO 请看对应 `modules/` 硬件文档。

| 状态 | Pattern | 含义 |
|------|---------|------|
| **INIT** | 常亮 3 秒后关闭 | 开机提示 |
| **OFF** | LED 关闭 | 正常空闲 / 运行显示 |
| **CONFIRM short** | 关闭、亮 500ms、关闭 | 短交互确认 |
| **CONFIRM double** | 关闭、亮 500ms、关 100ms、亮 500ms、关闭 | 4G 优先网络确认 |
| **CONFIRM normal** | 关闭、亮 500ms、关 100ms、亮 500ms、关闭 | 配置或连接确认 |
| **CONFIRM long** | 关闭，然后亮 500ms / 关 100ms 循环 3 次 | 长交互确认，包括恢复出厂长按 |
| **MQTT connected** | 常亮约 30 秒 | MQTT 连接成功提示 |
| **ERROR warning** | 亮 1000ms / 关 1000ms 持续循环 | MQTT 断开、MQTT 连接错误，或 MQTT 启动/重连失败 |
| **ERROR severe** | 亮 200ms / 关 100ms 持续循环 | Wi-Fi 或 CAT1/4G 无法联网后的网络连接失败 |

LED 不是网络 ready 信号。网络 ready 以 `network status` 的 `state=connected && ready=true` 为准；MQTT 相关流程以 `mqtt_state=connected` 为准。

`node agent --led 0|1` 只控制 ERROR 显示。INIT 和 CONFIRM 始终会显示；当 `led=0` 时，ERROR 逻辑状态仍存在，但硬件 LED 保持关闭。

### 5.2 KEY 行为

ESP 侧 KEY 行为默认在受支持的 `mmwk_sensor` 板卡上一致。各板具体 KEY 位置和 GPIO 请看对应 `modules/` 硬件文档。

- **短按 1 次**：确认当前优先网络。闪 1 次 = Wi-Fi，闪 2 次 = 4G。
- **连续短按 3 次**：在支持 4G 的设备上切换 Wi-Fi / 4G 优先网络。
- **长按 10 秒**：恢复出厂设置，清除 NVS 并重启。

## 6. 控制、传输与原始雷达透传

### 6.1 UART 接口

UART 是本地工厂初始化、调试、恢复和台架 bring-up 路径。另一个单片机在电平和管脚匹配时，可以直接连接板子的 UART。UART 管脚随板子而变，接线前请查看对应板子的原理图。

当前板子如果要让 PC 连接 UART，需要外接 UART 转 USB 转接器。PC 的 USB 口不能直接和裸 UART 管脚通信。

WDR 和新设计是普通 CLI / 控制场景下的当前例外：它们通过 UART 和 USB 复用支持内置 USB 串口，所以普通控制接口不需要额外 UART 转 USB 转接器。

ESP 芯片级刷机和普通控制接口是两件事。所有板子做 ESP 芯片级刷机时，仍然需要对应的外部转换器或刷机治具。

推荐主机入口：

```bash
./run.sh node info -p "$PORT"
```

UART 命令默认使用标准 CLI JSON 协议。CLI key 保护启用后，受保护命令需要 `--key`。

### 6.2 UART 和 USB 复用

UART 和 USB 复用会在启动或恢复后的空闲窗口内，在 UART 和 USB CDC 之间选择本地控制接口。目前只有 WDR 和新设计支持。

这个选择和优先网络无关。空闲窗口内检测到 UART 活动时，控制路径保持在 UART；窗口超时且没有 UART 活动时，控制路径切到 USB CDC。

在 WDR 上，CAT1/4G USB-DTE 只有在 4G 实际启动或运行时才单独参与仲裁；仅仅把优先网络设为 4G，不会阻止设备进入 UART 和 USB 复用。

### 6.3 MQTT 上的 CLI JSON

网络配置完成后，MQTT 是推荐的远程应用/控制路径。配置方式：

```bash
./run.sh network mqtt --uri mqtt://192.168.1.100:1883 -p "$PORT"
```

然后验证 ready：

```bash
./run.sh network status -p "$PORT"
```

网络 ready 以 `state=connected && ready=true` 为准；MQTT ready 以 `mqtt_state=connected` 为准。

### 6.4 MQTT Topic 身份

`network mqtt` 负责配置 broker / 鉴权设置。设备 MQTT 身份以及 canonical topic 派生仍绑定设备身份。

标准控制 topic：

| Topic | 内容 |
| --- | --- |
| `mmwk/{mac}/device/cmd` | 由 `network mqtt` 配置的 CLI JSON 命令输入。 |
| `mmwk/{mac}/device/resp` | 由 `network mqtt` 配置的 CLI JSON 响应和状态事件。 |


### 6.5 原始语义契约

- `raw_resp = startup-trimmed command-port output from on_cmd_data`
- `raw_data = raw data-port bytes from on_radar_data`
- `on_cmd_resp is an application-layer command response`，且它与 raw capture 不同。
- `on_radar_frame is an application-layer frame callback`，且它与 raw capture 不同。
- 雷达驱动会先裁掉启动阶段第一个 printable ASCII 字节之前的脏数据，再把命令口输出暴露给主机侧。
- `cmd_resp.log` 保留从第一个 printable ASCII 字节开始的启动 trim 后的命令口文本。

### 6.6 Raw Topic 分工

`radar raw` 会复用已配置的 MQTT broker/client，并派生原始雷达透传平面。

| Topic | 内容 |
| --- | --- |
| `mmwk/{mac}/raw/data` | 由 `radar raw` 派生的雷达 DATA UART 原始透传。 |
| `mmwk/{mac}/raw/resp` | 由 `radar raw` 派生的雷达 CMD UART 启动 trim 后命令口输出（来源 `on_cmd_data`）。 |
| `mmwk/{mac}/raw/cmd` | 可选的雷达 CMD UART 输入通道，仅在 host 模式下可用。 |

对于 fresh `mmwk_sensor_bridge` 设备，执行 `network mqtt` 并重启后，就应具备 MQTT 控制能力。
当 NVS 里还没有这些 agent key 时，`mmwk_sensor_bridge` 默认 `mqtt_en=1`、`raw_auto=1`。
其他 profile 可以选择不同的 profile 默认值，但保留相同的平台控制模型。

### 6.7 Host 模式 raw 命令输入

`mmwk/{mac}/raw/cmd` 仅在当前雷达会话运行于 host 模式时可用。它与 CLI JSON 的 `mmwk/{mac}/device/cmd` 是两条不同通道。

auto 模式下，MQTT raw 平面是只出不进的。

## 7. 雷达固件管理

### 7.1 Flash / OTA 参数

共享参数：

| 参数 | 适用命令 | 含义 |
| --- | --- | --- |
| `--fw <file.bin>` | `radar ota`、`radar flash` | 必填，表示写入雷达芯片的固件二进制。 |
| `--cfg <file.cfg>` | `radar ota`、`radar flash` | 可选，表示与所选固件匹配的雷达配置文本。 |
| `-p <serial_port>` | 参考示例 | 主机侧 UART 串口，CLI 通过它连接到设备控制服务。 |

HTTP OTA 专属参数：

| 参数 | 含义 |
| --- | --- |
| `--http-port <port>` | 当 CLI 启动临时 HTTP 文件服务时使用的端口。 |
| `--base-url <url>` | 跳过本地 HTTP 服务，直接让设备从一个现成的 HTTP 基础地址下载固件。 |
| `--version <str>` | 显式指定期望的雷达固件版本号。 |
| `--ota-timeout <sec>` | OTA 下载并应用的最长等待时间。 |
| `--progress-interval <sec>` | 设备上报刷机进度的时间间隔。 |

分块传输（`radar flash`）专属参数：

| 参数 | 含义 |
| --- | --- |
| `--chunk-size <bytes>` | 每个固件分块的大小。 |
| `--mqtt-delay <sec>` | 当 `radar flash` 走 MQTT 传输时，块与块之间的延时。 |
| `--progress-interval <sec>` | 分块刷机过程中设备上报进度的时间间隔。 |
| `--reboot-delay <sec>` | 刷机成功后 ESP 重启前的附加等待时间。 |

### 7.2 管理型固件目录

当你要管理 ESP 侧保存的雷达固件目录，而不是当场从主机推一份新的雷达镜像时，请使用 `fw` 相关命令。

```bash
./run.sh fw list -p "$PORT"
./run.sh fw set --index 0 -p "$PORT"
```

契约：

- `fw list` 是 profile 面向用户的固件目录查看面。每个条目都带有 `default` 和 `running` 标志，用来区分保存的默认固件和当前运行中的目录条目。
- bundled 条目属于运行时内置资产，不是主机上传后落到存储区的新对象；请把它们视为随固件携带的只读目录项。
- `fw set --index <n>` 是持久化的默认固件切换，不是单纯的 metadata 开关。

### 7.3 运行态固件状态

`device hi` / `node info` 会返回嵌套固件状态：

- `fw.default`
- `fw.running`
- `fw.switch`
- `fw.boot_mode`

`fw.default` 表示保存下来的持久化默认条目。`fw.running` 表示当前会话真实运行中的条目。`fw.boot_mode` 表示当前雷达会话的启动路径：`flash`、`uart`、`spi`、`host`。

旧字段 `radar_fw`、`radar_fw_version`、`radar_cfg` 仍然保留，并继续映射到 `fw.running`。

### 7.4 运行时重配置

当你只想修改运行时雷达契约，而不想再次刷写 firmware 时，请使用 `radar reconf`。它可以切换 `welcome` / `verify` / `version` 语义，也可以替换或清除运行时 cfg，同时保持当前雷达固件二进制不变。

```bash
./run.sh radar reconf --welcome --no-verify -p "$PORT"
./run.sh radar reconf --welcome --verify --version "1.2.3" -p "$PORT"
./run.sh radar reconf --welcome --no-verify --cfg ./runtime.cfg -p "$PORT"
./run.sh radar reconf --welcome --no-verify --clear-cfg -p "$PORT"
```

契约：

- Host 模式下会拒绝运行时重配置。
- `cfg_action` 取值为 `keep | replace | clear`。
- `--cfg` 对应 `cfg_action=replace`，只上传运行时 cfg，并以 `uart_data action=reconf_done` 收尾。
- `--clear-cfg` 对应 `cfg_action=clear`，会清除持久化的运行时 cfg override。
- 不传 `--cfg` 时，对应 `cfg_action=keep`，保留当前运行时 cfg 选择。
- 与 `radar flash`、`radar ota` 不同，`radar reconf` 不会重新刷写 firmware，也不会替换雷达二进制。
- 请把 `radar reconf` 当作可选的高级步骤。每次执行完 `radar reconf` 后，都要重新检查 `radar status`，并且等到 `state=running` 以后，再去依赖 `radar version` 或 `collect`。

### 7.5 运行时 CFG 回读

当你只想把当前实际生效的雷达 cfg 文本读出来，而不想改 firmware 或运行时契约状态时，请使用 `radar cfg`。

```bash
./run.sh radar cfg -p "$PORT"
```

契约：

- 默认读取当前实际生效的 file cfg 文本。
- 所谓“当前实际生效的 file cfg”，是指当前选中的运行时 override cfg；如果没有 override，则读取 firmware metadata 里的默认 cfg。
- 对 `radar flash` 明确传入的 firmware/cfg 配对，平台会持久化那对精确的 staging 运行时路径，而不会因为版本号相同就静默改绑到某个 bundled catalog 条目。
- 如果下次启动时无法精确重新打开这对持久化的显式运行时 firmware/cfg 路径，启动会直接失败，而不会静默替换成别的打包资产对。
- 如果当前选中的 file cfg 缺失、不可读或为空，请求会直接失败。
- CLI 只会把 cfg 文本本身输出到 stdout，因此重定向时可以保留原始 cfg 内容。

### 7.6 Metadata 来源契约

`radar flash` 和 `radar ota` 都会从 `--fw` 二进制旁边的 `meta.json` 推断雷达 metadata：`welcome` 加上可选的 `version`。

如果同时给了 CLI 参数和 `meta.json`，以显式 CLI 参数为准。如果你换成自定义 demo，请自行补一个匹配的 `meta.json`，或显式传入 `--welcome` / `--version`。

## 8. 启动与版本语义

### 8.1 启动模式

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

启动模式边界：

**Auto 模式：** `start_mode=auto` 表示保存下来的默认策略是由 ESP 负责雷达 bring-up。设备可以选择固件/配置 metadata、等待启动 CLI/welcome 输出、验证版本 metadata，并下发雷达配置。

**Host 模式：** `start_mode=host` 表示保存下来的默认策略是由主机接管启动，不是“auto 模式外加一个 raw topic”。设备仍然暴露传输面，但不会在启动期自动下发雷达配置，不会自动等待 welcome 文本，也不会作为启动所有权的一部分自动验证版本 metadata。

**运行态 Boot Path：** `fw.boot_mode=host` 表示当前这次雷达会话实际上走的是 host 启动路径。`mmwk/{mac}/raw/cmd` 仅在当前雷达会话运行于 host 模式时可用。

对真实应用、服务、仪表盘和 AI Agent，优先推荐 MQTT；UART 更适合工厂初始化、刷写、bring-up、台架调试和故障兜底。

### 8.2 Welcome 输出

- 启动文本是一种 boot observation，不是固定 banner 契约。
- welcome 路径是 MMWK 同时判断“雷达 app 是否真正启动”和“它打印了什么版本字符串”的唯一运行态来源。
- 如果 `welcome=true`，设备应在正常下发配置前看到启动阶段的 CLI/welcome 输出。

### 8.3 版本匹配

- `radar flash` 和 `radar ota` 都支持显式传入 `--version <str>`、`--verify` / `--no-verify`、`--welcome` / `--no-welcome`。
- `version` 表示启动 CLI/welcome 输出里的目标子串。
- 当启用版本校验时，MMWK 会在整段启动输出里查找目标子串，不要求固定某一行 welcome 文本。
- `--verify` 会打开版本匹配，并且要求必须提供版本字符串。
- 如果 `--verify` 不启用，刷机仍然可能成功，但 `radar version` 可能保持为空，因为没有期望字符串可匹配和保存。
- 如果你需要定制一个可识别的雷达固件版本号，请让雷达固件的启动 CLI 输出打印出那个目标字符串，并确保主机通过 `--version` 或相邻 `meta.json` 提供同一个期望字符串。

### 8.4 启动失败处理

如果 `welcome=true`，但在超时窗口内没有任何启动 CLI/welcome 输出，应把这次会话视为雷达启动失败：固件大概率没有在雷达侧成功启动。此时 `radar status` 会保持 `state=error`，并附带 `details` 字段解释失败原因。

## 9. 生产 / 售后 SOP

### 9.1 SOP 前置条件

- 固件：某个 `mmwk_sensor` 固件 profile。当前公开基础 profile 下，`node info.name` 通常会返回 `mmwk_sensor_bridge`。
- 串口：`UART0 / 115200 baud`。
- 可连接设备 AP 的手机或电脑。
- 可访问的 MQTT broker（优先局域网）。
- 可访问的 HTTP 上传端点（用于 `record` 验证）。

### 9.2 配置 Wi-Fi

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

### 9.3 配置 MQTT 与 raw 透传

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

### 9.4 设备身份检查

```bash
./cli/run.sh node info -p /dev/cu.usbserial-0001
```

`name` / `version` 描述当前运行在 MMWK 板子上的 ESP 固件身份；`radar_fw` / `radar_fw_version` / `radar_cfg` 描述的是 ESP 侧当前选择/默认的雷达元信息条目，不是直刷/OTA 后雷达芯片实时运行镜像的最终判据。要确认运行态，请结合 `radar fw version` 与 `radar status`。

### 9.5 用户交互检查

ESP 侧 KEY 与 LED 行为默认在所有受支持板型上一致。上电后按 [5. 用户交互](#5-用户交互) 确认 LED 和 KEY 行为。长按按钮 10 秒可清除 NVS 并重启（恢复出厂设置）。

### 9.6 主机侧采集冒烟测试

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

### 9.7 录制与上传验证

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

## 10. 运行态确认清单

在雷达刷写、OTA、reconf，或者 factory / baseline 恢复路径后的第一次上电后，建议结合以下命令一起确认：

```bash
./run.sh device hi -p "$PORT" | tee ./sensor_hi.json
./run.sh radar status -p "$PORT" | tee ./radar_status.json
./run.sh radar version -p "$PORT" | tee ./radar_version.json
./run.sh collect --duration 12 \
  --data-output ./data_resp.sraw \
  --resp-output ./cmd_resp.log \
  -p "$PORT"
```

最低预期证据：

- `device hi` 或 `node info` 能识别某个 `mmwk_sensor` 固件 profile。
- MQTT 相关流程开始前，`network status` 报告 `state=connected && ready=true`。
- 雷达 flash / OTA / reconf 后，`radar status` 返回 `running`。
- `cmd_resp.log` 包含启动 trim 后的命令口文本。
- 当当前雷达固件/配置组合预期会输出数据时，`data_resp.sraw` 非空。

如果 `device hi` 仍报告 `ip = 0.0.0.0`，请把设备网络视为尚未准备好进行 MQTT raw capture。

## 11. 故障排查参考

| 现象 | 可能原因 / 处理方式 |
| --- | --- |
| 看不到设备 AP | 给设备重新上电；如果仍无 AP，长按按钮 10 秒清除 NVS。 |
| MQTT 一直连不上 | 检查 `uri`、局域网连通性、防火墙规则、鉴权信息和 topic ACL。 |
| `raw_auto` 不生效 | 确认 MQTT 已启用且 MQTT 传输已连接。 |
| `collect` 超时 | 确保设备和主机都能访问同一个 MQTT broker。 |
| `details.kind=startup_failed` | 固件大概率没有真正启动到雷达 CLI。 |
| 雷达配置文件已经发出，但始终没有数据返回 | 大概率是 `.cfg` 和当前运行的雷达固件不匹配，导致雷达固件在应用配置后进入异常/死机状态。请重新核对固件 demo、板型/AOP 变体、CLI 指令是否匹配，并且先在雷达开发板上确认同一份固件 + 配置本身能够正确跑起来。 |

如果你要看完整的 bring-up 主线，请回到 [mmWave Sensor Development Kit](./mmwk-sensor.md)，再继续进入 [本地 `server.sh` + `run.sh` Wi-Fi 刷机与 5 分钟采集示例](./collect.md)。

## 12. 相关文档

- [出厂刷机指南](./flash.md)
- [本地 `server.sh` + `run.sh` Wi-Fi 刷机与 5 分钟采集示例](./collect.md)
- [设备 OTA 指南](./ota.md)
- [CLI README](../../cli/docs/zh-cn/README.md)
- [Radar Task Tools](../../cli/docs/zh-cn/radar-task-tools.md)
- [通过 Bridge 开发雷达](../../cli/docs/zh-cn/bridge-ti-radar-debug.md)
- [模组产品总览](../../modules/README_CN.md)
