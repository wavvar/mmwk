# Wavvar MMWK MCP 协议规范 V1.3

本文档说明 MMWK bridge/hub 固件暴露的 Model Context Protocol（MCP）兼容服务端能力、行为和配置接口。

当前默认内置协议为标准 CLI JSON（CLIv1），见 [CLIv1_CN.md](./CLIv1_CN.md)。只有在调用方显式指定 `--protocol mcp` 时，才需要参考本文档。

## 原始语义契约

- `raw_resp = startup-trimmed command-port output from on_cmd_data`
- `raw_data = raw data-port bytes from on_radar_data`
- `on_cmd_resp is an application-layer command response`，且它与 raw capture 不同。
- `on_radar_frame is an application-layer frame callback`，且它与 raw capture 不同。
- `raw_resp` 会在驱动侧裁掉启动脏数据后，从第一个 printable ASCII 字节开始对外发布。

## 传输与封包

- **UART**：UART0，115200 波特率，按行分隔的 JSON-RPC（`\n` / `\r\n`）
- **MQTT**：在已配置的 `cmd_topic`（请求）和 `resp_topic`（响应）上承载 JSON-RPC

说明：

- UART 解析器按行处理，每行发送一条完整 JSON-RPC 请求
- 服务端内核支持 JSON-RPC batch 数组

## 已实现的 JSON-RPC 方法

| Method | 是否实现 | 说明 |
|---|---|---|
| `initialize` | Yes | 返回协议、服务端信息和 capabilities |
| `notifications/initialized` | Yes | 仅通知，无响应 |
| `tools/list` | Yes | 按模式发现工具：BRIDGE 返回完整列表，HUB 返回兼容子集 `help` |
| `tools/call` | Yes | 主命令入口 |
| `resources/list` | Yes | 返回静态占位资源列表 |
| `resources/read` | Yes | 返回模拟内容，不是真实文件流 |
| `ping` | Yes | 返回空结果对象 |

### `initialize`

