# Bridge

Use `./cli/run.sh` from the package root for bridge bring-up, control, ESP OTA, radar firmware work, and collection flows. The CLI README contains the current public command surface and transport notes.

Bridge is the baseline transparent-passthrough profile for radar firmware development and raw capture. Start with `node info`, configure network and MQTT as needed, then use `radar fw ...`, `radar config ...`, `radar raw ...`, and `collect` from the public CLI.

Treat `collect` as the official command for the startup-aware bridge checklist. It can use `-p <serial-port>` to discover MQTT route identity, bootstrap raw passthrough, and capture both `raw_data` and startup-trimmed `raw_resp` into host files.

The helper scripts remain available when you need a published task wrapper instead of the main CLI flow:

- Use `./cli/config.sh set` to push Wi-Fi and MQTT settings over UART or an existing MQTT control path.
- Use `./cli/collect.sh` for registry-backed task collection.
- Use `./cli/collect.sh --trigger none|radar-restart|device-reboot` only when you intentionally want the external pure-MQTT startup helper.

For the detailed bridge contract, command sequence, and runtime verification notes, see [Bridge Reference](./bridge-reference.md). For the complete bring-up and five-minute raw capture walkthrough, see the [Local MQTT/HTTP End-to-End Collection Example](../../cli/docs/en/data-collection.md#9-local-mqtthttp-end-to-end-collection-example).
