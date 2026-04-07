# MMWK Sensor BRIDGE 参考

当你已经通过 [MMWK Bridge 模式](./bridge.md) 确定起步路径，只是需要深入查看 bridge 模式的技术语义、参数契约和运行态确认方法时，请读这份参考文档。

## 已验证执行前提

- 请从 `./mmwk_cli` 目录执行下面的 shell 示例，这样 `./mmwk_cli.sh` 和 `../firmwares/...` 这些参考路径才能按文档原样生效。
- 把 `PORT=/dev/cu.usbserial-0001` 替换成你自己机器上的真实 UART 串口。
- 这份参考文档默认你先执行 `./mmwk_cli.sh device hi -p "$PORT"`，并且返回 `name = mmwk_sensor_bridge`。如果它返回的是 `mmwk_sensor_hub` 之类的其他 profile，请先回到 [MMWK Bridge 模式](./bridge.md) 重新选择路径。
- `mmwk_cli.sh` 现在默认走标准 CLI JSON。如果旧调用方还依赖 MCP，请显式加上 `--protocol mcp` 作为兼容回退。
- 这份参考文档不替代 Wi-Fi / MQTT bring-up。执行 `collect` 之前，`device hi` 应已经能返回 `mqtt_uri`、`client_id`、`raw_data_topic`、`raw_resp_topic` 等 bridge MQTT 字段，并且设备运行时网络也应已经可用，例如 `ip` 不应还是 `0.0.0.0`；如果这些字段还没有，或者设备仍停在 `ip = 0.0.0.0`，请先回到 [MMWK Bridge 模式](./bridge.md)，再进入 [本地 `server.sh` + `mmwk_cli.sh` Wi-Fi 刷机与 5 分钟采集示例](./collect.md)。
- 如果你刚执行过 `radar flash`、`radar ota`、`radar reconf`，或者刚走完 factory / baseline 恢复路径后的第一次上电，请先等 `radar status` 返回 `running`，再去使用任何 late-attach 的 `collect` 流程。

下面这组 shell 变量已经按当前实现验证过，可以直接复用到后续命令：

```bash
cd ./mmwk_cli
export PORT=/dev/cu.usbserial-0001
export FW=../firmwares/radar/iwr6843/vital_signs/vital_signs_tracking_6843AOP_demo.bin
export CFG=../firmwares/radar/iwr6843/vital_signs/vital_signs_AOP_2m.cfg
```

## 原始语义契约

- `raw_resp = startup-trimmed command-port output from on_cmd_data`
- `raw_data = raw data-port bytes from on_radar_data`
- `on_cmd_resp is an application-layer command response`，且它与 raw capture 不同。
- `on_radar_frame is an application-layer frame callback`，且它与 raw capture 不同。
- 雷达驱动会先裁掉启动阶段第一个 printable ASCII 字节之前的脏数据，再把命令口输出暴露给主机侧。
- `cmd_resp.log` 保留从第一个 printable ASCII 字节开始的启动 trim 后的命令口文本。

## 刷机参数说明

当前 bridge 构建已经把 `out_of_box_6843_aop.bin` + `out_of_box_6843_aop.cfg` 作为设备内置默认雷达资产。下面的参考示例故意切换到 TI `vital_signs` 资产，用来验证真正的雷达替换流程：

- `../firmwares/radar/iwr6843/vital_signs/vital_signs_tracking_6843AOP_demo.bin`
- `../firmwares/radar/iwr6843/vital_signs/vital_signs_AOP_2m.cfg`

共享参数：

| 参数 | 适用命令 | 含义 |
| --- | --- | --- |
| `--fw <file.bin>` | `radar ota`、`radar flash` | 必填，表示写入雷达芯片的固件二进制。 |
| `--cfg <file.cfg>` | `radar ota`、`radar flash` | 可选，表示与所选固件匹配的雷达配置文本。 |
| `-p <serial_port>` | 参考示例 | 主机侧 UART 串口，CLI 通过它连接到设备控制服务。 |

