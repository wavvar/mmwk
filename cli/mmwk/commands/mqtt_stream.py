"""MQTT binary stream data-plane helpers."""

import contextlib
import hashlib
import json
import os
import struct
import time
import zlib


STREAM_FRAME_MAGIC = 0x46534B4D
STREAM_FRAME_VERSION = 1
STREAM_FRAME_HEADER_LEN = 36
DEFAULT_CONTENT_TYPE = "application/octet-stream"
DEFAULT_MQTT_CHUNK_SIZE = 512
DEFAULT_MQTT_WINDOW = 1


class MqttStreamError(RuntimeError):
    """Raised when the device reports a stream data-plane error."""


class MqttStreamAckTimeout(TimeoutError):
    """Raised when stream ACK flow control stalls."""


def build_stream_frame(
    *,
    stream_token: int,
    seq: int,
    offset: int,
    total_size: int,
    payload: bytes,
    flags: int = 0,
) -> bytes:
    payload_bytes = bytes(payload or b"")
    header = struct.pack(
        "<IBB2xIIIIIII",
        STREAM_FRAME_MAGIC,
        STREAM_FRAME_VERSION,
        int(flags) & 0xFF,
        int(stream_token) & 0xFFFFFFFF,
        int(seq) & 0xFFFFFFFF,
        int(offset) & 0xFFFFFFFF,
        len(payload_bytes),
        int(total_size) & 0xFFFFFFFF,
        zlib.crc32(payload_bytes) & 0xFFFFFFFF,
        0,
    )
    return header + payload_bytes


