# Wavvar MMWK

English version: [English docs](./README.md)

Wavvar MMWK（mmWave Kit）是一个面向产品化的毫米波雷达传感器平台。本目录包含运行和管理 MMWK 设备所需的预编译固件、文档和 CLI 工具。

## 特性

- **雷达开发快速起步**：默认的 [**BRIDGE 模式**](./docs/zh-cn/bridge.md) 会把 MMWK 变成透明网关，让你可以通过 MQTT（[CLIv1](./docs/CLIv1_CN.md) 默认，[MCPv1](./docs/zh-cn/mcpv1.md) 兼容）将原始雷达数据直接流式传输到上层应用或 AI Agent，几分钟内就能开始原型验证。
- **兼容 TI 固件**：可直接运行标准 TI 雷达二进制，无需修改。你可以使用完整的 TI 雷达生态，在 TI EVM 上开发，最终零迁移部署到 MMWK。
- **双 MCU 架构**：将雷达处理（TI C674x）与应用逻辑（ESP32/ESP32S3）分离，在保证实时雷达性能的同时，保留复杂联网、AI 逻辑和自定义应用开发能力。
- **灵活的数据管线**：支持 BRIDGE、HUB、RAW 等多种运行模式，可按场景在透明转发和板载智能处理之间切换。
- **AI 原生支持**：设备端通过 UART 和 MQTT 内置标准 CLI JSON 控制协议（[CLIv1](./docs/CLIv1_CN.md)），主机端提供对大语言模型高度友好的 CLI 工具；同时保留 [MCP/JSON-RPC 2.0](./docs/zh-cn/mcpv1.md) 的兼容层，供显式指定 `--protocol mcp` 的调用方使用。
- **完整工具链**：包含开源 CLI、集成测试和文档，降低开发门槛，并提供从开发到部署的参考实现。
- **面向量产与部署**：具备 OTA、标准化配置管理和经过现场验证的可靠性，适合量产与大规模部署。
- **生态与定制能力**：支持 200Hz 高频雷达固件、人员跟踪、生命体征等多类应用，也支持云平台和移动端的全栈定制。

## 硬件

### 架构

每块 MMWK 板卡都由两个 MCU 组成：ESP 和雷达芯片。`mmwk` 组件为 ESP 芯片和雷达芯片提供统一驱动。

![MMWK Hardware Architecture](./docs/mmwk_arch.png)

ESP 芯片通过三种接口与雷达芯片通信：

- **CMD UART**：用于发送配置与控制命令
- **DATA UART**：用于接收雷达输出数据（点云、TLV 帧等）的高速通道
- **SPI**：雷达数据传输的另一种高带宽接口

ESP 的 Flash 分区中包含 NVS（设备设置）、PHY 初始化数据、出厂应用，以及一个用于存放雷达固件二进制与配置文件的 **assets** 分区。在 bridge `auto`、hub `auto` 这类受管启动流程里，ESP 可以从该分区加载雷达固件，并自动完成雷达刷写与配置。

部分型号还带有 ESP 侧用户 IO、音频和 4G/LTE 模块。主机通过 USB-UART/Serial 与 ESP 连接，实现本地访问。

### 板卡型号

