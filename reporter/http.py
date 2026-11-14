"""인터넷 접속 공통 도구. 잠깐 실패하면 자동으로 몇 번 다시 시도해요."""

from __future__ import annotations

import logging
import time

import httpx

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; ai-trend-reporter/0.1)"
RETRY_STATUS = {429, 500, 502, 503, 504}


def make_client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
        follow_redirects=True,
    )


def request(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    retries: int = 3,
    **kwargs,
) -> httpx.Response:
    """요청을 보내고, 일시적인 오류(429·5xx·연결 끊김)면 잠시 기다렸다 다시 시도해요."""
    delay = 2.0
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = client.request(method, url, **kwargs)
            if resp.status_code in RETRY_STATUS and attempt < retries:
                wait = _retry_after(resp) or delay
                log.debug("%s → %s, %.0f초 후 재시도", url, resp.status_code, wait)
                time.sleep(wait)
                delay *= 2
                continue
            resp.raise_for_status()
            return resp
        except httpx.TransportError as exc:  # 연결 실패·시간 초과
            last_exc = exc
            if attempt < retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise
    raise last_exc or RuntimeError(f"요청 실패: {url}")


def get(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    return request(client, "GET", url, **kwargs)


def _retry_after(resp: httpx.Response) -> float | None:
    value = resp.headers.get("Retry-After")
    if value and value.isdigit():
        return min(float(value), 60.0)
    return None
