# Bridge 设备 OTA 指南

本指南仅用于已运行 bridge 固件设备的 OTA 升级。

## 适用范围

- 仅适用于已运行 bridge 固件的 OTA 流程。
- 使用 `../firmwares/esp/<board>/` 下的已发布 bridge 产物。
- 不包含出厂刷机与包构建说明。

若设备为空片或已擦除，请参考 [出厂刷机指南](./flash.md)。

## 前置条件

- 设备可通过 UART 访问，且已运行 bridge 固件。
- 已发布 OTA 包位于 `../firmwares/esp/<board>/mmwk_sensor_bridge/v<version>/ota.zip`。
- 如果存在 legacy 顶层 `mmwk_sensor_bridge_full.bin`，`server.sh --device-ota --device-ota-board <board>` 也会优先使用它。

## 启动本地发布辅助脚本

请使用 `server.sh --device-ota --device-ota-board <board>` 发布 bridge OTA 固件。

```bash
cd ./cli
./server.sh run --device-ota --device-ota-board <board> --host-ip <host_ip>
```

然后在另一个终端执行：

```bash
cd ./cli
./server.sh env
```

确认：

- `MMWK_SERVER_DEVICE_OTA_PATH` 指向 `server.sh` 实际要发布的 OTA `.bin`。
- `MMWK_SERVER_DEVICE_OTA_URL` 指向同一份解析后的 OTA 载荷。
- 当 `server.sh` 是从已发布 `ota.zip` 解析设备 OTA 时，`MMWK_SERVER_DEVICE_OTA_VERSION` 会返回解析出的版本号。

解析顺序如下：

- `server.sh` 会先检查 legacy 顶层 `firmwares/esp/<board>/mmwk_sensor_bridge_full.bin`。
- 如果这个文件不存在，它会自动回退到最新发布的 `firmwares/esp/<board>/mmwk_sensor_bridge/v*/ota.zip`，解出 OTA `.bin` 后再对外提供。

## 触发 OTA 并验证

```bash
cd ..
./cli/run.sh node ota --url "$MMWK_SERVER_DEVICE_OTA_URL" -p <port>
./cli/run.sh node info -p <port>
```

成功标准：

- OTA 命令成功，设备重连。
- OTA 后 `node info.version` 与期望版本一致。
- 如果 `MMWK_SERVER_DEVICE_OTA_VERSION` 非空，它也应与 `node info.version` 一致。
