"""Polite async HTTP: identifying UA, conditional GETs, bounded retries, per-host caps (research §15, §18)."""
from __future__ import annotations

import asyncio
import json
import logging
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

log = logging.getLogger(__name__)

MAX_BYTES = 50 * 1024 * 1024         # Ashby/OpenAI ≈ 14 MB, Simplify ≈ 13 MB; anything past 50 MB is wrong
RETRY_STATUS = {429, 500, 502, 503, 504}
PER_HOST = defaultdict(lambda: 2, {"api.lever.co": 1})
HOST_DELAY = {"api.lever.co": 1.0}   # Lever robots.txt: Crawl-delay: 1


class FetchError(Exception):
    def __init__(self, msg: str, status: int | None = None):
        super().__init__(msg)
        self.status = status


@dataclass
class Response:
    status: int
    data: Any | None          # parsed JSON, None on 304
    etag: str | None
    url: str

    @property
    def not_modified(self) -> bool:
        return self.status == 304


class Http:
    def __init__(self, user_agent: str, global_limit: int = 8):
        self.client = httpx.AsyncClient(
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            timeout=httpx.Timeout(60, connect=10),
            follow_redirects=True,
        )
        self._global = asyncio.Semaphore(global_limit)
        self._hosts: dict[str, asyncio.Semaphore] = {}

    def _host_sem(self, host: str) -> asyncio.Semaphore:
        if host not in self._hosts:
            self._hosts[host] = asyncio.Semaphore(PER_HOST[host])
        return self._hosts[host]

    async def close(self) -> None:
        await self.client.aclose()

    async def request(self, method: str, url: str, *, etag: str | None = None,
                      json_body: Any = None, params: dict | None = None, retries: int = 3) -> Response:
        host = urlsplit(url).netloc
        headers = {"If-None-Match": etag} if etag else {}
        attempt = 0
        while True:
            attempt += 1
            async with self._global, self._host_sem(host):
                try:
                    async with self.client.stream(method, url, headers=headers, json=json_body, params=params) as r:
                        if r.status_code == 304:
                            return Response(304, None, etag, str(r.url))
                        if r.status_code in RETRY_STATUS and attempt <= retries:
                            wait = _retry_after(r) or (2 ** attempt) * random.uniform(0.75, 1.25)
                        elif r.status_code >= 400:
                            raise FetchError(f"HTTP {r.status_code} for {url}", r.status_code)
                        else:
                            if int(r.headers.get("content-length") or 0) > MAX_BYTES:
                                raise FetchError(f"payload too large for {url}")
                            buf = bytearray()
                            async for chunk in r.aiter_bytes():
                                buf += chunk
                                if len(buf) > MAX_BYTES:
                                    raise FetchError(f"payload exceeded {MAX_BYTES} bytes for {url}")
                            try:
                                data = json.loads(buf)
                            except ValueError as e:
                                raise FetchError(f"invalid JSON from {url}: {e}") from e
                            return Response(r.status_code, data, r.headers.get("etag"), str(r.url))
                except (httpx.TransportError, httpx.TimeoutException) as e:
                    if attempt > retries:
                        raise FetchError(f"{type(e).__name__} for {url}") from e
                    wait = (2 ** attempt) * random.uniform(0.75, 1.25)
                finally:
                    if host in HOST_DELAY:
                        await asyncio.sleep(HOST_DELAY[host])
            log.info("retrying %s in %.1fs (attempt %d)", url, wait, attempt)
            await asyncio.sleep(wait)

    async def get(self, url: str, **kw) -> Response:
        return await self.request("GET", url, **kw)

    async def get_text(self, url: str, params: dict | None = None, retries: int = 3) -> str:
        """A page that is not JSON (Markdown lists, Next.js HTML), with the same retries and size cap."""
        host = urlsplit(url).netloc
        for attempt in range(1, retries + 2):
            async with self._global, self._host_sem(host):
                try:
                    r = await self.client.get(url, params=params, headers={"Accept": "text/html,text/plain,*/*"})
                    if r.status_code in RETRY_STATUS and attempt <= retries:
                        wait = _retry_after(r) or (2 ** attempt) * random.uniform(0.75, 1.25)
                    elif r.status_code >= 400:
                        raise FetchError(f"HTTP {r.status_code} for {url}", r.status_code)
                    elif len(r.content) > MAX_BYTES:
                        raise FetchError(f"payload too large for {url}")
                    else:
                        return r.text
                except (httpx.TransportError, httpx.TimeoutException) as e:
                    if attempt > retries:
                        raise FetchError(f"{type(e).__name__} for {url}") from e
                    wait = (2 ** attempt) * random.uniform(0.75, 1.25)
            await asyncio.sleep(wait)
        raise FetchError(f"gave up on {url}")

    async def resolve(self, url: str) -> str:
        """Where a short link (go.vansh.nyc/Zy) ends up after redirects. The body is never read."""
        host = urlsplit(url).netloc
        async with self._global, self._host_sem(host):
            try:
                async with self.client.stream("GET", url, headers={"Accept": "text/html,*/*"}) as r:
                    return str(r.url)
            except (httpx.TransportError, httpx.TimeoutException) as e:
                raise FetchError(f"{type(e).__name__} resolving {url}") from e

    async def post(self, url: str, body: Any, **kw) -> Response:
        return await self.request("POST", url, json_body=body, **kw)


def _retry_after(r: httpx.Response) -> float | None:
    try:
        return min(float(r.headers["retry-after"]), 120.0)
    except (KeyError, ValueError):
        return None
