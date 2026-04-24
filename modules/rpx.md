# RPX Module Usage Guide

[中文版](./rpx_cn.md)

**Version:** 1.2<br>
**Author:** Wavvar Technologies<br>
**Date:** August 2025<br>

## 1. Overview

This document covers the `RPX` series modules, including the `6843` series products and the `RPI` platform in the `6432` class.

`WDR` is documented separately because it belongs to a different product series. For `WDR/MDR` system-level documentation, refer to [./mdr.md](./mdr.md). For standalone `ML6432Ax` radar board documentation, refer to [./ml6432ax.md](./ml6432ax.md).

## 2. 6843 Series Sensing Modules

The 6843 series represents our flagship line of modules, equipped with TI's high-performance mmWave radar technology. Designed for advanced spatial sensing, they are ideal for environments that demand robust motion tracking and precise spatial measurement.

| MINI | RTP | RTL | CFH |
| --- | --- | --- | --- |
| <img src="./img/RPX/6843/MINI-module.png" width="200"> | <img src="./img/RPX/6843/RTP_front.png" width="200"> | <img src="./img/RPX/6843/RTL.png" width="200"> | <img src="./img/RPX/6843/CFH.png" width="200"> |
| **Form Factor:** 47×56×6.8mm | **Form Factor:** 65×65×10.5mm | **Form Factor:** 56×56×12mm | **Form Factor:** 70×71.5×11mm |

### 2.1 Target Applications

- Presence and fall detection
- Dynamic trajectory tracking
- Occupancy sensing
- Activity recognition
- Entry and exit monitoring
- In-bed / out-of-bed detection
- Point cloud data visualization

### 2.2 Specifications

| Category | Feature | Specification |
| --- | --- | --- |
| **Power** | External Supply | 5V⎓2A |
|  | Adapter Requirement | 100-240V AC Input |
|  | Power Consumption | < 10W |
| **Operational Parameters** | Primary Installation | Ceiling-mount or wall-mount |
|  | Maximum Detection Range (Wall-mounted) | Up to 30m |
|  | Field of View (FOV) | 140° (120° recommended for optimal performance) |
|  | Operating Temperature | 0°C to 45°C |
|  | Operating Humidity | < 95% (non-condensing) |
|  | Wall-mount Pitch Angle | 15°, 30°, 45° (customizable for > 30°) |
| **Radar Characteristics** | RF Frequency Band | 60-64 GHz |
|  | Tx/Rx Channels | 3T4R |
|  | Modulation Scheme | FMCW |
|  | Transmission Power | 15 dBm per channel |
| **Connectivity & Integration** | Cloud Protocols | MQTT, HTTP, HTTPS |
|  | Local Communication | Serial UART (Binary or JSON format; highly customizable) |
| **Hardware Architecture** | MCU Core | Dual-core + Tri-core Architecture |
|  | Co-processor | Hardware Accelerator (HWA) + DSP |
|  | Memory (RAM) | 520 KB + 8 MB (RFC-P02-06 operates on 512KB + 8MB) |
|  | Flash Storage | 8 MB |
|  | I/O & Indicators | 2× LEDs, 1× push button |
|  | IMU (Optional) | 9-axis gyroscope/accelerometer |
|  | Ambient Light Sensor | Optional support |
|  | Audio Input (Optional) | Single-channel microphone |
|  | Audio Output (Optional) | 8Ω speaker |

### 2.3 Hardware Interfaces & Controls

Both the `RTP` and `RPI` modules feature integrated status LEDs and a tactile button, managed independently by the ESP32-S3 microcontroller and the radar SoC. The GPIO mapping for the `RTP` module is shown below.

| Module | Component | Control Chip | LED Type / Description | GPIO |
| --- | --- | --- | --- | --- |
| RTP | LED1 | ESP32-S3 | RGB LED | ESP32_LED_IO48 |
| RTP | LED2 | Radar Chip | LED | AR_GPIO_2 |
| RTP | Button | ESP32-S3 | - | ESP32_KEY_IO33 |

## 3. RPI 6432 Sensing Module

Within the RPX family, the `RPI` module provides a compact `6432`-class sensing platform aimed at low-power presence detection and vital-sign related applications.

| Front View | Back View | Dimensions |
| --- | --- | --- |
| <img src="./img/RPX/6432/RPI_overview.png" width="210"> | <img src="./img/RPX/6432/RPI_top_back.png" width="210"> | 49×7mm |

For the `WDR/MDR` series based on `ML6432A` and `ML6432A_BO`, see [./mdr.md](./mdr.md) and [./ml6432ax.md](./ml6432ax.md).

### 3.1 Target Applications

- Non-contact vital-sign related monitoring
- Presence detection in compact embedded products
- Building automation and occupancy sensing
- Consumer electronics integration
- Security and motion-trigger applications

### 3.2 Specifications

| Category | Feature | Specification |
| --- | --- | --- |
| **Power** | Input Requirement | 3.3V, 4A peak |
|  | Nominal Consumption | ~200 - 300 mW |
| **Radar Characteristics** | RF Frequency Band | 57 - 64 GHz |
|  | Tx/Rx Channels | 2T3R |
|  | Transmission Power | 11 dBm |
|  | Detection Range | 0.1m - 20m (moving personnel / large targets); < 6m for micro-motion |
|  | Field of View (FOV) | Horizontal ±70° / Vertical ±60° |
| **Connectivity** | Supported Interfaces | UART, SPI, CAN FD, SOP I/O |

