"""HTTP helper with tenacity-based retries on transient failures."""
import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.RequestException,)),
    reraise=True,
)
def http_get(url: str, headers: dict | None = None, timeout: int = 20) -> requests.Response:
    """Wrapped requests.get with 3 retries + exponential backoff (2s, 4s, 8s).

    Reraises after the final attempt so callers can still surface failures.
    """
    return requests.get(url, headers=headers or {}, timeout=timeout)
