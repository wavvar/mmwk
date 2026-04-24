# 本地 `server.sh` + `mmwk_cli.sh` Wi-Fi 刷机与 5 分钟采集示例

## 原始语义契约

- `raw_resp = startup-trimmed command-port output from on_cmd_data`
- `raw_data = raw data-port bytes from on_radar_data`
- `on_cmd_resp` 是应用层 command response，与 raw capture 不同。
- `on_radar_frame` 是应用层 frame callback，与 raw capture 不同。

## 1. 目标与约束

本示例演示如何：

1. 用 `./mmwk_cli/server.sh` 在本机提供本地 MQTT 和 HTTP。
2. 用 `./mmwk_cli/mmwk_cli.sh` 通过 Wi-Fi/MQTT 控制设备，并让设备通过本地 HTTP 下载雷达固件与配置。
3. 连续采集 300 秒以上的 `raw_data` 和 `raw_resp`。

本次验证遵守了以下约束：

- 未修改设备默认启动模式。
- `raw_resp` 按“来自 `on_cmd_data` 的启动 trim 后命令口输出”处理。
- `welcome=true` 按“雷达启动阶段出现任意非空字符串即可成立”处理，不要求固定字符串，且允许多行。

## 2. 本次输入

以下命令假设当前工作目录为 `mmwk` 项目根目录，也就是同时包含 `firmwares/` 和 `mmwk_cli/` 的那个目录。

文中约定：

- `<artifact-dir>`
  - 演示固件目录。在当前 main 分支验证里，这里使用的是 `./firmwares/radar/iwr6843/vital_signs`。
- `<demo-output-dir>`
  - 保存命令文件、日志和采集结果的演示输出目录。

下文使用的示例值：

- 串口：`/dev/cu.usbserial-0001`
- 设备接入 Wi-Fi 后的 IP：`192.168.4.8`
- 主机 IP：`192.168.4.9`
- 本地 MQTT：`mqtt://192.168.4.9:1883`
- 本地 HTTP：`http://192.168.4.9:8380/`
- Wi-Fi SSID：`ventropic`
- Wi-Fi 密码：`ve12345678`
- MQTT client id：`dc5475c879c0`
- 设备控制 topic：
  - `mmwk/dc5475c879c0/device/cmd`
  - `mmwk/dc5475c879c0/device/resp`
- 原始数据 topic：
  - `mmwk/dc5475c879c0/raw/data`
  - `mmwk/dc5475c879c0/raw/resp`
- 雷达固件：`<artifact-dir>/vital_signs_tracking_6843AOP_demo.bin`
- 雷达配置：`<artifact-dir>/vital_signs_AOP_2m.cfg`

在你自己的运行里，不要假设上面的 MQTT id 和 topic 一定相同。执行完 `network mqtt` 并重启后，请先用 `device hi --transport mqtt` 读取实际的 `client_id`、控制 topic 和 raw topic，再把这些值替换到后续 MQTT 命令中。

本文档里的严格启动期流程仍以 `collect` 作为官方命令。如果你需要一个挂在 `mmwk_cli.sh` 外部、并且控制面和 raw 面都只走 pure MQTT 的 helper，请在 `mmwk_cli` 目录下使用 `./tools/mmwk_raw.sh`。如果你需要先下发 Wi-Fi / MQTT 设置，请先使用 `./tools/mmwk_cfg.sh`。

除非你的 broker 明确要求其他端口，默认 MQTT 端口应视为 `1883`。本文里更早的 `1884` 例子只是历史上的本地 server 示例残留，不是 CLI 或 `server.sh` 的默认值。

在 `mmwk_cli` 目录下，这个外挂 helper 支持：

```bash
./tools/mmwk_raw.sh --trigger none
./tools/mmwk_raw.sh --trigger radar-restart
./tools/mmwk_raw.sh --trigger device-reboot
```

这个 helper 的控制面和 raw 采集都保持 pure MQTT。需要先下发 Wi-Fi / MQTT 设置时，请先使用 `./tools/mmwk_cfg.sh`，再让 `./tools/mmwk_raw.sh` 复用对应 broker 或 `server.sh` state。

## 3. 关键说明与参数含义

### 3.1 `server.sh`