### 3.3 Hardware Interfaces and Status Indicators

The `RPI` top board includes two status LEDs. One is driven by the ESP32-S3 located on the bottom board through pin headers, while the other is controlled directly by the radar chip.

| Module | Component | Controller | Type | GPIO Pin |
| --- | --- | --- | --- | --- |
| RPI | LED1 (D1) | ESP32-S3 | LED | ESP32_LED_IO47 |
| RPI | LED2 (D2) | Radar Chip | LED | AR_IO5 |
| RPI | Button | ESP32-S3 (Bottom Board) | - | ESP32_KEY_IO40 |

**RPI Connector Pinout**<br>
The `RPI` module consists of a Top Board and a Bottom Board connected via two sets of 10-pin headers. The connector pinout is shown below.

| RPI Top Board Connector Pinout | RPI Bottom Board Connector Pinout |
| --- | --- |
| ![RPI Top Board Connector Pinout](./img/RPX/6432/RPI_top_pinout.png) | ![RPI Bottom Board Connector Pinout](./img/RPX/6432/RPI_bottom_pinout.png) |

## 4. Hardware Development Guide

To begin developing and testing with Wavvar modules, the hardware must be properly interfaced with a computer via our flashing debuggers. The sections below outline how to establish these connections and install the necessary software environments.

### 4.1 Development Environment Setup (RTP & RPI)

**SDK Installation:** For custom software development, please follow the official Espressif documentation to configure the ESP-IDF environment and compile the `hello_world` example:<br>
[Espressif ESP-IDF Get Started](https://docs.espressif.com/projects/esp-idf/en/release-v5.4/esp32/get-started/index.html)

### 4.2 Flashing Debugger Adapter

The USB-to-UART V1.3 debugger board facilitates firmware flashing and serial console access. It is offered in two configurations: **5V/2A** and **5V/500mA**. Both variants feature the same Type-C pinout and communication capability.

*Note: RTP devices actively operating on 4G/LTE networks demand higher peak currents and must be powered using the **5V/2A** variant.*

**Power Input Matrix:**

- The `RPI` module operates reliably on a standard **5V/1A** supply.
- All other Wavvar modules and integrated products require a **5V/2A** power source.

The **5V/2A** debugger variant shown below features an auxiliary power terminal to accommodate external 5V/2A DC adapters.

<div align="center"><img src="./img/RPX/misc/5V2A_flasher.png" style="width:50%;" alt="5V/2A Flashing Adapter"></div>

The figure below shows the **5V/500mA** version.

<div align="center"><img src="./img/RPX/misc/5V500mA.png" style="width:50%;" alt="5V/500mA Flashing Adapter"></div>

### 4.3 Debugger Orientation & Hardware Alignment

To ensure successful flashing and serial communication, please observe the side-sensitive alignment requirements for the Type-C interface.

- **RTP Module Alignment:** Align the **A-side** of the flashing debugger with the **A-side** of the module.
- **RPI Module Alignment:** Align the **A-side** of the flashing debugger with the **A-side** of the top board.
- **Mini & Pro Device Orientation:**

| Platform | Alignment Guide (Visual) |
| --- | --- |
| **Mini Device** (A-side alignment with chassis front) | <img src="./img/RPX/6843/mini_flasher.png" width="400" alt="Mini Alignment Guide"> |
| **Pro Device** (B-side alignment with chassis front) | <img src="./img/RPX/6843/pro_flasher.png" width="400" alt="Pro Alignment Guide"> |

### 4.4 Type-C Interface on the Flashing Debugger

If used for power supply only, the module does not distinguish between A and B sides. For communication purposes, the module's Type-C interface is side-sensitive. The pinout is shown below.

| Type-C | Number |
| --- | --- |
| A5 | UART_RX |
| A6 | RTS |
| A7 | DTR |
| B8 | UART_TX |
| A1/A12/B1/B12 | GND |
| A4/A9/B4/B9 | 5V in |

### 4.5 USB-to-UART V1.3 Flashing Debugger Pinout

| Pin | Color | Signal |
| --- | --- | --- |
| A5 | Orange | RX |
| A6 | Green | RTS |
| A7 | Blue | DTR |
| B8 | Yellow | TX |
| GND | Black | GND |
| VBUS | Red | 5V |

## 5. Custom Enclosures and Industrial Design

Wavvar offers end-to-end product realization services. Beyond the sensing modules discussed above, we also provide industrial design and mechanical design support for product integration.

| MINI Enclosure | PRO Enclosure | RPI Enclosure |
| --- | --- | --- |
| <img src="./img/RPX/6843/mini-1.png" style="width:80%;" alt="MINI Enclosure"> | <img src="./img/RPX/6843/pro-1.png" style="width:80%;" alt="PRO Enclosure"> | <img src="./img/RPX/6432/RPI.png" style="width:80%;" alt="RPI Enclosure"> |

## 6. Legacy DS Module Assistance

For customers utilizing or supporting our legacy generation, the DS module provides basic evaluation capabilities.

### 6.1 Evaluation and Prototyping

For foundational module development, we recommend consulting the official Texas Instruments documentation:<br>
[TI AWR6843AOPEVM Evaluation Module Guide](https://www.ti.com.cn/tool/cn/AWR6843AOPEVM)

**SOP Mode Configuration (Flashing Mode):**<br>
*Caution:* To prevent collateral thermal damage to adjacent SMD components, we strongly advise against soldering the SOP pins. Instead, use pogo pins or apply temporary mechanical pressure to short the terminals during flashing.
