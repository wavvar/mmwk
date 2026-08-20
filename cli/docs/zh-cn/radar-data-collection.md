# 雷达数据采集

公共接口只有一个 `radar` 工具：

- `radar raw` 控制字节路由；
- `radar record` 控制录制。

不再使用开机 raw 开关、独立 raw 工具或独立的 `bridge` 命令。

## 先选模式

雷达直接接在采集电脑上时，优先使用 host 模式。它可以走 UART 或原生 USB，
不需要配网、Wi‑Fi 或 MQTT；由主机发送配置、`sensorStart`、运行期命令和
`sensorStop`。

应用固件必须继续负责雷达配置和生命周期时，使用 auto 模式。auto raw 只是
MQTT DATA 旁路，只读，不提供命令或 parsed 响应。

设备不在本机时使用 MQTT host。两条链路都可用时可以分工，例如
`ctrl=wire, data=mqtt`：本机 UART/USB 发命令，MQTT 承载高速 DATA。

## 本机 host 采集

最短路径：

```bash
./run.sh collect --transport uart --port /dev/ttyUSB0 \
  --raw-baud 1000000 --duration 30 \
  --data-output ./radar.sraw --resp-output ./radar-cmd.log
```

Windows 使用 `run.ps1` 和实际 `COM` 端口。初始 parsed 控制速率仍是
`115200`；`--raw-baud` 只用于之后的 raw DATA。原生 WDR USB CDC 没有物理
波特率，不要传 `--raw-baud`：

```bash
./run.sh collect --transport usb --port /dev/ttyACM0 --duration 30
```

脚本会先读取设备身份（优先 `did`，旧固件依次回退 `id`、`client_id`），校验
可选的 `--did`，进入 host，打开 wire raw，并在发送 `sensorStart` 后立即开始
采集窗口。正常退出或第一次 `Ctrl-C` 会恢复 parsed 控制。

本机 host 的物理线没有独立的命令/数据分帧，因此 `radar.sraw` 是合并后的原始
线流，雷达命令响应可能出现在 DATA 块之前或之后；`radar-cmd.log` 保存的是
parsed 的启动/关闭确认。如果必须得到纯 DATA 文件，请使用 auto MQTT，或使用
下面的 `data=mqtt` 双通道采集。

同一个物理通道上的 raw 与 parsed 互斥。raw 打开前可以看到 parsed JSON；进入
raw 后该通道只传原始字节。若另有 MQTT 或另一条 UART/USB 路由，仍可用它发
命令。

统一采集器也支持推荐的双通道路径：

```bash
./run.sh collect --ctrl-transport uart --data-transport mqtt \
  --port /dev/ttyUSB0 --broker mqtt://192.168.1.100:1883 --did DEVICE_ID \
  --duration 30 --data-output ./radar.sraw --resp-output ./radar-cmd.log
```

显式双通道参数与 `--transport` 互斥。采集器会先订阅 MQTT DATA，再打开有线
raw，因此不会把高速 DATA 镜像到外部 UART；此时 `data-output` 只包含 MQTT
DATA，`resp-output` 保存本地有线响应。

## Raw 路由命令

查询状态：

```bash
./run.sh radar raw status -p /dev/ttyUSB0
```

打开或关闭：

```bash
./run.sh radar raw runtime --channel wire --baud 1000000 --escape +++ -p /dev/ttyUSB0
./run.sh radar raw runtime --ctrl wire --data mqtt --escape +++ \
  --transport uart --port /dev/ttyUSB0 --broker mqtt://192.168.1.100:1883 --did DEVICE_ID
./run.sh radar raw reconnect --channel mqtt --transport mqtt --did DEVICE_ID
./run.sh radar raw off --channel both --transport mqtt --did DEVICE_ID
```

`channel=wire|mqtt|both` 是全双工简写；显式 `ctrl`、`data` 可以把命令/响应
与雷达 DATA 分开。允许多个写入者，服务 FIFO 按入队顺序处理，但协议不提供
owner 或命令级响应关联。

默认转义为 `+++`：先保持静默 1 秒，发送不带回车换行的三个字节，再静默 1 秒。
可用 `--escape` 指定自定义可打印序列，保护时间固定为 1 秒。转义只关闭
wire；独立 MQTT 路由继续工作。

## Auto 纯 DATA 采集

auto 由应用拥有雷达，外部只接收 MQTT DATA：

```bash
./run.sh radar raw runtime --channel mqtt --transport mqtt --did DEVICE_ID
./run.sh collect --transport mqtt --mode auto --attach --did DEVICE_ID \
  --broker mqtt://192.168.1.100:1883 --duration 30
```

要在下一次 MQTT 重连后开始一次采集：

```bash
./run.sh radar raw reconnect --channel mqtt --transport mqtt --did DEVICE_ID
```

auto raw 只有 `raw/data`，没有 `raw/cmd`、`raw/resp`、CLI JSON、日志或 parsed
帧。`mode=reconnect` 消费一次后自动清除，不是永久开机开关。

## MQTT 与 QoS

host MQTT 的 `raw/cmd`、`raw/resp` 使用 QoS 1，`raw/data` 使用 QoS 0 且不保留。
auto MQTT 只有 QoS 0 的 `raw/data`。MQTT 消息边界不是雷达帧边界，解析前应按
到达顺序拼接 DATA 字节。

## 波特率限制

- MINI/PRO DATA 标称 `921600`；外部 UART `1000000` 余量很小，需要持续实机
  丢包验证。
- WDR DATA 为 `1250000`；当前 CP2102 的 `1000000` 无法无损承载。
- WDR 高速 DATA 优先使用原生 USB CDC 或 MQTT。
- WDR 若必须走 UART，需要经过验证的 2–3 Mbaud 转换器；bridge 不默认 2 Mbaud，
  当前外部 UART 上限按 1 Mbaud 处理。

只有明确接受丢包的诊断场景才使用 `--allow-lossy`；summary 不代表无损结果。

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

录制不会打开 raw 路由，改变 raw 路由也不会改变录制配置。