HTTP OTA 专属参数：

| 参数 | 含义 |
| --- | --- |
| `--http-port <port>` | 当 CLI 启动临时 HTTP 文件服务时使用的端口。 |
| `--base-url <url>` | 跳过本地 HTTP 服务，直接让设备从一个现成的 HTTP 基础地址下载固件。 |
| `--version <str>` | 显式指定期望的雷达固件版本号。 |
| `--ota-timeout <sec>` | OTA 下载并应用的最长等待时间。 |
| `--progress-interval <sec>` | 设备上报刷机进度的时间间隔。 |

分块传输（`radar flash`）专属参数：

| 参数 | 含义 |
| --- | --- |
| `--chunk-size <bytes>` | 每个固件分块的大小。 |
| `--mqtt-delay <sec>` | 当 `radar flash` 走 MQTT 传输时，块与块之间的延时。 |
| `--progress-interval <sec>` | 分块刷机过程中设备上报进度的时间间隔。 |
| `--reboot-delay <sec>` | 刷机成功后 ESP 重启前的附加等待时间。 |

## 管理型固件目录（`fw list` / `fw set`）

当你要管理 ESP 侧保存的雷达固件目录，而不是当场从主机推一份新的雷达镜像时，请使用 `fw` 相关命令。

示例：

```bash
./mmwk_cli.sh fw list -p "$PORT"
./mmwk_cli.sh fw set --index 0 -p "$PORT"
```

契约：

- `fw list` 是 bridge 面向用户的固件目录查看面。每个条目都带有 `default` 和 `running` 标志，用来区分“保存的默认固件”和“当前这次运行中的目录条目”。
- 当前 bridge 构建会从 staged assets 集合生成的 bundled catalog 暴露内置固件/配置对，因此 `fw list` 里会同时看到 manifest 管理项和 bridge 自带的只读固件/配置对。
- 这些 bundled 条目属于运行时内置资产，不是主机上传后落到存储区的新对象；请把它们视为随 bridge 出厂携带的只读目录项。
- `fw set --index <n>` 是持久化的默认固件切换，不是单纯的 metadata 开关。bridge 会把它路由到 UART 雷达 update/flash 路径；成功后，该固件会变成新的默认条目。
- `device hi` 现在会返回嵌套固件状态：`fw.default`、`fw.running`、`fw.switch`、`fw.mode`。
- `fw.default` 和 `fw.running` 都包含 `source`、`index`、`name`、`version`、`config`。
- `fw.default` 表示保存下来的持久化默认条目；`fw.running` 表示当前会话真实运行中的条目。
- `fw.running.source=runtime` 表示当前这次雷达会话固定在一对显式 staging 的运行时资产上，而不是目录/default 固件条目。
- `fw.switch` 用来报告 profile 门控后的切换能力。当前 bridge 构建会返回 `fw.switch.persist=true`、`fw.switch.temp=false`。
- `fw.mode` 表示当前雷达会话的启动路径：`flash`、`uart`、`spi`、`host`。
- 旧字段 `radar_fw`、`radar_fw_version`、`radar_cfg` 仍然保留，并继续映射到 `fw.running`。
- 运行时的非默认临时切换（`radar switch persist=false`）不属于这条已验证 bridge 参考主链。`mmwk_cli` 目前也没有把它作为用户命令暴露出来；在临时 SPI 启动路径完成当前雷达家族验证之前，请把它视为不支持。

## 运行时重配置（`radar reconf`）

当你只想修改运行时雷达契约，而不想再次刷写 firmware 时，请使用 `radar reconf`。它适合切换 `welcome` / `verify` / `version` 语义，以及可选的运行时 cfg 选择，同时保持当前雷达固件二进制不变。

示例：

