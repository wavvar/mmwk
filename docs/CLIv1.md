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
- `key` is optional and, when present, must be a top-level string field; do not put it inside `args`

## Key Protection

Factory or empty-key devices remain open. Once `node key set` stores a non-empty key, protected CLI requests over both UART and MQTT must include the correct top-level `"key"` field:

```json
{"type":"req","seq":2,"service":"radar","action":"status","key":"YOUR_KEY","args":{}}
```

Rules:

- `key` is never echoed in responses.
- There is no login/session/authenticate step in CLIv1; every protected request carries `key`.
- Public requests work without `key`: `help`, `proto list`, `proto status`, `proto manifest`, `node info` public view, and `node key status`.
- Protected requests include radar, network, endpoint, scene, node mutation/sensitive reads, `node key set` when a key already exists, and `node key clear`.
- Missing or wrong `key` on protected requests returns `unauthorized`.
- If a public request with a private view receives a wrong `key`, it returns `unauthorized`.

`node info` is public but has two views:

- When no key is stored, it returns the full existing identity/metadata payload and includes `auth_enabled=false`.
- When a key is stored and no `key` is supplied, it returns only public identity fields such as `name`, `board`, `version`, `id`, plus `auth_enabled` and `auth_required`.
- When the correct `key` is supplied, it returns the full identity/metadata payload.

Key management is under `node key`:

```json
{"type":"req","seq":3,"service":"node","action":"key","args":{"op":"status"}}
{"type":"req","seq":4,"service":"node","action":"key","args":{"op":"set","new_key":"YOUR_KEY"}}
{"type":"req","seq":5,"service":"node","action":"key","key":"YOUR_KEY","args":{"op":"clear"}}
```

- `status` is public and returns `enabled` / `required`.
- `set` sets the initial key when no key exists; when protection is already enabled, it updates the key only if the current top-level `key` is correct.
- `clear` removes the stored key and requires the current correct top-level `key`.
- There is no `rotate` operation; updating is handled by `set`.

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
