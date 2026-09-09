"""Tolerant RSS / Atom parsing with no third-party dependencies.

Real newspaper feeds are frequently malformed. ElementTree is strict, so every
parser here falls back to a regex sweep rather than losing the whole feed over
one stray ampersand.
"""

from __future__ import annotations

import html
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

NS = {
    "ht": "https://trends.google.com/trending/rss",
    "atom": "http://www.w3.org/2005/Atom",
    "media": "http://search.yahoo.com/mrss/",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "dc": "http://purl.org/dc/elements/1.1/",
}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_text(value: str | None) -> str:
    """Strip tags and entities, collapse whitespace."""
    if not value:
        return ""
    text = html.unescape(value)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def parse_date(value: str | None) -> datetime | None:
    """Parse the many date shapes feeds use. Always returns UTC-aware."""
    if not value:
        return None
    value = value.strip()
    try:
        dt = parsedate_to_datetime(value)
        if dt is not None:
            return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _root(xml_text: str):
    """Parse to an ElementTree root, repairing the usual breakages."""
    if not xml_text:
        return None
    text = xml_text.lstrip("﻿ \t\r\n")
    for candidate in (text, _repair(text)):
        try:
            return ET.fromstring(candidate)
        except ET.ParseError:
            continue
    return None


def _repair(text: str) -> str:
    """Escape bare ampersands and drop control characters."""
    text = re.sub(r"&(?!#?\w+;)", "&amp;", text)
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)


def _findtext(elem, *paths: str) -> str:
    for path in paths:
        node = elem.find(path, NS)
        if node is not None:
            if node.text and node.text.strip():
                return node.text
            # Some feeds put the link in an attribute instead.
            for attr in ("href", "url"):
                if node.get(attr):
                    return node.get(attr)
    return ""


# --------------------------------------------------------------------------
# Generic RSS / Atom
# --------------------------------------------------------------------------

def parse_items(xml_text: str) -> list[dict]:
    """Return [{title, link, published, summary, source}] from RSS or Atom."""
    root = _root(xml_text)
    if root is None:
        return _regex_items(xml_text)

    nodes = root.findall(".//item") or root.findall(".//atom:entry", NS)
    items: list[dict] = []
    for node in nodes:
        title = clean_text(_findtext(node, "title", "atom:title"))
        if not title:
            continue
        link = _findtext(node, "link", "atom:link", "guid").strip()
        if not link.startswith("http"):
            alt = node.find("atom:link[@rel='alternate']", NS) or node.find("atom:link", NS)
            if alt is not None and alt.get("href"):
                link = alt.get("href")
        published = parse_date(
            _findtext(node, "pubDate", "atom:published", "atom:updated", "dc:date", "published")
        )
        source = clean_text(_findtext(node, "source"))
        items.append({
            "title": title,
            "link": link,
            "published": published,
            "summary": clean_text(_findtext(node, "description", "atom:summary", "atom:content"))[:400],
            "source": source,
        })
    return items or _regex_items(xml_text)


_ITEM_BLOCK = re.compile(r"<(item|entry)[\s>].*?</\1>", re.S | re.I)
_FIELD = {
    "title": re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I),
    "link": re.compile(r"<link[^>]*?href=[\"']([^\"']+)[\"']|<link[^>]*>(.*?)</link>", re.S | re.I),
    "date": re.compile(r"<(?:pubDate|published|updated|dc:date)[^>]*>(.*?)</", re.S | re.I),
}


def _regex_items(xml_text: str) -> list[dict]:
    """Last resort when the XML simply will not parse."""
    if not xml_text:
        return []
    out: list[dict] = []
    for block in _ITEM_BLOCK.finditer(xml_text):
        chunk = block.group(0)
        m_title = _FIELD["title"].search(chunk)
        if not m_title:
            continue
        title = clean_text(m_title.group(1))
        if not title:
            continue
        link = ""
        m_link = _FIELD["link"].search(chunk)
        if m_link:
            link = clean_text(m_link.group(1) or m_link.group(2) or "")
        m_date = _FIELD["date"].search(chunk)
        out.append({
            "title": title,
            "link": link,
            "published": parse_date(clean_text(m_date.group(1))) if m_date else None,
            "summary": "",
            "source": "",
        })
    return out


# --------------------------------------------------------------------------
# Google Trends RSS (has its own ht: namespace with traffic + linked news)
# --------------------------------------------------------------------------

def parse_trends(xml_text: str) -> list[dict]:
    """Return [{query, traffic, published, picture, news:[{title,url,source}]}]."""
    root = _root(xml_text)
    if root is None:
        return []
    out: list[dict] = []
    for node in root.findall(".//item"):
        query = clean_text(_findtext(node, "title"))
        if not query:
            continue
        traffic = _parse_traffic(clean_text(_findtext(node, "ht:approx_traffic")))
        news = []
        for item in node.findall("ht:news_item", NS):
            news.append({
                "title": clean_text(_findtext(item, "ht:news_item_title")),
                "url": clean_text(_findtext(item, "ht:news_item_url")),
                "source": clean_text(_findtext(item, "ht:news_item_source")),
            })
        out.append({
            "query": query,
            "traffic": traffic,
            "published": parse_date(clean_text(_findtext(node, "pubDate"))),
            "picture": clean_text(_findtext(node, "ht:picture")),
            "news": [n for n in news if n["title"]],
        })
    return out


def _parse_traffic(value: str) -> int:
    """'20K+' -> 20000, '500+' -> 500."""
    if not value:
        return 0
    m = re.search(r"([\d.,]+)\s*([KMkm]?)", value)
    if not m:
        return 0
    try:
        num = float(m.group(1).replace(",", ""))
    except ValueError:
        return 0
    suffix = m.group(2).upper()
    return int(num * {"K": 1_000, "M": 1_000_000}.get(suffix, 1))


# --------------------------------------------------------------------------
# Google News specifics
# --------------------------------------------------------------------------

def google_news_url(query: str, hl: str, ceid: str, when: str | None = None) -> str:
    q = f"{query} when:{when}" if when else query
    params = urllib.parse.urlencode({
        "q": q, "hl": hl, "gl": ceid.split(":")[0], "ceid": ceid,
    })
    return f"https://news.google.com/rss/search?{params}"


_GN_SUFFIX = re.compile(r"\s+-\s+([^-]{2,60})$")


def split_google_title(title: str) -> tuple[str, str]:
    """Google News appends ' - Outlet'. Return (headline, outlet)."""
    m = _GN_SUFFIX.search(title)
    if m:
        return title[: m.start()].strip(), m.group(1).strip()
    return title.strip(), ""


def domain_of(url: str) -> str:
    """Publisher domain, with www/m/amp prefixes removed."""
    if not url:
        return ""
    host = urllib.parse.urlsplit(url).netloc.lower()
    for prefix in ("www.", "m.", "amp.", "en.", "telugu."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return host


def recent(dt: datetime | None, hours: float) -> bool:
    if dt is None:
        return False
    return dt >= datetime.now(timezone.utc) - timedelta(hours=hours)