- `run`
  - 前台常驻模式，适合专用终端或自动化会话。
- `--state-dir`
  - 保存 `pid`、`env`、`mosquitto.log`、`http.log` 等运行状态文件。
- `--serve-dir`
  - 本地 HTTP 对外提供文件的目录。本示例写作 `<artifact-dir>`。
- `--host-ip`
  - 设备访问主机时使用的地址。本示例固定为 `192.168.4.9`。
- `--mqtt-port`
  - 本地 MQTT 监听端口。本示例为 `1883`。
- `--http-port`
  - 本地 HTTP 监听端口。本示例为 `8380`。

### 3.2 `mmwk_cli.sh`

- `network mqtt`
  - 配置 broker URI、client id 以及 MQTT CLI JSON topic。
  - 对于 fresh bridge 设备，`network mqtt` 现在只负责写入 broker / 鉴权设置，而 MQTT topic 身份固定绑定 Wi-Fi STA MAC。
- `device agent --mqtt-en 1 --raw-auto 1`
  - 当 bridge 的 agent key 缺失时，默认值已经是 `mqtt_en=1`、`raw_auto=1`，因此执行 `network mqtt` 并重启就足以建立 MQTT 控制。
  - 但在这次验证里，我们只观察到 fresh baseline 已经报告了 `mqtt_en=1` 和 `raw_auto=1`，并没有单独证明 NVS 中这些 key 是否缺失。
  - 只有在手动 override 或排障时，才需要执行 `device agent --mqtt-en 1 --raw-auto 1`。
- `--transport mqtt`
  - 通过 MQTT 控制设备，而不是通过串口直连 CLI JSON。
- `--broker 192.168.4.9 --mqtt-port 1883`
  - 指向本地 `server.sh` 提供的 broker。
- `--device-id dc5475c879c0`
  - 这里展示的只是示例 MQTT `client_id` / topic id。你自己的运行应以 `device hi --transport mqtt` 返回的值为准。
- `--cmd-topic` / `--resp-topic`
  - 显式指定设备控制 topic，避免默认推导歧义。你自己的运行请使用 `device hi --transport mqtt` 返回的 topic。
- `--base-url http://192.168.4.9:8380/`
  - 让设备从本地 HTTP 服务下载 OTA 文件。
- `--welcome`
  - 声明该固件会输出任意非空启动 welcome 文本。
- `--no-verify`
  - 不要求 welcome 文本必须包含某个固定版本串。
- `collect -p /dev/cu.usbserial-0001`
  - 采集时额外带串口，用于自动发现设备并在开始采集前引导 `radar raw`。
  - CLI 现在还会先等设备重新拿到非零运行时 IP，再 arm MQTT raw capture，以降低 Wi-Fi / MQTT 仍在重连时丢掉启动阶段 `raw_resp` 的概率。
  - 请把它当成严格的启动期采集路径。如果你要把这条路径当作 fresh reboot 或雷达重启窗口的证明，`raw_resp` 必须非空。
- `--resp-optional`
  - 只用于 `radar status` 已经返回 `running` 之后的纯 MQTT late-attach 观察窗口。
  - 在雷达重启、OTA、reconf 或 factory / baseline 恢复后的启动窗口里，不要把 `--resp-optional` 当成启动证明。
- `--reset`
  - 如果设备重启后命令口运行日志短时间内污染了 UART CLI JSON，可以用它拿到干净启动窗口。
  - 一旦 MQTT 控制已经可用，后续命令优先走 MQTT。
- `--data-topic`
  - 订阅雷达 DATA UART 对应的 `raw_data`。
- `--resp-topic`
  - 订阅雷达 CMD UART 对应的 `raw_resp`。

再次强调 topic 分工：
- `mmwk/{mac}/device/cmd` 和 `mmwk/{mac}/device/resp` 是由 `network mqtt` 配置的 MQTT CLI JSON 控制 topic。
- `mmwk/{mac}/raw/data` 和 `mmwk/{mac}/raw/resp` 才是雷达透传输出 topic。
- `mmwk/{mac}/raw/cmd` 是独立的可选雷达输入 topic，只在 host 模式下存在，并且与 `mmwk/{mac}/device/cmd` 不同。
- 在 bridge/auto 模式下，MQTT raw 平面刻意保持“只出不进”，因此采集只需要 `mmwk/{mac}/raw/data` 和 `mmwk/{mac}/raw/resp`。

