"""Entry point.

    python -m radar           poll continuously and serve the dashboard
    python -m radar once      run a single tick and print the top stories
    python -m radar check     verify every configured source is alive
    python -m radar snapshot  freeze the live dashboard into docs/index.html
"""

from __future__ import annotations

import os
import sys

from . import config, poll, server, store


def _run() -> None:
    store.init()
    print(f"{config.REGION_NAME} news radar")
    print(f"  database   {config.DB_PATH}")
    print(f"  tick       every {config.TICK_SECONDS // 60} min")
    alerts = "telegram" if config.TELEGRAM_TOKEN else "console only"
    print(f"  alerts     {alerts} at score >= {config.ALERT_SCORE}")
    from . import watchdog
    print(f"  watchdog   {'systemd' if watchdog.enabled() else 'off (not under systemd)'}")
    poll.start_background()
    try:
        server.serve()
    except KeyboardInterrupt:
        print("\nstopped")


def _once() -> None:
    store.init()
    poll.run_tick(0)
    state = poll.snapshot()
    print(f"\nTop searches in {config.REGION_NAME} right now")
    for t in state["trends"][:10]:
        print(f"  {t['rising']:.2f}  {t['query']}  ({t['traffic']}+, {t['geo_label']})")
    print("\nTop stories")
    for c in state["board"][:12]:
        flag = f"  ← searching “{c['trend_query']}”" if c["trend_query"] else ""
        print(f"  {c['score']:5.1f}  [{c['outlet_count']} outlets, {c['age_min']}m]  "
              f"{c['title'][:78]}{flag}")
    if state["gaps"]:
        print("\nRising with thin coverage")
        for g in state["gaps"][:8]:
            print(f"  {g['query']}  ({g['traffic']}+, {g['coverage']} outlets)")


def _check() -> None:
    from . import feeds, net

    def probe(label: str, url: str, parser=feeds.parse_items) -> int:
        res = net.fetch_result(url, retries=1)
        count = len(parser(res.body)) if res.body else 0
        # A search that answers with nothing is quiet, not broken: a place can
        # simply have had no news in the window.
        mark = "ok  " if count else ("none" if res.ok else "DEAD")
        why = "" if count else (
            "  (nothing in this window)" if res.ok
            else f"  ({res.error or 'HTTP ' + str(res.status)})")
        print(f"  {mark} {count:>4}  {res.ms:>5}ms  {label}{why}")
        return count

    print("Google Trends")
    for geo, label, _ in config.TREND_FEEDS:
        probe(f"{label} ({geo})", f"https://trends.google.com/trending/rss?geo={geo}",
              feeds.parse_trends)
    print("Google News (sample of standing + district queries)")
    for q, (hl, ceid), when in config.STANDING_QUERIES[:3] + config.DISTRICT_QUERIES[:2]:
        probe(f"{q} when:{when}", feeds.google_news_url(q, hl, ceid, when))
    print("Google News front page and sections")
    for name, url in config.GOOGLE_NEWS_TOP + config.GOOGLE_NEWS_TOPICS:
        probe(name, url)
    print("Google News top stories by place")
    for section, queries in config.TOP_SECTIONS:
        for q, (hl, ceid), when in queries:
            probe(f"{section}: {q} when:{when}", feeds.google_news_url(q, hl, ceid, when))
    print("Reading signals")
    from datetime import datetime, timedelta, timezone
    y = datetime.now(timezone.utc) - timedelta(days=1)
    for proj, label in config.WIKI_PROJECTS:
        res = net.fetch_result(f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/{proj}/all-access/{y:%Y}/{y:%m}/{y:%d}", retries=1)
        print(f"  {'ok  ' if res.ok else 'DEAD'} {'':>4}  {res.ms:>5}ms  {label} top pages (yesterday){'' if res.ok else '  (' + (res.error or str(res.status)) + ')'}")
    print("Publishers")
    for name, _lang, url in config.PUBLISHER_FEEDS:
        probe(name, url)
    print("Social")
    for name, url in config.SOCIAL_FEEDS:
        probe(name, url)
    state = "enabled" if config.YOUTUBE_ENABLED else "disabled — probing anyway"
    print(f"YouTube ({state})")
    alive = 0
    for name, cid in config.YOUTUBE_CHANNELS:
        alive += 1 if probe(name, f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}") else 0
    if alive and not config.YOUTUBE_ENABLED:
        print("  -> the feed is answering again: set YOUTUBE_ENABLED = True in radar/config.py")
    print("Omarchy theme")
    from . import theme
    t = theme.current()
    print(f"  {t['source']:4}       {t['name']} ({t['mode']})")


def _snapshot() -> None:
    """Freeze the running dashboard into a single self-contained HTML file.

    For showing the tool to someone who will not run it: the page renders
    exactly as the desk sees it, with the data of this moment embedded, no
    server, no polling. Written to docs/index.html so GitHub Pages can host it.
    """
    import json
    import urllib.request
    from datetime import datetime, timedelta, timezone

    from . import server

    base = f"http://{config.SERVER_HOST}:{config.SERVER_PORT}"
    try:
        with urllib.request.urlopen(base + "/api/board", timeout=30) as r:
            board = json.load(r)
        with urllib.request.urlopen(base + "/api/theme", timeout=30) as r:
            th = json.load(r)
    except Exception as e:
        print(f"the radar is not answering on {base}: {e}")
        sys.exit(1)
    if not board.get("last_tick"):
        print("the radar has not completed a tick yet; try again in a minute")
        sys.exit(1)

    ist = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    taken = ist.strftime("%H:%M IST, %-d %B %Y")

    def embed(obj) -> str:  # a </script> inside a headline must not end the script
        return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")

    page = server.render_page()
    start = page.index("async function tick(){")
    end = page.index("tick(); setInterval(tick, 30000);") + len("tick(); setInterval(tick, 30000);")
    static = f"""const SNAPSHOT_TAKEN={json.dumps(taken)};
DATA={embed(board)};
applyTheme({embed(th)});
render();
clearInterval(countdownTimer);
document.getElementById('s-live').className='seg';
document.getElementById('s-live').textContent='snapshot';
document.getElementById('s-next').textContent='taken '+SNAPSHOT_TAKEN;"""
    page = page[:start] + static + page[end:]

    # With a key set, what gets written is the unlock form plus ciphertext —
    # the board itself never reaches the file. Without one it is written plain,
    # which is right for a page you are only ever going to open yourself.
    locked = ""
    if config.PAGE_KEY:
        from . import lock
        page = lock.gate_page(page, config.PAGE_KEY, config.REGION_SLUG)
        locked = ", encrypted"

    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "index.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(page)
    open(os.path.join(out_dir, ".nojekyll"), "w").close()
    print(f"wrote {out}  ({os.path.getsize(out) // 1024} KB, taken {taken}{locked})")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    {"run": _run, "once": _once, "check": _check, "snapshot": _snapshot}.get(cmd, _run)()
