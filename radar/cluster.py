"""Group items that are the same story — across outlets and across languages."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import config, lexicon, store


def _active_clusters(hours: int):
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    return store.conn().execute(
        "SELECT id, title, signature FROM clusters WHERE last_seen >= ? ORDER BY last_seen DESC",
        (cutoff,),
    ).fetchall()


def assign_clusters() -> int:
    """Attach every unclustered item to a cluster. Returns clusters touched."""
    c = store.conn()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=config.BOARD_WINDOW_HOURS)).isoformat()
    pending = c.execute(
        "SELECT id, title, entities, first_seen FROM items "
        "WHERE cluster_id IS NULL AND first_seen >= ? ORDER BY id",
        (cutoff,),
    ).fetchall()
    if not pending:
        return 0

    # Load the candidate pool once; index by entity key so each item only gets
    # compared against clusters it could plausibly belong to.
    clusters = [
        {"id": r["id"], "title": r["title"], "signature": r["signature"] or "",
         "ents": lexicon.entities(r["title"])}
        for r in _active_clusters(config.BOARD_WINDOW_HOURS)
    ]
    by_entity: dict[str, list[dict]] = {}
    for cl in clusters:
        for key in (cl["ents"] or {"~none"}):
            by_entity.setdefault(key, []).append(cl)

    touched: set[int] = set()
    for item in pending:
        title = item["title"]
        ents = set(item["entities"].split(",")) if item["entities"] else set()

        candidates: dict[int, dict] = {}
        for key in (ents or {"~none"}):
            for cl in by_entity.get(key, []):
                candidates[cl["id"]] = cl
        if not ents:
            # Entity-free headline: only compare against other entity-free ones.
            for cl in clusters:
                if not cl["ents"]:
                    candidates[cl["id"]] = cl

        best, best_score = None, 0.0
        for cl in candidates.values():
            s = lexicon.similarity(title, cl["title"], ents, cl["ents"])
            if s > best_score:
                best, best_score = cl, s

        if best and best_score >= lexicon.MERGE_THRESHOLD:
            cluster_id = best["id"]
            c.execute(
                "UPDATE clusters SET last_seen=? WHERE id=?",
                (item["first_seen"], cluster_id),
            )
        else:
            cur = c.execute(
                """INSERT INTO clusters(title, signature, first_seen, last_seen)
                   VALUES (?,?,?,?)""",
                (title, lexicon.signature(title), item["first_seen"], item["first_seen"]),
            )
            cluster_id = cur.lastrowid
            new = {"id": cluster_id, "title": title,
                   "signature": lexicon.signature(title), "ents": ents}
            clusters.append(new)
            for key in (ents or {"~none"}):
                by_entity.setdefault(key, []).append(new)

        c.execute("UPDATE items SET cluster_id=? WHERE id=?", (cluster_id, item["id"]))
        touched.add(cluster_id)

    _promote_titles(touched)
    return len(touched)


def _promote_titles(cluster_ids: set[int]) -> None:
    """Use the clearest headline in the cluster as its display title.

    Prefer an English one where the cluster is mixed — the desk reads faster in
    English — and prefer a headline from a named outlet over a bare one.
    """
    c = store.conn()
    for cid in cluster_ids:
        rows = c.execute(
            "SELECT title, lang, outlet, kind FROM items WHERE cluster_id=? "
            "ORDER BY length(title) DESC LIMIT 25",
            (cid,),
        ).fetchall()
        if not rows:
            continue
        # A written report titles the story better than a TV clip does.
        written = [r for r in rows if r["kind"] != "video"] or rows
        english = [r for r in written if r["lang"] == "en"]
        pool = english or written
        # Middling length beats both the truncated and the essay-length variants.
        pool = sorted(pool, key=lambda r: abs(len(r["title"]) - 75))
        c.execute("UPDATE clusters SET title=? WHERE id=?", (pool[0]["title"], cid))
