# Bridge

在 package root 下使用 `./cli/run.sh` 执行 bridge bring-up、控制、ESP OTA、雷达固件操作和采集流程。当前公开命令面和 transport 说明以 CLI README 为准。

Bridge 是面向雷达固件开发和 raw capture 的基础透明透传 profile。先用 `node info` 确认设备身份，按需配置网络和 MQTT，然后使用公开 CLI 的 `radar fw ...`、`radar config ...`、`radar raw ...` 和 `collect`。

请把 `collect` 视为这条 checklist 的官方命令。它可以通过 `-p <serial-port>` 自动发现 MQTT route 身份、引导 raw passthrough，并把 `raw_data` 与启动 trim 后的 `raw_resp` 同时采集到主机文件。

当你需要已发布包里的 task wrapper，而不是主 CLI 流程时，可以使用这些 helper：

- 用 `./cli/config.sh set` 通过 UART 或已有 MQTT 控制链路下发 Wi-Fi / MQTT 设置。
- 用 `./cli/collect.sh` 执行基于注册表的任务采集。
- 只有在明确需要 external pure-MQTT 启动期 helper 时，才使用 `./cli/collect.sh --trigger none|radar-restart|device-reboot`。

详细 bridge 契约、命令顺序和运行态确认说明见 [Bridge 参考](./bridge-reference.md)。完整的 bring-up 与 5 分钟 raw 采集流程见 [本地 MQTT/HTTP 完整采集示例](../../cli/docs/zh-cn/data-collection.md#9-本地-mqtthttp-完整采集示例)。