### 3.3 本次验证中确认的重要现象

- fresh device 的初始状态很关键。
  - 按当前 main，fresh factory image 启动后应表现为 `mqtt_en=1`、`raw_auto=1`、`mqtt_uri` 为空、`state=prov_waiting`、`ip_ready=false`、`sta_ip` 为空。
  - 这意味着对 fresh bridge 来说，真正选择私有/本地 broker 的动作就是执行 `network mqtt` 并重启。
  - 如果设备此时仍然显示公网 broker URI，应视为镜像早于当前 main，先重刷再继续。
- OTA 前的雷达状态仍可能先显示 `updating`。
  - 在当前 main 分支验证里，刚切到 MQTT 后，第一次 `radar status` 仍然返回了 `updating`，即使新的 OTA 还没有发送。
  - 这并没有阻塞后续 OTA。只要 MQTT 控制已经正常，Step 8 之前看到稳定的 `running` 或 `updating` 都可以接受。
- UART CLI JSON 与运行日志可能重叠。
  - 本次验证中，设备重启后如果立即通过 UART 再发 CLI JSON 命令，可能因为命令口上正在输出运行日志而出现 corrupt JSON。
  - 不要对同一个串口并发执行多个 UART 命令。
  - 如果重启后 UART 查询失败，先用 `--reset` 重试一次，或者等 MQTT 就绪后改走 MQTT。
- `radar ota` 的完成时序会随运行而变化。
  - 在 2026-03-19 这次验证里，CLI 先报了 timeout，后续轮询里 `radar status` 仍短暂保持 `updating`，随后才回到 `running`。
  - 在 2026-04-01 的复跑里，CLI 会在 phase 3 末尾自动追加 30 秒 grace，并在 `148.4` 秒时直接返回成功，即使 OTA 阶段的 `raw_resp` 抓取仍然为空。
  - 出现 timeout 时不要立刻重刷，而且无论 CLI 是否直接成功，都要继续走同样的 `radar status = running` ready gate。
- 雷达重启动作需要显式 ready gate。
  - 对 `radar flash`、`radar ota`、`radar reconf`，以及 factory / baseline 恢复后的第一次上电，都要轮询 `radar status`，直到返回 `running`。
  - 不要用固定 sleep 去替代这个 gate。
- 本次环境里，`radar version` 不是可靠的成功判断。
  - 它返回的内容与 `device hi` 相同，而不是独立的雷达版本字符串。
  - 因此应优先用 `radar status = running` 加上 `raw_resp` 中出现启动输出作为刷写成功证明。
- `raw_resp` 是启动 trim 后的命令口采集。
  - 它从第一个 printable ASCII 字节开始，不再保留前导脏字节。
  - 非打印字符、分隔符和截断的 banner 都是正常的。
  - 在当前 main 分支多次验证里，OTA 阶段抓到的 `raw_resp` 可能以 `xWR64xx MMW Demo 03.06.00.00` 开头，也可能直接为空；后续 300 秒采集阶段抓到的内容则可能从截断的 `IWR6843AOP Vital Signs...` banner 一直到更长的 `IWR6843AOP Vital Signs with People Tracking` 命令交互文本。
  - 只要出现任意非空启动输出，就满足 `welcome=true`。

## 4. 经过验证的执行流程

### 步骤 0：启动本地 `server.sh`

命令：

```bash
./mmwk_cli/server.sh run \
  --state-dir <demo-output-dir>/local_server \
  --serve-dir <artifact-dir> \
  --host-ip 192.168.4.9 \
  --mqtt-port 1883 \
  --http-port 8380
```

成功证明：

- `server.sh status` 返回 `MQTT Up   : yes` 和 `HTTP Up   : yes`
- `server.sh env` 返回：
  - `MMWK_SERVER_MQTT_URI=mqtt://192.168.4.9:1883`
  - `MMWK_SERVER_HTTP_BASE_URL=http://192.168.4.9:8380/`
- `<demo-output-dir>/local_server/http.log` 中可看到本地 HTTP 活动

