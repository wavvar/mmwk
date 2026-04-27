# 配置助手

`config.sh set` 用来配置设备的 Wi-Fi 与 MQTT 设置，而且不会改动官方 `run.sh` 的命令面。

工作目录应为 `cli` 目录：

```bash
cd ./cli
```

## 它负责什么

- 通过 `network wifi` 下发 Wi-Fi 凭据
- 4G 配置请直接使用官方 `network 4g` 和 `network priority` 命令
- 通过 `network mqtt` 下发 MQTT 设置
- 按需通过 `node reboot` 重启设备
- 按需启动或复用 `server.sh`，并把本地 broker URI 反向写回设备

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

### 2. 只走 MQTT 控制面

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

### 3. 4G 与网络优先级

`config.sh set` 仍然只负责 Wi-Fi/MQTT onboarding。PRO/WDR 的 4G 配置请直接使用官方 `run.sh` 网络命令：

```bash
./run.sh network 4g --apn YOUR_APN -p /dev/cu.usbserial-0001
./run.sh network priority --pref 4g -p /dev/cu.usbserial-0001
./run.sh network priority --pref wifi -p /dev/cu.usbserial-0001
```

保存 Wi-Fi 凭据不会改变 4G 优先级。4G 失败不会自动回退到 Wi-Fi；需要 Wi-Fi 时请显式切换优先级。

## 关键参数

- `--transport uart|mqtt`：当前用于下发配置的控制链路
- `--ssid` / `--password`：Wi-Fi 凭据
- `--mqtt-uri` / `--mqtt-user` / `--mqtt-pass`：保存到设备里的 broker 与鉴权设置
- `--device-id`，以及可选的 `--cmd-topic` / `--resp-topic`：告诉 `config.sh set` 当前 MQTT 控制链路应该走哪组 topic
- `--server-local`：启动或复用 `server.sh`，并使用它解析出的 broker URI
- `--server-state-dir`、`--server-serve-dir`、`--server-upload-dir`、`--server-host-ip`、`--server-target-ip`、`--server-mqtt-port`、`--server-http-port`：控制 `server.sh` 的启动/复用方式
- `--reboot`：写完设置后重启设备

## 说明

- 使用 `--server-local` 时不要再手动传 `--mqtt-uri`；broker 由 `server.sh` 决定。
- 设备侧 MQTT 身份和 canonical topics 固定绑定 Wi-Fi STA MAC。`--device-id`、`--cmd-topic`、`--resp-topic` 只用于让 `config.sh set` 接入当前 MQTT 控制链路，不会改写设备保存下来的 topic 身份。
- 如果你不传 `--reboot`，设置仍会写入，但设备可能要到下一次重启后才真正使用它们。
