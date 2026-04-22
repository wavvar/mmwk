# Wavvar MMWK Canonical CLI Protocol V1.0

This document defines the default canonical CLI JSON protocol used by current MMWK bridge/hub host flows. It is transport-neutral and carries the same service/action surface as the legacy MCP tool layer.

## Scope

- Default host protocol for `mmwk_cli`
- Same service names as the MCP tool namespace: `device`, `radar`, `fw`, `record`, `network`, `catalog`, `entity`, `scene`, `policy`, `help`, and related extensions
- Works over both UART and MQTT

`mmwk_cli` now defaults to this protocol. During the migration window, omitting `--protocol` prints a warning so callers can upgrade explicitly to `--protocol cli`. Use `--protocol mcp` only as a compatibility fallback.

## Transport and Framing

- **UART**: newline-delimited JSON objects on UART0 at 115200 baud
- **MQTT**: JSON objects published to the configured `cmd_topic` / `resp_topic`

Each request is a single JSON object. Batch arrays are not part of this protocol.

## Envelope

Type values are abbreviated:

- `req`: request
- `res`: response
- `evt`: event

Correlation uses `seq`. Events carry only `ts` as transport-level time metadata.

## Request

```json
{"type":"req","seq":1,"service":"device","action":"hi","args":{}}
```

Rules:

- `type` must be `req`
- `seq` must be a non-negative integer
- `service` must be a non-empty string
- `action` is optional but, when present, must be a string
- `args` is optional; when present it must be a JSON object

## Success Response

```json
{"type":"res","seq":1,"ok":true,"result":{"name":"mmwk_sensor_bridge","version":"1.2.2"}}
```

Rules:

- `type` is `res`
- `seq` echoes the request `seq`
- `ok=true` means `result` is present
- `result` is the canonical service payload object

## Error Response

```json
{"type":"res","seq":1,"ok":false,"error":{"code":"not.found","message":"Unknown service"}}
```

Error code strings currently include:

- `invalid.json`
- `invalid.req`
- `not.found`
- `invalid.arg`
- `unauthorized`
- `internal`

## Event

```json
{"type":"evt","service":"radar","event":"progress","ts":1712040000000,"data":{"status":"flash_progress","progress":50}}
```

Rules:

- Events are unsolicited
- `service` identifies the producer namespace
- `event` is the event name inside that namespace
- `ts` is a JSON-exact timestamp in milliseconds
- `data` is the event payload object

## Service Compatibility

The canonical CLI JSON protocol keeps the existing host command surface stable by preserving the same service and action vocabulary that the MCP tool layer already exposed.

Examples:

- `device hi` maps to `{"service":"device","action":"hi","args":{}}`
- `radar start --mode auto` maps to `{"service":"radar","action":"start","args":{"mode":"auto"}}`
- `help` maps to `{"service":"help","args":{}}`

## Compatibility With MCP

- MCP remains supported for callers that explicitly select `--protocol mcp`
- Service payload semantics stay aligned across CLI JSON and MCP
- The MCP compatibility specification lives in [MCPv1.md](./MCPv1.md)
