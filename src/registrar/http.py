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

# Rate limiter for the VS Marketplace API (150 requests per 5 minutes).
marketplace_limiter = create_inmemory_limiter(
    duration=5 * Duration.MINUTE, rate_per_duration=150
)


def is_retryable_exception(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        log.warning(f"Transient network/timeout error: {type(exc).__name__}")
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code in {408, 429, 500, 502, 503, 504}:
            log.warning(
                f"Retryable HTTP status {exc.response.status_code} — scheduling retry."
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
        log.warning(f"Low-level connection error: {type(exc).__name__}")
        return True
    return False


def _retry_policy():
    return retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(initial=2, jitter=2, max=30),
        retry=retry_if_exception(is_retryable_exception),
        reraise=True,
    )


class HTTPClient:
    def __init__(self):
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={"User-Agent": "ThemeScraper/2.0"},
            follow_redirects=True,
        )
        # Pre-bind decorated methods once so we don't recreate decorators per call.
        self.get = self._make_method("get")
        self.post = self._make_method("post")
        log.debug("HTTPClient initialised.")

    async def close(self):
        await self._client.aclose()
        log.debug("HTTPClient connection pool closed.")

    def _make_method(self, method: str):
        raw = getattr(self._client, method)

        @_retry_policy()
        async def _call(url, **kwargs):
            if url.startswith(MARKETPLACE_API):
                log.debug("Applying Marketplace rate-limiter...")
                await marketplace_limiter.try_acquire_async("marketplace")

            log.debug(f"HTTP {method.upper()} → {url}")
            resp = await raw(url, **kwargs)

            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = int(retry_after)
                        log.warning(f"429 Too Many Requests — backing off {delay}s.")
                        try:
                            await asyncio.sleep(delay)
                        except asyncio.CancelledError:
                            log.info("Rate-limit back-off cancelled during shutdown.")
                            raise
                    except ValueError:
                        log.warning(
                            f"429 with non-integer Retry-After value: '{retry_after}'"
                        )
                # Raise so tenacity retries after the sleep.
                raise httpx.HTTPStatusError(
                    "rate limited", request=resp.request, response=resp
                )

            resp.raise_for_status()
            return resp

        return _call
