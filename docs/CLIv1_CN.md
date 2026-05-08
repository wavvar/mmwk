# Wavvar MMWK 标准 CLI 控制协议 V1.1

本文档定义当前 MMWK bridge/hub 主机侧默认使用的标准 CLI JSON 控制协议。它与传输层无关，并且保留与旧 MCP tool 层一致的 service/action 语义。

## 适用范围

- `mmwk_cli` 的默认主机协议
- 与 MCP tool namespace 保持同一组 service 名称：`device`、`radar`、`fw`、`record`、`network`、`catalog`、`entity`、`scene`、`policy`、`help` 以及相关扩展
- 同时适用于 UART 和 MQTT

`mmwk_cli` 现在默认使用这套协议。迁移窗口内，如果调用方省略 `--protocol`，CLI 会打印一次 warning，提示你显式升级到 `--protocol cli`。只有在兼容性回退场景下才需要 `--protocol mcp`。

## 协议版本

CLIv1.1 在主机初始化时返回的 `protocolVersion` 为 `control.v1.1`。

## 版本变更

### V1.1

- 统一 CLI 初始化返回的协议版本为 `protocolVersion=control.v1.1`。
- 定义 UART 和 MQTT 上每条请求携带顶层 `key` 的保护机制。
- 定义设备存储 key 后 `node info` 的公开/私有两种视图。
- 定义 `node key status`、`node key set`、`node key clear` 三个 key 管理操作。
- 定义 `node claim`，用于通过 UART/local claim 设备身份，返回 `cid` / `oid` 和非密 MQTT 元数据。
- 保持 `proto list`、`proto status`、`proto manifest` 作为无需 key 的公开协议目录发现接口。

### V1.0

- 初始标准 CLI JSON 信封、请求/响应/事件封包，以及 service/action 兼容命令面。

## 传输与封包

- **UART**：UART0，115200 波特率，按行分隔 JSON 对象
- **MQTT**：向配置好的 `cmd_topic` / `resp_topic` 收发 JSON 对象

每次请求都是单个 JSON 对象；这套协议不定义 batch 数组。

## 信封字段

`type` 取缩写值：

- `req`：请求
- `res`：响应
- `evt`：事件

关联字段使用 `seq`。事件层面只保留 `ts` 这一项时间元数据。

## 请求

```json
{"type":"req","seq":1,"service":"device","action":"hi","args":{}}
```

规则：

- `type` 必须是 `req`
- `seq` 必须是非负整数
- `service` 必须是非空字符串
- `action` 可选；如果带上，必须是字符串
- `args` 可选；如果带上，必须是 JSON 对象
- `key` 可选；如果带上，必须是顶层字符串字段，不要放进 `args`

## Key 保护

出厂态或空 key 设备保持开放。执行 `node key set` 存入非空 key 后，UART 和 MQTT 上的受保护 CLI 请求都必须携带正确的顶层 `"key"` 字段：

```json
{"type":"req","seq":2,"service":"radar","action":"status","key":"YOUR_KEY","args":{}}
```

规则：

- 响应里不会回显 `key`。
- CLIv1 没有 login/session/authenticate 过程；每条受保护请求都携带 `key`。
- 公开请求无需 `key`：`help`、`proto list`、`proto status`、`proto manifest`、`node info` 公开视图，以及 `node key status`。
- 受保护请求包括 radar、network、endpoint、scene、node 修改/敏感读取，已有 key 时的 `node key set`，以及 `node key clear`。
- 受保护请求缺少或带错 `key` 时返回 `unauthorized`。
- 如果公开请求存在私有视图，且调用方带了错误 `key`，返回 `unauthorized`。

`node info` 是公开命令，但有两种视图：

- 未存储 key 时，返回原有完整身份/元数据载荷，并包含 `auth_enabled=false`。
- 已存储 key 且请求未携带 `key` 时，只返回公开身份字段，例如 `name`、`board`、`version`、`id`，以及 `auth_enabled`、`auth_required`。
- 携带正确 `key` 时，返回完整身份/元数据载荷。

