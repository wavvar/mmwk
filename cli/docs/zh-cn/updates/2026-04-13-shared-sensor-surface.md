# 共享 Sensor Surface 更新记录

日期：2026-04-13

## 摘要

- `bridge` 和 `hub` 现在共享一套 sensor runtime core。
- `bridge` / `hub` 仍然是编译期 profile，不存在运行期 bridge/hub profile 切换。
- 当前公开发现中心已经收敛到 `proto` 和 `endpoint`，不再以 `adapter`、`catalog` 这类 legacy facade 为中心。
- 对多传感器设备，子 endpoint 拥有测量真值、事件真值和状态真值；组合 endpoint 只负责聚合或拓扑编排。

## 当前公开 Surface

当前公开 surface：

- `proto`
- `endpoint`
- `radar`
- `radar.config`
- `radar.fw`
- 统一 `radar` raw/record action
- `scene`（仅 hub）

当前 raw 路由和采集语义请以独立的[雷达 DATA 采集指南](../data-collection.md)
为准；本页只保留历史 surface 迁移记录。

当前含义：

- `proto list|status|manifest` 表示节点公开协议目录。
- `endpoint list --json` 和 `endpoint describe` 表示面向 Matter 的 endpoint 目录。
- `scene` 是 hub 专属的编排 facade，不会替代 endpoint 真值归属。

已从公开 help/discovery 中移除：

- `adapter`
- `policy`
- 顶层 `raw`
- `raw_capture`

## 迁移示例

| 旧命令 | 新命令 |
|---|---|
| `catalog` | `endpoint list` |
| `adapter list` | `proto list` |
| `adapter status <protocol>` | `proto status <protocol>` |
| `adapter manifest <protocol>` | `proto manifest <protocol>` |
| `raw record status` | `radar record status` |
| `raw record start --uri ...` | `radar record start --uri ...` |
| `raw record trigger --event ... --duration ...` | `radar record trigger --event ... --duration-s ...` |
| `policy show` / `policy set` | 没有公开的一对一替代；改用 `endpoint config get|set <id>` 和 `radar record config get|set` |

## 发布说明

- 这份更新记录会继续随 `mmwk_cli` 一起发布；它是历史变更说明，不是另一套 legacy 契约。
- 当前唯一有效的公开契约仍以中英文 `README.md` 为准。