### 步骤 1：串口读取设备基线状态

命令：

```bash
./mmwk_cli/mmwk_cli.sh device hi --reset -p /dev/cu.usbserial-0001
./mmwk_cli/mmwk_cli.sh network status --reset -p /dev/cu.usbserial-0001
```

本次验证得到的 fresh-device 基线：

- 设备型号：`mmwk_sensor_bridge`
- 板型：`mini`
- `mqtt_uri = ""`（尚未配置）
- `mqtt_en = 1`
- `raw_auto = 1`
- `state = prov_waiting`
- `ip_ready = false`
- `sta_ip = ""`

这是一个很关键的 fresh-device 基线：设备仍在等待 Wi-Fi 配网，但 fresh bridge 默认已经保持 `mqtt_en=1` 和 `raw_auto=1`。

### 步骤 2：写入 Wi-Fi 参数

命令：

```bash
./mmwk_cli/mmwk_cli.sh network config \
  --ssid ventropic \
  --password ve12345678 \
  -p /dev/cu.usbserial-0001
```

成功证明：

- 返回 `WiFi credentials saved. Connecting...`

### 步骤 3：写入本地 MQTT 参数

命令：

```bash
./mmwk_cli/mmwk_cli.sh network mqtt \
  --mqtt-uri mqtt://192.168.4.9:1883 \
  -p /dev/cu.usbserial-0001
```

成功证明：

- 返回 `MQTT config updated. Reboot applying...`

重要说明：

- 这一步只负责写入 broker 设置；MQTT topic 身份固定绑定 Wi-Fi STA MAC。
- MQTT `client_id` 现在固定绑定 Wi-Fi STA MAC。重启后请通过 `device hi --transport mqtt` 确认派生出的 `client_id` 和 canonical topic。
- 对 fresh bridge 来说，执行完这一步并重启后，就应能启用 MQTT CLI JSON 控制。

### 步骤 4：针对旧持久化 agent 设置的可选手动 override

命令：

```bash
./mmwk_cli/mmwk_cli.sh device agent \
  --mqtt-en 1 \
  --uart-en 1 \
  --raw-auto 1 \
  --reset \
  -p /dev/cu.usbserial-0001
```

成功证明：

- 返回 `{"status":"success","msg":"Agent config updated"}`

只有当设备沿用了较旧的持久化值，或者你正在排查 MQTT 控制路径被手动关闭的问题时，才需要这一步。对于 fresh bridge 默认值，这一步不应成为必做项。

### 步骤 5：重启设备

命令：

```bash
./mmwk_cli/mmwk_cli.sh device reboot -p /dev/cu.usbserial-0001
```

成功证明：

- 返回 `{"status":"rebooting"}`

### 步骤 6：通过本地 MQTT 再次握手

命令：

```bash
./mmwk_cli/mmwk_cli.sh device hi \
  --transport mqtt \
  --broker 192.168.4.9 \
  --mqtt-port 1883 \
  --device-id dc5475c879c0 \
  --cmd-topic mmwk/dc5475c879c0/device/cmd \
  --resp-topic mmwk/dc5475c879c0/device/resp
```

成功证明：

- `MQTT connected, subscribing to mmwk/dc5475c879c0/device/resp`
- 返回：
  - `ip = 192.168.4.8`
  - `mqtt_uri = mqtt://192.168.4.9:1883`
  - `mqtt_en = 1`
  - `raw_auto = 1`
  - `wifi_rssi = -57`

### 步骤 7：检查 OTA 前的雷达状态

命令：

```bash
./mmwk_cli/mmwk_cli.sh radar status \
  --transport mqtt \
  --broker 192.168.4.9 \
  --mqtt-port 1883 \
  --device-id dc5475c879c0 \
  --cmd-topic mmwk/dc5475c879c0/device/cmd \
  --resp-topic mmwk/dc5475c879c0/device/resp
```

成功证明：

- 能通过 MQTT 返回一个有效的雷达状态。
- 在当前 main 分支验证里，OTA 前这一步实际返回的是 `{"state":"updating"}`。
- 如果你的设备此时已经返回 `{"state":"running"}`，同样是正常的。

### 步骤 8：执行 Wi-Fi OTA 刷写

命令：

