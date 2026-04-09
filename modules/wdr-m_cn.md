# WDR-M 主控承载板简介

## 目录

- [1. 板卡概述](#1-板卡概述)
- [2. 技术规格和主要特性](#2-技术规格和主要特性)
- [3. 系统角色与兼容性说明](#3-系统角色与兼容性说明)
- [4. 接口说明](#4-接口说明)
- [4.1 USB Type-C 接口参考](#41-usb-type-c-接口参考)
- [4.2 状态 LED 接口参考](#42-状态-led-接口参考)
- [4.3 按键接口参考](#43-按键接口参考)
- [4.4 外挂雷达接口说明](#44-外挂雷达接口说明)
- [5. 连接关系与板级参考图](#5-连接关系与板级参考图)
- [6. 相关文档](#6-相关文档)

## 1. 板卡概述

`WDR-M` 是 `WDR` 系统中的主控承载板。在详细硬件说明中，该角色统一以 `MDR-M` 表示，用于说明具体板级结构。`WDR` 完整模组由 `ML6432A_BO` 雷达板、`MDR-M` 主控板和 `WDR-4g` 通信板组成，其中 `WDR-M` 负责供电分配、本地控制、外围管理和板间互连。

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/mdr-module-top-view.png" alt="MDR 模块顶视图" width="80%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">MDR 模块顶视图</p>
</div>

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/wdr-module-front-view.png" alt="WDR 模块正面" width="44%" style="display: inline-block; margin: 0 12px;" />
  <img src="./img/MDR/wdr-module-back-view.png" alt="WDR 模块背面" width="44%" style="display: inline-block; margin: 0 12px;" />
  <p style="margin: 4px 0 0 0;">WDR 系列外观参考图</p>
</div>

## 2. 技术规格和主要特性

| 类别 | 项目 | 规格 |
| --- | --- | --- |
| **供电** | 外部供电 | 5V⎓2A |
|  | 适配器 | 100–240V AC 输入 |
|  | 整机功耗 | 典型：< 2W |
|  | | 峰值：< 5W（含外设） |
| **运行参数** | 安装方式 | 吸顶安装或壁挂安装 |
|  | 工作温度 | 0°C 至 45°C（整机环境温度） |
|  | 工作湿度 | < 95%（无冷凝） |
| **连接与集成** | 云端协议 | MQTT、HTTP、HTTPS |
|  | WiFi | Wi-Fi 802.11b/g/n, 20/40MHz |
|  |  | Station / SoftAP / Station + SoftAP |
|  |  | 最大 150 Mbps（802.11n, 40 MHz，理论值,实际取决于网络环境）|
|  | Bluetooth | Bluetooth 5 (LE) |
|  | 本地通信 | USB （可配置，见注 1） |
| **硬件架构** | 处理架构 | 双芯片异构架构（外挂雷达板 + 主控 MCU） |
|  | 主控MCU | ESP32-S3（Xtensa LX7 双核，最高 240 MHz） |
|  | 片上内存 | 512 KB |
|  | PSRAM | 8 MB |
|  | Flash 存储 | 8 MB（主控 MCU） |
|  | I/O 与指示器 | 1× 状态 LED、1× 按键 |
|  | 外挂雷达(可选) | 雷达芯片 / 雷达板外挂，通过接口接入 WDR 系统 |
|  | 蜂窝网络（可选）| wdr-g 外挂 （见注 1） |

> 注 1: 外挂4g使用usb通道，他和usb外接只能二选一；usb和ttl串口二选一

## 3. 系统角色与兼容性说明

从系统结构上看，`WDR-M` 位于中间层，负责连接雷达板与 `WDR-4G` 通信板，同时提供本地调试、板级控制以及通信路由所需的接口。

在功能支持层面，`WDR-M` 支持 `ML6432Ax` 系列。差别主要体现在机械连接方式：

| 兼容雷达板 | 集成方式 | 说明 |
| --- | --- | --- |
| `ML6432A_BO` | 直插连接 | 可通过板对板连接方式直接插接到 `WDR-M` |
| `ML6432A` | 转接连接 | 在功能上同样受支持，但需要通过转接线连接 |

两种雷达板在雷达侧使用相同的接口定义。如果用户只需要进行独立雷达板的烧录或调试，`ML6432A` 与 `ML6432A_BO` 都可以按统一的 `ML6432Ax` 使用流程操作。

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/mdr-m-board-attachment-orientation.png" alt="MDR-M 插接方向参考" width="42%" style="display: inline-block; margin: 0 12px;" />
  <img src="./img/MDR/ml6432a-bo-attachment-orientation.png" alt="ML6432A_BO 插接方向参考" width="42%" style="display: inline-block; margin: 0 12px;" />
  <p style="margin: 4px 0 0 0;">WDR-M 与 ML6432A_BO 的直插方向参考</p>
</div>

## 4. 接口说明

`WDR-M` 板上接口说明主要包括 `USB Type-C`、状态 `LED`、按键输入以及外挂雷达接入方式。

### 4.1 USB Type-C 接口参考

`P7` 为 `USB Type-C` 接口，可用于本地连接或调试维护。

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/mdr-m-usb-typec-reference.png" alt="MDR-M USB Type-C 参考图" width="75%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">图 1 WDR-M 上的 USB Type-C 接口参考</p>
</div>

### 4.2 状态 LED 接口参考

`WDR-M` 板上提供状态 `LED` 指示，便于快速观察调试状态。

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/mdr-m-status-led-reference.png" alt="MDR-M LED 参考图" width="60%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">图 2 WDR-M 上的状态 LED 参考</p>
</div>

### 4.3 按键接口参考

`WDR-M` 板上提供按键输入，可用于本地控制或交互行为设计。

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/mdr-m-key-reference.png" alt="MDR-M 按键参考图" width="80%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">图 3 WDR-M 上的按键参考</p>
</div>

### 4.4 外挂雷达接口说明

`WDR-M` 板上不集成雷达芯片，雷达部分采用外挂方式接入。系统集成时，外挂雷达板通过 `WDR-M` 与 `4G Cat1` 通信板协同工作；在文档层面，`WDR-M` 主要保留主控与接口侧说明，不单独展开板载雷达参数。

## 5. 连接关系与板级参考图

`4G Cat1` 通信板和雷达板都通过专用板级信号连接到 `WDR-M`。下列图示用于说明 `WDR-M` 与雷达板、通信板之间的主要连接关系。

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/mdr-m-to-radar-board-connection.png" alt="MDR-M 与雷达板连接参考图" width="85%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">图 4 WDR-M 与雷达板连接参考图</p>
</div>

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/mdr-m-to-cat1-board-connection.png" alt="MDR-M 与 Cat1 通信板连接参考图" width="85%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">图 5 WDR-M 与 4G Cat1 通信板连接参考图</p>
</div>

这些图适合在确认插接方向、追踪 `UART` 或 `USB` 相关信号，或检查通信板与雷达板如何接入 `WDR-M` 时使用。

## 6. 相关文档

- [MDR 模块简介](./mdr_cn.md)
- [ML6432Ax 系列介绍](./ml6432ax_cn.md)
- [WDR-4G 通信板简介](./wdr-4g_cn.md)
- [PRO 模组简介](./pro_cn.md)
