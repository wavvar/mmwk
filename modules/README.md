# Product Module Overview

[中文版](./README_CN.md)

This directory contains documentation for three product lines: [`RPX`](./rpx.md), [`WDR / MDR`](./mdr.md) with [`ML6432Ax`](./ml6432ax.md), and [`F9`](./f9a1.md). The sections below provide a quick product map and link to the corresponding detailed documents.

## 1. RPX Series

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/RPX/6843/MINI-module.png" alt="RPX MINI module" width="260" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">Representative module from the RPX series</p>
</div>

The `RPX` series focuses on standalone sensing modules and compact development platforms. It currently covers the `6843` branch and the `RPI` platform in the `6432` class.

- [`MINI`](./mini.md), [`PRO (RTP)`](./pro.md), `RTL`, and `CFH` are `6843`-series modules for presence detection, tracking, occupancy sensing, and spatial perception.
- [`RPI`](./rpx.md#3-rpi-6432-sensing-module) is a compact `6432`-class sensing platform for low-power embedded integration and vital-sign related applications.
- Detailed documents: [RPX series guide](./rpx.md) | [中文](./rpx_cn.md)
- Dedicated module docs: [MINI](./mini.md) | [PRO](./pro.md)

## 2. WDR / ML6432Ax Series

<div style="text-align: center; margin: 10px 0;">
  <img src="./img/MDR/mdr-module-top-view.png" alt="WDR module top view" width="70%" style="display: block; margin: 0 auto;" />
  <p style="margin: 4px 0 0 0;">Representative system view from the WDR series</p>
</div>

The `WDR` product series is a system-level platform built around the `ML6432Ax` radar-board family. In the [detailed hardware document](./mdr.md), the controller-board role is described as `MDR-M`, but the outward-facing product-series name is `WDR`.

- `WDR` is the complete module assembly formed by the `ML6432A_BO` radar board, the `MDR-M` main controller board, and the `4G Cat1` communication board.
- [`WDR-M`](./wdr-m.md), described as `MDR-M` in the detailed hardware notes, is the carrier and control board that connects the radar subsystem with local interfaces and cellular communication.
- [`WDR-4G`](./wdr-4g.md) is the communication board responsible for cellular connectivity in the `WDR` system.
- [`ML6432A_BO`](./ml6432a_bo.md) is the preferred direct-plug radar-board option for the `WDR` platform.
- [`ML6432A`](./ml6432a.md) provides the same radar-side functional class, but it is connected through an adapter cable instead of direct board insertion.
- System overview: [MDR module introduction](./mdr.md) | [中文](./mdr_cn.md)
- Board-level details: [WDR-M](./wdr-m.md) | [中文](./wdr-m_cn.md) | [WDR-4G](./wdr-4g.md) | [中文](./wdr-4g_cn.md)
- Radar-board details: [ML6432Ax series introduction](./ml6432ax.md) | [中文](./ml6432ax_cn.md) | [ML6432A_BO](./ml6432a_bo.md) | [中文](./ml6432a_bo_cn.md) | [ML6432A](./ml6432a.md) | [中文](./ml6432a_cn.md)

## 3. F9 Series

The `F9` series is represented here by rear safety radar products for electric two-wheel and three-wheel vehicles.

- `F9A1` is the standard rear safety radar module for blind-spot detection and related warning functions.
- `F9A1-D` is the matching installation variant for specific compatible vehicle structures.
- Detailed documents: [F9A1 technical specification](./f9a1.md) | [中文](./f9a1_cn.md)

## 4. Reading Guide

- Start with [mini.md](./mini.md) or [pro.md](./pro.md) for dedicated `6843` module details, or [rpx.md](./rpx.md) if you want the broader RPX product map including `RPI`.
- Start with [mdr.md](./mdr.md) if you need a complete `6432`-based controller-and-communication platform, then continue with [wdr-m.md](./wdr-m.md), [wdr-4g.md](./wdr-4g.md), [ml6432a_bo.md](./ml6432a_bo.md), or [ml6432a.md](./ml6432a.md) for board-level details.
- Start with [f9a1.md](./f9a1.md) if the target application is rear safety sensing for electric two-wheel or three-wheel vehicles.
