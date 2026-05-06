# MMWK 文档

这里汇总 MMWK 产品级工作流和协议参考入口。

- [MMWK Bridge 模式](./bridge.md)：bridge bring-up 起步路径。
- [本地 `server.sh` + `run.sh` Wi-Fi 刷机与 5 分钟采集示例](./collect.md)：已验证的 bridge 采集工作流。
- [出厂刷机指南](./flash.md)：空白或擦除设备的首次 ESP 刷写。
- [设备 OTA 指南](./ota.md)：ESP OTA 升级流程。
- [Wavvar MMWK 标准 CLI 控制协议 V1.1](../CLIv1_CN.md)：默认 UART/MQTT 控制协议。
- [Wavvar MMWK MCP 协议规范 V1.3](./mcpv1.md)：仅供显式选择 `--protocol mcp` 的兼容调用方使用。
