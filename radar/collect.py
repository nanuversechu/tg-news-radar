"""Source collectors. Every one of these is free and needs no API key.

Every collector records its outcome in `source_health`, so the dashboard can
say which sources are alive rather than leaving the desk to guess from a thin
board.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from . import config, feeds, lexicon, net, store


def _fingerprint(title: str, outlet: str) -> str:
    raw = f"{lexicon.normalise(title)}|{outlet.lower().strip()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _record(name: str, url: str, kind: str, res: net.Result, count: int,
            fresh: int = 0) -> None:
    """A source is healthy when it answered *and* gave us something to parse."""
    ok = res.ok and count > 0
    err = res.error or ("" if res.ok else f"HTTP {res.status}")
    if res.ok and count == 0:
        err = "empty feed"
    store.record_source(name, url, kind, ok, count=count, ms=res.ms, error=err, fresh=fresh)


def _fresh_count(items: list[dict]) -> int:
    return sum(1 for it in items if is_fresh(it.get("published")))


def is_fresh(published, *, allow_undated: bool = False) -> bool:
    """Is this inside the freshness window we are willing to show?

    The gate lives at ingest so old material never reaches the database. Feeds
    carry a long tail — most publisher RSS runs a median of 4 to 20 hours deep,
    and one was three years deep — and without this the board fills with
    yesterday regardless of how the scoring is tuned.
    """
    if published is None:
        return allow_undated
    if not isinstance(published, datetime):
        return False
    age_h = (datetime.now(timezone.utc) - published).total_seconds() / 3600.0
    if age_h < -0.5:
        return False              # future stamp: unusable
    return age_h <= config.MAX_ITEM_AGE_HOURS


def ingest(items: list[dict]) -> tuple[int, int]:
    """Insert new items, skipping ones already seen.

    Returns (newly stored, refused as too old).
    """
    c = store.conn()
    now = store.now_iso()
    added = 0
    stale = 0
    for it in items:
        title = (it.get("title") or "").strip()
        if len(title) < 12:
            continue
        # Items sourced from a live trend carry no real timestamp of their own;
        # they are by definition current, so they are allowed through undated.
        if not is_fresh(it.get("published"), allow_undated=it.get("kind") == "trendnews"):
            stale += 1
            continue
        outlet = it.get("outlet") or it.get("source") or feeds.domain_of(it.get("url", ""))
        fp = _fingerprint(title, outlet or "")
        published = it.get("published")
        cur = c.execute(
            """INSERT OR IGNORE INTO items
               (fingerprint, title, url, domain, outlet, lang, kind,
                published_at, first_seen, entities, rank)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                fp, title, it.get("url", ""), feeds.domain_of(it.get("url", "")),
                outlet or "", "te" if lexicon.is_telugu(title) else "en",
                it.get("kind", "news"),
                published.isoformat() if isinstance(published, datetime) else None,
                now,
                ",".join(sorted(lexicon.entities(title))),
                it.get("rank"),
            ),
        )
        if cur.rowcount:
            added += 1
        elif it.get("rank"):
            # Already seen from a query feed; the front-page rank is new news.
            c.execute("UPDATE items SET rank=MIN(COALESCE(rank, 999), ?) WHERE fingerprint=?",
                      (it["rank"], fp))
    return added, stale


# --------------------------------------------------------------------------
# Google Trends — what the state is typing into Google right now
# --------------------------------------------------------------------------