```bash
./mmwk_cli/mmwk_cli.sh radar ota \
  --fw <artifact-dir>/vital_signs_tracking_6843AOP_demo.bin \
  --cfg <artifact-dir>/vital_signs_AOP_2m.cfg \
  --welcome \
  --no-verify \
  --ota-timeout 300 \
  --progress-interval 5 \
  --raw-resp-output <demo-output-dir>/ota_cmd_resp.log \
  --transport mqtt \
  --broker 192.168.4.9 \
  --mqtt-port 1883 \
  --device-id dc5475c879c0 \
  --cmd-topic mmwk/dc5475c879c0/device/cmd \
  --resp-topic mmwk/dc5475c879c0/device/resp \
  --base-url http://192.168.4.9:8380/
```

本次验证观察到：

- 设备成功接收 OTA 命令。
- `<demo-output-dir>/local_server/http.log` 记录到了：
  - `GET /vital_signs_tracking_6843AOP_demo.bin HTTP/1.1" 200`
  - `GET /vital_signs_AOP_2m.cfg HTTP/1.1" 200`
- `radar status` 进入 `updating`。
- 进度条在固件阶段后又回到 `0%`，因为进入了配置文件阶段；这在本次验证中是预期行为。
- 在 2026-03-19 这次验证里，OTA 阶段的 `raw_resp` 抓到了 `2` 条消息 / `128` 字节，CLI 最终仍然报了 `OTA timeout`。
- 在 2026-04-01 的复跑里，OTA 阶段的 `raw_resp` 抓取保持为空，但 CLI 在追加 30 秒 phase 3 grace 后，于 `148.4` 秒时直接以 `flash_success` 成功结束。

这说明：

- 本地 HTTP 服务工作正常。
- 设备侧 OTA 确实已经开始。
- 按当前 main，CLI 可能在内建的 phase 3 grace 窗口内直接完成，也可能仍然先 timeout。
- OTA 步骤里的 `raw_resp` 抓取仍然只是 best-effort，即使 CLI 非 timeout 成功，这个文件也可能为空。

### 步骤 9：OTA 后确认 `running`

推荐命令：

```bash
./mmwk_cli/mmwk_cli.sh radar status \
  --transport mqtt \
  --broker 192.168.4.9 \
  --mqtt-port 1883 \
  --device-id dc5475c879c0 \
  --cmd-topic mmwk/dc5475c879c0/device/cmd \
  --resp-topic mmwk/dc5475c879c0/device/resp
```

本次验证观察到：

- 在 2026-03-19 的 timeout 场景里，timeout 刚发生后，设备仍然返回 `{"state":"updating"}`，继续轮询后才回到 `{"state":"running"}`，整个过程不需要重刷。
- 在 2026-04-01 的复跑里，`radar ota` 自身在 phase 3 grace 后就返回了成功，随后立即补查的 `radar status` 已经是 `{"state":"running"}`。

结论：

- 即使 `radar ota` 已经返回成功，也要继续轮询 `radar status`，直到看到 `running`。
- 如果 `radar ota` 超时，不要立刻重刷。
- 对 `radar flash`、`radar reconf`，以及 factory / baseline 恢复路径里的第一次上电，也要使用同样的 `radar status = running` gate。
- 后续再用 `raw_resp` 中的启动输出确认雷达已真正启动。
- 在 `radar ota` 步骤直接用 `--raw-resp-output` 抓 `raw_resp` 只能算 best-effort。2026-03-19 的 main 分支验证里，这段窗口抓到了 `2` 条消息 / `128` 字节；而 2026-04-01 的成功复跑里，这段窗口则是空的。
- 可靠的证明路径仍然是 `radar status = running`，再加上恢复后后续抓到的 `raw_resp` 启动输出。

### 步骤 10：采集 300 秒 `raw_data` 和 `raw_resp`

命令：

```bash
./mmwk_cli/mmwk_cli.sh collect \
  --duration 300 \
  --broker mqtt://192.168.4.9:1883 \
  --device-id dc5475c879c0 \
  --data-topic mmwk/dc5475c879c0/raw/data \
  --resp-topic mmwk/dc5475c879c0/raw/resp \
  --data-output <demo-output-dir>/data_resp_300s.sraw \
  --resp-output <demo-output-dir>/cmd_resp_300s.log \
  -p /dev/cu.usbserial-0001
```

