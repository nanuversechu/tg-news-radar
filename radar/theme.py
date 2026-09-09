"""Read the live Omarchy theme so the dashboard *is* the desktop's palette.

Omarchy writes every theme's colours to a small `colors.toml` and points
`~/.local/state/omarchy/current/theme` at whichever one is active. We read that
file on demand — cheap, no caching to go stale — so `omarchy theme set` changes
the dashboard on its next refresh without a restart.

Generated themes (the wallhaven ones) can name a muddy olive "red", and a
dim colour on a dark ground is unreadable at 13 px. So every role is contrast
checked against the background and nudged in lightness until it clears
4.5:1. The desktop keeps its palette; the text stays legible.
"""

from __future__ import annotations

import os
import tomllib
from functools import lru_cache

from . import config

# Rose Pine, used when there is no Omarchy theme to read.
FALLBACK = {
    "mode": "dark", "name": "Rose Pine",
    "background": "#191724", "lighter_background": "#26233a",
    "dark_background": "#1f1d2e", "selection": "#2a273f",
    "foreground": "#e0def4", "muted": "#8b86a4",
    "accent": "#31748f", "red": "#eb6f92", "yellow": "#f6c177", "orange": "#ebbcba",
    "green": "#3ddc97", "cyan": "#9ccfd8", "blue": "#31748f", "magenta": "#c4a7e7",
}

# Which theme slot plays which part in the dashboard.
ROLES = {
    "bg": "background",
    "panel": "lighter_background",
    "sel": "selection",
    "text": "foreground",
    "muted": "muted",
    "accent": "accent",
    "up": "green",
    "down": "red",
    "hot": "red",
    "warm": "yellow",
    "cool": "blue",
    # beat colours
    "weather": "cyan",
    "crime": "red",
    "politics": "blue",
    "cinema": "magenta",
    "faith": "yellow",
    "exams": "green",
    "infra": "orange",
    "civic": "yellow",
    "sport": "green",
}

# Roles that are painted as backgrounds, not text: no contrast rule applies.
SURFACE_ROLES = {"bg", "panel", "sel"}


# --------------------------------------------------------------------------
# Colour maths (WCAG relative luminance / contrast ratio)
# --------------------------------------------------------------------------

def _hex_to_rgb(h: str) -> tuple[float, float, float]:
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def _rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(v * 255))):02x}" for v in rgb)


def _luminance(rgb: tuple[float, float, float]) -> float:
    def f(v: float) -> float:
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a: str, b: str) -> float:
    la, lb = _luminance(_hex_to_rgb(a)), _luminance(_hex_to_rgb(b))
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _rgb_to_hsl(rgb):
    r, g, b = rgb
    mx, mn = max(rgb), min(rgb)
    l = (mx + mn) / 2
    if mx == mn:
        return 0.0, 0.0, l
    d = mx - mn
    s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r:
        h = (g - b) / d + (6 if g < b else 0)
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h / 6, s, l


def _hsl_to_rgb(hsl):
    h, s, l = hsl
    if s == 0:
        return (l, l, l)

    def hue(p, q, t):
        t %= 1
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q
    return (hue(p, q, h + 1 / 3), hue(p, q, h), hue(p, q, h - 1 / 3))


def ensure_contrast(colour: str, against: str, minimum: float = 4.5) -> str:
    """Shift a colour's lightness — hue and saturation kept — until it reads.

    Moves away from the background: lighter on a dark ground, darker on a
    light one. Gives up after a bounded number of steps and returns the best
    it found, so a pathological palette degrades rather than loops.
    """
    try:
        if contrast(colour, against) >= minimum:
            return colour
        h, s, l = _rgb_to_hsl(_hex_to_rgb(colour))
        dark_bg = _luminance(_hex_to_rgb(against)) < 0.5
        step = 0.04 if dark_bg else -0.04
        best, best_ratio = colour, contrast(colour, against)
        for _ in range(25):
            l = max(0.0, min(1.0, l + step))
            candidate = _rgb_to_hex(_hsl_to_rgb((h, s, l)))
            ratio = contrast(candidate, against)
            if ratio > best_ratio:
                best, best_ratio = candidate, ratio
            if ratio >= minimum:
                return candidate
        return best
    except (ValueError, ZeroDivisionError):
        return colour


# --------------------------------------------------------------------------
# Reading Omarchy
# --------------------------------------------------------------------------

def _read_omarchy() -> dict | None:
    path = os.path.join(config.OMARCHY_THEME_DIR, "colors.toml")
    try:
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    name = "Omarchy"
    try:
        with open(os.path.join(config.OMARCHY_STATE_DIR, "theme.name"), encoding="utf-8") as fh:
            name = fh.read().strip() or name
    except OSError:
        pass
    raw = {k: v for k, v in raw.items() if isinstance(v, str)}
    key = name.strip().lower().replace(" ", "-")
    raw["name"] = os.environ.get("RADAR_THEME_LABEL") or config.THEME_LABELS.get(key, name)
    return raw


def _stat_key() -> float:
    """mtime of colors.toml — the cache key, so a theme switch is seen at once."""
    try:
        return os.stat(os.path.join(config.OMARCHY_THEME_DIR, "colors.toml")).st_mtime
    except OSError:
        return 0.0


@lru_cache(maxsize=4)
def _build(_mtime: float) -> dict:
    raw = _read_omarchy()
    source = "omarchy" if raw else "fallback"
    pal = dict(FALLBACK)
    if raw:
        pal.update(raw)
        # Generated themes sometimes omit the secondary surfaces.
        pal.setdefault("lighter_background", pal.get("selection", pal["background"]))
        pal.setdefault("selection", pal["lighter_background"])
        pal.setdefault("orange", pal.get("yellow", pal["foreground"]))

    bg = pal["background"]
    roles: dict[str, str] = {}
    for role, slot in ROLES.items():
        colour = pal.get(slot) or FALLBACK.get(slot) or pal["foreground"]
        if role not in SURFACE_ROLES:
            # Muted is allowed to be quieter, but still legible.
            colour = ensure_contrast(colour, bg, 4.5)
        roles[role] = colour
    # Text painted on top of the accent (active tab, status label). Omarchy
    # itself uses the theme background for this — see any theme's alacritty
    # search-match colours — so do the same when it reads, else pick the
    # better of white and black.
    if contrast(bg, roles["accent"]) >= 3.0:
        roles["on_accent"] = bg
    else:
        w, k = contrast("#ffffff", roles["accent"]), contrast("#000000", roles["accent"])
        roles["on_accent"] = "#ffffff" if w >= k else "#000000"
    roles["line"] = pal.get("lighter_background", bg)
    # A hairline must be visible but not loud: nudge toward 1.6:1 if it vanished.
    if contrast(roles["line"], bg) < 1.25:
        roles["line"] = ensure_contrast(roles["line"], bg, 1.6)

    return {
        "source": source,
        "name": pal.get("name", "Rose Pine"),
        "mode": pal.get("mode", "dark"),
        "roles": roles,
    }


def current() -> dict:
    """The active theme, resolved to dashboard roles. Safe to call per request."""
    return _build(_stat_key())


def css_vars() -> str:
    t = current()
    return "\n".join(f"  --{k}:{v};" for k, v in t["roles"].items())
