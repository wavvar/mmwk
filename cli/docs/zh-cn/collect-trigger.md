# 采集触发助手

`collect.sh --trigger` 是高级 pure-MQTT 助手，适合明确要求控制和采集都不
经过 UART 的场景。普通本机、远程、split 和 attach 工作流请使用共用的
`run.sh collect` 引擎。

该助手直接运行 Python；`collect.ps1 --trigger` 不需要 Bash。请在发布包的
`cli` 目录执行：

```bash
./collect.sh --trigger none --broker mqtt://broker.example:1883 --did DEVICE_ID
```

支持 `none`、`radar-restart` 和 `device-reboot`。它订阅 `raw/data`，host
触发流程还订阅 `raw/resp`；DATA 保留二进制，响应文件保留 MQTT payload 边界。
账号、设备 key 不会写入 summary 或事件日志。

## Late attach

```bash
./collect.sh --trigger none \
  --broker mqtt://broker.example:1883 --did DEVICE_ID \
  --data-output ./data.sraw --resp-output ./resp.log --resp-optional
```

`--resp-optional` 只适用于稳态观察窗口，不是启动/welcome 证据，也不会接管应用
拥有的路由。

## 重连触发采集

```bash
./collect.sh --trigger device-reboot \
  --broker mqtt://broker.example:1883 --did DEVICE_ID \
  --data-output ./data.sraw --resp-output ./resp.log
```

助手先订阅，再 arm `mode=reconnect`，等待结构化确认后请求重启，并且只接受新一代
MQTT 连接后的 DATA。单次 arm 只消费一次，第二次重启必须重新 arm。`radar-restart`
遵循同样的先订阅后控制规则，但不重启设备。

## 参数与安全

- `--did` 或 `--prod --oid --cid` 用于选择 MQTT 路由；环境变量回退为
  `MMWK_DID`、`MMWK_PROD`、`MMWK_OID`、`MMWK_CID`；
- broker 使用非默认 ACL 名称时可用 `--raw-data`、`--raw-resp` 覆盖 topic；
  ACL 应只开放 `raw/cmd`、`raw/resp`、`raw/data`；
- `--duration` 默认 10 秒，`--timeout` 默认 10 秒；
- `--server-state-dir` 可从 `server.env` 提供本地 broker URI；
- 设备状态改变前会预留互不相同的输出路径；只有明确需要替换时才使用
  `--overwrite`。

本机 UART/USB 采集请阅读[雷达 DATA 采集](data-collection.md)，其中包含身份校验、
路由所有权、清理、QoS 和速率限制说明。