```bash
./mmwk_cli.sh radar reconf --welcome --no-verify -p "$PORT"
./mmwk_cli.sh radar reconf --welcome --verify --version "1.2.3" -p "$PORT"
./mmwk_cli.sh radar reconf --welcome --no-verify --cfg ./runtime.cfg -p "$PORT"
./mmwk_cli.sh radar reconf --welcome --no-verify --clear-cfg -p "$PORT"
```

契约：

- 这是 bridge-only 的运行时重配置；host mode is rejected。
- `cfg_action` 取值为 `keep | replace | clear`。
- `--cfg` 对应 `cfg_action=replace`，只上传运行时 cfg，并以 `uart_data action=reconf_done` 收尾。
- `--clear-cfg` 对应 `cfg_action=clear`，会清除持久化的运行时 cfg override。
- 不传 `--cfg` 时，对应 `cfg_action=keep`，保留当前运行时 cfg 选择。
- 与 `radar flash`、`radar ota` 不同，`radar reconf` 不会重新刷写 firmware，也不会替换雷达二进制。
- 请把 `radar reconf` 当作可选的高级步骤，而不是下面那条“最小已验证 bridge 参考链路”的一部分。每次执行完 `radar reconf` 后，都要重新检查 `radar status`，并且等到 `state=running` 以后，再去依赖 `radar version` 或 `collect`。

## 运行时 CFG 回读（`radar cfg`）

当你只想把当前实际生效的雷达 cfg 文本读出来，而不想改 firmware 或运行时契约状态时，请使用 `radar cfg`。

示例：

```bash
./mmwk_cli.sh radar cfg -p "$PORT"
```

契约：

- 默认读取当前实际生效的 file cfg 文本。
- 所谓“当前实际生效的 file cfg”，是指当前选中的运行时 override cfg；如果没有 override，则读取 firmware metadata 里的默认 cfg。
- 对 `radar flash` 明确传入的 firmware/cfg 配对，bridge 会持久化那对“精确的 staging 运行时路径”，而不会因为版本号相同就静默改绑到 bridge 自带的 `/assets` 目录项。
- 如果下次启动时无法精确重新打开这对持久化的显式运行时 firmware/cfg 路径，bridge 会直接启动失败，而不会静默替换成别的打包资产对。
- 在这条 bridge 参考链路里不要使用 `--gen`；bridge 会明确拒绝它，因为 bridge 没有 generated cfg 来源。
- `--gen` 是 hub-only，用来只读取 hub 运行时生成的 cfg；请求它时不能回退到 file cfg。
- 如果当前选中的 file cfg 缺失、不可读或为空，请求会直接失败。
- CLI 只会把 cfg 文本本身输出到 stdout，因此重定向时可以保留原始 cfg 内容。

## 启动模式契约

- `startup_mode` 表示当前保存/当前配置的默认模式。
- `supported_modes` 表示当前 profile 支持的模式列表。
- bridge 支持 `["auto", "host"]`。
- hub 只支持 `["auto"]`。
- `device startup --mode auto|host` 用来更新保存的默认启动模式。
- `radar status --set start --mode auto|host` 只是当前雷达服务的一次性启动请求，不会覆盖保存的默认模式。
- `raw_auto` 只控制 raw 平面的自动启动，不决定由谁负责雷达启动。

对 bridge 来说，各启动模式的含义如下：

- `auto` 表示 ESP 接管雷达 bring-up。设备可以选择 firmware/cfg metadata、等待启动 CLI/welcome 输出、校验版本信息，并自动下发雷达配置。
- `host` 表示由主机控制雷达 bring-up。设备仍然提供周边传输面，但不会在启动期自动下发雷达配置、不会自动等待 welcome 文本、也不会自动做版本校验。
- 在 bridge `host` 下，像 `radar flash`、`radar ota` 这样的显式维护命令仍可按需直接调用。
- 在 bridge `host` 且 `raw_auto=1` 时，自动启动的 raw 平面会同时包含 `mmwk/{mac}/raw/data`、`mmwk/{mac}/raw/resp` 和 `mmwk/{mac}/raw/cmd`。

## 版本号：有和没有时分别怎么处理

