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

_RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}
_LOW_LEVEL = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.ReadError,
    httpx.RemoteProtocolError,
)


def is_retryable_exception(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, *_LOW_LEVEL)):
        log.warning(f"Transient network/timeout error: {type(exc).__name__}")
        return True
    if (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response.status_code in _RETRYABLE_STATUSES
    ):
        log.warning(
            f"Retryable HTTP status {exc.response.status_code} — scheduling retry."
        )
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
    """Shared async HTTP session with per-method retries and Marketplace rate limiting."""

    def __init__(self):
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={"User-Agent": "ThemeScraper/2.0"},
            follow_redirects=True,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
        self.get = _bound(self._client.get)
        self.post = _bound(self._client.post)
        log.debug("HTTPClient initialised.")

    async def close(self):
        await self._client.aclose()
        log.debug("HTTPClient connection pool closed.")

    def stream(self, method: str, url: str, **kwargs):
        """Context-managed raw stream (downloads). Not rate-limited or retried."""
        return self._client.stream(method, url, **kwargs)


def _bound(raw):
    @_retry_policy()
    async def _call(url, **kwargs):
        if url.startswith(MARKETPLACE_API):
            log.debug("Applying Marketplace rate-limiter.")
            await marketplace_limiter.try_acquire_async("marketplace")
        log.debug(f"HTTP request → {url}")
        return await raw(url, **kwargs)

    return _call
