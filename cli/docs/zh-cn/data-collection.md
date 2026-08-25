# 雷达 DATA 采集

先按设备位置和雷达所有者选择工作流：

| 场景 | 使用路径 |
| --- | --- |
| MINI/PRO 直连本机 | host UART；不需要网络 |
| WDR 直连本机 | host 原生 USB CDC；不需要网络 |
| 远程设备 | host MQTT |
| 本地控制、远程 DATA | split `ctrl=wire,data=mqtt` |
| 应用已经拥有雷达 | MQTT DATA-only `--mode auto --attach` |

所有路径共用同一个采集引擎。POSIX 使用 `./run.sh` 或 `./collect.sh`；
Windows PowerShell 使用 `./run.ps1` 或 `./collect.ps1`，核心参数相同。

## 1. MINI/PRO 本机 UART

这是 MINI/PRO 最简单的工作流。parsed 控制 UART 从 115200 开始，raw DATA
最高使用 1000000：

```bash
./run.sh collect --transport uart --port /dev/ttyUSB0 \
  --raw-baud 1000000 --duration 30
```

Windows 下命令形状相同：

```powershell
.\run.ps1 collect --transport uart --port COM5 --raw-baud 1000000 --duration 30
```

本机 UART 采集不会配置或等待 Wi-Fi/MQTT。修改设备前，采集器读取 `node info`，
优先使用 `did`，旧固件依次回退 `id`、`client_id`，统一转为小写，并校验可选的
`--did`。身份不一致时，不打开输出，也不修改设备。

采集器会快照 raw 路由、所有权、running 状态和当前雷达 cfg。传 `--cfg FILE`
可仅为本次采集换用另一份 cfg；它在接管前校验，不会持久化，summary 的
`config_source` 记录其路径。不传时来源为 `device:radar.config`。

目标固件和配置已经在 host 模式运行时，可使用 `--mode host --attach`。该路径只为
本次会话打开临时 raw 路由并采集现有 DATA，不发送 cfg，也不执行 sensorStart/
sensorStop；结束后关闭自己打开的路由并核对原有 host 生命周期仍在运行。`--attach`
不能与 `--cfg` 同时使用，也不能接管已经打开的本地 raw 路由。

采集器会从所选 cfg 保留生命周期命令及其参数，包括 WDR 的
`sensorStop 0` 和 `sensorStart 0 0 0 0`。WDR 的 `baudRate` 只用于启动阶段，
运行期采集不会重放它；否则会改变雷达串口速率，却不同步桥接侧串口。

## 2. WDR 本机原生 USB

WDR DATA 是 1250000 baud，因此原生 USB CDC 是本机无损路径：

```bash
./run.sh collect --transport usb --port /dev/ttyACM0 --duration 30
```

原生 USB 没有物理 raw 波特率，不要传 `--raw-baud`。依据实时 `node info`
身份选择板卡，不要根据 `/dev/tty*` 名称或 USB 描述符猜测板型。

## 3. 远程 MQTT host 采集

设备没有直连本机时使用 MQTT：

```bash
./run.sh collect --transport mqtt \
  --broker mqtt://broker.example:1883 --did DEVICE_ID --duration 30
```

使用带鉴权的 TLS 时：

```bash
./run.sh collect --transport mqtt \
  --broker mqtts://broker.example:8883 --mqtt-user USER \
  --mqtt-password PASSWORD --mqtt-ca ./broker-ca.pem \
  --did DEVICE_ID --duration 30
```

host MQTT 在 `raw/cmd` 以 QoS 1 发送命令，在 `raw/resp` 以 QoS 1 接收响应，
高速 DATA 通过 `raw/data` QoS 0。发布一律 retain=false；收到的 retained raw
消息会被忽略。QoS 0 DATA 不设置离线 outbox。

MQTT 不保证不同 topic 之间的顺序。采集器按协议阶段关联响应，保留重复的 QoS 1
响应字节用于审计，但重复消息不会让同一阶段推进两次。raw 服务没有 owner token，
多个写入者可共享 FIFO，因此每个客户端都必须串行化自己的命令并关联自己的响应。

Broker ACL 只开放需要的 `raw/cmd`、`raw/resp`、`raw/data` topic。broker 密码、
MQTT 凭据、设备 key 和证书内容不会写入 summary 或事件日志。

## 4. 有线控制与 MQTT DATA split

本地 UART 便于发命令，但不应承载高速 DATA 时使用 split：

```bash
./run.sh collect --ctrl-transport uart --data-transport mqtt \
  --port /dev/ttyUSB0 --broker mqtt://broker.example:1883 \
  --did DEVICE_ID --duration 30
```

采集器在修改设备前核对实时 wire 身份和 MQTT topic 身份，并先订阅 DATA，再打开
raw。命令和响应留在 wire，DATA 不进入该 wire，而是从 MQTT 写入文件。显式 split
不等于 `channel=both`；`both` 会把所选平面广播到两个适配器。

