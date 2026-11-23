import asyncio
import json
import logging

import websockets

logger = logging.getLogger("evasion_detect")


class CDPClient:
    def __init__(self, port: int = 9222):
        self.port = port
        self._ws = None
        self._msg_id = 0
        self._responses: dict[int, asyncio.Future] = {}
        self._listener_task = None

    async def connect(self, target_url: str | None = None) -> None:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(f"http://localhost:{self.port}/json")
            targets = resp.json()

        target = targets[0]
        if target_url:
            target = next((t for t in targets if target_url in t.get("url", "")), targets[0])

        ws_url = target["webSocketDebuggerUrl"]
        self._ws = await websockets.connect(ws_url, max_size=10 * 1024 * 1024)
        self._listener_task = asyncio.create_task(self._listen())
        logger.info(f"CDP connected to {target.get('url', 'unknown')}")

    async def disconnect(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
        if self._ws:
            await self._ws.close()

    async def send(self, method: str, params: dict | None = None, timeout: float = 30.0) -> dict:
        self._msg_id += 1
        msg_id = self._msg_id

        message = {"id": msg_id, "method": method, "params": params or {}}
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._responses[msg_id] = future

        await self._ws.send(json.dumps(message))

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._responses.pop(msg_id, None)
            logger.error(f"CDP timeout: {method}")
            raise

    async def evaluate(self, expression: str, timeout: float = 30.0) -> dict:
        result = await self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
            timeout=timeout,
        )
        return result.get("result", {}).get("result", {}).get("value")

    async def navigate(self, url: str, timeout: float = 60.0) -> None:
        await self.send("Page.navigate", {"url": url}, timeout=timeout)
        await self.send("Page.enable")
        await asyncio.sleep(2)

    async def _listen(self) -> None:
        try:
            async for message in self._ws:
                data = json.loads(message)
                msg_id = data.get("id")
                if msg_id and msg_id in self._responses:
                    self._responses.pop(msg_id).set_result(data.get("result", {}))
        except websockets.ConnectionClosed:
            pass
        except asyncio.CancelledError:
            pass
