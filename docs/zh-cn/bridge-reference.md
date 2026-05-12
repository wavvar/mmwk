# Bridge 参考

当你已经读过简短的 [Bridge](./bridge.md) 入口，并且需要 bridge 专属的命令顺序、参数契约和运行态证明清单时，请看这份参考。

除非某一节明确要求进入 `./cli`，下面的示例都从 package root 执行。请把 `/dev/cu.usbserial-0001` 替换成你主机上的真实串口。

```bash
export PORT=/dev/cu.usbserial-0001
export FW=./firmwares/radar/iwr6843/vital_signs/vital_signs_tracking_6843AOP_demo.bin
export CFG=./firmwares/radar/iwr6843/vital_signs/vital_signs_AOP_2m.cfg
```

## 身份与 Ready 判断

本地 bring-up 先走 UART：

```bash
./cli/run.sh node info -p "$PORT"
./cli/run.sh network status -p "$PORT"
```

`node info` 用于识别 ESP 固件 profile，并发布 `did`、`prod`、`oid`、`cid`、`cmd`、`resp`、`raw_data`、`raw_resp` 等 route 字段。ready 判断以 `network status` 为准：`state=connected && ready=true` 是网络 ready 契约；依赖 MQTT 的流程还要看 `mqtt_state=connected`。

执行 `radar fw flash`、`radar fw ota`、`radar config apply`，或者 factory/baseline 恢复后的第一次上电后，都要轮询 `radar status`，直到返回 `running`。不要用固定 sleep 替代这个 gate。

## 原始语义契约

- `raw_resp = startup-trimmed command-port output from on_cmd_data`
- `raw_data = raw data-port bytes from on_radar_data`
- `on_cmd_resp is an application-layer command response`，且它与 raw capture 不同。
- `on_radar_frame is an application-layer frame callback`，且它与 raw capture 不同。
- `cmd_resp.log` 从启动 trim 后的第一个 printable ASCII 字节开始。

## 雷达固件命令

公开 CLI 把雷达固件生命周期命令放在 `radar fw` 下。

```bash
./cli/run.sh radar fw flash --fw "$FW" --cfg "$CFG" -p "$PORT"
./cli/run.sh radar fw ota --fw "$FW" --cfg "$CFG" -p "$PORT"
./cli/run.sh radar fw version -p "$PORT"
```

共享参数：

| 参数 | 适用命令 | 含义 |
| --- | --- | --- |
| `--fw <file.bin>` | `radar fw flash`、`radar fw ota` | 写入雷达芯片的雷达固件二进制。 |
| `--cfg <file.cfg>` | `radar fw flash`、`radar fw ota` | 可选，与所选 firmware 匹配的雷达 cfg 文本。 |
| `--version <str>` | `radar fw flash`、`radar fw ota` | 开启验证时要匹配的启动版本子串。 |
| `--welcome` / `--no-welcome` | `radar fw flash`、`radar fw ota` | 是否预期看到启动输出。 |
| `--verify` / `--no-verify` | `radar fw flash`、`radar fw ota` | 是否要求启动输出包含期望版本子串。 |

## 管理型固件目录

当你要查看或切换 ESP 侧雷达固件目录，而不是当场从主机推送二进制时，请使用 `radar fw` 目录命令。

```bash
./cli/run.sh radar fw list -p "$PORT"
./cli/run.sh radar fw set --index 0 -p "$PORT"
```

`radar fw list` 会标出保存的默认条目和当前运行条目。`radar fw set --index <n>` 是持久化默认固件切换，会走雷达 update 路径；它不是单纯的 metadata toggle。

## 运行时配置（`radar config apply`）

当雷达 firmware 二进制已经正确，只需要修改启动期望或运行时 cfg 选择时，请用 `radar config apply`，不要重新刷 firmware。

```bash
./cli/run.sh radar config apply --welcome --no-verify -p "$PORT"
./cli/run.sh radar config apply --welcome --verify --version "1.2.3" -p "$PORT"
./cli/run.sh radar config apply --welcome --no-verify --cfg ./runtime.cfg -p "$PORT"
./cli/run.sh radar config apply --welcome --no-verify --clear-cfg -p "$PORT"
```

契约：

- `--cfg` 对应 `cfg_action=replace`，只上传运行时 cfg，并以 `uart_data action=reconf_done` 收尾。
- `--clear-cfg` 对应 `cfg_action=clear`，会清除持久化的运行时 cfg override。
- 不传 `--cfg` 时，对应 `cfg_action=keep`，保留当前运行时 cfg 选择。
- `radar config apply` 不会刷写 firmware，也不会替换雷达二进制。
- 每次 apply 后，都要先等 `radar status` 返回 `running`，再依赖 `radar fw version` 或 late-attach 采集。

## 运行时 CFG 回读（`radar cfg`）

固件侧 action 名是 `radar cfg`；公开 CLI 命令是 `radar config read`。

