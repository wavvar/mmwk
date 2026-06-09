# MMWK 文档

这里汇总 MMWK 产品级工作流和协议参考入口。

- [mmWave Sensor Development Kit](./mmwk-sensor.md)：共享 sensor 平台 bring-up 起步路径。
- [Bridge 参考](./bridge-reference.md)：bridge 专属运行时契约和确认清单。
- [本地 `server.sh` + `run.sh` Wi-Fi 刷机与 5 分钟采集示例](./collect.md)：已验证的 sensor 采集工作流。
- [出厂刷机指南](./flash.md)：空白或擦除设备的首次 ESP 刷写。
- [设备 OTA 指南](./ota.md)：ESP OTA 升级流程。
- [CLI README](../../cli/docs/zh-cn/README.md)：macOS/Linux/Git Bash 与 Windows PowerShell 的主机 wrapper 入口。
- [Wavvar MMWK 标准 CLI 控制协议 V1.1](../CLIv1_CN.md)：默认 UART/MQTT 控制协议。
- [Wavvar MMWK MCP 协议规范 V1.3](./mcpv1.md)：仅供显式选择 `--protocol mcp` 的兼容调用方使用。