- `radar flash` 和 `radar ota` 都支持显式传入 `--version <str>`、`--verify` / `--no-verify`、`--welcome` / `--no-welcome`。
- `radar flash` 和 `radar ota` 都会从 `--fw` 二进制旁边的 `meta.json` 推断雷达 metadata：`welcome` 加上可选的 `version`。
- 如果同时给了 CLI 参数和 `meta.json`，以显式 CLI 参数为准。
- 设备不会主动去读取某个雷达内部版本寄存器。当前实现是在雷达启动后、下发任何雷达配置命令之前，扫描启动阶段的 CLI/welcome 输出文本。
- `welcome` 表示这份固件是否应该输出启动 CLI/welcome 文本。
- 当 `welcome=true` 时，只要启动阶段出现任意非空输出，就算 welcome 成立；它不是固定 banner 模板，而且可能是多行文本。
- `welcome` 之所以重要，有两个独立原因：它能证明雷达固件确实已经启动到会输出启动 CLI 的阶段；同时，这段文本里也携带了雷达固件真正的运行时版本信息。
- `version` 表示要在这段 CLI/welcome 输出里匹配的目标子串。
- 当启用版本校验时，MMWK 会在整段启动输出里查找目标子串，不要求固定某一行 welcome 文本。
- 如果 `welcome` metadata 标错了，MMWK 可能会一直等待一个永远不会出现的启动文本，或者跳过它唯一能拿到的运行态启动证明与版本来源。
- 如果 `welcome=true`，但在超时窗口内始终没有任何启动 CLI/welcome 输出，应直接视为雷达启动失败：固件大概率没有在雷达侧成功启动。此时 `radar status` 会保持 `state=error`，并附带 `details` 字段解释失败原因；雷达侧日志也会打印 boot observation 摘要。
- `--verify` 会打开版本匹配，并且要求必须提供版本字符串；如果没有启用 `--verify`，刷机本身仍然可以成功，但 `radar version` 可能为空，因为没有可匹配并保存的目标字符串。
- bridge 流程里使用的 `vital_signs` 示例目录现在已经自带同目录 `meta.json`，所以 `radar flash` 和 `radar ota` 都能自动推断期望雷达 metadata。如果你换成其他自定义 demo，请自行补一个匹配的 `meta.json`，或显式传入 `--welcome` / `--version`。
- 如果你需要定制 MMWK 识别到的雷达固件版本号，请让雷达固件的启动 CLI 输出打印出目标版本字符串，并让主机侧通过 `--version` 或同目录的 `meta.json` 传入相同的期望值。

最小 `meta.json` 示例：

```json
{
  "fws": [
    {
      "firmware": "vital_signs_tracking_6843AOP_demo.bin",
      "welcome": true,
      "version": "<startup-version-string>"
    }
  ]
}
```

## 传输层与 Topic 分工

`network mqtt` 负责配置设备 MQTT 身份以及 MCP 交互通道。`radar raw` 会复用同一 broker/client，并派生原始雷达透传平面。

| Topic | 内容 |
| --- | --- |
| `mmwk/{mac}/device/cmd` | 由 `network mqtt` 配置的 MCP 命令输入。 |
| `mmwk/{mac}/device/resp` | 由 `network mqtt` 配置的 MCP 响应和状态事件。 |
| `mmwk/{mac}/raw/data` | 由 `radar raw` 派生的雷达 DATA UART 原始透传。 |
| `mmwk/{mac}/raw/resp` | 由 `radar raw` 派生的雷达 CMD UART 启动 trim 后命令口输出（来源 `on_cmd_data`）。 |
| `mmwk/{mac}/raw/cmd` | 可选的雷达 CMD UART 输入通道，仅在 host 模式下可用。 |

对于 fresh bridge 设备，执行 `network mqtt` 并重启后，就应具备 MQTT 控制能力。
当 NVS 里还没有这些 agent key 时，bridge 默认 `mqtt_en=1`、`raw_auto=1`。
只有在手动 override 或排障时，才需要执行 `device agent --mqtt-en 1 --raw-auto 1`。