```bash
./cli/run.sh radar config read -p "$PORT"
./cli/run.sh radar config read --gen -p "$PORT"
```

旧 SDK 协议笔记可能写作 `./run.sh radar cfg -p "$PORT"`。在当前发布的 CLI 树里，请使用 `radar config read`。

契约：

- 默认读取当前实际生效的 file cfg 文本。
- 所谓当前实际生效的 file cfg，是指当前选中的运行时 override cfg；如果没有 override，则读取 firmware metadata 里的默认 cfg。
- 在这条 bridge 参考链路里不要使用 `--gen`；bridge 会明确拒绝它，因为 bridge 没有 generated cfg 来源。
- `--gen` 用来请求 hub 运行时生成的 cfg，并且只在 hub runtime 下可用；请求它时不能回退到 file cfg。
- 缺失、不可读、为空或其他不可用的 cfg 目标都是硬错误。
- CLI 只会把 cfg 文本本身输出到 stdout，因此重定向时可以保留原始 cfg 内容。

## 启动模式

统一使用以下含义：

- `mode` 是雷达状态面报告的已保存/已配置默认模式。
- `modes` 是当前固件 profile 支持的模式列表。
- `fw.boot_mode` 是当前运行态雷达 boot path：`flash`、`host`、`uart` 或 `spi`。
- `auto` 表示 ESP 接管雷达 bring-up。
- `host` 表示主机接管雷达 bring-up。
- `raw_auto` 只控制 raw 平面自动启动，不决定启动所有权。

```bash
./cli/run.sh radar start --mode auto -p "$PORT"
./cli/run.sh radar start --mode host -p "$PORT"
./cli/run.sh radar stop -p "$PORT"
./cli/run.sh radar status -p "$PORT"
```

`auto` 模式下，设备可以选择 firmware/cfg metadata、等待启动输出、验证版本 metadata，并下发雷达配置。`host` 模式下，主机负责雷达 bring-up；设备仍暴露传输面，并且 `{prod}/{oid}/{cid-or-did}/raw/cmd` 只在 host 模式下可用。

## 采集与 Helper 脚本

请把 `collect` 视为启动期感知 bridge checklist 的官方命令：

```bash
./cli/run.sh collect --duration 12 \
  --data-output ./data_resp.sraw \
  --resp-output ./cmd_resp.log \
  -p "$PORT"
```

最低证据：

- 启动/welcome 证明窗口里，`cmd_resp.log` 必须非空。
- 当当前 radar firmware/cfg 配对应输出数据时，`data_resp.sraw` 必须非空。
- `Resp topic frames` 和 `Data topic frames` 统计的是 MQTT 消息数，不是毫米波 TLV 帧数。

当你明确要脱离主 CLI 的启动期感知路径，只使用 external pure-MQTT 启动期 helper 时，可以使用：

```bash
./cli/config.sh set --server-local
./cli/collect.sh --trigger device-reboot
```

需要先下发 Wi-Fi/MQTT 设置时，请使用 `./cli/config.sh set`。只有在 `radar status` 已经返回 `running` 后，才把 `./cli/collect.sh --trigger none` 用作 late-attach 观察窗口，并且只在配合 `--resp-optional` 时使用。

## 录制器命令面

录制器状态、配置和触发使用公开的 `radar raw` 命令面：

```bash
./cli/run.sh radar raw status -p "$PORT"
./cli/run.sh radar raw config get -p "$PORT"
./cli/run.sh radar raw config set --json '{"auto_upload": true, "max_duration_sec": 30}' -p "$PORT"
./cli/run.sh radar raw start --uri http://192.168.1.100:8080/upload -p "$PORT"
./cli/run.sh radar raw trigger --event MANUAL --duration-s 10 -p "$PORT"
./cli/run.sh radar raw stop -p "$PORT"
```

## 运行态确认清单

在雷达固件刷写、OTA、运行时 config apply，或 factory/baseline 恢复后的第一次上电后，使用这组命令：

```bash
./cli/run.sh node info -p "$PORT" | tee ./bridge_info.json
./cli/run.sh network status -p "$PORT" | tee ./network_status.json
./cli/run.sh radar status -p "$PORT" | tee ./radar_status.json
./cli/run.sh radar fw version -p "$PORT" | tee ./radar_version.json
./cli/run.sh collect --duration 12 \
  --data-output ./data_resp.sraw \
  --resp-output ./cmd_resp.log \
  -p "$PORT"
```

预期证据：

- `node info` 能识别 `mmwk_sensor_bridge` profile。
- MQTT 相关流程开始前，`network status` 报告 `state=connected && ready=true`。
- `radar status` 返回 `running`。
- `cmd_resp.log` 从第一个 printable ASCII 字节开始，内容是启动 trim 后的命令口文本。
- 当当前雷达 firmware/cfg 配对应输出数据时，`data_resp.sraw` 非空。
