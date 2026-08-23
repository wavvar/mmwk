# Radar Task Tools

这些 task-oriented wrapper 位于 `run.sh` 之外，为共用采集引擎提供注册表和配置
辅助：

- `config.sh`：统一入口，包含 `init`、`update`、`list`；
- `collect.sh`：把采集参数转发给 `run.sh collect`，其 `--trigger` 形式是高级
  pure-MQTT 助手。

本文使用 POSIX shell 示例。Windows PowerShell 可使用 `config.ps1` 和
`collect.ps1`；前者的 registry/config helper 仍需要 Bash，后者直接调用 Python
采集引擎，不需要 Bash。

## 注册设备

设备注册表是 `<working>/device.yml`。默认依次查找当前目录的 `./collect`、
`~/.mmwk/collect`，都不存在时创建 `./collect`；也可显式传 `--working DIR`。

```bash
./config.sh init --port /dev/ttyUSB1 --working ./collect-lab
./config.sh list --working ./collect-lab
./config.sh update --did 0123456789ab --cfg ./runtime.cfg --working ./collect-lab
```

`init` 完成 UART 配置、重启和 MQTT ready 校验后才写入 registry。记录至少包含
`did`、MQTT URI、HTTP base URL 和更新时间。请把 `list` 输出的身份和 broker URI
显式传给后续采集命令。

## 使用共用采集引擎

本机 UART/USB、远程 MQTT、split 和 attach 都使用同一入口：

```bash
# MINI/PRO UART
./collect.sh --transport uart --port /dev/ttyUSB1 --duration 30

# WDR 原生 USB（不要传 --raw-baud）
./collect.sh --transport usb --port /dev/ttyACM0 --duration 30

# 应用自有 MQTT DATA，只观察不接管
./collect.sh --transport mqtt --mode auto --attach \
  --broker mqtt://broker.example:1883 --did 0123456789ab --duration 30

# 本地控制 + MQTT DATA
./collect.sh --ctrl-transport uart --data-transport mqtt \
  --port /dev/ttyUSB1 --broker mqtt://broker.example:1883 \
  --did 0123456789ab --duration 30
```

host-owned MQTT 采集去掉 `--mode auto --attach` 并使用 `--transport mqtt`。所有
输出路径会在设备状态改变前预留；已有文件需显式 `--overwrite` 才会替换。普通
采集不会接管已存在的 host raw 路由，attach 不发送 cfg、不 start/stop radar，也
不恢复自己没有修改的状态。

如果需要重连触发，请阅读[采集触发助手](collect-trigger.md)；如果需要完整的
身份、QoS、速率和清理规则，请阅读[雷达 DATA 采集](data-collection.md)。

## 开发调试

`config.sh update` 可把 cfg 或固件推送到已注册设备。面向公开发布的 6843/6432
选板、刷写和 wrapper 顺序见[通过 Bridge 开发雷达](bridge-ti-radar-debug.md)。