raw 与 parsed 只在同一物理通道上互斥。另一条 UART、原生 USB 或 MQTT 控制通道
仍可保持 parsed，同时让其他通道运行 raw。

## 5. 应用自有 DATA 与重连采集

应用自有 auto 模式只有 MQTT DATA。应用固件必须已经拥有雷达并提供活动的 MQTT
DATA 路由；下面的 host 命令不会创建该路由：

```bash
./run.sh collect --transport mqtt --mode auto --attach \
  --broker mqtt://broker.example:1883 --did DEVICE_ID --duration 30
```

`--attach` 把路由标记为 borrowed。它不改变所有权、不发送 cfg、不 start/stop
雷达、不关闭路由，也不恢复自己未修改的状态。路由不存在或所有权不匹配时，会在
修改前失败。高级场景也可用 `--mode host --attach` 观察已有 host MQTT DATA
路由，仍遵守相同的非所有者规则。

跨设备重启只采集一次时，使用 reconnect helper。它先订阅，再 arm
`mode=reconnect`，要求收到结构化确认，然后重启，并等待该 arm 在新的设备代际中
变成 runtime 路由：

```bash
./collect.sh --trigger device-reboot \
  --broker mqtt://broker.example:1883 --did DEVICE_ID --duration 30
```

PowerShell 使用 `./collect.ps1 --trigger device-reboot` 和相同参数。arm 最多消费
一次；第二次重启不会再次开始 DATA，除非新的 reconnect arm 已确认。

## 6. 输出与成功标准

未指定输出路径时，引擎创建一组按身份隔离的文件：

```text
collections/<did>/<UTC timestamp>/radar.sraw
collections/<did>/<UTC timestamp>/commands.log
collections/<did>/<UTC timestamp>/summary.json
collections/<did>/<UTC timestamp>/events.jsonl
```

使用显式输出时，`--data-output` 和 `--resp-output` 必须一起传。还可设置
`--summary-output`、`--events-output`、`--wire-output`。所有路径必须不同。完整
集合会在修改设备前一次性预留；任一冲突都会使本次采集失败且不截断文件。
`--overwrite` 先写同目录临时文件，只在最终完成时原子替换每个目标。

`radar.sraw` 是校验后的 DATA，并从雷达 magic
`02 01 04 03 06 05 08 07` 开始；`commands.log` 保存采集命令响应。可选 wire
审计是已观察 raw 传输 payload 的完整合并序列，包括发出的命令以及收到的响应/DATA
chunk。它没有方向或帧分隔符，因此运行期交错后不能做通用解复用。

一次自有路由采集成功时，应同时满足：

- 看到 DATA magic 后才开始 duration 计时；
- `data_bytes` 大于零，`duration_s` 不包含 setup 和 cleanup；
- 固件有报告时，检查源/目标字节、CRC、队列高水位和 drop 计数；
- `cleanup.state_restored` 为 true，并分别检查 config、lifecycle、route、
  ownership 的恢复结果。

attach 还应满足 `borrowed_route=true`；这里的成功表示 borrowed 路由仍存在，不表示
采集器拥有或恢复过它。

## 7. 清理与手工恢复

普通自有采集遇到已打开的 runtime raw 路由会拒绝执行，不会关闭其他客户端会话。
如果没有完整可恢复的 config 和生命周期快照，也不会替换运行中的 host 会话。每个
成功 mutation 都会在下一步前登记，清理只逆转本次采集拥有的 mutation。

正常关闭时，采集器会在 escape 前后两个 guard 窗口持续读取，从而排空 WDR 的末尾
DATA，并在 host ingress 保持静默时避免原生 USB 反压。

第一次 `Ctrl-C` 执行正常清理。若清理本身再次被中断，先让 wire 静默 1 秒，发送
不带换行的可打印 escape，再静默 1 秒，然后以 115200 恢复 parsed 控制。默认
escape 是 `+++`；`--escape` 接受 1–16 个可打印字符，但前后 1 秒 guard 固定。

如果 summary 显示 config、lifecycle、route、ownership、parsed 或 baud 恢复失败，
应先明确恢复该项，再开始另一会话。

## 8. UART 限制与证据

- 外部 raw UART 上限为 1000000，不存在默认 2 Mbaud；
- MINI/PRO DATA 标称 921600，1000000 只有 8.5% adapter margin，因此告警和
  drop 计数是验收必查证据；
- WDR DATA 为 1250000，默认拒绝把外部 UART 当作无损路径；请使用原生 USB、
  MQTT 或 split。`--allow-lossy` 只用于诊断，并明确失去无损验收资格。

代码审查、单元测试和本地构建只属于软件证据。硬件证明必须刷入本次会话构建或选择
的产物，核对实时 DID/board，并运行对应物理设备套件。