## welcome / 启动输出语义

- 启动文本是一种 boot observation，不是固定 banner 契约。
- welcome 路径是 MMWK 同时判断“雷达 app 是否真正启动”和“它打印了什么版本字符串”的唯一运行态来源。
- 如果 `welcome=true`，设备应在正常下发配置前看到启动阶段的 CLI/welcome 输出。
- 如果在超时窗口内看不到这段输出，设备就会把本次会话视为失败，并在 `radar status` 里留下结构化失败信息。

## host 模式与 bridge 模式边界

- `startup_mode=host` 表示主机接管启动，不是“auto 模式外加一个 raw topic”。
- `startup_mode=auto` 表示由 ESP 负责 bridge 的雷达启动与配置 bring-up。
- `mmwk/{mac}/raw/cmd` 仅在 host 模式下可用。
- bridge/auto 模式下，MQTT raw 平面是只出不进的。
- `mmwk/{mac}/raw/cmd` 与 MCP 的 `mmwk/{mac}/device/cmd` 是两条不同通道。
- 对真实应用、服务、仪表盘和 AI Agent，优先推荐 MQTT；UART 更适合工厂初始化、刷写、bring-up、台架调试和故障兜底。

## 运行态确认清单

在雷达刷写、OTA、reconf，或者 factory / baseline 恢复路径后的第一次上电后，建议结合以下命令一起确认：

```bash
./mmwk_cli.sh device hi -p "$PORT" | tee ./bridge_hi.json
./mmwk_cli.sh device hi --transport mqtt --broker "$BROKER_HOST" --mqtt-port "$MQTT_PORT" --device-id "$DEVICE_ID" --cmd-topic "$CMD_TOPIC" --resp-topic "$RESP_TOPIC"
./mmwk_cli.sh radar status --transport mqtt --broker "$BROKER_HOST" --mqtt-port "$MQTT_PORT" --device-id "$DEVICE_ID" --cmd-topic "$CMD_TOPIC" --resp-topic "$RESP_TOPIC"
./mmwk_cli.sh radar version --transport mqtt --broker "$BROKER_HOST" --mqtt-port "$MQTT_PORT" --device-id "$DEVICE_ID" --cmd-topic "$CMD_TOPIC" --resp-topic "$RESP_TOPIC"
./mmwk_cli.sh collect --duration 12 \
  --broker "$BROKER_URI" \
  --device-id "$DEVICE_ID" \
  --data-topic "$RAW_DATA_TOPIC" \
  --resp-topic "$RAW_RESP_TOPIC" \
  --resp-optional \
  --data-output ./data_resp.sraw \
  --resp-output ./cmd_resp.log
```

请按以下方式解释结果：

