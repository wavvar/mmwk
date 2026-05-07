# 配置助手

`config.sh init` 会把 UART 接入的设备注册进 `device.yml`，`config.sh set` 用来配置设备的 Wi-Fi 与 MQTT 设置，而且不会改动官方 `run.sh` 的命令面。`config.sh search` 通过 mDNS 搜索附近 MMWK 设备。

工作目录应为 `cli` 目录：

```bash
cd ./cli
```

下面示例使用 POSIX shell 写法。Windows PowerShell 下，只有在本机可用 Bash（例如 Git Bash）时才使用 `.\config.ps1 ...`；这个 PowerShell wrapper 会转调 `config.sh`，以保持行为一致。如果没有 Bash，请直接使用主 CLI 的 `.\run.ps1 network wifi|mqtt|status ...` 手工配置，或先安装 Git Bash 后再使用 registry helper。

## 它负责什么

- 通过 `network wifi` 下发 Wi-Fi 凭据
- 4G 配置请直接使用官方 `network 4g` 和 `network priority` 命令
- 通过 `network mqtt` 下发 MQTT 设置
- 发现通过 `_mmwk._tcp.local.` 广播出来的 MMWK device id
- 按需通过 `node reboot` 重启设备
- 按需启动或复用 `server.sh`，并把本地 broker URI 反向写回设备
- 按需在 `init` 前准备主机 Wi-Fi 网口的 bridge AP 网段地址

这个工具既可以走 UART，也可以走现有 MQTT 控制链路。

## 常见流程

### 1. UART + 本地 `server.sh`

当设备就在桌面上、串口还插着，而且你希望脚本顺手把本地 broker 也准备好时，使用：

```bash
./config.sh set --server-local \
  --ssid "MyWiFi" \
  --password "MyPass" \
  --port /dev/cu.usbserial-0001 \
  --reboot
```

启用 `--server-local` 后，`config.sh set` 会启动或复用 `server.sh`，读取它解析出的 MQTT URI，再把这个 URI 写回设备。现在 `server.sh` 也会打印请求端口、实际端口、日志文件路径和 env 文件路径，方便你诊断。

### 2. 通过 bridge AP 链路执行 UART init

当主机已经连到 bridge provisioning AP，例如 `VENTROPIC-*`，而 bridge 需要在同一个 AP 网段访问主机上的 MQTT/HTTP 服务时，使用 `init --ap-link`：

```bash
./config.sh init --port /dev/ttyUSB1 --ap-link
```

`--ap-link` 表示“准备 bridge AP 链路的主机侧地址”。它不是 Ethernet 参数。helper 会先寻找主机 Wi-Fi 网口，再检查这个网口是否已经有目标 AP 网段地址；只有缺少地址时才会执行 `sudo`。

默认地址是：

```text
192.168.4.2/24
```

如果 Wi-Fi 网口已经有这个 `/24` 内的任意 `192.168.4.x` 地址，`init --ap-link` 不会修改网口，也不会执行 `sudo`，而是直接使用已有主机 IP。如果没有，它会添加指定 alias，并且 `init` 结束后不会自动删除，因为后续 mDNS 搜索、OTA、采集和调试通常还会继续使用同一个 AP-link 地址。

自动发现规则按平台区分：

- Linux：优先使用 `/sys/class/net/*/wireless`、`iw dev`，以及 `wlan0`、`wl*` 这类 Wi-Fi 网口名。
- WSL：先向 Windows 查询名称或描述包含 `Wi-Fi`、`Wireless`、`WLAN`、`802.11` 的网卡，再按 MAC 地址映射回 Linux 网口。这样可以避开默认 WSL `eth0` / vEthernet 路径。
- macOS：使用 `networksetup -listallhardwareports`，选择 `Wi-Fi` / `AirPort` 对应的设备，通常是 `en0` 或 `en1`。

如果你已经知道正确网口，可以手动指定：

