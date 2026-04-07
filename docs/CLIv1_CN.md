# Wavvar MMWK 标准 CLI 控制协议 V1.0

本文档定义当前 MMWK bridge/hub 主机侧默认使用的标准 CLI JSON 控制协议。它与传输层无关，并且保留与旧 MCP tool 层一致的 service/action 语义。

## 适用范围

- `mmwk_cli` 的默认主机协议
- 与 MCP tool namespace 保持同一组 service 名称：`device`、`radar`、`fw`、`record`、`network`、`catalog`、`entity`、`scene`、`policy`、`help` 以及相关扩展
- 同时适用于 UART 和 MQTT

`mmwk_cli` 现在默认使用这套协议。迁移窗口内，如果调用方省略 `--protocol`，CLI 会打印一次 warning，提示你显式升级到 `--protocol cli`。只有在兼容性回退场景下才需要 `--protocol mcp`。

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
- `radar status --set start --mode auto` 对应 `{"service":"radar","action":"status","args":{"set":"start","mode":"auto"}}`
- `help` 对应 `{"service":"help","args":{}}`

## 与 MCP 的兼容

- 只要显式指定 `--protocol mcp`，MCP 兼容路径仍然可用
- CLI JSON 与 MCP 的业务载荷语义保持对齐
- MCP 兼容规范见 [MCPv1_CN.md](./MCPv1_CN.md)
