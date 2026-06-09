# WDR-4G Communication Board Introduction

[Chinese Version](./wdr-4g_cn.md)

## Table of Contents

- [1. Board Overview](#1-board-overview)
- [2. Technical Specifications and Key Features](#2-technical-specifications-and-key-features)
- [3. System Role Description](#3-system-role-description)
- [4. Interconnect and Board-Level Reference Diagrams](#4-interconnect-and-board-level-reference-diagrams)
- [5. Related Documents](#5-related-documents)

## 1. Board Overview

`WDR-4G` is the `4G Cat1` communication board in the `WDR` system. In `MDR` system documentation, this board appears as the `4G Cat1` communication board and is used to provide cellular communication and remote connectivity. A complete `WDR` module is composed of the `ML6432A_BO` radar board, the `MDR-M` main controller board, and the `4G Cat1` communication board, making it suitable for complete-device solutions that require both local sensing and remote networking.

## 2. Technical Specifications and Key Features

| Category | Item | Specification |
| --- | --- | --- |
| **Power** | Input Supply | 5V2A |
| **Environmental Parameters** | Operating Temperature | 0 to +40°C |
|  | Storage Temperature | -40°C to +85°C |
|  | Operating Humidity | ≤95% (non-condensing) |
| **External Interfaces** | P3 | 4-pin, USB + UART communication interface |
|  | P4 | 4-pin, power + control interface |
| **P3 Interface Definition** | USB_DP | USB differential signal D+ |
|  | USB_DM | USB differential signal D- |
|  | UART_TX | Main module serial transmit (`MAIN_TXD`) |
|  | UART_RX | Main module serial receive (`MAIN_RXD`) |
| **P4 Interface Definition** | VBAT | External power input |
|  | GND | Power ground |
|  | CAT1_RST | Module reset / power-on control |
| **Communication Capability** | UART | Main AT command channel for communication with an external host controller |
|  | USB | Supports USB 2.0 (CDC virtual serial port) for AT commands, debugging, and upgrades |
| **SIM Function** | SIM Type | Nano SIM |
|  | SIM Interface | On-board SIM circuit with protection and filtering |
| **RF** | Antenna Interface | IPEX antenna connector |
| **Control and Status** | Status Indicator | On-board LED for network status indication |
| **On-board Fixed Features** | SIM Protection | TVS + matching circuit |
|  | USB Protection | TVS protection |

## 3. System Role Description

Within the `WDR` system, `WDR-4G` is responsible for cellular communication and data backhaul during field deployment. `WDR-M` sits in the middle layer and connects the radar board to `WDR-4G`, while also providing the interfaces required for local debugging, board-level control, and communication routing. `WDR-4G` and `WDR-M` communicate over a USB link.

| Associated Board | Relationship | Description |
| --- | --- | --- |
| `WDR-M` (`MDR-M`) | Main control and interconnect | `WDR-4G` connects to `WDR-M` through dedicated board-level signals |
| `ML6432A_BO` radar board | System component | Forms the complete `WDR` module together with `WDR-M` and `WDR-4G` |

## 4. Interconnect and Board-Level Reference Diagrams

The diagrams below illustrate the relationship between `WDR-4G` and `WDR-M`, together with an interface schematic reference.

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/mdr-cat1-board-interface-schematic.png" alt="4G Cat1 communication board interface schematic" width="85%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">Figure 1. WDR-4G interface schematic reference</p>
</div>

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/mdr-m-to-cat1-board-connection.png" alt="MDR-M to Cat1 communication board connection reference" width="85%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">Figure 2. WDR-4G to WDR-M connection reference</p>
</div>

These references are suitable for checking how `WDR-4G` is integrated into the system, tracing the board-to-board connections, or reviewing how the communication board connects into `WDR-M`.

## 5. Related Documents

- [MDR Module Introduction](./mdr.md)
- [WDR-M Main Controller Carrier Board Introduction](./wdr-m.md)