```bash
./config.sh init --port /dev/ttyUSB1 --ap-link --ap-iface eth1
./config.sh init --port /dev/cu.usbserial-0001 --ap-link --ap-iface en0
```

如果实验环境不用默认主机地址，可以改 AP CIDR：

```bash
./config.sh init --port /dev/ttyUSB1 --ap-link --ap-cidr 192.168.4.10/24
```

需要添加地址时，helper 会执行下面其中一个命令：

```bash
# Linux / WSL
sudo ip addr add 192.168.4.2/24 dev <wifi-iface>

# macOS
sudo ifconfig <wifi-iface> alias 192.168.4.2 netmask 255.255.255.0
```

如果 `sudo` 失败，或者你希望自己执行提权步骤，错误信息会打印完整命令。手动执行后，重新运行同一条 `config.sh init --ap-link ...`；helper 会检测到 AP 网段地址已经存在，并跳过 `sudo`。

当没有显式传 `--mqtt-server` 或 `--http-server` 时，`init --ap-link` 还会把选中的 AP 主机 IP 传给 `server.sh`。这样生成的 MQTT / HTTP URL 会留在 bridge AP 网段，例如 `mqtt://192.168.4.2:1883`，不会误用主机上的其他网口地址。

通常不需要清理这个 alias。只有确认后续不再需要通过该主机做 bridge AP 搜索或采集时，才手动删除：

```bash
# Linux / WSL
sudo ip addr del 192.168.4.2/24 dev <wifi-iface>

# macOS
sudo ifconfig <wifi-iface> -alias 192.168.4.2
```

### 3. 只走 MQTT 控制面

当设备已经在线、你只想远程改配置而不想碰 UART 时，使用：

```bash
./config.sh set --transport mqtt \
  --broker 192.168.1.100 \
  --mqtt-port 1883 \
  --device-id dc5475c879c0 \
  --mqtt-uri mqtt://192.168.1.200:1883 \
  --reboot
```

`--transport mqtt` 只表示“当前这次配置命令”通过现有 MQTT 控制链路送达。设备侧 MQTT 身份现在固定绑定 Wi-Fi STA MAC，所以 `network mqtt` 只保存 broker / 鉴权设置，对外返回的 canonical topic 只是只读派生值。

### 4. 4G 与网络优先级

`config.sh set` 仍然只负责 Wi-Fi/MQTT onboarding。PRO 设备和带 4G 的 WDR 设备请直接使用官方 `run.sh` 网络命令配置 4G：

```bash
./run.sh network 4g --apn YOUR_APN -p /dev/cu.usbserial-0001
./run.sh network priority --pref 4g -p /dev/cu.usbserial-0001
./run.sh network priority --pref wifi -p /dev/cu.usbserial-0001
```

保存 Wi-Fi 凭据不会改变 4G 优先级。4G 失败不会自动回退到 Wi-Fi；需要 Wi-Fi 时请显式切换优先级。

### 5. 用 mDNS 搜索设备

当你还不知道 device id，但需要选择 MQTT topic 或更新 `device.yml` 时，使用：

```bash
./config.sh search
./config.sh search --json
./config.sh search --expect-one --print-device-id
```

默认输出是紧凑表格，包含 device id、name、board、version、mode、addresses 和 hostname。JSON 输出把同样字段放在 `devices` 里。

脚本调用时，如果调用方必须拿到唯一设备，使用 `--expect-one`。发现多个设备时它会返回错误并打印候选列表；没有发现设备时也会返回错误。`--device-id ID` 会先按发现到的 `id` / `client_id` 字段过滤，再做唯一性检查。`--print-device-id` 面向 shell wrapper，只打印选中设备的 `client_id` / `id`：

```bash
DEVICE_ID="$(./config.sh search --expect-one --print-device-id)"
./config.sh search --device-id "$DEVICE_ID" --expect-one --json
```

