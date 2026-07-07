from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket
from groovy.executor.live_midi import LiveIoState
from groovy.executor.osc_live import OscCaptureStore, parse_widget_target


class MidiInHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        message = json.dumps(payload)
        for ws in self._clients:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


class OscUdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, project_dir, live_state: LiveIoState, hub: MidiInHub) -> None:
        self.project_dir = project_dir
        self.live_state = live_state
        self.hub = hub
        self.store = OscCaptureStore(project_dir)

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if not self.live_state.settings.osc_live_enabled:
            return
        if addr[0] not in {"127.0.0.1", "::1"}:
            return
        parsed = _parse_osc_message(data)
        if not parsed:
            return
        address, args = parsed
        if not self.store.append(address, args):
            return
        target = parse_widget_target(address)
        asyncio.create_task(
            self.hub.broadcast(
                {
                    "type": "osc.message",
                    "address": address,
                    "args": args,
                    "target": {"node_id": target[0], "param": target[1]} if target else None,
                }
            )
        )


def _pad4(index: int) -> int:
    return (index + 3) & ~3


def _parse_osc_message(data: bytes) -> tuple[str, list[Any]] | None:
    if not data or b"\x00" not in data:
        return None
    end = data.index(0)
    address = data[:end].decode("utf-8", errors="ignore")
    offset = _pad4(end + 1)
    if offset >= len(data):
        return address, []
    tag_end = data.index(0, offset)
    tags = data[offset:tag_end].decode("ascii", errors="ignore")
    offset = _pad4(tag_end + 1)
    args: list[Any] = []
    for tag in tags[1:]:
        if tag == "f" and offset + 4 <= len(data):
            import struct

            args.append(struct.unpack(">f", data[offset : offset + 4])[0])
            offset += 4
        elif tag == "i" and offset + 4 <= len(data):
            import struct

            args.append(struct.unpack(">i", data[offset : offset + 4])[0])
            offset += 4
        elif tag == "s":
            end_str = data.index(0, offset)
            args.append(data[offset:end_str].decode("utf-8", errors="ignore"))
            offset = _pad4(end_str + 1)
        else:
            break
    return address, args


async def start_osc_listener(project_dir, live_state: LiveIoState, hub: MidiInHub) -> asyncio.DatagramTransport | None:
    loop = asyncio.get_running_loop()
    try:
        transport, _ = await loop.create_datagram_endpoint(
            lambda: OscUdpProtocol(project_dir, live_state, hub),
            local_addr=("127.0.0.1", 9000),
        )
        return transport
    except OSError:
        return None
