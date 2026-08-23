# 雷达 DATA 采集

这是一份面向用户的雷达字节采集指南。先按雷达所在位置选择路径：

1. **本机 host：** MINI/PRO 用 UART，WDR 用原生 USB CDC；
2. **远程设备：** MQTT host；
3. **混合链路：** 本地 UART/USB 发控制，MQTT 承载 DATA；
4. **应用自有：** attach 到已经存在的 MQTT DATA，不接管所有权。

四条路径共用同一个 `collect` 引擎。POSIX 入口是 `./run.sh`，Windows
PowerShell 使用 `./run.ps1`；`collect.sh` 与 `collect.ps1` 转发相同采集参数。
可选的 `collect.sh --trigger` 是高级纯 MQTT 重连流程。

## 本机 host：最短路径

MINI/PRO 通常先用 115200 的 parsed 控制 UART，再把 raw DATA UART 切到
1000000：

```bash
./run.sh collect --transport uart --port /dev/ttyUSB0 \
  --raw-baud 1000000 --duration 30 \
  --data-output ./radar.sraw --resp-output ./radar-cmd.log
```

Windows 使用 `./run.ps1` 和实际 `COM` 端口。采集器先读取实时身份（优先
`did`，旧固件依次回退 `id`、`client_id`），统一转小写，并在改变设备状态前
校验 `--did`。显式 `--cfg` 会在接管前读取；summary 用 `config_source` 记录来源，
采集器不会把显式配置持久化。

本机流程是 parsed 控制、host start、打开 raw、可选 cfg、`sensorStart`、采集
DATA、`sensorStop`、转义和恢复。已有 host raw 路由时，普通采集会在修改设备前
拒绝，不会关闭别的客户端路由；如果要替换运行中的 host 会话，必须先有完整可
恢复的配置/生命周期快照。清理结果分别报告 raw 关闭、radar stop、parsed/config
恢复、所有权恢复和路由恢复。第一次 `Ctrl-C` 执行同样清理；第二次中断打印带
1 秒保护时间的转义恢复序列后退出。

本机物理线是合并字节流，不提供命令/DATA 分帧：`radar.sraw` 可能在 DATA 前后
包含 parsed 命令响应；命令日志保存 parsed 的启动/关闭确认。要得到纯 DATA 文件，
请使用 split 或 MQTT DATA。

## WDR 原生 USB

原生 USB CDC 没有物理 raw 波特率，不要传 `--raw-baud`：

```bash
./run.sh collect --transport usb --port /dev/ttyACM0 --duration 30 \
  --data-output ./wdr.sraw --resp-output ./wdr-cmd.log
```

请依据 `node info` 返回的设备身份选择 WDR，不要依据 `/dev/tty*` 名称猜板型。
只有在本次生成的固件已刷入、实时身份已核对并运行对应套件后，USB 结果才算硬件
证据。

## 远程 MQTT host

设备不在本机时使用 MQTT。host 模式在采集窗口内拥有雷达生命周期：

```bash
./run.sh collect --transport mqtt --broker mqtt://broker.example:1883 \
  --did DEVICE_ID --duration 30 \
  --data-output ./remote.sraw --resp-output ./remote-cmd.log
```

host MQTT 的命令和 parsed 确认在 `raw/cmd`、`raw/resp` 上使用 QoS 1；高速
DATA 在 `raw/data` 上使用 QoS 0 且关闭 retain。MQTT 不保证跨 topic 顺序，客户端
必须按生命周期阶段关联响应，容忍 QoS 1 重复，不能因为某 topic 后发布就假定它
一定在另一 topic 后到达。协议没有 owner token，多个写入者可以共享服务 FIFO，
所以每个客户端要自行关联响应。

账号、broker 密码、设备 key 和证书内容不会写进 summary 或事件日志。ACL 只授予
需要的 `raw/cmd`、`raw/resp`、`raw/data` topic。

## 混合 split：`ctrl=wire,data=mqtt`

本地 UART 无法承载雷达 DATA 速率时，把控制留在本地、DATA 发往 MQTT：

```bash
./run.sh collect --ctrl-transport uart --data-transport mqtt \
  --port /dev/ttyUSB0 --broker mqtt://broker.example:1883 \
  --did DEVICE_ID --duration 30 \
  --data-output ./split.sraw --resp-output ./split-cmd.log
```

