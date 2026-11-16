# 聚合 SDK 第一阶段迁移预览（尚未发布）

本文仅适用于 [SDK PR #70](https://github.com/wavvar/mmwk_sdk/pull/70) 配套的 `mmwk/arch_v2` 开发分支。`mmwk/dev` 与 `main` 仍使用当前按板型交付的旧版 SDK。新的四组合构建与 PRO/WDR 共用 S3 归档**尚未完成目标工具链和硬件验收**。

计划中的公共组件只有两个：`mmwk_board` 交付由消费方编译的板型配置源码；`mmwk_sdk` 按验证通过的 ESP target/ABI 兼容组交付聚合 `libmmwk_sdk.a`。消费方需在 ESP-IDF 早期依赖展开前明确选定 6843/6432 后端、配对固件与配置以及能力组合。

四种组合：`offline`（纯雷达）、`local-control`（雷达加本地控制）、`wifi-data`（雷达加 Wi-Fi、无管理控制）、`default`（受支持的兼容功能）。按键与 LED 业务策略归应用；禁用的 Wi-Fi/MQTT/HTTP、管理控制或 legacy UI 不应进入基础镜像。

## 当前 arch_v2 可以使用的入口

旧式默认构建保持兼容：

```sh
cd sdk/examples
./build.sh presence mini
./build.sh presence pro
./build.sh presence wdr
./build.sh all
```

也可写 `./build.sh presence pro --preset default`，其输出独立放在 `build/presence/pro/default`。目前脚本能识别其他 preset 名称，但会**明确报错拒绝构建**，绝不会把旧版完整固件误标成 offline 等新能力组合。

## 解锁新组合之前必须完成的条件

聚合包必须带有经完整校验的 schema-3 `release-manifest.json`、版本匹配的公共头文件和板型源码、正确 ABI 的聚合归档、对应 firmware/config 资源，以及包含包摘要与消费选择的锁定记录。presence 必须真实迁到 RAW 订阅和按能力装配，且在初始化前关闭 legacy UI。最终候选必须通过三板 × 四组合全部 12 次目标构建/链接，再进入完整设备及全部在用硬件版本的实机验收。

纯离线应用不需要先安装主机 CLI。真正完成目标构建之后，公开说明将补齐首次刷写资源分区及 `idf.py -B <build-dir> -p <port> flash monitor` 的准确步骤；不可用动态串口编号判断板型。

**合并前只能提交 `mmwk/arch_v2`，不得调用当前固定向 `mmwk/dev` 投递的正式发布器。** SDK 合并 main 也不自动构成发布授权。

## CLI 刷写会话兼容

`mmwk/arch_v2` 中的主机 CLI 现可识别旧版 `err=-2` 与新版 SDK 的 `err=-3415` 雷达 UART 升级会话失活反馈，且不会把无关的 `err=-20`、`err=-34150` 误判为同类问题。原有的有界重试及重开会话逻辑不变。当前只进行主机模拟传输回归，**未执行真实设备刷写或 OTA**。CLI 仍独立维护，不进入 SDK 候选覆盖路径。
