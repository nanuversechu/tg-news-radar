"""One polling tick, and the loop that repeats it.

Reliability rules that live here:

* A tick that fails to fetch keeps the last good board on screen rather than
  blanking it. The dashboard is told the data is degraded; it is not lied to.
* The loop heartbeats to systemd throughout, including while sleeping, so a
  hung poller is restarted rather than left looking alive.
* The poller thread is checked for life on every health request and revived
  if it has died.
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone

from . import cluster, collect, config, lexicon, net, notify, score, store, watchdog

_state_lock = threading.Lock()
_state: dict = {
    "last_tick": None,
    "last_error": None,
    "tick_count": 0,
    "window_hours": config.MAX_ITEM_AGE_HOURS,
    "tick_seconds": config.TICK_SECONDS,
    "next_tick_at": None,
    "trends": [],
    "trailing": [],
    "board": [],
    "gaps": [],
    "reading": [],
    "sections": [],
    "sources": [],
    "cooldowns": {},
    "degraded": [],
    "stats": {},
    "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
}
_thread: threading.Thread | None = None


def snapshot() -> dict:
    with _state_lock:
        return json.loads(json.dumps(_state, default=str))


def _source_summary() -> list[dict]:
    """Health rows trimmed to what the strip needs."""
    out = []
    for r in store.source_health():
        out.append({
            "name": r["name"], "kind": r["kind"],
            "ok": (r["failures"] or 0) == 0 and bool(r["last_ok"]),
            "failures": r["failures"] or 0,
            "last_ok": r["last_ok"], "last_error": r["last_error"] or "",
            "count": r["last_count"] or 0, "ms": r["last_ms"] or 0,
            "fresh_count": r["fresh_count"] if "fresh_count" in r.keys() else None,
            "last_fresh": r["last_fresh"] if "last_fresh" in r.keys() else None,
        })
    return out


def run_tick(tick: int = 0, *, verbose: bool = True) -> dict:
    """Collect, cluster, score, alert. Returns a summary dict."""
    started = time.time()
    store.init()
    slow = (tick % config.SLOW_EVERY_N_TICKS) == 0
    hourly = (tick % config.HOURLY_EVERY_N_TICKS) == 0
    stats = {"trends": 0, "new_items": 0, "google_news": 0, "top": 0, "topics": 0,
             "districts": 0, "publishers": 0, "sections": 0, "social": 0, "youtube": 0,
             "chased": 0, "reading": 0}
    degraded: list[str] = []

    trends = collect.collect_trends()
    stats["trends"] = len(trends)
    if not trends:
        # Google hiccupped. Yesterday's list is wrong; an empty one is worse.
        with _state_lock:
            trends = list(_state["trends"])
        degraded.append("trends")

    items: list[dict] = collect.trend_news_items(trends)

    gn = collect.collect_google_news(config.STANDING_QUERIES)
    stats["google_news"] = len(gn)
    items += gn
    if not gn:
        degraded.append("google_news")

    top = collect.collect_top_stories()
    stats["top"] = len(top)
    items += top

    sec = collect.collect_sections()
    stats["sections"] = len(sec)
    items += sec

    dq = collect.collect_google_news(collect.district_queries(tick), "Google News · districts")
    stats["districts"] = len(dq)
    items += dq

    chased = collect.chase_trends(trends)
    stats["chased"] = len(chased)
    items += chased

    if slow:
        tp = collect.collect_topics()
        stats["topics"] = len(tp)
        items += tp
        pub = collect.collect_publishers()
        stats["publishers"] = len(pub)
        items += pub
        soc = collect.collect_social()
        stats["social"] = len(soc)
        items += soc
        yt = collect.collect_youtube()
        stats["youtube"] = len(yt)
        items += yt

    if hourly:
        stats["reading"] = collect.collect_wiki_top()

    stats["new_items"], stats["too_old"] = collect.ingest(items)
    cluster.assign_clusters()
    board = score.score_all(trends)
    _add_english_gloss(board)
    gap_list = score.trend_coverage(trends, board)   # annotates trends in place
    trailing = collect.trailing_trends(trends)
    reading = score.reading_view(board)
    sections = score.sections_view()

    # The very first run has no history to accelerate against, so every story
    # looks like a breakout. Fill the baseline quietly and start alerting from
    # the next tick.
    if store.get_meta("bootstrapped") == "1":
        alerts = score.due_alerts(board)
        if alerts:
            notify.send_alerts(alerts)
    else:
        store.set_meta("bootstrapped", "1")
        stats["bootstrap"] = True

    if slow:
        store.housekeeping()

    stats["seconds"] = round(time.time() - started, 1)
    stats["clusters"] = len(board)
    sources = _source_summary()
    stats["sources_ok"] = sum(1 for s in sources if s["ok"])
    stats["sources_total"] = len(sources)

    now = datetime.now(timezone.utc)
    with _state_lock:
        _state["last_tick"] = now.isoformat(timespec="seconds")
        _state["tick_count"] = tick + 1
        _state["trends"] = _dedupe_trends(trends)[:40]
        _state["trailing"] = trailing
        if board or "google_news" not in degraded:
            _state["board"] = _board_payload(board, trends)
        else:
            degraded.append("board")
        _state["gaps"] = gap_list
        _state["reading"] = reading
        _state["sections"] = sections
        _state["sources"] = sources
        _state["cooldowns"] = net.cooldowns()
        _state["degraded"] = degraded
        _state["stats"] = stats
        _state["last_error"] = None

    store.set_meta("last_tick", _state["last_tick"])
    watchdog.heartbeat(f"tick {tick + 1}: {len(board)} stories, "
                       f"{stats['sources_ok']}/{stats['sources_total']} sources ok")
    if verbose:
        print(f"[tick {tick}] {stats}" + (f" degraded={degraded}" if degraded else ""), flush=True)
    return stats


def _board_payload(board: list[dict], trends: list[dict], top: int = 60) -> list[dict]:
    """The top stories, plus every story a live search points at.

    Coverage is computed over the whole scored list, so a search's matching
    stories can sit below the top sixty. Clicking that search must show them,
    so they ride along flagged `extra`; the page hides extras unless a search
    filter is active.
    """
    wanted = {cid for t in trends for cid in t.get("coverage_ids", [])}
    out = []
    for i, cl in enumerate(board):
        if i < top:
            out.append(cl)
        elif cl["id"] in wanted:
            out.append({**cl, "extra": True})
    return out


def _dedupe_trends(trends: list[dict]) -> list[dict]:
    """One cell per query. The list is sorted by rising score, and AP carries
    the highest geo weight, so the first occurrence is the one to keep."""
    seen: set[str] = set()
    out = []
    for t in trends:
        key = t["query"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def _add_english_gloss(board: list[dict]) -> None:
    """Put a one-line English reading under the Telugu headlines near the top.

    Skipped entirely without a Groq key, and only ever asked about the handful
    of clusters a sub-editor is actually looking at.
    """
    if not config.GROQ_API_KEY:
        return
    c = store.conn()
    wanted = [cl for cl in board[:20] if lexicon.is_telugu(cl["title"])]
    cached = {}
    for cl in wanted:
        row = c.execute("SELECT title_en FROM clusters WHERE id=?", (cl["id"],)).fetchone()
        if row and row["title_en"]:
            cached[cl["title"]] = row["title_en"]

    fresh = notify.gloss([cl["title"] for cl in wanted if cl["title"] not in cached])
    for cl in wanted:
        english = cached.get(cl["title"]) or fresh.get(cl["title"])
        if not english:
            continue
        cl["title_en"] = english
        if cl["title"] not in cached:
            c.execute("UPDATE clusters SET title_en=? WHERE id=?", (english, cl["id"]))


def _sleep_with_heartbeat(seconds: float) -> None:
    """Sleep in slices so systemd keeps hearing from us between ticks.

    Watches the wall clock as well as the monotonic one. Linux's monotonic
    clock stops during suspend, so after a laptop lid is closed for an hour
    the monotonic deadline is still minutes away while the data on screen is
    an hour old. The wall clock has moved on, and that ends the sleep.
    """
    end_mono = time.monotonic() + seconds
    end_wall = time.time() + seconds
    while True:
        left = min(end_mono - time.monotonic(), end_wall - time.time())
        if left <= 0:
            return
        time.sleep(min(left, 30.0))
        watchdog.heartbeat()


def sleep_remaining(end_mono: float, end_wall: float) -> float:
    """Seconds left, by whichever clock says less. Exposed for tests."""
    return max(0.0, min(end_mono - time.monotonic(), end_wall - time.time()))


def loop(forever: bool = True) -> None:
    tick = 0
    watchdog.ready()
    # When two radars share a machine they must not hammer Google in lockstep.
    # READY is sent first, so systemd sees a healthy start either way.
    if config.START_DELAY_SECONDS > 0:
        watchdog.status(f"staggering start by {config.START_DELAY_SECONDS}s")
        _sleep_with_heartbeat(config.START_DELAY_SECONDS)
    while True:
        started = time.monotonic()
        try:
            run_tick(tick)
        except Exception:
            err = traceback.format_exc()
            with _state_lock:
                _state["last_error"] = err.splitlines()[-1]
            print("[tick error]\n" + err, flush=True)
            # A failed tick is still a live process; say so.
            watchdog.heartbeat("tick failed: " + err.splitlines()[-1])
        tick += 1
        if not forever:
            return
        # Sleep only the remainder of the interval. Sleeping the full amount
        # after a slow tick silently doubles the gap between polls.
        elapsed = time.monotonic() - started
        rest = max(30.0, config.TICK_SECONDS - elapsed)
        if config.TICK_SECONDS - elapsed < 30:
            print(f"[tick {tick - 1}] took {elapsed:.0f}s, longer than the "
                  f"{config.TICK_SECONDS}s interval", flush=True)
        with _state_lock:
            _state["next_tick_at"] = (datetime.now(timezone.utc)
                                      + timedelta(seconds=rest)).isoformat(timespec="seconds")
        _sleep_with_heartbeat(rest)


def start_background() -> threading.Thread:
    global _thread
    _thread = threading.Thread(target=loop, name="radar-poller", daemon=True)
    _thread.start()
    return _thread


def ensure_poller() -> bool:
    """True if the poller is running; restarts it if it has died."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return True
    if _thread is None:
        return False
    print("[poller] thread died — restarting", flush=True)
    start_background()
    return _thread.is_alive()


def is_stale() -> bool:
    """Data older than three intervals is stale, whatever the reason."""
    with _state_lock:
        last = store.parse_iso(_state["last_tick"])
    if not last:
        return False  # first tick still running; not stale, just young
    return (datetime.now(timezone.utc) - last).total_seconds() > config.TICK_SECONDS * 3
