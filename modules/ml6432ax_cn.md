# 6432模组简介

## 目录

- [1. 模组简介](#1-模组简介)
- [2. 技术规格和主要特性](#2-技术规格和主要特性)
- [3. 应用领域](#3-应用领域)
- [4. WDR/MDR 系列集成说明](#4-wdrmdr-系列集成说明)
- [5. 接口说明](#5-接口说明)
- [6. 使用与烧录说明](#6-使用与烧录说明)
- [6.1 启动模式配置说明](#61-启动模式配置说明)
- [6.2 固件烧录步骤](#62-固件烧录步骤)
- [6.3 模组使用说明](#63-模组使用说明)
- [6.4 串口连接说明](#64-串口连接说明)

## 1. 模组简介

ML6432A 系列是基于 TI IWR6432AOP 芯片开发的高性能低功耗毫米波雷达模组。模组集成了雷达射频前端、数字处理单元及天线，具有尺寸紧凑、集成度高等特点。本模组主要面向智能家居、人员存在检测、体征检测、运动检测等应用领域。支持 UART 和 SPI 接口，方便用户进行快速开发和集成。系列包含 ML6432A 和 ML6432A_BO，如下图所示。

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/ml6432a-front-view.png" alt="ML6432A 模组正面" width="50%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">ML6432A</p>
</div>

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/ml6432a-bo-front-view.png" alt="ML6432A_BO 模组正面" width="60%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">ML6432A_BO</p>
</div>

## 2. 技术规格和主要特性

<table style="margin: 0 auto; text-align: center;">
  <thead>
    <tr>
      <th>参数类别</th>
      <th>参数项</th>
      <th>规格</th>
      <th>备注</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td rowspan="5">基础参数</td>
      <td>尺寸</td>
      <td>15*39*7.2mm</td>
      <td>ML6432A</td>
    </tr>
    <tr>
      <td>尺寸</td>
      <td>7.6*48*7.2mm</td>
      <td>ML6432A_BO</td>
    </tr>
    <tr>
      <td>通信接口</td>
      <td>UART，SPI，CAN，SOP IO</td>
      <td></td>
    </tr>
    <tr>
      <td>供电输入</td>
      <td>3.3V 4A</td>
      <td></td>
    </tr>
    <tr>
      <td>功耗</td>
      <td>~200-300mW</td>
      <td></td>
    </tr>
    <tr>
      <td rowspan="3">射频参数</td>
      <td>工作频段</td>
      <td>57GHz-64GHz</td>
      <td></td>
    </tr>
    <tr>
      <td>收发通路</td>
      <td>2T3R</td>
      <td></td>
    </tr>
    <tr>
      <td>发射功率</td>
      <td>11dBm</td>
      <td></td>
    </tr>
    <tr>
      <td rowspan="2">探测性能</td>
      <td>探测距离</td>
      <td>0.1m-20m</td>
      <td>针对人体移动（大目标）；微动检测&lt;6m</td>
    </tr>
    <tr>
      <td>视场角</td>
      <td>水平±70°/垂直±60°</td>
      <td></td>
    </tr>
  </tbody>
</table>

## 3. 应用领域

- 健康监护：非接触式生命体征监测（呼吸与心率）
- 楼宇自动化：自动门、占用检测、人员追踪与计数
- 个人电子产品：笔记本电脑、智能家电（空调、冰箱、智能马桶）、智能手表
- 安防监控：可视门铃、IP 网络摄像头、运动检测器
- 汽车电子：车内入侵检测等

## 4. WDR/MDR 系列集成说明

`ML6432Ax` 系列同时也是 `WDR/MDR` 产品线中的雷达板系列。在系统集成场景下，`ML6432A` 和 `ML6432A_BO` 在雷达侧保持相同的电气接口定义，但安装方式不同。

- `ML6432A_BO` 是面向 `MDR-M` / `WDR-M` 的优先直插版本。
- `ML6432A` 使用相同的雷达侧接口类别，但通常需要通过转接线连接，而不是直接插接到主控板。

以下图片来自 WDR/MDR 集成资料，可作为补充参考。

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/ml6432a-connector-layout-reference.png" alt="ML6432A 连接器布局参考图" width="48%" style="display: inline-block; margin: 0 12px;" />
  <img src="./img/MDR/ml6432a-p1-p2-position-reference.png" alt="ML6432A P1 与 P2 位置参考图" width="38%" style="display: inline-block; margin: 0 12px;" />
  <p style="margin: 4px 0 0 0;">连接器布局与 P1/P2 位置参考</p>
</div>

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/ml6432a-signal-schematic-reference.png" alt="ML6432A 信号原理参考图" width="70%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">WDR/MDR 集成资料中的信号原理参考图</p>
</div>

如需查看完整的 WDR/MDR 系统级说明，请参考 [mdr_cn.md](./mdr_cn.md)。

## 5. 接口说明

模组通过两个 6-Pin 连接器（P1、P2）与外部进行连接。接口包含电源、复位、模式设置以及 SPI、UART、CAN FD 通信接口。ML6432A 与 ML6432A_BO 在接口线序说明上有所区别，具体如下。

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/ml6432a-front-view.png" alt="ML6432A 正面" width="40%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">图 5 ML6432A 正面</p>
</div>

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/ml6432a-back-view.png" alt="ML6432A 背面" width="40%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">图 6 ML6432A 背面</p>
</div>

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/ml6432a-connector-pin-assignment.png" alt="ML6432A 接口线序" width="40%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">图 7 ML6432A 接口线序</p>
</div>

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/ml6432a-bo-front-view.png" alt="ML6432A_BO 正面" width="60%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">图 8 ML6432A_BO 正面</p>
</div>

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/ml6432a-bo-back-view.png" alt="ML6432A_BO 背面" width="60%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">图 9 ML6432A_BO 背面</p>
</div>

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/ml6432a-bo-connector-pin-assignment.jpg" alt="ML6432A_BO 接口线序" width="55%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">图 10 ML6432A_BO 接口线序</p>
</div>

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/ml6432a-interface-schematic.png" alt="ML6432A 接口原理图" width="90%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">图 11 接口原理图</p>
</div>

## 6. 使用与烧录说明

模组支持使用 MMWK 烧录和标准烧录。通过 MMWK 烧录请参考 MMWK 文档。进行标准烧录、模组调试或固件烧写前，需准备以下驱动及工具（根据实际硬件下载对应驱动）。

- CP210x 串口驱动：[下载地址](https://www.silabs.com/software-and-tools/usb-to-uart-bridge-vcp-drivers?tab=downloads)
- CH340 串口驱动：[下载地址](https://www.wch.cn/downloads/CH341SER_EXE.html)
- 友善串口调试助手：[下载地址](https://www.alithon.com/downloads)
- UniFlash 下载工具（必选）：[下载地址](https://www.ti.com/tool/UNIFLASH?keyMatch=UNIFLASH&tisearch=universal_search&usecase=software)

### 6.1 启动模式配置说明

模组通过 MCU_IO_MODE_SET（P2.5）引脚控制启动模式，不同电平对应不同工作状态。

- 刷机模式配置方法：P2.5 引脚保持悬空或接低电平，设备开机后会进入刷机模式。（说明：悬空或直接拉至 GND 均可进入刷机模式）
- 应用启动模式（正常工作模式）配置方法：P2.5 引脚接高电平，设备开机后会进入应用启动模式，建议将引脚通过 10kΩ 电阻拉高到 3.3V 输入。

### 6.2 固件烧录步骤

- 将设备配置为刷机模式；
- 通过串口助手将设备连接至电脑；
- 使用 UniFlash 工具进行固件烧录。

操作步骤可参考 TI 官方文档：[文档地址](https://software-dl.ti.com/ccs/esd/uniflash/docs/v9_3/uniflash_quick_start_guide.html)

### 6.3 模组使用说明

固件烧录完成后：

- 将设备切换至应用启动模式；
- 通过串口连接设备；
- 可在串口工具中查看设备运行数据、发送配置文件或调试指令。

### 6.4 串口连接说明

硬件连接关系如下。

<table style="margin: 0 auto; text-align: center;">
  <thead>
    <tr>
      <th>设备端口</th>
      <th>串口工具</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>3V3</td>
      <td>3.3V 输出</td>
    </tr>
    <tr>
      <td>GND</td>
      <td>GND</td>
    </tr>
    <tr>
      <td>RS232_RX</td>
      <td>TX</td>
    </tr>
    <tr>
      <td>RS232_TX</td>
      <td>RX</td>
    </tr>
  </tbody>
</table>

连接电脑时，将串口调试助手 USB 插入电脑后，系统会识别为串口设备。设备分配到的端口名称取决于主机系统；在 Windows 系统中，通常会显示为类似 `COM20` 的 COM 口。
