# 采集触发助手

`collect.sh --trigger` 是一个 Pure-MQTT raw 数据采集工具，适合那些你明确要求控制面和 raw 采集都不要碰 UART 的场景。

工作目录应为 `cli` 目录：

```bash
cd ./cli
```

下面示例使用 POSIX shell 写法。Windows PowerShell 下使用 `.\collect.ps1 --trigger ...`；这个 pure-MQTT trigger 模式不需要 Bash，只要求已安装 Python 3.10+ 依赖。如果本机有 Bash，`collect.ps1` 会转调 `collect.sh` 以获得完整 wrapper 行为。

## 它负责什么

- 把 `raw_data` 写到 `data_resp.sraw`
- 把启动 trim 后的命令口原始字节写到 `cmd_resp.log`
- 保持运行期控制和 raw 采集都只走 MQTT
- 支持 `trigger=none`、`trigger=radar-restart` 和 `trigger=device-reboot`

它不是严格启动期 `collect -p` 路径的替代品。

## Broker 解析

除非 broker 明确要求其他端口，默认 MQTT 端口应视为 `1883`。

如果没有显式传 `--broker`，同时 `MMWK_SERVER_MQTT_URI` 也没设置，`collect.sh --trigger` 会自动从 server.sh state 里读取 broker。默认读取 `./build_output/local_server/server.env`，也可以用 `--server-state-dir` 指到别的 state dir。

`collect.sh --trigger` 仍然需要 MQTT 路由身份。未 claim 设备传 `--did`；已 claim 路由传 `--prod --oid --cid`。环境变量 fallback 是 `MMWK_DID`、`MMWK_PROD`、`MMWK_OID` 和 `MMWK_CID`。

## 示例

### 1. 中途 late-attach 稳态采集

```bash
./collect.sh --trigger none \
  --broker mqtt://192.168.1.100:1883 \
  --did dc5475c879c0 \
  --data-output ./data_resp.sraw \
  --resp-output ./cmd_resp.log \
  --resp-optional
```

### 2. 复用本地 `server.sh` state

```bash
./config.sh set --server-local \
  --ssid "MyWiFi" \
  --password "MyPass" \
  --port /dev/cu.usbserial-0001 \
  --reboot

./collect.sh --server-state-dir ./build_output/local_server \
  --trigger device-reboot \
  --did dc5475c879c0
```

### 3. 通过 MQTT 触发一段新的启动窗口

```bash
./collect.sh --trigger device-reboot \
  --did dc5475c879c0 \
  --resp-output ./cmd_resp.log \
  --data-output ./data_resp.sraw
```

## 关键参数

- `--did`：DID 路由回退值；除非已经传了 `--cid` 或导出了 `MMWK_CID`，否则必须提供。
- `--prod` / `--oid` / `--cid`：product、租户和 claimed 路由段；`cid` 优先于 `did`。
- `--raw-data` / `--raw-resp`：直接覆盖 raw topic。不传时，`collect.sh --trigger` 会按 `prod/oid/cid/did` 推导；对于 restart/reboot 触发流程，也会优先读取运行时上报的 raw topic。
- `--duration`：采集时长，默认 `10` 秒。
- `--timeout`：MQTT 订阅和控制面准备超时，默认 `10` 秒。
- `--resp-optional`：只允许和 `--trigger none` 搭配，用于 late-attach 稳态窗口里“这次不强求 fresh startup `raw_resp`”的场景。
- `--server-state-dir`：默认是 `./build_output/local_server`；当你没有显式传 broker 时，wrapper 会去读取其中的 `server.env`。

## Trigger 说明

- `trigger=none`：中途 late-attach 的稳态采集；只有这里允许 `--resp-optional`
- `trigger=radar-restart`：先订阅，再通过派生出的 `cmd` / `resp` 控制 topic 重启雷达
- `trigger=device-reboot`：先订阅，再通过 MQTT 发送 `node reboot`；要求 MQTT 控制链路已经可用，而且 `raw_auto=1`