key 管理位于 `node key`：

```json
{"type":"req","seq":3,"service":"node","action":"key","args":{"op":"status"}}
{"type":"req","seq":4,"service":"node","action":"key","args":{"op":"set","new_key":"YOUR_KEY"}}
{"type":"req","seq":5,"service":"node","action":"key","key":"YOUR_KEY","args":{"op":"clear"}}
```

- `status` 是公开操作，返回 `enabled` / `required`。
- `set` 在没有 key 时设置初始 key；保护已启用时，只有当前顶层 `key` 正确才会更新 key。
- `clear` 删除已存储 key，并要求当前顶层 `key` 正确。
- 没有 `rotate` 操作；更新 key 由 `set` 完成。

## Node Claim

`node claim` 用来从 claim provider 获取具体设备身份。它和 `network prov` 语义不同：`network prov` 启动 Wi-Fi 配网，`node claim` 获取 `dev.cid`、`dev.oid` 和可选 MQTT 凭据。

请求：

```json
{"type":"req","seq":6,"service":"node","action":"claim","args":{"endpoint":"https://claim.example.com/device","token":"ONE_TIME_TOKEN"}}
```

规则：

- `node claim` 只能通过 UART/local 执行；MQTT transport 返回 `unsupported_transport`。
- `endpoint` 可选，只覆盖本次请求的固件默认 claim 地址。
- `token` 可选，是一次性输入；不会持久化，也不会在响应中回显。
- claim 成功必须同时得到 `dev.cid` 和 `dev.oid`。
- 已 claim 的设备返回 `already_claimed`，错误响应里不带身份字段。
- `token`、`mqtt.user`、`mqtt.pass` 等密钥不会返回。
- `node info` 只在身份存在时显示 `cid` 和 `oid`。
- `node info` 只在设备仍处于工厂状态时显示 `factory: INIT`。

成功响应：

```json
{"type":"res","seq":6,"ok":true,"result":{"claimed":true,"cid":"CID123","oid":"OID456","mqtt":{"cid":"CID123","uri":"mqtt://broker.local"}}}
```

## 成功响应

```json
{"type":"res","seq":1,"ok":true,"result":{"name":"mmwk_sensor_bridge","version":"1.2.2"}}
```

规则：

- `type` 为 `res`
- `seq` 回显请求里的 `seq`
- `ok=true` 时必须带 `result`
- `result` 是该 service 的标准业务载荷对象

## 错误响应

```json
{"type":"res","seq":1,"ok":false,"error":{"code":"not.found","message":"Unknown service"}}
```

当前错误码字符串包括：

- `invalid.json`
- `invalid.req`
- `not.found`
- `invalid.arg`
- `unauthorized`
- `unsupported_transport`
- `already_claimed`
- `provider_unavailable`
- `invalid_response`
- `persist_failed`
- `claim_failed`
- `internal`

## 事件

```json
{"type":"evt","service":"radar","event":"progress","ts":1712040000000,"data":{"status":"flash_progress","progress":50}}
```

规则：

- 事件是设备主动推送的非请求消息
- `service` 标识事件来源命名空间
- `event` 是该命名空间内的事件名
- `ts` 是毫秒级、可被 JSON 精确表示的时间戳
- `data` 是事件载荷对象

## 与现有命令面的兼容关系

这套标准 CLI JSON 协议通过保留与 MCP tool 层一致的 service/action 词汇，保证现有 host 命令面不需要变化。

例如：

- `device hi` 对应 `{"service":"device","action":"hi","args":{}}`
- `radar start --mode auto` 对应 `{"service":"radar","action":"start","args":{"mode":"auto"}}`
- `help` 对应 `{"service":"help","args":{}}`

## 与 MCP 的兼容

- 只要显式指定 `--protocol mcp`，MCP 兼容路径仍然可用
- CLI JSON 与 MCP 的业务载荷语义保持对齐
- MCP 兼容规范见 [MCPv1_CN.md](./MCPv1_CN.md)
