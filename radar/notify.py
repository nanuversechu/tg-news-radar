"""Desk alerts and optional LLM gloss. Both are off unless you configure them."""

from __future__ import annotations

import urllib.parse

from . import config, lexicon, net, store


def send_alerts(alerts: list[dict]) -> None:
    for cl in alerts:
        text = format_alert(cl)
        print("\n" + "=" * 62 + f"\nALERT  {cl['score']}  {cl['title']}\n" + "=" * 62, flush=True)
        if config.TELEGRAM_TOKEN and config.TELEGRAM_CHAT_ID:
            if _telegram(text):
                store.conn().execute(
                    "UPDATE alerts SET delivered=1 WHERE cluster_id=? AND delivered=0",
                    (cl["id"],),
                )


def format_alert(cl: dict) -> str:
    bits = [f"<b>{_esc(cl['title'])}</b>",
            f"score {cl['score']} · {cl['age_min']} min old · {cl['outlet_count']} outlets"]
    if cl.get("trend_query"):
        bits.append(f"searched now: <i>{_esc(cl['trend_query'])}</i> ({cl.get('trend_geo','')})")
    for link in cl.get("links", [])[:4]:
        if link["url"]:
            bits.append(f"· <a href=\"{_esc(link['url'])}\">{_esc(link['outlet'] or 'link')}</a>")
    return "\n".join(bits)


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _telegram(text: str) -> bool:
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    return bool(net.post_json(url, payload))


# --------------------------------------------------------------------------
# Optional: one-line English gloss for Telugu headlines, via the Groq free tier
# --------------------------------------------------------------------------

def gloss(titles: list[str]) -> dict[str, str]:
    """Translate Telugu headlines to short English. Empty dict if unconfigured."""
    if not config.GROQ_API_KEY:
        return {}
    todo = [t for t in titles if lexicon.is_telugu(t)][:12]
    if not todo:
        return {}
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(todo))
    body = {
        "model": config.GROQ_MODEL,
        "temperature": 0.1,
        "messages": [
            {"role": "system",
             "content": "Translate each numbered Telugu news headline into plain English. "
                        "Reply with the same numbering, one line each, nothing else."},
            {"role": "user", "content": numbered},
        ],
    }
    data = net.post_json(
        "https://api.groq.com/openai/v1/chat/completions", body,
        headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
    )
    if not data:
        return {}
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return {}
    out: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or "." not in line[:4]:
            continue
        num, _, rest = line.partition(".")
        try:
            idx = int(num.strip()) - 1
        except ValueError:
            continue
        if 0 <= idx < len(todo) and rest.strip():
            out[todo[idx]] = rest.strip()
    return out


def google_search_link(query: str) -> str:
    return "https://www.google.com/search?" + urllib.parse.urlencode({"q": query, "gl": "IN"})


def trends_explore_link(query: str, geo: str = "") -> str:
    geo = geo or config.HOME_GEO
    return "https://trends.google.com/trends/explore?" + urllib.parse.urlencode(
        {"q": query, "geo": geo, "date": "now 1-d"}
    )