- `radar status` 应显示可用状态，例如 `running`。
- 在 `radar flash` 或 `radar reconf` 之后的短暂恢复窗口里，`radar status` 可能会先返回 `starting`。请先等到 `state=running`，再把 `radar version` 当成最终运行态证明。
- 对 `radar flash`、`radar ota`、`radar reconf`，以及 factory / baseline 恢复后的第一次上电，都要把轮询 `radar status = running` 当成强制 gate，不要用固定 sleep 去替代。
- 先用一次 UART `device hi -p "$PORT"` 确认当前确实在 bridge profile，并把这次会话对应的 MQTT 身份字段取出来。
- 在当前 PRO 真机验证里，独立的 UART 命令反复开关串口后，设备可能重新回到启动窗口。只要 MQTT 控制已经 ready，后续 `device hi`、`radar status`、`radar version` 都优先建议走 MQTT。
- `device hi` 应在 `name` / `version` 中返回当前 ESP 固件身份。
- 如果 `device hi` 里仍然显示 `ip = 0.0.0.0`，请把它视为设备网络还没 ready 到可以做 MQTT raw capture。此时 `collect` 可能会先短暂等待，然后仍然在 broker 连接阶段失败。
- `device hi.fw.default`、`device hi.fw.running`、`device hi.fw.switch`、`device hi.fw.mode` 是 bridge 管理多固件会话时的标准固件状态字段。
- 其中 `radar_fw`、`radar_fw_version`、`radar_cfg` 反映的是当前会话真实运行中的雷达元信息条目；直刷、OTA 或运行态切换成功后，它们不会继续固定在 `fw.default`。
- `radar_fw`、`radar_fw_version`、`radar_cfg` 是 `fw.running` 的旧兼容别名。
- `fw.switch.persist=true` 且 `fw.switch.temp=false` 表示当前 bridge 构建支持持久化默认固件切换，但还没有对外提供已验证的运行时 SPI 临时切换能力。
- 请以 `radar version` 配合 `radar status` 作为运行态确认，但前提是这次会话本身持久化了版本字符串。
- 如果当前运行态契约没有持久化版本字符串，`radar version` 可能为空。请把 `radar status=running` 当成主要运行态证明；当 `radar version` 非空时，再把它当作补充证据。
- 如果 `radar status` 返回 `state=error` 且带有 `details`，请把它当成结构化的启动/运行失败诊断结果。
- `details.kind=startup_failed` 表示固件大概率没有真正启动到雷达 CLI。
- 当采集窗口内确实出现了新的启动命令口输出时，`cmd_resp.log` 应该从第一个 printable ASCII 字节开始，用户看到的是启动 trim 后的命令口文本。
- 在这条清单里，`collect --resp-optional` 只用于 `radar status` 已经证明雷达在运行之后的 late-attach 稳态观察窗口；它不是启动/welcome 证明。
- 如果你改用 `collect -p "$PORT"` 作为这些恢复窗口的启动期证明路径，就要要求非空 `raw_resp` / `cmd_resp.log`。
- 这条 late-attach 运行态检查会故意保持 pure MQTT。不要把 `-p "$PORT"` 再加回这一步，除非你同时移除 `--resp-optional`，并重新要求非空启动 `raw_resp`。
- 如果你需要一个挂在官方 `collect` 命令之外的 pure-MQTT 启动期 helper，请在 `mmwk_cli` 目录下运行 `./tools/mmwk_raw.sh`。它支持 `trigger=none`、`trigger=radar-restart` 和 `trigger=device-reboot`。如果你还需要先下发 Wi-Fi / MQTT 设置，或者要把设备改指到本地 `server.sh` broker，请先运行 `./tools/mmwk_cfg.sh`。
- 如果你需要严格验证启动文本，请回到 [本地 `server.sh` + `mmwk_cli.sh` Wi-Fi 刷机与 5 分钟采集示例](./collect.md) 里的完整 bring-up / OTA / collect 流程。

## 已验证运行态命令链

如果你想要一条“现在就能照抄执行、并且和当前实现一致”的 bridge reference 主链，请在 `./mmwk_cli` 目录里按下面顺序执行这组运行态确认命令：

