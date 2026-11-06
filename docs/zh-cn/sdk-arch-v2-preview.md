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

schema-3 Manifest 必须包含覆盖**全部**受管文件的 `file_sha256`（而非仅验证当前板型归档），包括板型配置源码、公开 CMake、两类雷达资源、`NOTICE`、许可证及补丁。Manifest 自身的 SHA256 由 `mmwk-sdk.lock.json` 锁定；即使不是本次选中的文件，只要缺失或被篡改也必须失败。聚合包必须带有经完整校验的 schema-3 `release-manifest.json`、版本匹配的公共头文件和板型源码、正确 ABI 的聚合归档、对应 firmware/config 资源，以及包含包摘要与消费选择的锁定记录。presence 必须真实迁到 RAW 订阅和按能力装配，且在初始化前关闭 legacy UI。最终候选必须通过三板 × 四组合全部 12 次目标构建/链接，再进入完整设备及全部在用硬件版本的实机验收。

纯离线应用不需要先安装主机 CLI。真正完成目标构建之后，公开说明将补齐首次刷写资源分区及 `idf.py -B <build-dir> -p <port> flash monitor` 的准确步骤；不可用动态串口编号判断板型。

**合并前只能提交 `mmwk/arch_v2`，不得调用当前固定向 `mmwk/dev` 投递的正式发布器。** SDK 合并 main 也不自动构成发布授权。

## CLI 刷写会话兼容

`mmwk/arch_v2` 中的主机 CLI 现可识别旧版 `err=-2` 与新版 SDK 的 `err=-3415` 雷达 UART 升级会话失活反馈，且不会把无关的 `err=-20`、`err=-34150` 误判为同类问题。原有的有界重试及重开会话逻辑不变。当前只进行主机模拟传输回归，**未执行真实设备刷写或 OTA**。CLI 仍独立维护，不进入 SDK 候选覆盖路径。

## 应用独立管理按键与 LED

新版聚合 SDK 在原有 `startup` 参数中增加
`disable_legacy_key`、`disable_legacy_led` 字段，**无需新增公开导出函数**。
在调用 `mmwk_sensor_bridge_run()` 前设置为 `true`，即可跳过 SDK
默认按键 GPIO/任务和 LED 驱动/延迟任务的初始化，让应用独占相应 GPIO
并自行实现按键、灯效策略。这两个字段**不等于**关闭 Wi-Fi、自动配网或其他
网络服务；网络能力需要独立选择。内部旧固件保留零默认值和现有行为。

原生 presence 使用 `#ifdef MMWK_SENSOR_STARTUP_LEGACY_UI_POLICY_V1`
适配新版头文件；在尚未替换的旧版分板库中不引用不存在的字段。
这仅证明源码适配，完整聚合构建和实体按键/LED 争用还需要后续验收。

## 不依赖主机 CLI 的构建、首次刷写和监控

首先加载匹配版本的 ESP-IDF，并根据实物确认板型；**不能仅凭 USB
串口号推断硬件型号**。以下操作只依赖 ESP-IDF、Python 和公开 SDK：

```sh
cd sdk/examples
./build.sh presence mini
./flash.sh presence mini --port /dev/ttyUSB0 --monitor
# 仅监控，不刷写：
./flash.sh presence mini --port /dev/ttyUSB0 --monitor-only

# 指定 default 时使用独立输出目录：
./build.sh presence wdr --preset default
./flash.sh presence wdr --preset default --port /dev/ttyACM0 --monitor
```

`flash.sh` 必须显式提供 `--port`，并检查构建目录中的
`sdkconfig` 板型/ESP 目标/size 优化、`flasher_args.json` 和应用
及 `assets.bin` 镜像；不允许只刷 ESP 应用而漏刷雷达资源。
presence 工程已有
`spiffs_create_partition_image(assets ... FLASH_IN_PROJECT)`，因此
`idf.py flash` 首刷时会一并写入配对的雷达固件、配置和 `meta.json`
分区。`--monitor-only` 不执行刷写。实际设备执行仍属于 S6，不冒充已验收。

独立 ESP-IDF 应用可只加入交付的 `sdk/components` 作为组件根，
在应用 `main/CMakeLists.txt` 中依赖 `mmwk_sdk`，选用目标板型
`sdkconfig.defaults` 并保持 `CONFIG_COMPILER_OPTIMIZATION_SIZE=y`。
自己的 `assets` 分区应只包含匹配同一雷达家族的固件/config/catalog，
且使用 `FLASH_IN_PROJECT` 一并首刷，不能从相邻私有仓自动回退资源。
新版聚合库可用之后，还必须校验完整 Manifest 和消费锁；当前旧库
暂时只支持既有 default 功能。Windows 上可指定相应 COM 串口。

## 原生 presence 自定义按键和 LED

在 `sdk/examples/presence/main/main.c` 编辑：

```c
static const presence_ui_policy_t s_ui_policy = {
    .claim_key = false,  // 应用需要读取按键时才开启
    .claim_led = false,  // 应用需要独立控制 LED 时才开启
    .led_initially_on = false,
};
```

`presence_ui_configure(&s_ui_policy)` 在 `mmwk_sensor_bridge_run()`
**之前**执行。默认两项均为 false：应用不初始化任何 GPIO，也不会创建
按键／灯效任务。新版聚合 SDK 提供 `mmwk_board_get_config()`，
启用相应选项后由应用独立占用 IO，可通过
`presence_ui_read_key()`、`presence_ui_set_led()` 自行实现按键防抖、
事件和 LED 状态；示例**不创建**默认按键任务、网络手势或灯效动画。
MINI/PRO/WDR 的实际引脚行为留在最后 S6 验收。
旧版分板库没有转移 GPIO 所有权的能力，因此开启占用时明确返回
`ESP_ERR_NOT_SUPPORTED`；保持默认关闭时仍兼容旧例程。

## 可选的外部 RAW 命令入口

新 SDK 增加了应用启动前可选择的
`startup.disable_external_raw_commands = true`（使用
`MMWK_SENSOR_STARTUP_RAW_COMMAND_POLICY_V1` 宏判断支持）。
该配置不再分配外部 RAW 命令 worker、队列及复制数据缓冲池；
雷达内部启动/配置命令和 RAW 输出订阅不受影响。
默认为 **false**，保持原有主机控制、Bridge 与 Hub 行为。
仅当应用明确不需要从 UART/MQTT 接收外部 RAW 命令时才关闭；
它**不代表**关闭全部无线网络能力。ESP 目标构建、并发停止和重复启动
仍需验证，当前已发布旧包没有这个字段。