示例：

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"v1.3","capabilities":{},"clientInfo":{"name":"client","version":"1.0"}}}
```

典型响应（BRIDGE）：

```json
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"v1.3","capabilities":{"tools":{},"resources":{"listChanged":false,"subscribe":false}},"serverInfo":{"name":"mmwk_sensor_bridge","version":"1.0.0"}}}
```

- `serverInfo.name` 与模式有关：`mmwk_sensor_bridge` 或 `mmwk_sensor_hub`
- `serverInfo.version` 来自当前运行模式对应的对外发布固件构建元数据
- `device hi.name` / `device hi.version` 是 ESP 固件身份的标准字段，应与 `serverInfo.name` / `serverInfo.version` 一致。

认证说明：

- 如果固件配置了 `auth_token`，则 `initialize` 需要在 `params.clientInfo.token` 或 `params.token` 中携带匹配 token
- 不匹配时，服务端返回错误码 `-32001`（`Unauthorized`）

## `tools/call` 响应格式

成功的 `tools/call` 响应如下：

```json
{
  "jsonrpc":"2.0",
  "id":<same id>,
  "result":{
    "content":[
      {"type":"text","text":"<JSON string payload>"}
    ]
  }
}
```

关键点：

- `text` 是 JSON **字符串**，不是嵌套 JSON 对象
- 载荷结构会因工具、模式和 action 不同而变化

## 服务端通知

服务端主动推送格式：

```json
{"jsonrpc":"2.0","method":"notifications/message","params":{"level":"info","data":{...}}}
```

这类消息来自运行时事件（传感器、升级、协议透传等）。`params.data` 可能是：

- 已解析 JSON 对象
- 无法解析为 JSON 时的原始字符串

## 工具可用性矩阵

| Tool | 是否出现在 `tools/list` | BRIDGE | HUB | 说明 |
|---|---|---|---|---|
| `radar` | BRIDGE: Yes, HUB: No | Yes | Yes | HUB 中隐藏，但仍可直接调用 |
| `record` | BRIDGE: Yes, HUB: No | Yes | Yes | HUB 中隐藏 |
| `uart_data` | BRIDGE: Yes, HUB: No | Yes | Yes | UART 分块 OTA 控制；HUB 中隐藏 |
| `hub` | BRIDGE: No, HUB: No | No | Yes | HUB 运行时专用工具 |
| `device` | BRIDGE: Yes, HUB: No | Yes | Yes | 不同模式下 action 行为不同 |
| `network` | BRIDGE: Yes, HUB: No | Yes | Yes | HUB 中隐藏 |
| `help` | BRIDGE: Yes, HUB: Yes | Yes | Yes | HUB 发现入口 |
| `fw` | BRIDGE: Yes, HUB: No | Yes | Yes | 固件目录管理 |
| `catalog` | BRIDGE: Yes, HUB: No | Yes | Yes | IoT 端点注册表发现 |
| `entity` | BRIDGE: Yes, HUB: No | Yes | Yes | 标准实体管理 |
| `adapter` | BRIDGE: Yes, HUB: No | Yes | Yes | 标准适配器管理 |
| `scene` | BRIDGE: Yes, HUB: No | Yes | Yes | 标准场景管理 |
| `policy` | BRIDGE: Yes, HUB: No | Yes | Yes | 标准策略管理 |
| `raw_capture` | BRIDGE: Yes, HUB: No | Yes | Yes | 扩展原始数据采集管理 |

## 工具细节（运行时行为）

### `radar`

`action` 枚举：`ota`、`flash`、`reconf`、`cfg`、`status`、`switch`、`raw`、`debug`、`version`

#### `action=ota`

必填：

- `base`
- `firmware`

可选：

- `config`
- `version`
- `force`
- `prog_intvl`

HUB 额外解析：

- `fw_topic`
- `cert_url`

#### `action=flash`

必填：

- `firmware_size`

可选：

- `config_size`
- `chunk_size`
- `prog_intvl`

BRIDGE 额外支持：

- `reboot_delay`：刷写成功后延迟重启秒数

#### `action=reconf`

运行时雷达契约更新。它会保留当前雷达固件二进制，只修改启动期望以及可选的运行时 cfg 选择，不会再次刷写 firmware。

必填：

- `welcome`

可选：

- `verify`
- `version`（当 `verify=true` 时必填）
- `cfg_action`（`keep` | `replace` | `clear`，默认 `keep`）
- `config_size`（当 `cfg_action="replace"` 时必填）
- `chunk_size`（可选，用于 cfg 分块上传）

契约说明：

- 这是 bridge-only 的运行时重配置；host mode is rejected。
- `cfg_action=keep` 保留当前持久化的运行时 cfg 路径。
- `cfg_action=replace` 需要后续 `uart_data` 发送配置分块，并以 `action: "reconf_done"` 结束。
- `cfg_action=clear` 会清除持久化的运行时 cfg override，回退到正常的固件默认 cfg 来源。
- 与 `action=flash`、`action=ota` 不同，`action=reconf` 不会传输或替换雷达固件二进制。

#### `action=cfg`

读取当前雷达 cfg。

可选：

- `gen`（boolean，默认 `false`）

契约说明：

- 不传 `gen` 或 `gen=false` 时，返回当前实际生效的 file cfg 文本。
- 所谓“当前实际生效的 file cfg”，是指当前选中的运行时 override cfg；如果没有 override，则读取 firmware metadata 里的默认 cfg。
- `gen=true` 表示只请求 hub 运行时生成的 cfg。
- BRIDGE 会拒绝 `gen=true`；不会回退到 file cfg。
- 成功返回的 payload 是 `{ "cfg": "...full radar cfg text..." }`。
- 缺失、不可读、为空或其他不可用的 cfg 目标都属于硬错误。

#### `action=status`

可选控制参数：

- `set: "start" | "stop"`
- `mode: "auto" | "host"`（当 `set="start"` 时使用）

模式契约：

- 带 `mode` 的 `set="start"` 是当前雷达服务的一次性启动请求。
- 它不会改写持久化的 `device.startup` 默认模式。
- BRIDGE 接受 `auto` 和 `host`。
- HUB 只支持 `auto`，并会拒绝 `host`。

如果未设置 `set`，则返回当前服务状态。

未设置 `set` 时，返回结果至少包含：

- `state`：`running` | `stopped` | `starting` | `updating` | `error`
- `details`（可选）：结构化的启动/运行失败详情，仅在 `state=error` 时出现
  - `kind`
  - `stage`
  - `message`
  - `error_code`
  - `error_name`
  - `expected_welcome`
  - `expected_version`

兼容性约定：

- 这里的“启动 CLI/welcome 输出”指雷达启动阶段的任意非空文本；它可能是多行，不能被当作固定 banner 模板。
- 如果 `welcome=true`，但在超时窗口内没有任何启动 CLI/welcome 输出，实现应保持 `state=error`，并返回 `details.kind = startup_failed`。

#### `action=switch`

必填：

- `index`

可选：

- `persist`（boolean，默认 `false`）

契约说明：

- `persist=true` 表示请求持久化地切换默认固件。
- `persist=true` 会走 UART update/flash 路径；成功后，所选 catalog 条目会变成新的默认固件。
- `persist=false` 表示请求一次性的运行时切换。
- 当 `persist=false` 且目标正好是当前默认条目时，服务会回到普通的 default-flash 启动路径。
- 当 `persist=false` 且目标是非默认条目时，只有当前 profile 报告 `fw.switch.temp=true` 时，服务才会走临时 SPI 启动路径。
- 如果目标已经等于当前正在运行的固件，且 `persist=false`，服务会直接返回成功，并给出 `changed=false`，不会做任何事。
- 如果目标已经等于当前正在运行的固件，但调用方仍设置 `persist=true`，服务仍按“持久化默认固件切换”的契约处理；只有当目标已经同时是默认条目和运行条目时，才会变成 no-op。
- 当前 profile 的切换能力通过 `device hi.fw.switch` 和 `mgmt.radar_runtime.fw.switch` 对外报告。
- BRIDGE 家族当前报告 `fw.switch.persist=true`、`fw.switch.temp=false`。
- HUB 家族当前报告 `fw.switch.persist=false`、`fw.switch.temp=false`。
- 由于当前对外 profile 都报告 `fw.switch.temp=false`，不要假定运行时 SPI 临时切换已经可用。对 xWRL6432 家族尤其如此，因为它的临时启动路径仍未完成验证。
- 成功返回的 payload 包含 `action`、`index`、`persist`、`changed`。

#### `action=version`

BRIDGE 和 HUB 均已实现。

#### `action=raw`

设置模式（存在 `enabled` 时）：

- `enabled`
- `uri`（可选；如果省略或与设备 `mqtt_uri` 相同，则复用共享 MQTT client）

BRIDGE 和 HUB 都使用固定的 raw topic：

- 运行时始终派生 `mmwk/{mac}/raw/data` 和 `mmwk/{mac}/raw/resp`
- 在 host 模式下，运行时还会派生 `mmwk/{mac}/raw/cmd`
- 在 bridge/auto 模式下，MQTT raw 平面仍然只出不进，因此不会暴露 `raw_cmd_topic`
- `enabled=true` 时显式传入 `data_topic` / `resp_topic` / `cmd_topic` 会被拒绝

各 topic 的含义：

- `data_topic`：镜像雷达 DATA UART 路径的原始字节，通常保存为 `data_resp.sraw`
- `resp_topic`：来自 `on_cmd_data` 的启动 trim 后命令口输出，`cmd_resp.log` 会从第一个 printable ASCII 字节开始
- `on_cmd_resp` 和 `on_radar_frame` 是应用层回调，必须与 raw 采集分离
- `cmd_topic`：可选的雷达 CMD UART 输入 topic，仅在 host 模式下可用，与 MCP 交互 topic `mmwk/{mac}/device/cmd` 不同

BRIDGE 专属扩展：

- `uart_enabled`：是否将 `RADAR_SVC_EVT_SENSOR_DATA` 通知同时转发到 UART

查询模式（无 `enabled` 时）：

- 返回当前 raw 配置，至少包含 `enabled`

#### `action=debug`

统一调试面，用于运行时诊断。

子操作（`op`）：

- `set`：需要 `packets` 和 `frames`
- `get`：返回当前调试开关
- `snapshot`：返回数据路径计数器
- `reset`：清零诊断计数

持久化说明：

- 调试开关仅作用于运行时，不持久化；重启后恢复默认值

### `fw`

- `action=info`：无额外参数
- `action=list`：无额外参数
- `action=list` 返回一个固件目录数组。
- 每个条目都包含 `index`、`name`、`version`、`config_name`、`source`、`path`、`size`、`default`、`running`。
- `default=true` 表示当前持久化默认固件条目。
- `running=true` 表示当前这次雷达会话正在运行的、且来自 ESP 管理 catalog 的条目。
- `action=set`：必填 `index`
- `action=set` 是“持久化默认固件切换”的别名。
- `action=set` 等价于 `radar action=switch` 且 `persist=true`。
- 如果请求的 index 已经同时是当前默认条目和当前运行条目，服务会返回成功，并给出 `changed=false`。
- 否则，服务会走 UART update/flash 路径；成功后，所选 index 会变成新的默认条目。
- `action=set` 成功返回的 payload 包含 `action`、`index`、`persist`、`changed`。
- `action=del`：必填 `index`
- 当前正在运行的条目不能删除。
- 默认条目 / factory 条目的保护仍由 firmware manager 负责，调用方不能假定任意 catalog 条目都可删除。
- `action=download`：需要 `source`、`name`、`version`、`size`

### `record`

- `action=start`：`uri` 为上传目标
- `action=stop`：无额外参数
- `action=trigger`：可选 `event` 和 `duration_sec`

模式差异：

- HUB 若省略 `event`，默认 `"MANUAL"`
- BRIDGE 若省略 `event`，则保持为空

### `hub`（仅 HUB 固件）

必需字段：

- `sensor`，取值为 `fall|presence|vs|tracker|zone|gate|hotplace`

常见可选字段：

- `sensitivity`
- `empty_delay_ms`
- `zid`
- `gid`
- `boundary`

如果在 BRIDGE 固件上调用 `hub`，会返回 `"Unknown tool"`。

### `device`

Schema 中的 action：

- BRIDGE：`startup`、`agent`、`heartbeat`、`hi`、`reboot`
- HUB：`startup`、`agent`、`heartbeat`、`hi`

#### `action=hi`

- 返回设备身份和状态载荷
- ESP 固件身份字段以 `name` 和 `version` 为准
- 不再返回 `esp_fw` 和 `esp_fw_version`；请统一读取 `name` / `version`
- `startup_mode` 返回当前保存/配置的默认模式
- `supported_modes` 返回当前 profile 支持的启动模式列表
- BRIDGE 运行时还会返回：
  - `radar_fw`、`radar_fw_version`、`radar_cfg`
  - `fw.default`、`fw.running`、`fw.switch`、`fw.mode`
  - `mqtt_uri`、`client_id`、`cmd_topic`、`resp_topic`
  - `mqtt_en`、`uart_en`、`raw_auto`
  - `raw_data_topic`、`raw_resp_topic`
  - bridge 在 `startup_mode=host` 时还会返回 `raw_cmd_topic`
- `fw.default` 和 `fw.running` 都是对象，包含 `source`、`index`、`name`、`version`、`config`
- `fw.default` 表示保存下来的持久化默认条目；`fw.running` 表示当前会话真实运行中的条目
- `fw.switch` 包含当前 profile 门控出来的切换能力标志 `persist` 和 `temp`
- `fw.mode` 表示当前雷达会话的启动路径：`flash`、`uart`、`spi`、`host`
- 旧字段 `radar_fw`、`radar_fw_version`、`radar_cfg` 仍然保留，它们与 `fw.running` 对齐

profile 能力契约：

- BRIDGE 报告 `supported_modes: ["auto", "host"]`
- HUB 报告 `supported_modes: ["auto"]`
- BRIDGE 当前报告 `fw.switch.persist=true`、`fw.switch.temp=false`
- HUB 当前报告 `fw.switch.persist=false`、`fw.switch.temp=false`

#### `action=startup`

- `mode: "auto" | "host"`，用于持久化启动模式

启动契约：

- `startup_mode` 表示当前保存/配置的默认模式
- BRIDGE 接受 `auto` 和 `host`
- HUB 只支持 `auto`
- 如果 HUB 在旧持久化状态里发现 `host`，初始化阶段会先修复为 `auto`，再对外暴露 `device hi` / `mgmt.device`
- `raw_auto` 与启动所有权独立，它只控制 raw 平面的自动启动

#### `action=heartbeat`

- `interval`
- `fields`

BRIDGE 和 HUB 都支持 `fields` 数组转换。

#### `action=agent`

- 支持通过 NVS 读写 `mqtt_en`、`uart_en`、`raw_auto`
- 当 NVS 里缺失这些 key 时，BRIDGE 默认 `mqtt_en=1`、`raw_auto=1`
- 当 NVS 里缺失这些 key 时，HUB 默认 `mqtt_en=0`、`raw_auto=1`
- 这些都只是读取时的 fallback；系统不会在首次启动时把推导出的默认值自动写回 NVS
- 如果未提供写入字段，则返回当前 agent 配置

#### `action=reboot`

- 仅 BRIDGE 支持

### `network`

Schema actions：`config`、`prov`、`ntp`、`mqtt`、`status`、`diag`

- `action=config`：`ssid`、`password`
- `action=prov`：`enable`
- `action=mqtt`：支持 `cid`、`mqtt_uri`、`mqtt_user`、`mqtt_pass`、`cmd_topic`、`resp_topic`
- `action=ntp`：支持 `server`、`tz_offset`、`interval`
- `action=status`：返回 `state`、`sta_ip`、`ip_ready`、`prov_wait_remaining_sec`、`led_state`

其中：

- `state`：`initializing` | `connecting` | `retry_backoff` | `connected` | `prov_waiting` | `failed`
- `sta_ip`：当前运行态 STA IP；未就绪时为 `0.0.0.0`
- `ip_ready`：标准化网络就绪位；只有设备拿到可用的运行态 STA IP 时才为 `true`

标准 ready 语义是严格的：只有 `state=connected` 且 `ip_ready=true` 才能继续执行主流程。

- `action=diag`：返回诊断字段 `state`、`retry_count`、`max_retry`、`retry_backoff_ms`、`last_disconnect_reason_code`、`last_disconnect_reason_name`、`terminal_failure`、`failure_source`

其中 `failure_source` 取值为 `none`、`retry_exhausted`、`manual_provisioning`

### `help`

- 返回命令摘要和文档 URL
- 响应字段包括 `commands`、`mode`、`url`、`format`

### `uart_data`

BRIDGE 中会出现在 `tools/list` 且可调用；HUB 中不出现在 `tools/list`，但仍可按名称调用。

支持两类形式：

1. 分块上传：
- `file`
- `seq`
- `data`

2. 控制：
- `action: "complete"`、`"cancel"` 或 `"reconf_done"`

`uart_data` 既用于 UART 固件分块升级，也用于 `action=reconf` 在 `cfg_action="replace"` 时上传运行时 cfg，然后以 `action: "reconf_done"` 收尾。

### `catalog`

- 无额外参数
- 返回标准端点列表，例如 `entities`、`adapters`、`scenes`、`policies`

### `entity`

- `list`、`get`、`add`、`del`
- `add` 需要 `id`、`type`，可选 `config`、`state`

管理类实体说明：

- `mgmt.radar_runtime` 会暴露当前 `radar_state`，以及嵌套的 `fw.default`、`fw.running`、`fw.switch`、`fw.mode`
- `mgmt.firmware_catalog` 会暴露同一份顶层 `fw` 摘要，以及一个 `firmwares` 数组；数组里的每个条目都带有 `default` 和 `running` 标志

### `adapter`

- `list`、`get`、`set`、`manifest`
- `set` 需要 `id`、`config`

### `scene`

- `list`、`get`、`set`、`active`
- `set` 需要 `id`，可选 `name`、`trigger`、`actions`

### `policy`

- `list`、`get`、`set`、`del`
- `set` 需要 `id`，可选 `name`、`condition`、`enforcement`

### `raw_capture`

- `start`、`stop`、`trigger`
- 语义与 `record` 类似，但面向原始流采集

### Resources API（当前状态）

- `resources/list` 返回静态占位资源：`file://sdcard/logs/latest.log`
- `resources/read` 当前返回模拟 tail 内容，不是真正的文件流