```bash
./mmwk_cli.sh device hi -p "$PORT" | tee ./bridge_hi.json

export BROKER_URI="$(python3 - <<'PY'
import json
with open("./bridge_hi.json", "r", encoding="utf-8") as fp:
    payload = json.load(fp)
print(payload["mqtt_uri"])
PY
)"
export BROKER_HOST="$(python3 - <<'PY'
from urllib.parse import urlparse
import json
with open("./bridge_hi.json", "r", encoding="utf-8") as fp:
    payload = json.load(fp)
print(urlparse(payload["mqtt_uri"]).hostname or "")
PY
)"
export MQTT_PORT="$(python3 - <<'PY'
from urllib.parse import urlparse
import json
with open("./bridge_hi.json", "r", encoding="utf-8") as fp:
    payload = json.load(fp)
print(urlparse(payload["mqtt_uri"]).port or 1883)
PY
)"
export DEVICE_ID="$(python3 - <<'PY'
import json
with open("./bridge_hi.json", "r", encoding="utf-8") as fp:
    payload = json.load(fp)
print(payload["client_id"])
PY
)"
export CMD_TOPIC="$(python3 - <<'PY'
import json
with open("./bridge_hi.json", "r", encoding="utf-8") as fp:
    payload = json.load(fp)
print(payload["cmd_topic"])
PY
)"
export RESP_TOPIC="$(python3 - <<'PY'
import json
with open("./bridge_hi.json", "r", encoding="utf-8") as fp:
    payload = json.load(fp)
print(payload["resp_topic"])
PY
)"
export RAW_DATA_TOPIC="$(python3 - <<'PY'
import json
with open("./bridge_hi.json", "r", encoding="utf-8") as fp:
    payload = json.load(fp)
print(payload["raw_data_topic"])
PY
)"
export RAW_RESP_TOPIC="$(python3 - <<'PY'
import json
with open("./bridge_hi.json", "r", encoding="utf-8") as fp:
    payload = json.load(fp)
print(payload["raw_resp_topic"])
PY
)"

until ./mmwk_cli.sh device hi --transport mqtt --broker "$BROKER_HOST" --mqtt-port "$MQTT_PORT" --device-id "$DEVICE_ID" --cmd-topic "$CMD_TOPIC" --resp-topic "$RESP_TOPIC"; do
  sleep 3
done
./mmwk_cli.sh radar status --transport mqtt --broker "$BROKER_HOST" --mqtt-port "$MQTT_PORT" --device-id "$DEVICE_ID" --cmd-topic "$CMD_TOPIC" --resp-topic "$RESP_TOPIC"
./mmwk_cli.sh radar version --transport mqtt --broker "$BROKER_HOST" --mqtt-port "$MQTT_PORT" --device-id "$DEVICE_ID" --cmd-topic "$CMD_TOPIC" --resp-topic "$RESP_TOPIC"
./mmwk_cli.sh collect --duration 12 \
  --broker "$BROKER_URI" \
  --device-id "$DEVICE_ID" \
  --data-topic "$RAW_DATA_TOPIC" \
  --resp-topic "$RAW_RESP_TOPIC" \
  --resp-optional \
  --data-output ./data_resp.sraw \
  --resp-output ./cmd_resp.log
```

请按下面的方式理解这组命令：

- 第一条 UART `device hi` 先确认设备当前确实处在 bridge profile，并把这次会话的 MQTT 身份字段落到 `./bridge_hi.json`。
- 后面的环境变量导出步骤会把这些字段转成可直接复用的 MQTT 参数，这样后续运行态确认就不用再为每一步反复重开 UART。
- `radar status` 仍然是决定性的运行态检查。`radar version` 非空时很有价值，但它为空本身不应被当成失败。
- 因为这条命令链在执行到最后一步前，已经是“雷达正在运行后再接入”的场景，所以最后的 `collect --resp-optional` 是 late-attach MQTT 观察窗口，不是启动采集。
- 最后的 `collect --resp-optional` 是主机侧最终证明：bridge raw forwarding 仍然能产出 `raw_data`，并且如果这次窗口里真的出现了新的启动 trim 后命令口输出，也会写入 `cmd_resp.log`。
- 如果你要拿 fresh startup/welcome 作为证明，就不要放宽这一步：应从 boot/OTA 窗口一开始就启动采集，并要求非空 `raw_resp`。
- 上面各节里的 `radar flash`、`radar ota`、`radar reconf` 仍然保留给“你明确要改雷达 firmware / metadata / 运行时契约”的高级操作；每次做完这些高级操作后，都请再回到这里这条运行态确认主链。

如果你要看完整的 bring-up 主线，请回到 [MMWK Bridge 模式](./bridge.md)，再继续进入 [本地 `server.sh` + `mmwk_cli.sh` Wi-Fi 刷机与 5 分钟采集示例](./collect.md)。
