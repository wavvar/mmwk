"""Run the public CLI local MQTT broker with aMQTT."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from pathlib import Path

import yaml
from amqtt.broker import Broker


def _load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle) or {}
    if not isinstance(value, dict):
        raise ValueError(f"aMQTT config must be a mapping: {path}")
    return value


async def _run(config_path: Path) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [local_mqtt] %(levelname)s %(name)s: %(message)s",
    )
    broker = Broker(_load_config(config_path))
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_stop() -> None:
        loop.call_soon_threadsafe(stop_event.set)

    for signame in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, signame, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, request_stop)
        except (NotImplementedError, RuntimeError):
            signal.signal(sig, lambda _sig, _frame: request_stop())

    await broker.start()
    print("aMQTT broker started", flush=True)
    try:
        await stop_event.wait()
    finally:
        await broker.shutdown()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the MMWK local aMQTT broker")
    parser.add_argument("--config", required=True, help="Path to generated aMQTT YAML config")
    args = parser.parse_args(argv)
    return asyncio.run(_run(Path(args.config)))


if __name__ == "__main__":
    raise SystemExit(main())
