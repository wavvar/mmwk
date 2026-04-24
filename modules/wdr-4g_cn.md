# WDR-4G 通信板简介

## 目录

- [1. 板卡概述](#1-板卡概述)
- [2. 技术规格和主要特性](#2-技术规格和主要特性)
- [3. 系统角色说明](#3-系统角色说明)
- [4. 连接关系与板级参考图](#4-连接关系与板级参考图)
- [5. 相关文档](#5-相关文档)

## 1. 板卡概述

`WDR-4G` 是 `WDR` 系统中的 `4G Cat1` 通信板。在 `MDR` 系统说明中，该板以 `4G Cat1` 通信板的形式出现，用于提供蜂窝通信与远程联网能力。`WDR` 完整模组由 `ML6432A_BO` 雷达板、`MDR-M` 主控板和 `4G Cat1` 通信板组成，适合需要本地感知与远程联网能力的整机方案。

## 2. 技术规格和主要特性

| 类别 | 项目 | 规格 |
| --- | --- | --- |
| **供电** | 输入电源 | 5V2A |
| **环境参数** | 工作温度 | 0 ～ +40°C |
|  | 存储温度 | -40°C ～ +85°C |
|  | 工作湿度 | ≤95%（无冷凝） |
| **对外接口** | P3 | 4Pin，USB + UART 通信接口 |
|  | P4 | 4Pin，电源 + 控制接口 |
| **P3 接口定义** | USB_DP | USB 差分信号 D+ |
|  | USB_DM | USB 差分信号 D− |
|  | UART_TX | 模组主串口发送（MAIN_TXD） |
|  | UART_RX | 模组主串口接收（MAIN_RXD） |
| **P4 接口定义** | VBAT | 外部电源输入 |
|  | GND | 电源地 |
|  | CAT1_RST | 模组复位/开机控制 |
| **通信能力** | UART | 主 AT 指令通道，用于外部主控通信 |
|  | USB | 支持 USB 2.0（CDC 虚拟串口），用于 AT 指令、调试及升级 |
| **SIM 功能** | SIM 类型 | Nano SIM |
|  | SIM 接口 | 板载 SIM 电路（含保护与滤波） |
| **射频** | 天线接口 | IPEX 天线座 |
| **控制与状态**  | 状态指示 | 板载LED网络状态指示灯 |
| **板载固定特性**
|  | SIM 保护 | TVS + 匹配电路 |
|  | USB 保护 | TVS 防护 |

## 3. 系统角色说明

在 `WDR` 系统中，`WDR-4G` 负责蜂窝通信与现场部署时的数据回传。`WDR-M` 位于中间层，负责连接雷达板与 `WDR-4G`，同时提供本地调试、板级控制以及通信路由所需的接口。`WDR-4G`与`WDR-M`之间使用usb链路通信。

| 关联板卡 | 关系 | 说明 |
| --- | --- | --- |
| `WDR-M`（`MDR-M`） | 主控与互连 | `WDR-4G` 通过专用板级信号连接到 `WDR-M` |
| `ML6432A_BO` 雷达板 | 系统组成 | 与 `WDR-M`、`WDR-4G` 共同构成完整 `WDR` 模组 |

## 4. 连接关系与板级参考图

下列图示用于说明 `WDR-4G` 与 `WDR-M` 的连接关系及接口原理参考。

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/mdr-cat1-board-interface-schematic.png" alt="4G Cat1 通信板接口原理图" width="85%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">图 1 WDR-4G 接口原理参考图</p>
</div>

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/mdr-m-to-cat1-board-connection.png" alt="MDR-M 与 Cat1 通信板连接参考图" width="85%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">图 2 WDR-4G 与 WDR-M 连接参考图</p>
</div>

这些图适合在确认 `WDR-4G` 的系统接入方式、追踪板间连接关系，或检查通信板如何接入 `WDR-M` 时使用。

## 5. 相关文档

- [MDR 模块简介](./mdr_cn.md)
- [WDR-M 主控承载板简介](./wdr-m_cn.md)