采集器会在修改设备前校验两条链路的 DID，先订阅 MQTT 再打开 raw，并保证 DATA
不走有线 UART。显式 split 与 `channel=both` 不同；`both` 是向两个物理适配器
广播，不能解释成 split。

## 应用自有 DATA 与安全 attach

应用可以提供只读的 MQTT DATA 路由：

```bash
./run.sh radar raw runtime --channel mqtt \
  --transport mqtt --did DEVICE_ID
./run.sh collect --transport mqtt --mode auto --attach \
  --broker mqtt://broker.example:1883 --did DEVICE_ID --duration 30
```

`--attach` 要求请求的 DATA 路由已经存在。它会标记路由为 borrowed，不改变所有权，
不发送 cfg，不 start/stop radar，不关闭其他所有者的路由，也不恢复自己没有修改的
状态。auto 只接收 DATA，不等待命令或 parsed 响应；路由不存在时会在修改前失败。

若要在下一次 MQTT 重连后只采集一次：

```bash
./run.sh radar raw reconnect --channel mqtt \
  --transport mqtt --did DEVICE_ID
```

应先订阅，再 arm，并等待结构化确认后再重启。单次 arm 会被下一代 MQTT 连接消费；
第二次重启不会自动重新开始，除非再次 arm。

## Raw 路由控制

统一 radar 工具有两个并列 action：`raw` 与 `record`。

```bash
./run.sh radar raw status -p /dev/ttyUSB0
./run.sh radar raw runtime --channel wire --baud 1000000 --escape +++ -p /dev/ttyUSB0
./run.sh radar raw runtime --ctrl wire --data mqtt --escape +++ \
  --transport uart --port /dev/ttyUSB0 --broker mqtt://broker.example:1883 \
  --did DEVICE_ID
./run.sh radar raw off --channel both --transport mqtt --did DEVICE_ID
```

同一物理通道上的 raw 与 parsed 互斥；另一条 parsed 控制链路仍可保持。默认转义
是 `+++`：先静默 1 秒，发送不带换行的可打印序列，再静默 1 秒。`--escape` 可
指定 1–16 个可打印字符，保护时间固定为 1 秒。

## 输出、覆盖与恢复

默认输出是 `data_resp.sraw` 和 `cmd_resp.log`。可用 `--data-output`、
`--resp-output`、可选的 `--wire-output`、`--summary-output` 指定文件。完整输出
集合会在设备状态改变前检查冲突；除非明确传 `--overwrite`，任一冲突都会使整次
采集失败；路径必须互不相同。summary JSON 包含身份、传输方式、配置来源、源/目标
字节数、可用时的队列高水位、告警及分项清理结果。

采集器不会声称能够对合并有线流进行通用命令/DATA 解复用，因为运行期写入可能
交错。如果清理报告配置、running、路由或所有权恢复失败，应先按报告处理再重新
连接雷达。硬件线恢复时保持静默，发送配置的转义（默认 `+++`）并各等待 1 秒，
然后回到 parsed 115200。

## 速率策略

- 外部 UART DATA 上限为 1000000；
- MINI/PRO DATA 标称 921600，1000000 只有约 8.5% 余量，summary 会提示必须做
  持续丢包计数测试；
- WDR DATA 为 1250000，默认外部 UART 会拒绝无损采集，请使用原生 USB、MQTT 或
  split；`--allow-lossy` 只适合明确接受丢包的诊断，不具备无损验收资格；
- 不存在默认 2 Mbaud。

构建/测试输出只能证明源码和产物有效。硬件证据必须来自本次产物刷写、实时身份
核对和对应板型套件；软件测试结果不等同于硬件证明。

## 录制

录制与 raw 转发独立：

```bash
./run.sh radar record status -p /dev/ttyUSB0
./run.sh radar record config get -p /dev/ttyUSB0
./run.sh radar record config set --json '{"auto_upload":true}' -p /dev/ttyUSB0
./run.sh radar record start --uri file://recording -p /dev/ttyUSB0
./run.sh radar record trigger --event manual --duration-s 10 -p /dev/ttyUSB0
./run.sh radar record stop -p /dev/ttyUSB0
```

`config set` 只接受 `config`，不接受 patch 别名。录制不会打开 raw 路由，改变
raw 路由也不会改变录制配置。
