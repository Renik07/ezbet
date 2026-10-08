from __future__ import annotations

from http.client import IncompleteRead
import time
from urllib.error import (
    HTTPError,
    URLError,
)
from urllib.parse import urlsplit
from urllib.request import (
    Request,
    urlopen,
)
from .ingestion_types import SourceFetchError


def fetch_remote_document(url: str | None, timeout: int = 10) -> str | None:
    if not url:
        return None
    try:
        return _fetch_remote_document(url, timeout)
    except SourceFetchError:
        return None


def _fetch_remote_document(url: str, timeout: int) -> str:
    last_error: Exception | None = None
    request: str | Request = url
    host = urlsplit(url).netloc.lower()
    if host == "championat.com" or host.endswith(".championat.com"):
        request = Request(
            url,
            headers={
                "Accept": "application/xml,text/xml,text/html;q=0.9,*/*;q=0.8",
                "Cookie": "unity_pause_sso=1",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
                ),
            },
        )

    for attempt in range(1, 4):
        try:
            with urlopen(request, timeout=timeout) as response:
                if getattr(response, "status", 200) >= 400:
                    raise SourceFetchError(f"Fetch failed for {url}: HTTP {response.status}")
                payload = response.read()
            return payload.decode("utf-8", errors="ignore")
        except HTTPError as exc:
            raise SourceFetchError(f"Fetch failed for {url}: HTTP {exc.code}") from exc
        except IncompleteRead as exc:
            last_error = exc
            if attempt >= 3:
                break
            time.sleep(0.2 * attempt)
        except URLError as exc:
            last_error = exc
            if attempt >= 3:
                break
            time.sleep(0.2 * attempt)
        except OSError as exc:
            last_error = exc
            if attempt >= 3:
                break
            time.sleep(0.2 * attempt)

    if isinstance(last_error, URLError):
        raise SourceFetchError(
            f"Fetch failed for {url}: {last_error.reason if hasattr(last_error, 'reason') else last_error}"
        ) from last_error
    if isinstance(last_error, IncompleteRead):
        raise SourceFetchError(f"Fetch failed for {url}: incomplete response body after retries") from last_error
    if isinstance(last_error, OSError):
        raise SourceFetchError(f"Fetch failed for {url}: {last_error}") from last_error
    raise SourceFetchError(f"Fetch failed for {url}: unknown network error")