运行时注意：

- 当使用 `-p/--port` 时，`collect` 现在会先等 bridge 恢复 Wi-Fi / MQTT 连通性，再 arm raw MQTT capture 和 restart probe。
- 这对真机很重要，因为如果设备侧 MQTT client 仍未连上，最早那一段启动 `raw_resp` 很容易直接丢掉。
- 如果你切到纯 MQTT 的 `collect --resp-optional`，必须先经过步骤 9 的 ready gate，也就是先确认 `radar status` 已经回到 `running`。
- 如果把 `collect -p` 当作启动证明路径，本次采集里的 `cmd_resp_300s.log` / `raw_resp` 就不应为空。

本次验证的示例结果：

- 2026-03-19 运行：
  - `Collected frames: 3135`
  - `Collected bytes: 384044`
  - `Data topic frames (DATA UART / binary): 3134`
  - `Data topic bytes (DATA UART / binary): 383980`
  - `Resp topic frames (CMD UART / startup-trimmed command-port text): 1`
  - `Resp topic bytes (CMD UART / startup-trimmed command-port text): 64`
- 2026-04-01 复跑：
  - `Collected frames: 3152`
  - `Collected bytes: 313470`
  - `Data topic frames (DATA UART / binary): 3107`
  - `Data topic bytes (DATA UART / binary): 311546`
  - `Resp topic frames (CMD UART / startup-trimmed command-port text): 45`
  - `Resp topic bytes (CMD UART / startup-trimmed command-port text): 1924`

本步骤可使用的示例输出文件名：

- `<demo-output-dir>/data_resp_300s.sraw`：本次 300 秒运行中非空的 `raw_data` 采集文件
- `<demo-output-dir>/cmd_resp_300s.log`：在 2026-03-19 运行里为 `64` bytes，在 2026-04-01 复跑里为 `1924` bytes，但都从第一个 printable ASCII 字节开始

本步骤的硬性验收门槛：

- `data_resp` 必须至少达到 `100 KB`。
- `cmd_resp` 必须体现多段逻辑行的命令口输出。
- 采集结束后，`radar status` 仍必须是 `running`。

本次 `raw_resp` 的示例内容：

```text
***********************************
\rIWR6843AOP Vital Signs with People Tracking
\rmmwDemo:/>sensorStop
```

说明：

- `raw_resp` 仍然来自 `on_cmd_data`，但驱动会先裁掉第一个 printable ASCII 字节之前的启动脏数据。
- 在有效运行之间，`raw_resp` 的体量差异可能很大，既可能只是单段截断 banner，也可能是多行命令交互文本。
- 截断 banner 仍然是可以接受的。
- 对用户来说，`cmd_resp.log` 应该已经是干净的命令口文本。

### 步骤 11：采集后复核雷达状态

命令：

```bash
./mmwk_cli/mmwk_cli.sh radar status \
  --transport mqtt \
  --broker 192.168.4.9 \
  --mqtt-port 1883 \
  --device-id dc5475c879c0 \
  --cmd-topic mmwk/dc5475c879c0/device/cmd \
  --resp-topic mmwk/dc5475c879c0/device/resp
```

成功证明：

- 返回 `{"state":"running"}`

### 步骤 12：停止本地 `server.sh`

命令：

```bash
./mmwk_cli/server.sh stop --state-dir <demo-output-dir>/local_server
```

成功证明：

- 返回 `Local server stopped`

## 5. 给客户的推荐手工执行顺序

终端 A：

```bash
./mmwk_cli/server.sh run \
  --serve-dir <artifact-dir> \
  --host-ip 192.168.4.9 \
  --mqtt-port 1883 \
  --http-port 8380
```

终端 B：