def collect_trends() -> list[dict]:
    """Refresh the trends table and return rows with rising rate and direction.

    The RSS feed is a snapshot, not a time series, so we build the time series
    ourselves: how long we have been seeing a query, its rank in the feed, and
    how its estimated traffic has moved. Direction compares against roughly
    thirty minutes ago, not the previous poll — Google's traffic figures are
    bucketed and move rarely, so a one-poll comparison shows an arrow for five
    minutes and then nothing.
    """
    urls = {
        f"https://trends.google.com/trending/rss?geo={geo}": (geo, label, weight)
        for geo, label, weight in config.TREND_FEEDS
    }
    responses = net.fetch_all_results(list(urls))
    c = store.conn()
    now = store.now_iso()
    seen_now: list[dict] = []

    for url, res in responses.items():
        geo, label, weight = urls[url]
        entries = feeds.parse_trends(res.body) if res.body else []
        _record(f"Google Trends · {label}", url, "trends", res, len(entries))
        for rank, entry in enumerate(entries, start=1):
            query = entry["query"]
            if not lexicon.desk_script(query):
                continue  # Hindi, Marathi, Tamil…: not this desk's readers
            ents = ",".join(sorted(lexicon.entities(query)))
            row = c.execute(
                "SELECT traffic, rank, peak_traffic, first_seen FROM trends "
                "WHERE query=? AND geo=?", (query, geo),
            ).fetchone()
            prev_traffic = row["traffic"] if row else 0
            if row:
                c.execute(
                    """UPDATE trends SET prev_traffic=traffic, traffic=?, prev_rank=rank,
                       rank=?, peak_traffic=MAX(peak_traffic, ?), last_seen=?,
                       picture=COALESCE(NULLIF(?,''), picture), entities=?
                       WHERE query=? AND geo=?""",
                    (entry["traffic"], rank, entry["traffic"], now, entry["picture"],
                     ents, query, geo),
                )
                first_seen = row["first_seen"]
            else:
                c.execute(
                    """INSERT INTO trends(query, geo, traffic, prev_traffic, rank, prev_rank,
                       peak_traffic, first_seen, last_seen, picture, entities)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (query, geo, entry["traffic"], 0, rank, 0, entry["traffic"],
                     now, now, entry["picture"], ents),
                )
                first_seen = now
            c.execute(
                "INSERT INTO trend_history(query, geo, ts, traffic, rank) VALUES (?,?,?,?,?)",
                (query, geo, now, entry["traffic"], rank),
            )

            seen_now.append({
                "query": query,
                "geo": geo,
                "geo_label": label,
                "geo_weight": weight,
                "traffic": entry["traffic"],
                "prev_traffic": prev_traffic,
                "rank": rank,
                "first_seen": first_seen,
                "picture": entry["picture"],
                "news": entry["news"],
                "entities": set(ents.split(",")) if ents else set(),
            })

    for t in seen_now:
        t["rising"] = _rising_score(t)
        t["direction"], t["delta"] = _direction(t)
    seen_now.sort(key=lambda t: t["rising"], reverse=True)
    return seen_now


def _age_min(iso: str) -> float:
    first = store.parse_iso(iso)
    if not first:
        return 999.0
    return max(0.0, (datetime.now(timezone.utc) - first).total_seconds() / 60)


def _rising_score(trend: dict) -> float:
    """0..1 — how much this looks like a query on the way up, not on the way down."""
    age_min = max(1.0, _age_min(trend["first_seen"]))

    # Novelty: brand new queries are the whole point of a radar.
    novelty = 1.0 if age_min <= 30 else max(0.0, 1.0 - (age_min - 30) / 480.0)

    # Growth in Google's own traffic estimate since the previous poll.
    growth = 0.0
    if trend["prev_traffic"] > 0 and trend["traffic"] > trend["prev_traffic"]:
        growth = min(1.0, (trend["traffic"] - trend["prev_traffic"]) / max(trend["prev_traffic"], 1))

    # Absolute size, log-flattened so a 2M query does not drown everything.
    size = min(1.0, (trend["traffic"] ** 0.35) / 40.0) if trend["traffic"] else 0.2

    raw = 0.45 * novelty + 0.30 * growth + 0.25 * size
    return round(min(1.0, raw * trend["geo_weight"]), 4)


def _direction(trend: dict) -> tuple[str, str]:
    """('new' | 'up' | 'down' | 'flat', human delta) against ~30 minutes ago."""
    if _age_min(trend["first_seen"]) <= config.TICK_SECONDS / 60 * 1.5:
        return "new", "new"
    then = (datetime.now(timezone.utc) - timedelta(minutes=config.TREND_LOOKBACK_MIN)).isoformat()
    row = store.conn().execute(
        "SELECT traffic, rank FROM trend_history WHERE query=? AND geo=? AND ts<=? "
        "ORDER BY ts DESC LIMIT 1", (trend["query"], trend["geo"], then),
    ).fetchone()
    if not row:
        return "flat", ""
    if trend["traffic"] > row["traffic"]:
        return "up", f"{row['traffic']:,}→{trend['traffic']:,}"
    if trend["traffic"] < row["traffic"]:
        return "down", f"{row['traffic']:,}→{trend['traffic']:,}"
    if row["rank"] and trend["rank"] < row["rank"] - 1:
        return "up", f"#{row['rank']}→#{trend['rank']}"
    if row["rank"] and trend["rank"] > row["rank"] + 1:
        return "down", f"#{row['rank']}→#{trend['rank']}"
    return "flat", ""


def trailing_trends(current: list[dict]) -> list[dict]:
    """Queries that were trending recently and have now dropped off the feed.

    A desk wants to know what has *stopped* rising as much as what started —
    it is the difference between a story with legs and one that has peaked.
    """
    live = {(t["query"], t["geo"]) for t in current}
    since = (datetime.now(timezone.utc) - timedelta(minutes=config.TRAILING_WINDOW_MIN)).isoformat()
    rows = store.conn().execute(
        "SELECT query, geo, traffic, peak_traffic, last_seen, first_seen FROM trends "
        "WHERE last_seen >= ? ORDER BY peak_traffic DESC", (since,),
    ).fetchall()
    labels = {geo: label for geo, label, _ in config.TREND_FEEDS}
    out = []
    for r in rows:
        if (r["query"], r["geo"]) in live or r["geo"] == "IN":
            continue
        out.append({
            "query": r["query"],
            "geo": r["geo"],
            "geo_label": labels.get(r["geo"], r["geo"]),
            "peak_traffic": r["peak_traffic"] or r["traffic"],
            "gone_min": round(_age_min(r["last_seen"])),
            "lasted_min": round(max(0.0, _age_min(r["first_seen"]) - _age_min(r["last_seen"]))),
        })
    return out[:12]


def trend_news_items(trends: list[dict]) -> list[dict]:
    """The article links Google already attaches to each trending query."""
    out: list[dict] = []
    for t in trends:
        for news in t["news"]:
            out.append({
                "title": news["title"],
                "url": news["url"],
                "outlet": news["source"],
                "published": store.parse_iso(t["first_seen"]),
                "kind": "trendnews",
            })
    return out


# --------------------------------------------------------------------------
# Google News RSS
# --------------------------------------------------------------------------

def collect_google_news(queries: list[tuple[str, tuple[str, str], str]],
                        label: str = "Google News · standing queries") -> list[dict]:
    url_map = {
        feeds.google_news_url(q, hl, ceid, when): q
        for q, (hl, ceid), when in queries
    }
    if not url_map:
        return []
    responses = net.fetch_all_results(list(url_map))
    out: list[dict] = []
    answered = 0
    worst = None
    for url, res in responses.items():
        if res.ok:
            answered += 1
        elif worst is None or res.status == 429:
            worst = res
        if not res.body:
            continue
        for item in feeds.parse_items(res.body):
            headline, outlet = feeds.split_google_title(item["title"])
            if not headline:
                continue
            out.append({
                "title": headline,
                "url": item["link"],
                "outlet": outlet or item.get("source") or "",
                "published": item["published"],
                "kind": "news",
            })
    # One health line for the batch: it is one host, and it fails as one.
    total = len(url_map)
    summary = net.Result("https://news.google.com/rss", "" if answered else None,
                         200 if answered else (worst.status if worst else 0),
                         max((r.ms for r in responses.values()), default=0),
                         "" if answered >= total * 0.5 else
                         f"{total - answered}/{total} queries failed"
                         + (f" ({worst.error})" if worst and worst.error else ""))
    store.record_source(label, summary.url, "news", answered >= max(1, total * 0.5),
                        count=len(out), ms=summary.ms, error=summary.error,
                        fresh=_fresh_count(out))
    return out


def district_queries(tick: int) -> list[tuple[str, tuple[str, str], str]]:
    """The slice of the district list that runs this tick."""
    n = config.DISTRICT_ROTATION
    return [q for i, q in enumerate(config.DISTRICT_QUERIES) if i % n == tick % n]


def chase_trends(trends: list[dict]) -> list[dict]:
    """Search news for the queries that are actually rising.

    This is the loop that matters: Trends tells us what people want, this tells
    us what has been written about it — and, by its absence, what has not.
    """
    picks = [t for t in trends if t["rising"] > 0.25][: config.MAX_TREND_CHASES]
    queries = []
    for t in picks:
        hl_ceid = ("te-IN", "IN:te") if lexicon.is_telugu(t["query"]) else ("en-IN", "IN:en")
        queries.append((t["query"], hl_ceid, config.TREND_CHASE_WINDOW))
    return collect_google_news(queries, "Google News · trend chases") if queries else []


# --------------------------------------------------------------------------
# Publisher, geo and social feeds
# --------------------------------------------------------------------------

def _collect_feeds(sources: list[tuple[str, str]], kind: str, per_feed: int,
                   *, ranked: bool = False) -> list[dict]:
    url_map = {url: name for name, url in sources}
    if not url_map:
        return []
    responses = net.fetch_all_results(list(url_map))
    out: list[dict] = []
    for url, res in responses.items():
        name = url_map[url]
        items = feeds.parse_items(res.body) if res.body else []
        batch: list[dict] = []
        for rank, item in enumerate(items[:per_feed], start=1):
            title = item["title"]
            outlet = name
            if name.startswith("Google News"):
                title, outlet = feeds.split_google_title(title)
                outlet = outlet or name
            batch.append({
                "title": title,
                "url": item["link"],
                "outlet": outlet,
                "published": item["published"],
                "kind": kind,
                "rank": rank if ranked else None,
            })
        _record(name, url, kind, res, len(items), fresh=_fresh_count(batch))
        out += batch
    return out


def collect_top_stories() -> list[dict]:
    """Google's front page for Telugu and English readers, rank kept."""
    return _collect_feeds(config.GOOGLE_NEWS_TOP, "news", 40, ranked=True)


def collect_topics() -> list[dict]:
    """Every Google News section, both languages."""
    return _collect_feeds(config.GOOGLE_NEWS_TOPICS, "news", 40)


# --------------------------------------------------------------------------
# What people are reading: most-read feeds and Wikipedia's top pages
# --------------------------------------------------------------------------

_WIKI_SKIP = ("మొదటి_పేజీ", "దస్త్రం:", "ప్రత్యేక:", "వికీపీడియా:", "వాడుకరి:", "చర్చ:",
              "Main_Page", "Special:", "File:", "Wikipedia:", "User:", "Talk:", "-")


def collect_wiki_top() -> int:
    """Yesterday's most-viewed pages per project. Daily data, labelled as such."""
    c = store.conn()
    now = datetime.now(timezone.utc)
    y = now - timedelta(days=1)
    rows = 0
    for proj, label in config.WIKI_PROJECTS:
        url = (f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/{proj}/all-access/"
               f"{y:%Y}/{y:%m}/{y:%d}")
        res = net.fetch_result(url, retries=1)
        arts = []
        if res.ok:
            try:
                import json
                arts = json.loads(res.body)["items"][0]["articles"]
            except (ValueError, KeyError, IndexError, TypeError):
                arts = []
        name = f"{label} · read yesterday"
        _record(name, url, "reading", res, len(arts), fresh=len(arts))
        if not arts:
            continue
        c.execute("DELETE FROM reading WHERE source=?", (name,))
        kept = 0
        for a in arts:
            title = a.get("article", "")
            if not title or title.startswith(_WIKI_SKIP) or ":" in title.split("_")[0]:
                continue
            kept += 1
            c.execute(
                "INSERT OR REPLACE INTO reading(source, title, url, rank, views, ts) "
                "VALUES (?,?,?,?,?,?)",
                (name, title.replace("_", " "), f"https://{proj}.org/wiki/{title}",
                 kept, a.get("views"), store.now_iso()),
            )
            rows += 1
            if kept >= config.WIKI_TOP_N:
                break
    return rows


def collect_publishers() -> list[dict]:
    return _collect_feeds([(n, u) for n, _l, u in config.PUBLISHER_FEEDS], "news", 40)


def merge_section(feeds_items: list[list[dict]]) -> list[dict]:
    """Interleave several ranked feeds (English, Telugu) into one ranked list.

    Position k of every feed comes before position k+1 of any, so Google's
    ordering survives and neither language crowds the other out. Duplicate
    headlines keep their first appearance.
    """
    out: list[dict] = []
    seen: set[str] = set()
    longest = max((len(f) for f in feeds_items), default=0)
    for k in range(longest):
        for f in feeds_items:
            if k < len(f):
                key = lexicon.normalise(f[k]["title"])
                if key and key not in seen:
                    seen.add(key)
                    out.append({**f[k], "rank": len(out) + 1})
    return out


def collect_sections() -> list[dict]:
    """Google's current ranking for the state and its cities, both languages.

    Writes the `sections` table for the panel and returns the items for the
    board. Only items inside the freshness window are kept, so the panel can
    never show yesterday.
    """
    c = store.conn()
    now = store.now_iso()
    all_items: list[dict] = []
    for section, queries in config.TOP_SECTIONS:
        url_map = {feeds.google_news_url(q, hl, ceid, when): q for q, (hl, ceid), when in queries}
        responses = net.fetch_all_results(list(url_map))
        per_feed: list[list[dict]] = []
        answered = 0
        for url in url_map:
            res = responses.get(url)
            if not res or not res.body:
                continue
            answered += 1
            batch = []
            for item in feeds.parse_items(res.body):
                headline, outlet = feeds.split_google_title(item["title"])
                if headline and is_fresh(item["published"]):
                    batch.append({"title": headline, "url": item["link"],
                                  "outlet": outlet or item.get("source") or "",
                                  "published": item["published"], "kind": "news"})
            per_feed.append(batch)
        merged = merge_section(per_feed)
        summary = net.Result("https://news.google.com/rss/search", "" if answered else None,
                             200 if answered else 0, 0, "" if answered else "no feed answered")
        _record(f"Google News · top · {section}", summary.url, "news", summary,
                sum(len(b) for b in per_feed), fresh=len(merged))
        if answered:
            c.execute("DELETE FROM sections WHERE section=?", (section,))
            for it in merged[: config.SECTION_ROWS * 3]:
                c.execute(
                    "INSERT OR REPLACE INTO sections(section, title, url, outlet, lang, "
                    "published_at, rank, ts) VALUES (?,?,?,?,?,?,?,?)",
                    (section, it["title"], it["url"], it["outlet"],
                     "te" if lexicon.is_telugu(it["title"]) else "en",
                     it["published"].isoformat(), it["rank"], now),
                )
        all_items += merged
    return all_items


def collect_social() -> list[dict]:
    return _collect_feeds(config.SOCIAL_FEEDS, "social", 25)


def collect_youtube() -> list[dict]:
    if not config.YOUTUBE_ENABLED:
        return []
    sources = [(name, f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}")
               for name, cid in config.YOUTUBE_CHANNELS]
    return [it for it in _collect_feeds(sources, "video", 15)
            if feeds.recent(it["published"], 12)]