## 传感器事件载荷（HUB 模式）

HUB 传感器激活时，`notifications/message` 中常见字段包括：

- `presence`
- `fall`
- `vs`
- `tracker`
- `zone`
- `gate`
- `hotplace`

## 模式感知契约（统一口径）

当前 schema 与运行时遵循以下规则：

- 工具发现是模式感知的
- BRIDGE 的 `tools/list` 暴露完整工具集
- HUB 的 `tools/list` 默认仅暴露 `help`
- `device.mqtt` 已移除，MQTT 配置统一归入 `network.mqtt`
- `fw` 在 BRIDGE/HUB 都可调用
- `device.agent` 同时支持 `mqtt_en`、`uart_en`、`raw_auto`
- `network.mqtt` 支持 `mqtt_uri`、`mqtt_user`、`mqtt_pass`；`cid`、`cmd_topic`、`resp_topic` 在返回值里仍可观测，但写入时会被拒绝
- `radar.raw` 在两种模式下都使用固定 topic：始终派生 `mmwk/{mac}/raw/data` 和 `mmwk/{mac}/raw/resp`，host 额外派生 `mmwk/{mac}/raw/cmd`，topic override 会被显式拒绝
- `radar.raw` 仅负责配置，诊断功能归入 `radar.debug`
- `radar.debug` 在 BRIDGE/HUB 都可用
- HUB `radar ota` 支持 `fw_topic` 与 `cert_url`

验证：

- 该协议的主机侧集成契约由 bridge 模式和 hub 模式的验收套件共同覆盖。
