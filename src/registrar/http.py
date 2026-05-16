import asyncio

import httpx
from pyrate_limiter import Duration
from pyrate_limiter.limiter_factory import create_inmemory_limiter
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from registrar.config import MARKETPLACE_API
from registrar.logging import log

# Limiter for Marketplace API
marketplace_limiter = create_inmemory_limiter(
    duration=5 * Duration.MINUTE, rate_per_duration=150
)


def is_retryable_exception(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        log.warning(
            f"Transient Network/Timeout exception encountered: {type(exc).__name__}"
        )
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in {408, 429, 500, 502, 503, 504}:
            log.warning(
                f"Server returned retryable status block ({status}). Registering request for retry."
            )
            return True
    if isinstance(
        exc,
        (
            httpx.ConnectError,
            httpx.ReadTimeout,
            httpx.ReadError,
            httpx.RemoteProtocolError,
        ),
    ):
        log.warning(f"Low level connection pipeline error: {type(exc).__name__}")
        return True
    return False


def retry_http():
    return retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(initial=2, jitter=2, max=30),
        retry=retry_if_exception(is_retryable_exception),
        reraise=True,
    )


class HTTPClient:
    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={"User-Agent": "ThemeScraper/2.0"},
            follow_redirects=True,
        )
        log.debug("Shared httpx AsyncClient pipeline initialized.")

    async def close(self):
        await self.client.aclose()
        log.debug("Shared httpx AsyncClient connection pool terminated cleanly.")

    def _request(self, method: str):
        func = getattr(self.client, method)

        @retry_http()
        async def inner(url, **kwargs):
            # Use the right limiter depending on URL
            if url.startswith(MARKETPLACE_API):
                log.debug(
                    "Throttling request pipeline via Marketplace rate limiter constraints..."
                )
                await marketplace_limiter.try_acquire_async("marketplace")

            log.debug(f"Outbound HTTP Request Execution: {method.upper()} -> {url}")
            resp = await func(url, **kwargs)

            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = int(retry_after)
                        log.warning(
                            f"[rate-limit] 429 Too Many Requests encountered -> Server demands pause for {delay}s"
                        )
                        try:
                            await asyncio.sleep(delay)
                        except asyncio.CancelledError:
                            log.info(
                                "Rate limiter dynamic window wait back-off canceled during shutdown sequence."
                            )
                            raise
                    except ValueError:
                        log.warning(
                            f"[rate-limit] 429 received with unparsable non-integer Retry-After window content: '{retry_after}'"
                        )

                # Raise so tenacity will retry after the sleep
                raise httpx.HTTPStatusError(
                    "rate limited",
                    request=resp.request,
                    response=resp,
                )

            resp.raise_for_status()
            return resp

        return inner

    async def get(self, url, **kwargs):
        return await self._request("get")(url, **kwargs)

    async def post(self, url, **kwargs):
        return await self._request("post")(url, **kwargs)
