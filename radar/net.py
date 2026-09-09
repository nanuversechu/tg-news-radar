"""Polite HTTP fetching on the standard library only.

Reliability lives here as much as anywhere: a host that starts refusing us is
left alone for a while instead of being hammered into a ban, a fetch that
hangs cannot stall the whole tick, and every source's outcome is recorded so
the dashboard can say which ones are healthy.
"""

from __future__ import annotations

import gzip
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass

from . import config

_host_lock = threading.Lock()
_last_hit: dict[str, float] = {}
_cooldown_until: dict[str, float] = {}


@dataclass
class Result:
    url: str
    body: str | None
    status: int          # HTTP status, 0 for network failure, -1 for skipped (cooldown)
    ms: int
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.body is not None and 200 <= self.status < 300


def _host(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc


def _throttle(url: str) -> None:
    """Keep at least HOST_DELAY seconds between requests to one host."""
    host = _host(url)
    while True:
        with _host_lock:
            now = time.monotonic()
            prev = _last_hit.get(host, 0.0)
            wait = prev + config.HOST_DELAY - now
            if wait <= 0:
                _last_hit[host] = now
                return
        time.sleep(min(wait, 2.0))


def _cooling(url: str) -> float:
    """Seconds left on this host's cooldown, 0 if none."""
    with _host_lock:
        return max(0.0, _cooldown_until.get(_host(url), 0.0) - time.monotonic())


def _cool(url: str, seconds: float) -> None:
    with _host_lock:
        host = _host(url)
        _cooldown_until[host] = max(_cooldown_until.get(host, 0.0), time.monotonic() + seconds)


def cooldowns() -> dict[str, int]:
    """Hosts currently being left alone, with seconds remaining."""
    now = time.monotonic()
    with _host_lock:
        return {h: int(t - now) for h, t in _cooldown_until.items() if t > now}


def fetch_result(url: str, *, timeout: int | None = None, retries: int = 2) -> Result:
    """GET a URL. Never raises — a dead source must not take the poller down."""
    timeout = timeout or config.FETCH_TIMEOUT
    started = time.monotonic()
    left = _cooling(url)
    if left > 0:
        return Result(url, None, -1, 0, f"cooling down {int(left)}s")

    last_err, last_status = "", 0
    for attempt in range(retries + 1):
        _throttle(url)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": config.USER_AGENT,
                "Accept": "application/rss+xml, application/atom+xml, application/xml, "
                          "text/xml, application/json, */*",
                "Accept-Language": "te-IN,te;q=0.9,en-IN;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                enc = (resp.headers.get("Content-Encoding") or "").lower()
                if "gzip" in enc:
                    raw = gzip.decompress(raw)
                elif "deflate" in enc:
                    raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                charset = resp.headers.get_content_charset() or "utf-8"
                try:
                    body = raw.decode(charset, errors="replace")
                except LookupError:
                    body = raw.decode("utf-8", errors="replace")
                ms = int((time.monotonic() - started) * 1000)
                return Result(url, body, resp.status, ms)
        except urllib.error.HTTPError as e:
            last_status, last_err = e.code, f"HTTP {e.code}"
            # Being told to go away is the one failure we must obey. Retrying
            # a 429 turns a five-minute limit into an hour-long ban.
            if e.code == 429:
                retry_after = e.headers.get("Retry-After") if e.headers else None
                try:
                    secs = float(retry_after) if retry_after else config.COOLDOWN_429
                except ValueError:
                    secs = config.COOLDOWN_429
                _cool(url, max(secs, 60.0))
                break
            if e.code in (403, 404, 410):
                break  # not going to change on retry
            if e.code >= 500 and attempt == retries:
                _cool(url, config.COOLDOWN_5XX)
        except (urllib.error.URLError, OSError, EOFError, zlib.error) as e:
            last_status, last_err = 0, type(e).__name__
        except Exception as e:  # anything else: report, do not raise
            last_status, last_err = 0, type(e).__name__
            break
        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))
    return Result(url, None, last_status, int((time.monotonic() - started) * 1000), last_err)


def fetch(url: str, *, timeout: int | None = None, retries: int = 2) -> str | None:
    """Body or None. Kept for callers that only care about the text."""
    return fetch_result(url, timeout=timeout, retries=retries).body


def fetch_all_results(urls: list[str]) -> dict[str, Result]:
    """Fetch many URLs concurrently, each bounded in time."""
    out: dict[str, Result] = {}
    if not urls:
        return out
    workers = min(config.MAX_PARALLEL, len(urls))
    # A pool that is not waited on at exit lets one hung future outlive the
    # tick instead of blocking it; the result is simply recorded as a timeout.
    pool = ThreadPoolExecutor(max_workers=workers)
    futures = {pool.submit(fetch_result, u): u for u in urls}
    deadline = config.FETCH_TIMEOUT * 3
    for fut, url in futures.items():
        try:
            out[url] = fut.result(timeout=deadline)
        except FutureTimeout:
            out[url] = Result(url, None, 0, deadline * 1000, "hung")
        except Exception as e:
            out[url] = Result(url, None, 0, 0, type(e).__name__)
    pool.shutdown(wait=False, cancel_futures=True)
    return out


def fetch_all(urls: list[str]) -> dict[str, str | None]:
    """Backwards-compatible body-only view."""
    return {u: r.body for u, r in fetch_all_results(urls).items()}


def post_json(url: str, payload: dict, headers: dict | None = None, timeout: int = 40):
    """POST JSON and return the parsed response, or None."""
    import json

    body = json.dumps(payload).encode("utf-8")
    hdrs = {"Content-Type": "application/json", "User-Agent": config.USER_AGENT}
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return None
