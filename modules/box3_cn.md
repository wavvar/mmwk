# ESP32-S3-BOX-3 扩展坞雷达指南

[English Version](./box3.md)

## 适用范围

本文说明 ESP32-S3-BOX-3、BOX-3 扩展坞与 ML6432A/ML6432A_BO（IWRL6432）
雷达的接入方式。`BOX3` 在 SDK 中是独立的板级目标；只有扩展坞雷达适配部分
沿用 WDR 类 6432 雷达协议和控制约定，BOX3 原生显示、触摸、音频、启动按键
仍使用 BOX3 自己的 IO，不改成 WDR 的整板 IO。

## 扩展坞与雷达接线

以下 GPIO 使用扩展坞标号，箭头以 ESP32 主机视角表示信号方向。

| BOX-3 扩展坞 | 雷达引脚 | 功能 |
| ---: | --- | --- |
| GPIO41 | P1.2 `RS232_RX` | 雷达命令 UART TX（ESP -> 雷达） |
| GPIO40 | P1.4 `RS232_TX` | 雷达命令 UART RX（雷达 -> ESP） |
| GPIO11 | P1.1 `SPIA_MOSI` | SPI MOSI |
| 不连接 | P1.3 `SPIA_MISO` | SPI MISO 不可用；GPIO13 已用于 MODE_SET |
| GPIO14 | P1.6 `SPIA_CLK` | SPI 时钟 |
| GPIO21 | P1.5 `SPIA_CS` | SPI 片选 |
| GPIO10 | P2.2 `NRESET` | 雷达复位/电源控制 |
| GPIO13 | P2.5 `MCU_IO_MODE_SET` | 雷达 SOP/启动模式控制 |
| 扩展坞 3V3 | P2.1 `RA_3V3` | 常供雷达 3.3 V |
| 扩展坞 GND | P2.3 GND | 共地 |

P2.4、P2.6 的 CAN 以及 `RADA_POW_CTL` 在此适配中不连接。`RA_3V3` 使用满足
雷达峰值电流要求的稳压 3.3 V 常供电，不能让 ESP32 GPIO 直接给雷达供电。
UART 刷写的确定性模式切换保留 GPIO10 `NRESET`。雷达适配器连接期间，
GPIO40 和 GPIO41 不能再用于外部 JTAG。

6432 雷达的命令和运行数据在此目标共用 UART1，因此 SDK 不再分配独立的数据
UART。雷达连接器没有独立的 SPI IRQ/控制线，`SPI_INT` 明确保持 `-1`；由于
GPIO13 已分配给 MODE_SET，SPI MISO 也保持 `-1`，BOX3 仅验收 UART 路径。

## 保留的 BOX3 原生 IO

SDK 保留 BOX3 已有外设的原生引脚：

- 音频：I2S MCLK/LRCK/SCLK/DIN/DOUT = GPIO2/45/17/16/15，PA = GPIO46，
  编解码器 I2C = GPIO8/18。
- 显示：ILI9341 的 MOSI/SCLK/CS/DC/RST/背光 = GPIO6/7/5/4/48/47。
- 触摸中断 = GPIO3；启动按键 = GPIO0；雷达桥接目标不占用原生状态 LED。

这些引脚属于 BOX3 自身外设，不用于上面的扩展坞雷达信号。

## 构建与验证边界

在 SDK 根目录执行桥接目标构建：

```bash
cd mmwk_sdk/projects/mmwk_sensor_bridge
./build.sh box3
```

该目标会放入 6432 的 `radw_6432.release.appimage` 和 `radw_6432_wdr.cfg`，
并提供标准的雷达命令、复位、SOP、状态和原始数据路径。硬件验证只覆盖 UART
路径，不包含 SPI 固件刷写/写入验证。
