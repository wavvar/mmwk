# ESP32-S3-BOX-3 Dock radar guide

[中文版](./box3_cn.md)

## Scope

This guide covers an ESP32-S3-BOX-3 with its BOX-3 Dock and an
ML6432A/ML6432A_BO (IWRL6432) radar. `BOX3` is a separate SDK board target.
Only the Dock radar adapter follows the WDR-class 6432 radar contract; the
native BOX3 display, touch, audio, and boot-button pins are not remapped to
WDR pins.

## Dock-to-radar wiring

Use the Dock GPIO labels below. Arrows describe signal direction from the
ESP32 host's point of view.

| BOX-3 Dock | Radar pin | Function |
| ---: | --- | --- |
| GPIO41 | P1.2 `RS232_RX` | Radar command UART TX (ESP -> radar) |
| GPIO40 | P1.4 `RS232_TX` | Radar command UART RX (radar -> ESP) |
| GPIO11 | P1.1 `SPIA_MOSI` | SPI MOSI |
| Not connected | P1.3 `SPIA_MISO` | SPI MISO is unavailable; GPIO13 is used by MODE_SET |
| GPIO14 | P1.6 `SPIA_CLK` | SPI clock |
| GPIO21 | P1.5 `SPIA_CS` | SPI chip select |
| GPIO10 | P2.2 `NRESET` | Radar reset/power control |
| GPIO13 | P2.5 `MCU_IO_MODE_SET` | Radar SOP/boot-mode control |
| Dock 3V3 | P2.1 `RA_3V3` | Continuously powered radar 3.3 V rail |
| Dock GND | P2.3 GND | Common ground |

P2.4 and P2.6 CAN and `RADA_POW_CTL` are not connected in this adapter. Supply
`RA_3V3` continuously from a regulated 3.3 V source sized for the radar's peak
current; do not power the radar directly from an ESP32 GPIO. GPIO10 `NRESET`
is retained for deterministic UART flash-mode switching. GPIO40 and GPIO41
cannot be used for external JTAG while the radar adapter is connected.

The 6432 radar command and runtime data share UART1 in this target. The SDK
therefore leaves a separate data UART unassigned. The connector does not
provide an independent SPI IRQ/control line, so `SPI_INT` is intentionally
`-1`. SPI MISO is also `-1` because GPIO13 is assigned to MODE_SET; BOX3
validation is UART-only.

## Native BOX3 pins retained

The SDK keeps the documented BOX3 peripherals on their native pins:

- Audio: I2S MCLK/LRCK/SCLK/DIN/DOUT = GPIO2/45/17/16/15, PA = GPIO46,
  codec I2C = GPIO8/18.
- Display: ILI9341 MOSI/SCLK/CS/DC/RST/backlight = GPIO6/7/5/4/48/47.
- Touch interrupt = GPIO3; boot button = GPIO0; no native status LED is
  claimed by the radar bridge.

These pins are reserved for BOX3's own peripherals and are not used for the
Dock radar signals listed above.

## Build and validation boundary

From the SDK checkout, build the bridge target explicitly:

```bash
cd mmwk_sdk/projects/mmwk_sensor_bridge
./build.sh box3
```

The target stages the 6432 `radw_6432.release.appimage` and
`radw_6432_wdr.cfg` assets and exposes the standard radar command, reset,
SOP, status, and raw-data paths. Hardware validation covers the UART path and
excludes SPI firmware flash/write validation.