```bash
./mmwk_cli/mmwk_cli.sh network config --ssid ventropic --password ve12345678 --reset -p /dev/cu.usbserial-0001
./mmwk_cli/mmwk_cli.sh network mqtt --mqtt-uri mqtt://192.168.4.9:1883 --reset -p /dev/cu.usbserial-0001
./mmwk_cli/mmwk_cli.sh device reboot --reset -p /dev/cu.usbserial-0001
./mmwk_cli/mmwk_cli.sh device hi --transport mqtt --broker 192.168.4.9 --mqtt-port 1883 --device-id dc5475c879c0 --cmd-topic mmwk/dc5475c879c0/device/cmd --resp-topic mmwk/dc5475c879c0/device/resp
./mmwk_cli/mmwk_cli.sh radar ota --fw <artifact-dir>/vital_signs_tracking_6843AOP_demo.bin --cfg <artifact-dir>/vital_signs_AOP_2m.cfg --welcome --no-verify --raw-resp-output ./ota_cmd_resp.log --transport mqtt --broker 192.168.4.9 --mqtt-port 1883 --device-id dc5475c879c0 --cmd-topic mmwk/dc5475c879c0/device/cmd --resp-topic mmwk/dc5475c879c0/device/resp --base-url http://192.168.4.9:8380/
```

如果设备沿用了较旧的持久化 agent 值，导致 MQTT 控制仍未开启，再在重启前执行下面这个手动 override：

```bash
./mmwk_cli/mmwk_cli.sh device agent --mqtt-en 1 --raw-auto 1 --reset -p /dev/cu.usbserial-0001
```

如果 `radar ota` timeout，或者你只是想在采集前做一次显式 ready gate：

```bash
while true; do
  ./mmwk_cli/mmwk_cli.sh radar status --transport mqtt --broker 192.168.4.9 --mqtt-port 1883 --device-id dc5475c879c0 --cmd-topic mmwk/dc5475c879c0/device/cmd --resp-topic mmwk/dc5475c879c0/device/resp
  sleep 10
done
```

等雷达返回 `running` 后：

```bash
./mmwk_cli/mmwk_cli.sh collect --duration 300 --broker mqtt://192.168.4.9:1883 --device-id dc5475c879c0 --data-topic mmwk/dc5475c879c0/raw/data --resp-topic mmwk/dc5475c879c0/raw/resp --data-output ./data_resp_300s.sraw --resp-output ./cmd_resp_300s.log -p /dev/cu.usbserial-0001
```

如果设备刚重启后 UART CLI JSON 查询失败，不要立刻判断设备异常，先用 `--reset` 重试一次。

## 6. 本次产物

- 演示目录：`<demo-output-dir>`
- 关键产物：
  - `<demo-output-dir>/data_resp_300s.sraw`
  - `<demo-output-dir>/cmd_resp_300s.log`
  - `<demo-output-dir>/ota_cmd_resp.log`
  - `<demo-output-dir>/collect_300s.log`
  - `<demo-output-dir>/local_server/mosquitto.log`
  - `<demo-output-dir>/local_server/http.log`
  - 本文档：`./collect.md`

## 7. 结论

本次在 fresh mini bridge 设备上的验证结果是成功的：

- 本地 `server.sh` 成功提供了 MQTT 和 HTTP，并直接服务了 main 仓库自带的 `./firmwares/radar/iwr6843/vital_signs` 资产。
- fresh bridge 现在应在执行 `network mqtt` 并重启后直接具备 MQTT 控制；`device agent --mqtt-en 1 --raw-auto 1` 仅保留为旧持久化值场景下的手动 override / 排障路径。
- OTA 前，MQTT 侧的 `radar status` 可能已经是 `updating`，也可能已经是 `running`；这两种情况都在验证里出现过，而且都不会阻塞后续 OTA。
- 设备成功通过 Wi-Fi 使用本地 HTTP 获取 `.bin` 和 `.cfg`。
- 多次验证里，`radar ota` 的完成路径不同：2026-03-19 这次先 timeout、后续轮询恢复到 `running`；2026-04-01 复跑则在内建 phase 3 grace 后于 `148.4` 秒直接成功返回。两种情况都不需要重刷。
- OTA 阶段的 `raw_resp` 抓取始终只能算 best-effort：一条验证记录抓到了 `2` 条消息 / `128` 字节，另一条成功复跑则是 `0` 字节。
- 多次 300 秒采集都成功完成。观测到的 `raw_data` 介于 `311546` 到 `383980` 字节之间，`raw_resp` 介于 `64` 到 `1924` 字节之间，并且采集结束后雷达始终保持 `running`。
