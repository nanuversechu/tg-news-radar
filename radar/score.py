"""Turn raw signals into one number a sub-editor can act on.

The score answers a single question: how likely is this to be big in the next
few hours, given that people are already searching for it and more than one
newsroom has independently decided it is a story?
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone

from . import config, lexicon, store


def _minutes_since(value) -> float:
    dt = store.parse_iso(value) if isinstance(value, str) else value
    if not dt:
        return 9999.0
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 60.0)


STALE = 9e6  # "older than anything we will ever show"


def item_age(row) -> float:
    """Minutes since an item was *published*, not since we happened to find it.

    Discovery time alone would make an eight-hour-old wire story look like it
    broke this minute.

    A date that fails the sanity check must resolve to *old*, never to fresh.
    An earlier version fell back to discovery time here, which meant Andhra
    Jyothy's frozen 2023 feed — every item three years stale, well past the
    sanity window — was served as breaking news at zero minutes old. A source
    with broken dates is the one you can least afford to trust.
    """
    raw = row["published_at"]
    published = store.parse_iso(raw)
    if published:
        age = (datetime.now(timezone.utc) - published).total_seconds() / 60.0
        if age < -30:
            return STALE          # published in the future: not a real date
        if age > config.RETENTION_DAYS * 1440:
            return STALE          # implausibly old: an archive, not the news
        return max(0.0, age)
    if raw:
        return STALE              # a date we could not parse is not a fresh one
    # Genuinely undated (e.g. the article links Trends attaches to a query):
    # discovery time is the only estimate available.
    return _minutes_since(row["first_seen"])


def _direction(cluster_id: int, score_now: float, outlets_now: int,
               age_min: float) -> tuple[str, float, int]:
    """('new'|'up'|'down'|'flat', score delta, outlet delta) vs ~15 minutes ago."""
    then = (datetime.now(timezone.utc)
            - timedelta(minutes=config.STORY_LOOKBACK_MIN)).isoformat()
    row = store.conn().execute(
        "SELECT score, outlets FROM cluster_history WHERE cluster_id=? AND ts<=? "
        "ORDER BY ts DESC LIMIT 1", (cluster_id, then),
    ).fetchone()
    if not row:
        if age_min <= config.TICK_SECONDS / 60 * 1.5:
            return "new", 0.0, 0
        return "flat", 0.0, 0
    d_score = round(score_now - (row["score"] or 0.0), 1)
    d_out = outlets_now - (row["outlets"] or 0)
    if d_score >= config.STORY_DELTA or d_out >= 2:
        return "up", d_score, d_out
    if d_score <= -config.STORY_DELTA:
        return "down", d_score, d_out
    return "flat", d_score, d_out


def score_all(trends: list[dict]) -> list[dict]:
    """Recompute every active cluster's score. Returns them, best first."""
    c = store.conn()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=config.BOARD_WINDOW_HOURS)).isoformat()
    clusters = c.execute(
        "SELECT id, title, first_seen, last_seen, peak_score FROM clusters "
        "WHERE last_seen >= ?", (cutoff,),
    ).fetchall()

    now_iso = store.now_iso()
    scored: list[dict] = []
    for cl in clusters:
        items = c.execute(
            "SELECT title, url, outlet, domain, lang, kind, published_at, first_seen, rank "
            "FROM items WHERE cluster_id=? ORDER BY first_seen DESC", (cl["id"],),
        ).fetchall()
        if not items:
            continue
        result = _score_cluster(cl, items, trends)
        # Items age between being ingested and being scored, so re-check the
        # contract here: if even the freshest report in a cluster has aged out,
        # the story leaves the board rather than lingering a few minutes over.
        if result["age_min"] > config.MAX_ITEM_AGE_HOURS * 60:
            continue
        # Direction is read *before* this tick's history row is written, so
        # the comparison is against the past and not against itself.
        result["direction"], result["score_delta"], result["outlet_delta"] = _direction(
            cl["id"], result["score"], result["outlet_count"], result["age_min"])
        c.execute(
            """UPDATE clusters SET score=?, peak_score=MAX(peak_score, ?),
               breakdown=?, trend_query=?, picture=? WHERE id=?""",
            (result["score"], result["score"], json.dumps(result["breakdown"]),
             result["trend_query"], result["picture"], cl["id"]),
        )
        # One row per cluster per tick was 44,000 rows a day — the table that
        # grew the database to 106 MB. Only trajectories worth reading later
        # are kept.
        if result["score"] >= config.HISTORY_MIN_SCORE:
            c.execute(
                "INSERT INTO cluster_history(cluster_id, ts, score, item_count, outlets) "
                "VALUES (?,?,?,?,?)",
                (cl["id"], now_iso, result["score"], result["item_count"],
                 result["outlet_count"]),
            )
        scored.append(result)

    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored


def _score_cluster(cl, items, trends: list[dict]) -> dict:
    title = cl["title"]
    ents = lexicon.entities(title)
    for it in items[:12]:
        ents |= lexicon.entities(it["title"])

    ages = [item_age(it) for it in items]
    age_min = min(ages) if ages else 9999.0   # the story is as old as its freshest report
    outlets = {(it["outlet"] or it["domain"] or "").lower() for it in items}
    outlets.discard("")
    outlet_count = len(outlets)

    # --- corroboration: independent newsrooms carrying it -------------------
    corroboration = min(1.0, math.log1p(outlet_count) / math.log(7))

    # --- velocity: items per hour over the cluster's life -------------------
    span_min = max(ages) - min(ages) if len(ages) > 1 else 0.0
    hours = max(0.5, span_min / 60.0)
    rate = len(items) / hours
    velocity = min(1.0, math.log1p(rate) / math.log(9))

    # --- acceleration: the last half hour against the ninety before it -----
    # Scaled to the freshness window: comparing hours against hours says
    # nothing when nothing on the board is older than two.
    last_hour = sum(1 for a in ages if a <= 30)
    prev_three = sum(1 for a in ages if 30 < a <= 120)
    baseline = prev_three / 3.0
    if last_hour == 0:
        acceleration = 0.0
    elif baseline < 0.35:
        # No history to compare against: a brand-new story is accelerating by
        # definition, but only credit it once more than one outlet has it.
        acceleration = 0.62 if outlet_count >= 2 else 0.32
    else:
        acceleration = min(1.0, (last_hour / baseline) / 3.0)

    # --- search demand: does a live Google trend match this story? ----------
    #
    # Each headline is tested on its own. Testing against the union of every
    # entity in the cluster let a story inherit a match from a sibling report
    # that merely mentioned the same person.
    headlines = [title] + [it["title"] for it in items[:8]]
    trend_score, trend_query, picture, trend_geo = 0.0, "", "", ""
    for t in trends:
        match = max(lexicon.matches_trend(t["query"], h) for h in headlines)
        if match <= 0:
            continue
        value = match * (0.45 + 0.55 * t["rising"]) * t["geo_weight"]
        if value > trend_score:
            trend_score = min(1.0, value)
            trend_query, picture, trend_geo = t["query"], t.get("picture", ""), t["geo_label"]

    # --- prominence: where Google's front page puts it ---------------------
    # Rank on the top-stories feed is the one reading-behaviour signal Google
    # gives away for free. Position 1 is worth 1.0, position 30 nothing.
    ranks = [it["rank"] for it in items if it["rank"]]
    best_rank = min(ranks) if ranks else None
    prominence = max(0.0, 1.0 - (best_rank - 1) / 30.0) if best_rank else 0.0

    # --- freshness ---------------------------------------------------------
    freshness = 0.5 ** (age_min / config.FRESHNESS_HALFLIFE_MIN)

    components = {
        "trend": trend_score,
        "acceleration": acceleration,
        "corroboration": corroboration,
        "prominence": prominence,
        "velocity": velocity,
        "freshness": freshness,
    }
    raw = sum(config.WEIGHTS[k] * v for k, v in components.items())
    mult, locality_label = lexicon.locality(ents)
    score = round(min(100.0, 100.0 * raw * mult), 1)

    videos = [it for it in items if it["kind"] == "video"]

    return {
        "id": cl["id"],
        "title": title,
        "score": score,
        "peak_score": max(cl["peak_score"] or 0, score),
        "age_min": round(age_min),
        "first_seen": cl["first_seen"],
        "locality_mult": mult,
        "item_count": len(items),
        "outlet_count": outlet_count,
        "outlets": sorted(outlets)[:12],
        "video_count": len(videos),
        "languages": sorted({it["lang"] for it in items}),
        "entities": sorted(ents),
        "locality": locality_label,
        "front_page_rank": best_rank,
        "trend_query": trend_query,
        "trend_geo": trend_geo,
        "picture": picture,
        "breakdown": {k: round(v, 3) for k, v in components.items()},
        "links": [
            {"title": it["title"], "url": it["url"], "outlet": it["outlet"],
             "lang": it["lang"], "kind": it["kind"], "age_min": round(item_age(it))}
            for it in sorted(items, key=item_age)[:12]
        ],
    }


