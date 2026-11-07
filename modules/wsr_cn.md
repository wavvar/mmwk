# WSR 模组简介

[English Version](./wsr.md)

## 目录

- [1. 模组概述](#1-模组概述)
- [2. 外观与尺寸](#2-外观与尺寸)
- [3. 技术规格和主要特性](#3-技术规格和主要特性)
- [4. 本地接口与数据采集](#4-本地接口与数据采集)
- [4.1 UART](#41-uart)
- [4.2 原生 USB Type-C](#42-原生-usb-type-c)
- [5. 出厂烧录](#5-出厂烧录)
- [6. ESP 芯片管脚描述](#6-esp-芯片管脚描述)
- [7. 相关文档](#7-相关文档)

## 1. 模组概述

`WSR` 属于 `RPX 6843` 系列感知模组。当前硬件版本以 `PRO` 为基线：主控、雷达、供电、外围能力、UART 行为和机械结构均与 PRO 一致；差异仅在 Type-C 口，其线序、原生 USB 功能和出厂烧录入口与 `WDR` 一致。

因此，WSR 使用 `ESP32-S3` 主控和 `IWR6843AoP` 雷达，适用于人体存在检测、跌倒检测、轨迹跟踪、空间占用检测、活动识别、出入监测、在床/离床检测和点云数据采集等场景。

## 2. 外观与尺寸

WSR 与 PRO 共用机械和外观基线。下图可作为当前硬件外形参考；Type-C 的电气功能以本文第 4、5 节为准。

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/RPX/6843/pro-1.png" alt="WSR 与 PRO 共用的机械外形参考" width="45%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">WSR 与 PRO 共用的机械外形参考</p>
</div>

| 项目 | 规格 |
| --- | --- |
| 尺寸 | 83x83x17 mm |

## 3. 技术规格和主要特性

下表沿用当前 PRO 硬件规格；WSR 的独立参数更新后，以后续公开版本为准。

| 类别 | 项目 | 规格 |
| --- | --- | --- |
| **供电** | 外部供电 | 5V⎓2A |
|  | 适配器 | 100–240V AC 输入 |
|  | 整机功耗 | < 10W |
| **运行参数** | 安装方式 | 吸顶安装或壁挂安装 |
|  | 最大检测距离（壁挂） | 与安装高度、俯仰角、目标反射特性及算法配置有关，可配置 |
|  | 视场角（FOV） | 水平约 120°–140°；实际覆盖范围受安装方式、外壳结构及算法配置影响 |
|  | 工作温度 | 0°C 至 45°C（整机环境温度） |
|  | 工作湿度 | < 95%（无冷凝） |
|  | 壁挂俯仰角 | 30°（下俯角度） |
| **雷达特性** | 射频频段 | 60–64 GHz |
|  | 发射/接收通道 | 3TX / 4RX（见注 1） |
|  | 调制方式 | FMCW |
|  | 单发射通道输出功率（EIRP） | 15 dBm |
| **连接与集成** | 云端协议 | MQTT、HTTP、HTTPS |
|  | Wi-Fi | Wi-Fi 802.11 b/g/n（2.4 GHz） |
|  | 本地通信 | UART、原生 USB Type-C |
|  | 蜂窝网络 | LTE Cat.1 bis（4G，全网通） |
| **硬件架构** | 处理架构 | 双芯片异构架构（毫米波雷达 SoC + 主控 MCU） |
|  | 雷达处理单元 | ARM Cortex-R4F + C674x DSP + 硬件加速器（HWA） |
|  | 主控单元 | ESP32-S3（Xtensa LX7 双核，最高 240 MHz） |
|  | 片上内存 | 512 KB（主控 MCU）+ 1.75 MB（雷达 SoC） |
|  | PSRAM | 8 MB |
|  | Flash 存储 | 8 MB（主控 MCU）+ 4 MB（雷达 SoC，可选） |
|  | I/O 与指示器 | 1× RGB LED、1× 按键、1× LED（可选） |
|  | IMU | 可选 6 轴陀螺仪 + 3 轴加速度计 |
|  | 环境光传感器 | 可选支持 |
|  | 语音 | 可选 1× 扬声器、1× 麦克风 |

> 注 1：`1.3 V` 模式下最多支持 `2TX` 同时发射；`3TX` 同时发射需要 `1V LDO bypass` 工作模式。

## 4. 本地接口与数据采集

WSR 同时支持 UART 和原生 USB 采集。这两种本机直连方式都不需要网络；MQTT 仅在远程采集或 UART 控制、MQTT 传输 DATA 的分流方案中使用。

### 4.1 UART

WSR 的 UART 行为与 PRO 一致：CLI JSON 控制从 115200 开始，雷达 DATA 标称 921600，主机 raw UART 最高使用 1000000。

```bash
./cli/run.sh collect --transport uart --port <uart-port> \
  --raw-baud 1000000 --duration 30
```

### 4.2 原生 USB Type-C

WSR 的 Type-C 口采用与 WDR 相同的线序和原生 USB 功能，不使用 PRO 的外接 USB 转 UART 通信方式。USB 数据线连接到 ESP32-S3 原生 USB 信号：

| Type-C 信号 | ESP32-S3 信号 |
| --- | --- |
| D- | GPIO19 / USB_D- |
| D+ | GPIO20 / USB_D+ |
| VBUS | 5V 输入 |
| GND | GND |

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/mdr-m-usb-typec-reference.png" alt="WSR 与 WDR 共用的 Type-C 信号功能参考" width="75%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">WSR 与 WDR 共用的 Type-C 信号功能参考</p>
</div>

原生 USB CDC 可承载 CLI JSON 控制和雷达 DATA，不需要 Wi-Fi 或 MQTT，也没有需要用户配置的物理 raw 波特率。

```bash
./cli/run.sh node info --transport usb --port <native-usb-port>
./cli/run.sh collect --transport usb --port <native-usb-port> --duration 30
```

应以 `node info` 返回的 `board=wsr` 和设备身份选择目标设备，不要只依据端口名或 USB 描述符判断板型。

## 5. 出厂烧录

WSR 的出厂烧录入口与 WDR 一致，可通过原生 Type-C 连接执行首次烧录。发布包必须选择 WSR 板型；对应路径约定为：

```text
./firmwares/esp/wsr/mmwk_sensor_bridge/v<version>/factory.zip
```

解压后按[出厂烧录指南](../docs/zh-cn/flash.md)执行，并在恢复后通过原生 USB 读取 `node info`，确认 `board=wsr` 和 `version`。PRO、WDR 与 WSR 发布包不能相互替代。

## 6. ESP 芯片管脚描述

WSR 的 ESP32-S3 管脚功能沿用 PRO。Type-C 口将 GPIO19/20 用作原生 USB；其余管脚定义不变。

| GPIO | 类型 | 功能 |
| --- | --- | --- |
| GPIO0 | I/O | ESP32_IO0 下载设置 |
| GPIO1 | I/O | I2C_SCL |
| GPIO2 | I/O | I2C_SDA |
| GPIO3 | I/O | I2S_DOUT |
| GPIO4 | I/O | I2S_DIN |
| GPIO5 | I/O | I2S_LRCK |
| GPIO6 | I/O | I2S_BCLK |
| GPIO7 | I/O | I2S_MCLK |
| GPIO8 | I/O | U2TXD |
| GPIO9 | I/O | U2RXD |
| GPIO10 | I/O | AR_NRST（BMI160 复位） |
| GPIO11 | I/O | SPI_MOSI（BMI160） |
| GPIO12 | I/O | U1RXD |
| GPIO13 | I/O | SPI_CS（BMI160） |
| GPIO14 | I/O | SPI_CLK（BMI160） |
| GPIO15 | I/O | SPI_MISO（BMI160） |
| GPIO16 | I/O | SPI_HOSR_INT（BMI160 中断） |
| GPIO17 | I/O | PA_CTL（射频 PA 控制） |
| GPIO18 | I/O | VEML6030_INT |
| GPIO19 | I/O | USB_D- |
| GPIO20 | I/O | USB_D+ |
| GPIO21 | I/O | IOT_PWCTL |
| GPIO26–GPIO32 | SPI 专用 | 内部 Flash/PSRAM |
| GPIO33 | I/O | KEY_IN（按键输入） |
| GPIO34 | I/O | BMI160_INT1 |
| GPIO35 | I/O | CAT1_RESET |
| GPIO36 | I/O | U0TXD（CAT1 串口发送） |
| GPIO37 | I/O | U0RXD（CAT1 串口接收） |
| GPIO38–GPIO42 | I/O | 内部保留，不能他用 |
| GPIO43 | UART | 调试串口 TXD（U0TXD） |
| GPIO44 | UART | 调试串口 RXD（U0RXD） |
| GPIO45 | 输入 | ESP32_FLASH_POW_IO45 |
| GPIO46 | 输入 | STATUS（启动配置脚） |

## 7. 相关文档

- [PRO 模组简介](./pro_cn.md)
- [WDR-M 主控承载板简介](./wdr-m_cn.md)
- [雷达 DATA 采集](../cli/docs/zh-cn/data-collection.md)
- [出厂烧录指南](../docs/zh-cn/flash.md)