mDNS 发现只发布设备身份、板型、版本、模式、hostname 和本地链路地址。它不发布 MQTT broker URI；broker 需要通过参数、`device.yml`、`server.sh` 或环境变量解析。

如果主机已经连到设备的 provisioning AP，但本机接口没有 AP 网段地址，可以显式指定接口：

```bash
./config.sh search --ap-iface wlan0 --ap-cidr 192.168.4.2/24
```

`search --ap-iface` 比 `init --ap-link` 更窄：它只会给指定接口临时添加 `--ap-cidr`，如果该 CIDR 已经存在则跳过添加；搜索结束后会删除临时地址，除非同时传 `--keep-ap-alias`。它不会猜测接口，也不会改路由。主机仍然需要和设备 AP 处在同一个 Wi-Fi 链路上。

## 关键参数

### `config.sh init`

- `--port PORT`：bring-up 使用的 UART 串口
- `--ssid` / `--password`：可选，重启前写入设备的 Wi-Fi 凭据
- `--mqtt-server`、`--mqtt-port`、`--http-server`、`--http-port`：显式端点；不传时会启动或复用 `server.sh`
- `--ap-link`：在解析本地 server 默认地址前，准备主机 Wi-Fi 网口的 bridge AP 网段地址
- `--ap-iface IFACE`：为 `--ap-link` 手动指定主机 Wi-Fi 网口
- `--ap-cidr CIDR`：为 `--ap-link` 指定主机 AP 网段地址，默认 `192.168.4.2/24`
- `--working DIR`：`device.yml` 的 registry 根目录

### `config.sh set`

- `--transport uart|mqtt`：当前用于下发配置的控制链路
- `--ssid` / `--password`：Wi-Fi 凭据
- `--mqtt-uri` / `--mqtt-user` / `--mqtt-pass`：保存到设备里的 broker 与鉴权设置
- `--device-id`，以及可选的 `--cmd-topic` / `--resp-topic`：告诉 `config.sh set` 当前 MQTT 控制链路应该走哪组 topic
- `--server-local`：启动或复用 `server.sh`，并使用它解析出的 broker URI
- `--server-state-dir`、`--server-serve-dir`、`--server-upload-dir`、`--server-host-ip`、`--server-target-ip`、`--server-mqtt-port`、`--server-http-port`：控制 `server.sh` 的启动/复用方式
- `--reboot`：写完设置后重启设备

### `config.sh search`

- `--timeout SEC`：mDNS 搜索时长
- `--json`：输出机器可读 JSON
- `--device-id ID`：按发现到的 `id` 或 `client_id` 过滤
- `--expect-one`：要求只发现一个匹配设备，否则失败
- `--print-device-id`：配合 `--expect-one`，只打印选中的 `client_id` / `id`
- `--ap-iface IFACE`：要临时添加 AP 网段地址的主机接口
- `--ap-cidr CIDR`：用于设备 AP 搜索的临时主机地址，默认 `192.168.4.2/24`
- `--keep-ap-alias`：搜索后保留临时地址

## 说明

- 使用 `--server-local` 时不要再手动传 `--mqtt-uri`；broker 由 `server.sh` 决定。
- 设备侧 MQTT 身份和 canonical topics 固定绑定 Wi-Fi STA MAC。`--device-id`、`--cmd-topic`、`--resp-topic` 只用于让 `config.sh set` 接入当前 MQTT 控制链路，不会改写设备保存下来的 topic 身份。
- 如果你不传 `--reboot`，设置仍会写入，但设备可能要到下一次重启后才真正使用它们。
- `config.sh search` 依赖 mDNS multicast，因此发现的是当前本地链路上的设备，不会跨路由网络搜索。
- `config.sh search` 不发现 MQTT broker 端点。发现流程的调用方仍需要从参数、环境、本地 server 状态或 `device.yml` 获得 broker。
- `init --ap-link` 只修改主机侧网口地址；它不会帮主机连接 Wi-Fi，不会改设备 Wi-Fi 凭据，也不会删除已有 alias。