Name | ESP | Audio | Radar | LED | 4G/LTE Support
--- | --- | --- | --- | --- | ---
[MINI](./modules/mini_cn.md) | ESP32 | No | IWR6843AoP | 1 | No
[PRO](./modules/pro_cn.md) | ESP32S3 | Optional | IWR6843AoP | 1 | No
[RPI](./modules/rpx_cn.md#3-rpi-6432-感知模块) | ESP32S3 | Yes | IWRL6432AoP | 1 | No
[CFH](./modules/rpx_cn.md#2-6843-系列感知模块) | ESP32S3 | Yes | IWR6843AoP | 1 | No
IOT | ESP32S3 | No | IWR6843AoP | 1 | Yes
[WDR](./modules/mdr_cn.md) | ESP32S3 | Yes | IWRL6432AoP | 2 | Optional

这里的 `LED` 特指雷达芯片侧 LED，其 IO 继承自 TI 参考例程，必须由雷达固件控制。

所有板卡还包含一个由 ESP 控制的按键和一个由 ESP 控制的 LED。

如果你需要的是产品线级别的硬件背景，而不只是 [bridge 工作流说明](./docs/zh-cn/bridge.md)，建议先看 [模组产品总览](./modules/README_CN.md)。RPX 线现在已经有 [MINI 模组简介](./modules/mini_cn.md) 和 [PRO 模组简介](./modules/pro_cn.md) 两份独立文档；[RPI](./modules/rpx_cn.md#3-rpi-6432-感知模块) 和 [CFH](./modules/rpx_cn.md#2-6843-系列感知模块) 仍放在 [RPX 模块使用指南](./modules/rpx_cn.md) 中。`WDR/MDR` 的控制板与雷达板路径可继续阅读 [MDR 模块简介](./modules/mdr_cn.md)、[WDR-M 主控承载板简介](./modules/wdr-m_cn.md)、[WDR-4G 通信板简介](./modules/wdr-4g_cn.md)、[ML6432A_BO 模组简介](./modules/ml6432a_bo_cn.md) 和 [ML6432A 模组简介](./modules/ml6432a_cn.md)。

双 MCU 架构让用户可以快速评估任意 TI 雷达固件。你可以继续使用 TI 的工具链和开发板完成雷达固件开发与调试，再在 MMWK 的 ESP MCU 上开发应用。像 People Tracking、Vital Signs 这类 TI 现有固件都可以运行在 MMWK 上。

ESP 芯片充当雷达芯片的控制器，负责供电、刷写固件、配置雷达，以及进行补充的数据处理；雷达芯片则负责信号处理与数据生成。`mmwk` 组件对用户屏蔽这两颗芯片的细节，提供统一接口。

ESP 也可用于实现应用层算法，例如 AI 推理、MQTT，以及自定义控制/协议层（CLIv1 默认，MCPv1 兼容）等。

### MMWK 与 TI 评估板对比

MMWK 使用与 TI 相同的雷达芯片，并完全兼容标准 TI 固件二进制。推荐的开发流程是结合两种平台的优势：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Recommended Workflow                             │
│                                                                         │
│  Stage 1: Algorithm Research            Stage 2: Deployment & Scale     │
│  ─────────────────────────              ─────────────────────────────   │
│  TI EVM + DCA1000                       MMWK                            │
│                                                                         │
│  • Lab environment                      • Real-world scenarios          │
│  • Raw ADC capture via DCA1000          • Standalone operation          │
│  • MATLAB / Python offline analysis     • WiFi / MQTT / 4G connectivity │
│  • Algorithm prototyping & tuning       • On-device ESP processing      │
│  • Full TI toolchain (CCS, mmWave SDK)  • OTA firmware updates          │
│                                         • CLIv1 控制面（默认）+ MCPv1 兼容   │
│                                                                         │
│  ──────────────── firmware binary ──────────────▶                       │
│  Same .bin + .cfg works on both platforms                               │
└─────────────────────────────────────────────────────────────────────────┘
```

**阶段 1：算法研发（TI EVM + DCA1000）**：使用 TI 官方评估板（例如 IWR6843AoP EVM）配合 DCA1000 采集卡完成 ADC 原始数据采集、MATLAB/Python 离线分析和算法原型验证。这个阶段非常适合调优 chirp 参数、构建信号处理链以及在实验室环境中验证探测性能。

**阶段 2：场景扩展与应用部署（MMWK）**：当算法与固件在 TI EVM 上验证完成后，可以将同一份 `.bin` + `.cfg` 刷到 MMWK 板卡上。MMWK 提供 WiFi/MQTT/4G 联网、ESP 板载处理、OTA，以及标准 CLIv1 控制面（含 MCPv1 兼容），帮助你把实验室研究快速落地到养老、智能家居、医疗等真实场景中。

> **关键点**：在 TI 评估板上开发和验证过的固件二进制可以直接加载到 MMWK，无需修改。MMWK 是对 TI 生态的扩展，而不是替代。

### Bring Your Own Device & Software

MMWK 支持你把自己的软件和硬件带入生态：

- **软件（BYOS）**：可以基于现有应用层继续开发，也可以完全重写固件栈以适配专有感知逻辑与云端集成。
- **硬件（BYOD）**：可以将 MMWK 相关软件运行在你自己的硬件上。我们也在持续扩展对 TI 标准 EVM 与 ESP32 开发板的支持。

## Getting Started

MMWK 默认以 [BRIDGE 模式](./docs/zh-cn/bridge.md) 运行。请先根据设备当前状态选择入口：

1. **[出厂刷机指南](./docs/zh-cn/flash.md)**：如果板卡是空片或已被擦除，请先从这里完成第一次 ESP bridge 烧录。
2. **[MMWK Sensor BRIDGE 模式](./docs/zh-cn/bridge.md)**：如果设备已经在运行 bridge 固件，并且你想跑通第一次端到端 bring-up，包括雷达刷写和数据采集，请从这里开始。
3. **[设备 OTA 指南](./docs/zh-cn/ota.md)**：如果设备已经在运行 bridge 固件，而你只需要做 ESP OTA 更新，请直接看这里。

[MMWK Bridge 模式](./docs/zh-cn/bridge.md) 是 bridge 模式的规范起步入口，会继续把你分流到出厂刷机、雷达刷写加采集、ESP OTA，以及更深入的 [MMWK Sensor BRIDGE 参考](./docs/zh-cn/bridge-reference.md)。

## 工具

每台 MMWK 设备都通过标准协议暴露其能力。开源 CLI 通过该协议与设备通信，任何自定义应用也可以使用同样的协议。

```
┌─────────────────┐     CLIv1（默认）/ MCPv1（兼容）     ┌──────────────────┐
│   mmwk_cli      │ ──── UART (serial) or MQTT ──────▶ │  MMWK Device     │
│   (Python)      │ ◀──── notifications / responses ── │  (ESP firmware)  │
└─────────────────┘                                    └──────────────────┘
       ▲                                                        ▲
       │  same protocol                                         │
       ▼                                                        │
  Custom App /                                          CLIv1 内置协议（默认）
  AI Agent (Claude, etc.)                               （可选 MCPv1 兼容层）
```

### 控制协议

当前主机侧工作流默认使用一套标准 CLI JSON 协议，它保留了与旧 MCP tool 层一致的 service/action 语义。MCP 仍然保留，供显式指定 `--protocol mcp` 的兼容调用方使用。

设备通过两种传输方式接收命令并推送传感器事件：

- **UART**（115200 波特率，按行分隔 JSON）
- **MQTT**（用于 WiFi / LAN / 云端远程访问）

标准 CLI JSON 协议见 [Wavvar MMWK 标准 CLI 控制协议 V1.0](./docs/CLIv1_CN.md)。

如果你要走 MCP 兼容路径，任何兼容 MCP 的客户端，包括 Claude 这类 AI Agent，仍然可以发现工具（`tools/list`）、调用设备动作（`tools/call`），并接收实时传感器通知，而无需自定义驱动。完整 MCP 兼容规范见 [Wavvar MMWK MCP 协议规范 V1.3](./docs/zh-cn/mcpv1.md)。

### MMWK CLI（开源）

[mmwk_cli](./mmwk_cli/) 是一个 **开源** Python CLI，它默认使用标准 CLI JSON 协议，并在需要时支持回退到 MCP，同时也是构建自定义主机侧应用的参考实现。

- **跨平台**：Python 3.10+，支持 macOS、Linux、Windows
- **双传输**：UART（本地）与 MQTT（远程）
- **固件更新**：支持 HTTP OTA 和 UART 分块传输
- **运行时重配置**：支持 `radar reconf`，可在不重新刷写 firmware 的前提下切换运行时 `welcome` / `verify` / cfg 行为
- **启动契约发现**：`radar status` 和 `mgmt.radar_runtime` 会暴露 `start_mode` 与 `supported_start_modes`；`fw.boot_mode` 则表示当前运行态真实使用的雷达 boot path。BRIDGE 支持 `["auto", "host"]`，HUB 支持 `["auto"]`
- **设备控制**：握手、雷达启停、WiFi/MQTT 配置、固件分区管理
- **零配置 shell 包装脚本**：`./mmwk_cli/mmwk_cli.sh` 是 macOS/Linux 下的默认入口；如果你要直接调用 Python，请先进入 `mmwk_cli` 目录，再使用 `PYTHONPATH=scripts python3 -m mmwk_cli`
- **内置本地服务助手**：`./mmwk_cli/server.sh` 提供开箱即用的本地 MQTT Broker 与 HTTP 文件服务，辅助 OTA 升级与数据采集
- **AI 命令行支持**：CLI 接口和参数设计对大语言模型（LLM）极其友好，可被 Claude 等自治 AI Agent 直接调用以发现、配置和控制雷达
- **附带集成测试**：包含端到端刷写、OTA 和持久化验证

完整用法与命令参考见 [CLI README](./mmwk_cli/docs/zh-cn/README.md)。

## 雷达固件

任何能运行在受支持雷达芯片上的固件，都可以与 MMWK 配合使用。你可以从 TI 官网下载最新固件：

- [mmWave SDK](https://www.ti.com/tool/download/MMWAVE-SDK) 用于 IWR6843AoP
- [mmWave Low Power SDK](https://www.ti.com/tool/download/MMWAVE-L-SDK) 用于 IWRL6432AoP
- [RADAR-TOOLBOX](https://www.ti.com/tool/download/RADAR-TOOLBOX) 也是重要资源

大多数标准 TI 固件都需要配套配置文件。该文件是一个文本文件，包含雷达运行参数；在收到配置文件前，雷达处理不会启动。也有少数 TI 固件无需配置文件，加载后即可开始运行。

> **注意**：配置文件与固件一一对应。请务必使用正确的 `*.cfg`。强烈建议先在 TI 评估板上验证固件和配置文件，再用于本项目。

### TI 预编译雷达固件

以下雷达固件已包含在 `firmwares/radar/` 中：

| Chip | Firmware | Directory | Files |
|------|----------|-----------|-------|
| IWR6843AoP | Out-of-box Demo | `iwr6843/oob/` | `.bin` + `.cfg` |
| IWR6843AoP | Vital Signs Detection | `iwr6843/vital_signs/` | `.bin` + `.cfg` |
| IWRL6432AoP | Presence Detection | `iwrl6432/presence/` | `.appimage` + `.cfg` |

### MMWK_ROID

ROID 是 Wavvar 面向高采样 ROI 观测与精细微动分析的一条毫米波雷达固件路线。它保留从 `RAW ROI` 到 `PHASE`、`BREATH`、`HEART` 的分层输出，比只给粗粒度存在结果的链路更适合高精度心率 / 呼吸观测，以及研究型信号分析。

它既可作为更高精度生命体征观测的固件基础，也为类心电波形研究和血压算法验证保留了继续扩展的数据入口。该固件按商业授权方式提供，请联系 `bp@wavvar.com`。

完整介绍见 [中文文档](./docs/zh-cn/roid.md)；English version: [MMWK_ROID Overview](./docs/en/roid.md)。

## ESP 固件

预编译 ESP 固件位于 `firmwares/esp/`。每个变体对应特定板型和功能组合。

Bridge 固件生命周期文档：

- [出厂刷机指南](./docs/zh-cn/flash.md)：面向空片/擦除设备和首刷包流程。
- [设备 OTA 指南](./docs/zh-cn/ota.md)：面向已运行 bridge 固件设备的 OTA 更新流程。

### mmwk_sensor_bridge

`mmwk_sensor_bridge` 是运行在 ESP 上的 BRIDGE 模式固件。在该模式下，ESP 不进行雷达信号处理，而是作为雷达芯片与外部主机之间的透明桥接层。

**核心特性：**

- **雷达固件管理**：在 bridge `auto` 下，ESP 可以自动从 SPIFFS 载入雷达固件（`.bin` + `.cfg`）并执行受管 bring-up；在 bridge `host` 下，启动所有权留给主机，ESP 不会自动下发雷达配置
- **OTA 刷写**：支持通过 HTTP/MQTT 远程更新雷达固件，也支持 UART 分块传输
- **原始数据转发**：将雷达原始数据帧直接转发到主机，不做信号处理
- **控制协议**：在 UART（115200）和 MQTT 上内置标准 CLI JSON 协议（CLIv1）；同时保留 MCPv1 JSON-RPC 兼容服务端，供显式指定 `--protocol mcp` 的调用方使用
- **WiFi 配网**：首次启动时创建 `MMWK_XXXX` 热点，用户可通过浏览器门户配置 WiFi
- **MQTT 中继**：连上 WiFi 后，通过 MQTT Broker 中继雷达数据与控制命令

### mmwk_sensor_hub

`mmwk_sensor_hub` 是运行在 ESP 上的 HUB 模式固件。它在 BRIDGE 能力之上增加了板载雷达处理，并额外暴露 `hub` MCP 工具，用于更高层的感知工作流。

当前未提供该固件的预编译版本。

## 法律声明

`firmwares/radar/` 中提供的雷达固件二进制既包含来自 [**Texas Instruments (TI)**](https://www.ti.com) 的原始构建，也包含来自 [**Wavvar**](https://wavvar.com) 的自定义构建。

- **TI 固件**：来自 TI 工具箱或 SDK 的二进制仍归 Texas Instruments 所有，这些文件在仓库中仅用于评估和集成。官方发布请参考 [TI Radar Toolbox](https://dev.ti.com/tirex/explore/node?node=A__AGun-M.W.r.X.G.X.r.G.X.r.G.X.A)。
- **Wavvar 固件**：自定义二进制（例如 MMWK_ROID）由 Wavvar 开发并拥有。
