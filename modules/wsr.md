# WSR Module Introduction

[Chinese Version](./wsr_cn.md)

## Table of Contents

- [1. Module Overview](#1-module-overview)
- [2. Appearance and Dimensions](#2-appearance-and-dimensions)
- [3. Technical Specifications and Key Features](#3-technical-specifications-and-key-features)
- [4. Local Interfaces and DATA Collection](#4-local-interfaces-and-data-collection)
- [4.1 UART](#41-uart)
- [4.2 Native USB Type-C](#42-native-usb-type-c)
- [5. Factory Flashing](#5-factory-flashing)
- [6. ESP Pin Description](#6-esp-pin-description)
- [7. Related Documents](#7-related-documents)

## 1. Module Overview

`WSR` is part of the `RPX 6843` sensing-module family. The current hardware uses `PRO` as its baseline: the controller, radar, power, peripherals, UART behavior, and mechanical design are the same as PRO. The only difference is the Type-C port, whose wiring, native USB function, and factory-flash entry follow `WDR`.

WSR therefore combines an `ESP32-S3` controller with an `IWR6843AoP` radar. Typical applications include presence and fall detection, trajectory tracking, occupancy sensing, activity recognition, entry/exit monitoring, in-bed/out-of-bed detection, and point-cloud DATA collection.

## 2. Appearance and Dimensions

WSR shares the current PRO mechanical and enclosure baseline. The figure below is the shared hardware-form reference; use Sections 4 and 5 for the WSR Type-C electrical behavior.

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/RPX/6843/pro-1.png" alt="Shared WSR and PRO mechanical reference" width="45%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">Shared WSR and PRO mechanical reference</p>
</div>

| Item | Specification |
| --- | --- |
| Dimensions | 83x83x17 mm |

## 3. Technical Specifications and Key Features

The table below follows the current PRO hardware specification. A later public revision may refine WSR-specific parameters.

| Category | Item | Specification |
| --- | --- | --- |
| **Power** | External Supply | 5V⎓2A |
|  | Adapter | 100-240V AC input |
|  | System Power Consumption | < 10W |
| **Operating Parameters** | Installation Method | Ceiling mount or wall mount |
|  | Maximum Detection Range (Wall-mounted) | Configurable; depends on installation, target reflection, and algorithm configuration |
|  | Field of View (FOV) | Approximately 120°-140° horizontally; actual coverage depends on installation, enclosure, and algorithm configuration |
|  | Operating Temperature | 0°C to 45°C (system ambient temperature) |
|  | Operating Humidity | < 95% (non-condensing) |
|  | Wall-mount Pitch Angle | 30° downward |
| **Radar Characteristics** | RF Frequency Band | 60-64 GHz |
|  | Tx/Rx Channels | 3TX / 4RX (see Note 1) |
|  | Modulation | FMCW |
|  | Output Power per TX Channel (EIRP) | 15 dBm |
| **Connectivity and Integration** | Cloud Protocols | MQTT, HTTP, HTTPS |
|  | Wi-Fi | Wi-Fi 802.11 b/g/n (2.4 GHz) |
|  | Local Communication | UART, native USB Type-C |
|  | Cellular Network | LTE Cat.1 bis (4G, full-network support) |
| **Hardware Architecture** | Processing Architecture | Dual-chip heterogeneous architecture (mmWave radar SoC + main MCU) |
|  | Radar Processing Unit | ARM Cortex-R4F + C674x DSP + Hardware Accelerator (HWA) |
|  | Main Controller | ESP32-S3 (dual-core Xtensa LX7, up to 240 MHz) |
|  | On-chip Memory | 512 KB (main MCU) + 1.75 MB (radar SoC) |
|  | PSRAM | 8 MB |
|  | Flash Storage | 8 MB (main MCU) + 4 MB (radar SoC, optional) |
|  | I/O and Indicators | 1x RGB LED, 1x key, 1x LED (optional) |
|  | IMU | Optional 6-axis gyroscope + 3-axis accelerometer |
|  | Ambient Light Sensor | Optional |
|  | Voice | Optional 1x speaker and 1x microphone |

> Note 1: Up to `2TX` simultaneous transmission is supported in `1.3 V` mode. `3TX` simultaneous transmission requires `1V LDO bypass` mode.

## 4. Local Interfaces and DATA Collection

WSR supports both UART and native USB collection. Neither directly attached path requires a network. MQTT is needed only for remote collection or split UART-control/MQTT-DATA workflows.

### 4.1 UART

WSR uses the same UART behavior as PRO: CLI JSON control starts at 115200, radar DATA is nominally 921600, and host raw UART uses at most 1000000.

```bash
./cli/run.sh collect --transport uart --port <uart-port> \
  --raw-baud 1000000 --duration 30
```

### 4.2 Native USB Type-C

The WSR Type-C port uses the same wiring and native USB function as WDR. It does not use the PRO external USB-to-UART communication path. Its USB DATA signals connect to the native ESP32-S3 USB pins:

| Type-C Signal | ESP32-S3 Signal |
| --- | --- |
| D- | GPIO19 / USB_D- |
| D+ | GPIO20 / USB_D+ |
| VBUS | 5V input |
| GND | GND |

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/mdr-m-usb-typec-reference.png" alt="Shared WSR and WDR Type-C signal-function reference" width="75%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">Shared WSR and WDR Type-C signal-function reference</p>
</div>

Native USB CDC carries CLI JSON control and radar DATA without Wi-Fi or MQTT. It has no user-configurable physical raw baud.

```bash
./cli/run.sh node info --transport usb --port <native-usb-port>
./cli/run.sh collect --transport usb --port <native-usb-port> --duration 30
```

Select the target from the `board=wsr` and device identity returned by `node info`; do not infer the board from a port name or USB descriptor alone.

## 5. Factory Flashing

WSR follows the WDR factory-flashing entry and can be flashed through native Type-C. Always use a WSR package. Its publication path is:

```text
./firmwares/esp/wsr/mmwk_sensor_bridge/v<version>/factory.zip
```

Extract the package and follow the [Factory Flash Guide](../docs/en/flash.md). After recovery, read `node info` over native USB and confirm `board=wsr` and `version`. PRO, WDR, and WSR packages are not interchangeable.

## 6. ESP Pin Description

WSR follows the PRO ESP32-S3 pin map. GPIO19/20 are routed to the WSR native USB Type-C port; all other pin functions remain unchanged.

| GPIO | Type | Function |
| --- | --- | --- |
| GPIO0 | I/O | ESP32_IO0 download setting |
| GPIO1 | I/O | I2C_SCL |
| GPIO2 | I/O | I2C_SDA |
| GPIO3 | I/O | I2S_DOUT |
| GPIO4 | I/O | I2S_DIN |
| GPIO5 | I/O | I2S_LRCK |
| GPIO6 | I/O | I2S_BCLK |
| GPIO7 | I/O | I2S_MCLK |
| GPIO8 | I/O | U2TXD |
| GPIO9 | I/O | U2RXD |
| GPIO10 | I/O | AR_NRST (BMI160 reset) |
| GPIO11 | I/O | SPI_MOSI (BMI160) |
| GPIO12 | I/O | U1RXD |
| GPIO13 | I/O | SPI_CS (BMI160) |
| GPIO14 | I/O | SPI_CLK (BMI160) |
| GPIO15 | I/O | SPI_MISO (BMI160) |
| GPIO16 | I/O | SPI_HOSR_INT (BMI160 interrupt) |
| GPIO17 | I/O | PA_CTL (RF PA control) |
| GPIO18 | I/O | VEML6030_INT |
| GPIO19 | I/O | USB_D- |
| GPIO20 | I/O | USB_D+ |
| GPIO21 | I/O | IOT_PWCTL |
| GPIO26-GPIO32 | SPI dedicated | Internal Flash/PSRAM |
| GPIO33 | I/O | KEY_IN |
| GPIO34 | I/O | BMI160_INT1 |
| GPIO35 | I/O | CAT1_RESET |
| GPIO36 | I/O | U0TXD (CAT1 serial TX) |
| GPIO37 | I/O | U0RXD (CAT1 serial RX) |
| GPIO38-GPIO42 | I/O | Internally reserved |
| GPIO43 | UART | Debug serial TXD (U0TXD) |
| GPIO44 | UART | Debug serial RXD (U0RXD) |
| GPIO45 | Input | ESP32_FLASH_POW_IO45 |
| GPIO46 | Input | STATUS (boot strapping pin) |

## 7. Related Documents

- [PRO Module Introduction](./pro.md)
- [WDR-M Main Controller Carrier Board Introduction](./wdr-m.md)
- [Radar DATA Collection](../cli/docs/en/data-collection.md)
- [Factory Flash Guide](../docs/en/flash.md)