def trend_coverage(trends: list[dict], scored: list[dict]) -> list[dict]:
    """Demand against supply, per query.

    For every live search, how many independent outlets have a matching story
    on the board right now, and which stories. Annotates each trend in place
    with `coverage_outlets`, `coverage_ids`, `local`, and returns the
    commissioning list: rising searches with one outlet or none.
    """
    gaps = []
    for t in trends:
        outlets: set[str] = set()
        ids: list[int] = []
        best = 0.0
        for cl in scored:
            if lexicon.matches_trend(t["query"], cl["title"]) >= 0.55:
                outlets |= {o.lower() for o in cl.get("outlets", [])}
                ids.append(cl["id"])
                best = max(best, cl["score"])
        t["coverage_outlets"] = len(outlets)
        t["coverage_ids"] = ids[:20]
        t["coverage_best"] = round(best, 1)
        t["local"] = lexicon.locality(set(t.get("entities") or set()))[1] == config.LOCAL_LABEL

        if t["rising"] < 0.30 or t["geo"] == "IN":
            continue
        # A bare common noun trending ("price", "manager") is not a commission.
        if not t.get("entities") and len(lexicon.tokens(t["query"])) < 2:
            continue
        if len(outlets) <= 1:
            gaps.append({
                "query": t["query"], "geo": t["geo_label"], "traffic": t["traffic"],
                "rising": t["rising"], "picture": t.get("picture", ""),
                "coverage": len(outlets), "age_min": round(_minutes_since(t["first_seen"])),
                "news": t.get("news", [])[:3],
            })
    gaps.sort(key=lambda g: (g["coverage"], -g["rising"]))
    return gaps[:12]


def reading_view(scored: list[dict]) -> list[dict]:
    """What people are reading, each item marked local / covered.

    `covered` means a story on the board matches it; `local` means the lexicon
    finds a place, person or institution from this state in it.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    rows = store.conn().execute(
        "SELECT source, title, url, rank, views, ts FROM reading WHERE ts >= ? "
        "ORDER BY source, rank", (since,),
    ).fetchall()
    titles = [cl["title"] for cl in scored[:80]]
    out = []
    for r in rows:
        ents = lexicon.entities(r["title"])
        covered = any(
            lexicon.similarity(r["title"], t) >= lexicon.MERGE_THRESHOLD
            or lexicon.matches_trend(r["title"], t) >= 0.55
            for t in titles
        )
        out.append({
            "source": r["source"], "title": r["title"], "url": r["url"],
            "rank": r["rank"], "views": r["views"],
            "local": lexicon.locality(ents)[1] == config.LOCAL_LABEL,
            "covered": covered,
            "age_min": round(_minutes_since(r["ts"])),
        })
    return out


def sections_view() -> list[dict]:
    """The top-stories panels: newest first, nothing outside the window."""
    rows = store.conn().execute(
        "SELECT section, title, url, outlet, lang, published_at, rank FROM sections "
        "ORDER BY section, published_at DESC",
    ).fetchall()
    limit = config.MAX_ITEM_AGE_HOURS * 60
    out: list[dict] = []
    for r in rows:
        age = item_age({"published_at": r["published_at"], "first_seen": None})
        if age > limit:
            continue
        out.append({
            "section": r["section"], "title": r["title"], "url": r["url"],
            "outlet": r["outlet"], "lang": r["lang"], "rank": r["rank"],
            "age_min": round(age),
        })
    return out


def gaps(trends: list[dict], scored: list[dict]) -> list[dict]:
    """Kept for callers that only want the commissioning list."""
    return trend_coverage(trends, scored)


def due_alerts(scored: list[dict]) -> list[dict]:
    """Clusters worth interrupting someone for, respecting a cooldown."""
    c = store.conn()
    cooldown = (datetime.now(timezone.utc)
                - timedelta(minutes=config.ALERT_COOLDOWN_MIN)).isoformat()
    out = []
    for cl in scored:
        if cl["score"] < config.ALERT_SCORE:
            continue
        if cl["outlet_count"] < config.ALERT_MIN_OUTLETS:
            continue
        if cl["age_min"] > config.ALERT_MAX_AGE_MIN:
            continue
        recent = c.execute(
            "SELECT 1 FROM alerts WHERE cluster_id=? AND ts >= ? LIMIT 1",
            (cl["id"], cooldown),
        ).fetchone()
        if recent:
            continue
        c.execute(
            "INSERT INTO alerts(cluster_id, ts, score, delivered) VALUES (?,?,?,0)",
            (cl["id"], store.now_iso(), cl["score"]),
        )
        out.append(cl)
    return out
