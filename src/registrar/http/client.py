import asyncio
from typing import Callable

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential_jitter,
)

from registrar.logging import log


def is_retryable_exception(exc: BaseException) -> bool:
    # Network / timeout errors (always retryable)
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True

    # HTTP errors (only selected statuses)
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status in {
            408,  # request timeout
            429,  # rate limit
            500,  # server error
            502,
            503,
            504,
        }

    return False


class RateLimiter:
    def __init__(self):
        self.delay = 0.0
        self.lock = asyncio.Lock()

    async def throttle(self):
        if self.delay > 0:
            log.debug(f"[rate-limit] sleeping {self.delay:.2f}s")
            await asyncio.sleep(self.delay)

    async def on_rate_limited(self):
        async with self.lock:
            self.delay = min(self.delay * 2 + 1, 30)
            log.warning(f"[rate-limit] hit → backoff to {self.delay:.2f}s")

    async def on_success(self):
        async with self.lock:
            self.delay = max(self.delay * 0.85, 0)


class HTTPClient:
    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0),
            headers={"User-Agent": "ThemeScraper/1.0"},
        )
        self.rate_limiter = RateLimiter()

    async def __aenter__(self):
        log.info("HTTP client started")
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()
        log.info("HTTP client closed")

    def _request(self, method: str) -> Callable:
        func = getattr(self.client, method)

        @retry(
            stop=stop_after_attempt(6) | stop_after_delay(60),
            wait=wait_exponential_jitter(initial=0.5, max=15),
            retry=retry_if_exception(is_retryable_exception),
            reraise=True,
        )
        async def inner(url, **kwargs):
            await self.rate_limiter.throttle()

            log.debug(f"{method.upper()} {url}")

            try:
                resp = await func(url, **kwargs)

                # Explicit handling for rate limiting
                if resp.status_code == 429:
                    await self.rate_limiter.on_rate_limited()
                    raise httpx.HTTPStatusError(
                        "rate limited",
                        request=resp.request,
                        response=resp,
                    )

                await self.rate_limiter.on_success()
                return resp

            except Exception as e:
                log.debug(f"{method.upper()} error {url} → {type(e).__name__}")
                raise

        return inner

    async def get(self, url, **kwargs):
        return await self._request("get")(url, **kwargs)

    async def post(self, url, **kwargs):
        return await self._request("post")(url, **kwargs)
