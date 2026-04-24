# MDR 模块简介

## 目录

- [1. 模块概述](#1-模块概述)
- [2. 系统组成](#2-系统组成)
- [3. 雷达板兼容性说明](#3-雷达板兼容性说明)
- [4. 连接关系与板级参考图](#4-连接关系与板级参考图)
- [5. MDR-M 对外接口说明](#5-mdr-m-对外接口说明)

## 1. 模块概述

MDR 模块是一个由三块板组成的毫米波感知与通信平台，整体由 `ML6432A_BO` 雷达板、`MDR-M` 主控板以及 `4G Cat1` 通信板构成。在该架构中，雷达板负责感知，`MDR-M` 负责本地控制与系统互连，Cat1 通信板负责蜂窝网络回传。

相较于单独使用雷达板，MDR 更强调系统级集成能力。它将雷达感知、控制管理和 4G 通信整合在同一套硬件结构中，适合需要本地感知与远程联网能力的整机方案。

在产品命名中，`WDR` 是一个系列名称。实际交流里提到“WDR 开发板”时，很多情况下具体指的是 `WDR-M` 这块板子。本文在涉及板级描述时，统一使用 `MDR-M` 作为具体主控板名称。

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/mdr-module-top-view.png" alt="MDR 模块顶视图" width="80%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">MDR 模块顶视图</p>
</div>

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/mdr-module-side-view.png" alt="MDR 模块侧视图" width="80%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">MDR 模块侧视图</p>
</div>

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/wdr-module-front-view.png" alt="WDR 模块正面" width="44%" style="display: inline-block; margin: 0 12px;" />
  <img src="./img/MDR/wdr-module-back-view.png" alt="WDR 模块背面" width="44%" style="display: inline-block; margin: 0 12px;" />
  <p style="margin: 4px 0 0 0;">WDR 系列外观参考图</p>
</div>

## 2. 系统组成

MDR 模块由以下几个硬件部分组成。

| 板卡 | 作用 | 说明 |
| --- | --- | --- |
| `ML6432A_BO` 雷达板 | 实现毫米波感知、雷达前端处理和数据输出 | 是 MDR 方案中优先推荐的直插式雷达板 |
| `MDR-M` 主控板 | 负责供电分配、本地控制、外围管理和板间互连 | 是整机中的核心承载与控制板 |
| `4G Cat1` 通信板 | 提供蜂窝通信与远程联网能力 | 用于现场部署时的数据回传 |

从系统结构上看，`MDR-M` 位于中间层，负责连接雷达板与 Cat1 通信板，同时提供本地调试、板级控制以及通信路由所需的接口。

## 3. 雷达板兼容性说明

在功能支持层面，`MDR-M` 支持 `ML6432Ax` 系列。这意味着 MDR 模块既可以基于 `ML6432A_BO` 组装，也可以基于 `ML6432A` 组装，差别主要在于机械连接方式。

实际集成差异如下：

- `ML6432A_BO` 可通过板对板连接方式直接插接在 `MDR-M` 上。
- `ML6432A` 在功能上同样受支持，但不能直接插接，需要通过转接线与 `MDR-M` 连接。

两种雷达板在雷达侧使用相同的接口定义。如果用户只需要进行独立雷达板的烧录或调试，`ML6432A` 与 `ML6432A_BO` 都可以按统一的 `ML6432Ax` 使用流程操作。

| 版本 | 正面视图 | 背面视图 | 集成方式 |
| --- | --- | --- | --- |
| `ML6432A_BO` | <img src="./img/MDR/ml6432a-bo-front-view-alt.png" width="250" alt="ML6432A_BO 补充正面图"> | <img src="./img/MDR/ml6432a-bo-back-view-alt.png" width="250" alt="ML6432A_BO 补充背面图"> | 可直接插接到 `MDR-M` / `WDR-M` |
| `ML6432A` | <img src="./img/MDR/ml6432a-front-view.png" width="170" alt="ML6432A 正面图"> | <img src="./img/MDR/ml6432a-back-view-alt.png" width="170" alt="ML6432A 补充背面图"> | 需要通过转接线连接 |

如需查看雷达板的详细电气参数、接口定义以及独立使用说明，请参考 [ML6432Ax 系列介绍文档](./ml6432ax_cn.md)。

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/ml6432a-bo-front-view.png" alt="ML6432A_BO 正面" width="60%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">ML6432A_BO 雷达板</p>
</div>

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/mdr-m-board-attachment-orientation.png" alt="MDR-M 插接方向参考" width="42%" style="display: inline-block; margin: 0 12px;" />
  <img src="./img/MDR/ml6432a-bo-attachment-orientation.png" alt="ML6432A_BO 插接方向参考" width="42%" style="display: inline-block; margin: 0 12px;" />
  <p style="margin: 4px 0 0 0;">MDR-M 与 ML6432A_BO 的直插方向参考</p>
</div>

因此，在构建完整 MDR 模块时，更推荐使用 `ML6432A_BO`。如果使用非 BO 版本，系统功能仍然成立，但雷达板需要通过外部转接线连接，而不是直接安装在主控板上。

## 4. 连接关系与板级参考图

`4G Cat1` 通信板和雷达板都通过专用板级信号连接到 `MDR-M`。下列图示用于说明 MDR 模块内部的主要连接关系。

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/mdr-cat1-board-interface-schematic.png" alt="4G Cat1 通信板接口原理图" width="85%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">4G Cat1 通信板接口原理图</p>
</div>

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/mdr-m-to-radar-board-connection.png" alt="MDR-M 与雷达板连接参考图" width="85%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">MDR-M 与雷达板连接参考图</p>
</div>

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/mdr-m-to-cat1-board-connection.png" alt="MDR-M 与 Cat1 通信板连接参考图" width="85%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">MDR-M 与 Cat1 通信板连接参考图</p>
</div>

这些图适合在确认插接方向、追踪 UART 或 USB 相关信号，或检查通信板与雷达板如何接入 `MDR-M` 时使用。

## 5. MDR-M 对外接口说明

`MDR-M` 还提供了一些便于调试与集成的外部接口参考：

- `P7` 为 USB Type-C 接口，可用于本地连接或调试维护。
- 板上提供状态 LED 参考图，便于快速观察调试状态。
- 板上提供按键参考图，可用于本地控制或交互行为设计。

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/mdr-m-usb-typec-reference.png" alt="MDR-M USB Type-C 参考图" width="75%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">MDR-M 上的 USB Type-C 接口参考</p>
</div>

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/mdr-m-status-led-reference.png" alt="MDR-M LED 参考图" width="60%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">MDR-M 上的状态 LED 参考</p>
</div>

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/mdr-m-key-reference.png" alt="MDR-M 按键参考图" width="80%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">MDR-M 上的按键参考</p>
</div>

通过这些接口与板级参考图，MDR 模块在整机装配、调试和部署阶段会更容易理解和使用。
