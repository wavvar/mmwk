# Bridge 设备 OTA 指南

本指南仅用于已运行 bridge 固件设备的 OTA 升级。

## 适用范围

- 仅适用于已运行 bridge 固件的 OTA 流程。
- 使用 `../firmwares/esp/<board>/` 下的预编译产物。
- 不包含出厂刷机与包构建说明。

若设备为空片或已擦除，请参考 [出厂刷机指南](./flash.md)。

## 前置条件

- 设备可通过 UART 访问，且已运行 bridge 固件。
- 设备已运行 bridge 固件。
- OTA 固件位于 `../firmwares/esp/<board>/mmwk_sensor_bridge_full.bin`。
- 可选版本文件位于 `../firmwares/esp/<board>/mmwk_sensor_bridge.version`。

## 启动本地发布辅助脚本

请使用 `server.sh --device-ota --device-ota-board <board>` 发布 bridge OTA 固件。

```bash
cd ./mmwk_cli
./server.sh run --device-ota --device-ota-board <board> --host-ip <host_ip>
```

然后在另一个终端执行：

```bash
cd ./mmwk_cli
./server.sh env
```

确认：

- `MMWK_SERVER_DEVICE_OTA_URL` 指向 `mmwk_sensor_bridge_full.bin`。
- 当版本文件存在时，`MMWK_SERVER_DEVICE_OTA_VERSION` 与 `mmwk_sensor_bridge.version` 一致。

## 触发 OTA 并验证

```bash
cd ..
./mmwk_cli/mmwk_cli.sh device ota --url "$MMWK_SERVER_DEVICE_OTA_URL" -p <port>
./mmwk_cli/mmwk_cli.sh device hi -p <port>
```

成功标准：

- OTA 命令成功，设备重连。
- OTA 后 `device hi.version` 与 `mmwk_sensor_bridge.version` 中的期望版本一致。
