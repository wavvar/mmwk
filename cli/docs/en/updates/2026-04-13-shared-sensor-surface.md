# Shared Sensor Surface Update

Date: 2026-04-13

## Summary

- `bridge` and `hub` now share one sensor runtime core.
- `bridge` and `hub` remain compile-time profiles; there is no runtime bridge/hub profile switch.
- Public discovery now centers on `proto` and `endpoint`, rather than on legacy facades such as `adapter` or `catalog`.
- For multi-sensor devices, child endpoints own measurements, events, and truth; composite endpoints only aggregate or orchestrate topology.

## Current Public Surface

Current public surfaces:

- `proto`
- `endpoint`
- `radar`
- `radar.config`
- `radar.fw`
- `radar.raw`
- `scene` as a hub-only surface

Current meanings:

- `proto list|status|manifest` is the node public protocol directory.
- `endpoint list --json` and `endpoint describe` expose the Matter-oriented endpoint directory.
- `scene` is a hub-only orchestration facade; it does not replace endpoint truth ownership.

Removed from public help/discovery:

- `adapter`
- `policy`
- top-level `raw`
- `raw_capture`

## Migration

| Old command | New command |
|---|---|
| `catalog` | `endpoint list` |
| `adapter list` | `proto list` |
| `adapter status <protocol>` | `proto status <protocol>` |
| `adapter manifest <protocol>` | `proto manifest <protocol>` |
| `raw record status` | `radar raw status` |
| `raw record start --uri ...` | `radar raw start --uri ...` |
| `raw record trigger --event ... --duration ...` | `radar raw trigger --event ... --duration-s ...` |
| `policy show` / `policy set` | no public 1:1 replacement; use `endpoint config get|set <id>` and `radar raw config get|set` |

## Publish Note

- This update record remains published with `mmwk_cli`; it is historical context, not a separate legacy contract.
- The canonical current contract still lives in the main English and Chinese `README.md` files.
