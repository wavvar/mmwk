# MMWK RAW

`mmwk_raw.sh` 是一个 Pure-MQTT raw 数据采集工具，适合那些你明确要求控制面和 raw 采集都不要碰 UART 的场景。

工作目录应为 `mmwk_cli` 目录：

```bash
cd ./mmwk_cli
```

## 它负责什么

- 把 `raw_data` 写到 `data_resp.sraw`
- 把启动 trim 后的命令口原始字节写到 `cmd_resp.log`
- 保持运行期控制和 raw 采集都只走 MQTT
- 支持 `trigger=none`、`trigger=radar-restart` 和 `trigger=device-reboot`

它不是严格启动期 `collect -p` 路径的替代品。

## Broker 解析

除非 broker 明确要求其他端口，默认 MQTT 端口应视为 `1883`。

如果没有显式传 `--broker`，同时 `MMWK_SERVER_MQTT_URI` 也没设置，`mmwk_raw.sh` 会自动从 server.sh state 里读取 broker。默认读取 `./output/local_server/server.env`，也可以用 `--server-state-dir` 指到别的 state dir。

`mmwk_raw.sh` 仍然需要设备 id。请显式传 `--device-id`，或者自己导出 `MMWK_DEVICE_ID`。

## 示例

### 1. 中途 late-attach 稳态采集

```bash
./tools/mmwk_raw.sh --trigger none \
  --broker mqtt://192.168.1.100:1883 \
  --device-id mmwk_demo_01 \
  --data-output ./data_resp.sraw \
  --resp-output ./cmd_resp.log
```

### 2. 复用本地 `server.sh` state

```bash
./tools/mmwk_cfg.sh --server-local \
  --ssid "MyWiFi" \
  --password "MyPass" \
  --port /dev/cu.usbserial-0001 \
  --reboot

./tools/mmwk_raw.sh --server-state-dir ./output/local_server \
  --trigger device-reboot \
  --device-id mmwk_demo_01
```

### 3. 通过 MQTT 触发一段新的启动窗口

```bash
./tools/mmwk_raw.sh --trigger device-reboot \
  --device-id mmwk_demo_01 \
  --resp-output ./cmd_resp.log \
  --data-output ./data_resp.sraw
```

## Trigger 说明

- `trigger=none`：中途 late-attach 的稳态采集；只有这里允许 `--resp-optional`
- `trigger=radar-restart`：先订阅，再通过 MQTT 重启雷达
- `trigger=device-reboot`：先订阅，再通过 MQTT 发送 `device reboot`；要求 MQTT 控制链路已经可用，而且 `raw_auto=1`
