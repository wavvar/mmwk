# Product Module Overview

[中文版](./README_CN.md)

This directory contains documentation for three product lines: `RPX`, `WDR` with `ML6432Ax`, and `F9`. The sections below provide a quick product map and link to the corresponding detailed documents.

## 1. RPX Series

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/RPX/6843/MINI-module.png" alt="RPX MINI module" width="260" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">Representative module from the RPX series</p>
</div>

The `RPX` series focuses on standalone sensing modules and compact development platforms. It currently covers the `6843` branch and the `RPI` platform in the `6432` class.

- `MINI`, `RTP`, `RTL`, and `CFH` are `6843`-series modules for presence detection, tracking, occupancy sensing, and spatial perception.
- `RPI` is a compact `6432`-class sensing platform for low-power embedded integration and vital-sign related applications.
- Detailed documents: [RPX series guide](./rpx.md) | [中文](./rpx_cn.md)

## 2. WDR / ML6432Ax Series

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/mdr-module-top-view.png" alt="WDR module top view" width="70%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">Representative system view from the WDR series</p>
</div>

The `WDR` product series is a system-level platform built around the `ML6432Ax` radar-board family. In the detailed hardware document, the controller-board role is described as `MDR-M`, but the outward-facing product-series name is `WDR`.

- `WDR` is the complete module assembly formed by the `ML6432A_BO` radar board, the `MDR-M` main controller board, and the `4G Cat1` communication board.
- `WDR-M`, described as `MDR-M` in the detailed hardware notes, is the carrier and control board that connects the radar subsystem with local interfaces and cellular communication.
- `ML6432A_BO` is the preferred direct-plug radar-board option for the `WDR` platform.
- `ML6432A` provides the same radar-side functional class, but it is connected through an adapter cable instead of direct board insertion.
- Detailed documents: [MDR module introduction](./mdr.md) | [中文](./mdr_cn.md)
- Radar-board details: [ML6432Ax series introduction](./ml6432ax.md) | [中文](./ml6432ax_cn.md)

## 3. F9 Series

The `F9` series is represented here by rear safety radar products for electric two-wheel and three-wheel vehicles.

- `F9A1` is the standard rear safety radar module for blind-spot detection and related warning functions.
- `F9A1-D` is the matching installation variant for specific compatible vehicle structures.
- Detailed documents: [F9A1 technical specification](./f9a1.md) | [中文](./f9a1_cn.md)

## 4. Reading Guide

- Start with [rpx.md](./rpx.md) if you need a standalone sensing module or a compact development platform.
- Start with [mdr.md](./mdr.md) if you need a complete `6432`-based controller-and-communication platform, then continue with [ml6432ax.md](./ml6432ax.md) for radar-board details.
- Start with [f9a1.md](./f9a1.md) if the target application is rear safety sensing for electric two-wheel or three-wheel vehicles.
