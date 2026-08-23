# 通过 Bridge 开发雷达

这份文档介绍公开 bridge 开发循环：通过 UART 配置，更新配对的雷达固件和 cfg，
再用共用 host/MQTT 引擎采集。Windows 可用 `server.ps1`、`run.ps1`、
`collect.ps1`；注册表配置仍可用 `config.ps1`。采集 PowerShell wrapper 不需要
Bash。

## 选择 bridge 板型

| 雷达系列 | Bridge | 固件配对 |
| --- | --- | --- |
| `IWR6843` / `IWR6843AOP` | `mini` 或 `pro` | `firmwares/radar/iwr6843/` 下 `.bin` + `.cfg` |
| `IWRL6432` | `wdr` | `firmwares/radar/iwrl6432/` 下 `.appimage` + `.cfg` |

固件与 cfg 必须来自同一版本。WDR 高速 DATA 应使用原生 USB、MQTT 或 split；
外部 1000000 波特 UART 无法无损承载 1250000 波特的雷达输出。

## 通用循环

```bash
./server.sh start --serve-dir <radar-artifact-dir>
eval "$(./server.sh env)"
./config.sh init --port <control-port> --working ./collect-lab
./config.sh update --did <DID> --fw <radar.bin> --cfg <radar.cfg> --working ./collect-lab
./run.sh radar status --transport mqtt --broker "$MMWK_SERVER_HOST_IP" --did <DID>
```

用 `config.sh list` 确认 DID 和 broker URI。不要根据 `/dev/tty*` 名称判断板型，
应以实时 `node info` 身份为准。

## 采集

MINI/PRO 本机 UART：

```bash
./collect.sh --transport uart --port <control-port> --raw-baud 1000000 \
  --duration 30 --data-output ./radar.sraw --resp-output ./radar-cmd.log
```

WDR 本机 USB：

```bash
./collect.sh --transport usb --port <native-usb-port> --duration 30
```

远程 MQTT host 或应用自有 attach：

```bash
./collect.sh --transport mqtt --broker mqtt://broker.example:1883 \
  --did <DID> --duration 30
./collect.sh --transport mqtt --mode auto --attach \
  --broker mqtt://broker.example:1883 --did <DID> --duration 30
```

控制与 DATA split：

```bash
./collect.sh --ctrl-transport uart --data-transport mqtt \
  --port <control-port> --broker mqtt://broker.example:1883 --did <DID>
```

引擎会在改变设备前校验身份并预留输出，先订阅再打开 MQTT DATA，并分别报告
路由/config/running/所有权清理。普通采集会拒绝已有 host raw 路由；`--attach`
只借用已有的应用 DATA 路由，不执行生命周期修改；该 auto 路由必须由应用预先创建，
attach 命令本身不会创建它。

完整的 QoS、topic ACL、重连、输出、清理和波特率契约见[雷达 DATA 采集](data-collection.md)。
构建/测试输出只能证明软件；硬件证据必须来自本次产物刷写和实时身份核对。