class MqttStreamPublisher:
    """Publish one host-to-device MQTT binary stream and close it through control."""

    def __init__(
        self,
        mcp,
        *,
        timeout: float = 300.0,
        ack_timeout: float = 10.0,
        status_timeout: float = 2.0,
        poll_interval: float = 0.05,
    ):
        self.mcp = mcp
        self.timeout = float(timeout)
        self.ack_timeout = float(ack_timeout)
        self.status_timeout = float(status_timeout)
        self.poll_interval = float(poll_interval)
        self._preserved_notifications = []

    @staticmethod
    def _file_sha256(path) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as fp:
            for chunk in iter(lambda: fp.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _extract_payload(self, result) -> dict:
        if isinstance(result, dict):
            if "content" in result:
                text = self.mcp.extract_text(result)
                try:
                    payload = json.loads(text)
                except Exception:
                    return {}
                return payload if isinstance(payload, dict) else {}
            if "text" in result:
                try:
                    payload = json.loads(result["text"])
                except Exception:
                    return {}
                return payload if isinstance(payload, dict) else {}
            return dict(result)
        return {}

    def _call_stream(self, arguments: dict, *, timeout: float | None = None) -> dict:
        result = self.mcp.call_tool(
            "stream",
            arguments,
            timeout=self.timeout if timeout is None else float(timeout),
        )
        return self._extract_payload(result)

    def _publish_binary(self, topic: str, payload: bytes) -> None:
        transport = self.mcp.transport
        publish_binary = getattr(transport, "publish_binary", None)
        if callable(publish_binary):
            publish_binary(topic, payload, qos=getattr(transport, "qos", None))
            return

        client = getattr(transport, "client", None)
        if client is None:
            raise RuntimeError("MQTT stream requires a transport with binary publish support")
        qos = int(getattr(transport, "qos", 1))
        info = client.publish(topic, payload, qos=qos)
        wait_for_publish = getattr(info, "wait_for_publish", None)
        if qos > 0 and callable(wait_for_publish):
            wait_for_publish(timeout=5)

    @staticmethod
    def _notification_data(notification) -> dict:
        if not isinstance(notification, dict):
            return {}
        if str(notification.get("status", "")).startswith("stream_"):
            return notification
        params = notification.get("params")
        if not isinstance(params, dict):
            return {}
        data = params.get("data", {})
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                data = {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _terminal_device_error(data: dict) -> str:
        status = str(data.get("status") or "")
        if status != "device_ota_error":
            return ""
        url = data.get("url")
        if url not in (None, "", "mqtt-stream"):
            return ""
        if url in (None, "") and data.get("source") != "device":
            return ""
        return str(data.get("msg") or data.get("error") or status)

    @staticmethod
    def _stream_error_message(data: dict) -> str:
        return str(
            data.get("error")
            or data.get("msg")
            or data.get("status")
            or "stream_error"
        )

    def _drain_stream_events(self, stream_id: str) -> tuple[int | None, dict | None]:
        transport = self.mcp.transport
        drain = getattr(transport, "drain_notifications", None)
        notifications = drain() if callable(drain) else []
        ack_seq = None
        preserve = []

        for notification in notifications:
            data = self._notification_data(notification)
            if not data:
                preserve.append(notification)
                continue
            status = data.get("status")
            if self._terminal_device_error(data):
                self._preserved_notifications.extend(preserve)
                return None, data
            if data.get("stream_id") != stream_id:
                preserve.append(notification)
                continue
            if status == "stream_error":
                self._preserved_notifications.extend(preserve)
                return None, data
            if status == "stream_ack":
                try:
                    seq = int(data.get("seq"))
                except (TypeError, ValueError):
                    continue
                ack_seq = seq if ack_seq is None else max(ack_seq, seq)
                continue
            preserve.append(notification)

        self._preserved_notifications.extend(preserve)
        return ack_seq, None

    def _discard_stale_stream_notifications(self) -> None:
        transport = self.mcp.transport
        drain = getattr(transport, "drain_notifications", None)
        if not callable(drain):
            return

        preserve = []
        for notification in drain():
            data = self._notification_data(notification)
            status = str(data.get("status") or "") if data else ""
            if status.startswith("stream_"):
                continue
            preserve.append(notification)
        self._preserved_notifications.extend(preserve)

    def _restore_preserved_notifications(self) -> None:
        if not self._preserved_notifications:
            return
        notifications = list(self._preserved_notifications)
        self._preserved_notifications.clear()
        transport = self.mcp.transport
        restore = getattr(transport, "restore_notifications", None)
        if callable(restore):
            restore(notifications)
            return
        with getattr(transport, "lock", contextlib.nullcontext()):
            queue = getattr(transport, "notifications", None)
            if isinstance(queue, list):
                queue[:0] = notifications
                return
        add = getattr(transport, "add_notification", None)
        if callable(add):
            for notification in notifications:
                add(notification)

    def _abort_stream(self, reason: str, *, timeout: float | None = None) -> None:
        try:
            self._call_stream({"action": "abort", "reason": reason}, timeout=timeout)
        except Exception:
            pass

    def _raise_queued_error(self, stream_id: str) -> None:
        _ack_seq, stream_error = self._drain_stream_events(stream_id)
        if stream_error is not None:
            raise MqttStreamError(self._stream_error_message(stream_error))

    def _status_ack_seq(self, stream_id: str) -> int | None:
        try:
            status = self._call_stream({"action": "status"}, timeout=self.status_timeout)
        except Exception:
            return None

        if str(status.get("stream_id") or "") != stream_id:
            return None
        if str(status.get("status") or "") == "failed":
            raise MqttStreamError(self._stream_error_message(status))
        try:
            ack_seq = int(status.get("ack_seq"))
        except (TypeError, ValueError):
            return None
        if ack_seq < 0 or ack_seq == 0xFFFFFFFF:
            return None
        return ack_seq

    def _wait_for_ack(self, stream_id: str, pending_seq: int) -> int:
        deadline = time.monotonic() + max(0.0, self.ack_timeout)
        while True:
            ack_seq, stream_error = self._drain_stream_events(stream_id)
            if stream_error is not None:
                raise MqttStreamError(self._stream_error_message(stream_error))
            if ack_seq is not None and ack_seq >= pending_seq:
                return ack_seq
            if time.monotonic() >= deadline:
                status_ack_seq = self._status_ack_seq(stream_id)
                if status_ack_seq is not None and status_ack_seq >= pending_seq:
                    return status_ack_seq
                self._abort_stream("ack_timeout", timeout=self.status_timeout)
                raise MqttStreamAckTimeout(f"Timed out waiting for stream ACK seq={pending_seq}")
            if self.poll_interval > 0:
                time.sleep(self.poll_interval)

    def publish_file(
        self,
        path,
        *,
        target: str,
        object_name: str,
        metadata: dict | None = None,
        content_type: str = DEFAULT_CONTENT_TYPE,
        chunk_size: int | None = None,
        window: int | None = None,
    ) -> dict:
        file_path = os.fspath(path)
        size = os.path.getsize(file_path)
        sha256 = self._file_sha256(file_path)
        open_args = {
            "action": "open",
            "direction": "host_to_device",
            "purpose": "ota",
            "target": target,
            "object": object_name,
            "size": size,
            "sha256": sha256,
            "content_type": content_type,
            "expires_ms": min(0xFFFFFFFF, max(1000, int(self.timeout * 1000))),
        }
        if metadata:
            open_args["metadata"] = dict(metadata)
        open_args["chunk_size"] = int(chunk_size or DEFAULT_MQTT_CHUNK_SIZE)
        open_args["window"] = int(window or DEFAULT_MQTT_WINDOW)

        abort_reason = "status_error"
        self._discard_stale_stream_notifications()
        try:
            opened = self._call_stream(open_args)
            stream_id = str(opened.get("stream_id") or "")
            data_topic = str(opened.get("data_topic") or "")
            if not stream_id or not data_topic:
                raise RuntimeError("stream.open response missing stream_id or data_topic")
            try:
                stream_token = int(opened["stream_token"])
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError("stream.open response missing stream_token") from exc

            frame_chunk_size = int(opened.get("chunk_size") or chunk_size or 1024)
            frame_window = int(opened.get("window") or window or 1)
            if frame_chunk_size <= 0 or frame_window <= 0:
                self._abort_stream("invalid_open")
                raise RuntimeError("stream.open returned invalid chunk_size/window")

            self._call_stream({"action": "status"})

            pending = set()
            seq = 0
            offset = 0

            with open(file_path, "rb") as fp:
                while offset < size or pending:
                    while offset < size and len(pending) < frame_window:
                        payload = fp.read(frame_chunk_size)
                        if not payload:
                            break
                        frame = build_stream_frame(
                            stream_token=stream_token,
                            seq=seq,
                            offset=offset,
                            total_size=size,
                            payload=payload,
                        )
                        abort_reason = "publish_error"
                        self._publish_binary(data_topic, frame)
                        pending.add(seq)
                        offset += len(payload)
                        seq += 1

                    if pending:
                        abort_reason = "ack_error"
                        ack_seq = self._wait_for_ack(stream_id, min(pending))
                        pending = {item for item in pending if item > ack_seq}

            abort_reason = "close_error"
            try:
                close_result = self._call_stream({"action": "close"})
            except Exception as exc:
                try:
                    self._raise_queued_error(stream_id)
                except MqttStreamError as stream_exc:
                    raise stream_exc from exc
                raise
            self._raise_queued_error(stream_id)
            return close_result
        except MqttStreamAckTimeout:
            raise
        except Exception:
            self._abort_stream(abort_reason)
            raise
        finally:
            self._restore_preserved_notifications()
