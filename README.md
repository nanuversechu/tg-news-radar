# Telangana news radar

Tells you what Telangana is searching for and reading **right now**, which of
it the press has already covered, and which it has not — so a desk can write to
demand instead of guessing at it.

Built for a desk, not a data scientist. No API keys, no accounts, no
`pip install` — Python's standard library and nothing else.

This is the twin of the [Andhra Pradesh radar](../ap-news-radar). Every file in
`radar/` is byte-identical between the two; only `config.py` differs. A fix in
one is a file copy away from the other.

## See it without installing anything

**<https://nanuversechu.github.io/tg-news-radar/>** — the board as the desk sees
it. **It is private:** the page is encrypted, and asks for a key before it
shows anything. It **republishes itself every 15 minutes**, so the link stays
current without anyone touching it.

### How the lock works

GitHub Pages is a static host — there is no server to check a password
against, and a page that merely *asks* for one while carrying the content in
its HTML protects nothing. So the board is genuinely encrypted:
**AES-256-GCM**, with the key derived in the reader's browser by PBKDF2-SHA256
over 250,000 iterations. What GitHub serves is an unlock form and a block of
ciphertext. `curl` on the URL returns ciphertext. A wrong key fails the GCM
authentication tag and yields nothing.

The key lives in the publish service unit and in `.radar-key` — both outside
the repository, both `chmod 600`. `publish.sh` refuses to run without one, so
the board cannot reach the open web by accident. A reader's key is remembered
for their browser tab; a link of the form `…/#k=THE-KEY` opens straight in,
and the fragment is never sent to any server.

Honest limits: this protects against anyone who does not have the key, not
against someone who has it, and not against an attacker willing to grind
guesses offline against the downloaded file — which is why the key is 79 bits
of randomness rather than a word. To change it, edit `.radar-key` and the
`Environment=RADAR_PAGE_KEY=` line in the publish unit, then run
`./publish.sh`.

Allowing for GitHub's ten-minute CDN cache, a reader sees a board at most
about twenty-five minutes old. The refresh is a systemd timer running
[`publish.sh`](publish.sh); it only publishes when the radar answered and
produced a real page, so a stopped radar leaves the last good snapshot up
rather than replacing it with an error. The page is force-pushed to a
single-commit `gh-pages` branch, so the repository stays the size of one
snapshot however often it refreshes.

`publish.sh` needs `python-cryptography` for the encryption step (already on
Arch). The radar itself still needs nothing but the standard library.

```bash
./publish.sh          # publish immediately, by hand
```

The Andhra Pradesh twin is at <https://nanuversechu.github.io/ap-news-radar/>.

## Bookmark this

**<http://127.0.0.1:8788>** — the Telangana board.
(The Andhra one is on **8787**; the two run side by side.)

It runs as a background service that starts on boot and restarts itself if it
ever crashes, so the link should simply always work. Nothing to launch.

The first tick after a reboot takes about two and a half minutes: this radar
waits 150 seconds before its first poll so the two radars never fetch from
Google in the same second. It also stays quiet on the first tick on purpose —
it has no history to compare against yet, so it fills the baseline instead of
alerting. After that it refreshes every 5 minutes.

### If the link is ever dead

```bash
systemctl --user status tg-radar
```

```bash
systemctl --user restart tg-radar
```

```bash
journalctl --user -u tg-radar -n 50
```

---

## The look

Square corners, JetBrainsMono Nerd Font, meters drawn in block characters —
identical to the Andhra board.

The palette is **Neon Noir**: a violet-black ground, pink for the brand and the
loudest scores, mint for rising, coral for fading, near-white for anything you
actually read. Light or dark follows your desktop; the status bar names your
Omarchy theme. `RADAR_PALETTE=omarchy` follows the desktop's own colours.

Direction is never colour alone: **▲ up · ▼ down · ● new · → flat**.

### On the board

Five panels, in the order a desk needs them.

1. **Searching now** — every live Google search from Telangana (then Andhra
   Pradesh, then India, at lower weight), each with an arrow against thirty
   minutes ago, its traffic bucket, a `TG` mark when it names a Telangana
   place, person or institution, and **its coverage right now**: `6 outlets`,
   `1 outlet`, or `uncovered`. Click a search and the board narrows to the
   stories that answer it. Hindi, Marathi, Tamil and Kannada queries from the
   India-wide feed are dropped.
2. **Trailing** — searches that were trending and have dropped off in the last
   90 minutes, with what they peaked at.
3. **Top stories** — Google News' current ranking for **Telangana, Hyderabad
   and Warangal**, English and Telugu interleaved in Google's own order, newest
   first, nothing older than two hours. Fetched with no account and no cookies,
   so it is what Google shows a stranger, not what it shows you.
4. **Story board** — everything published in the last two hours, scored, with
   direction arrows, outlet counts, and `GN #3` when Google's front page ranks
   it. **Hover any score** for the six components that make it up.
5. **Reading** — Telugu Wikipedia's most-viewed pages. Daily data, so the list
   is *yesterday* and says so.

**Keyboard**: `/` filter · `j` `k` move · `o` open · `1`–`5` tabs · `s`
sources · `esc` clear.

## What it watches

### The freshness contract

**Nothing older than 2 hours, anywhere** — enforced at ingest, again at
scoring, and in every query window sent to Google.

### Sources — 45, every one verified live on 9 September 2026

| Signal | Source | Refresh |
|---|---|---|
| What Telangana is searching | Google Trends RSS, `geo=IN-TG` | 5 min |
| Same for Andhra Pradesh + India | Google Trends RSS, `IN-AP` / `IN` | 5 min |
| Top stories by place | Google News search for Telangana, Hyderabad, Warangal, both languages, `when:2h` | 5 min |
| Google's front page | Google News top stories, Telugu and English, rank kept | 5 min |
| Every Google News section | 8 Telugu + 4 English topic sections | 15 min |
| Breaking coverage | 34 standing queries in Telugu and English, all `when:2h` | 5 min |
| District sweeps | 27 district queries, a third each tick | every district every 15 min |
| Coverage of what's rising | Google News searched for each rising trend | 5 min |
| Telangana newspapers | 16 publisher RSS feeds | 15 min |
| Telugu TV | 6 YouTube channels | 15 min |
| Chatter | Reddit r/hyderabad (marked ◆ social) | 15 min |
| What Telugu readers looked up | Telugu Wikipedia most-viewed pages | hourly |

The sixteen publisher feeds: **Namasthe Telangana**, **Telangana Today**,
**Siasat**, **V6 Velugu**, **HMTV**, **Hans India (Telangana)**, **The Hindu**
(Telangana and Hyderabad desks), plus the Telugu titles that cover both states
— **TV9**, **NTV**, **10TV**, **Sakshi**, **Vaartha**, **Oneindia Telugu**,
**Gulte**, **Deccan Chronicle**.

Television: **V6 News**, **T News**, **TV9 Telugu**, **NTV**, **TV5**,
**10TV**. YouTube's feed endpoint died for three weeks in August 2026 and came
back on 9 September; if it goes again, set `YOUTUBE_ENABLED = False`.

Tried and dead: Eenadu, Samayam, Zee Telugu, News18 Telugu, Deccan Herald,
Andhra Prabha, HT Telugu. They are listed in `config.py` so nobody retries them.

### Built to stay up

Same machinery as the Andhra radar: a systemd watchdog that restarts a *hung*
poller and not merely a dead one, per-host cooldowns that obey a 429, last-good
data kept when a source returns empty, a loud `▲ STALE` state, a poller thread
revived if it dies, and a poll loop that watches the wall clock so a closed
laptop lid does not stall the next poll.

## How it decides what matters

```
score = 100 × locality × ( 0.32 trend        does a live Google search match this?
                         + 0.20 acceleration reports in the last 30 min vs the 90 before
                         + 0.18 corroboration how many independent outlets have it
                         + 0.12 prominence   rank on Google News' front page, if any
                         + 0.10 velocity     raw reports per hour
                         + 0.08 freshness    decays with a 40 minute half-life )
```

`locality` is `1.0` when the story names a Telangana place, politician or
institution, `0.55` for the wider Telugu sphere — Andhra Pradesh politics,
Telugu film stars — and `0.18` otherwise. It is derived from the lexicon, so
adding a minister there is enough.

### Cross-language matching without a GPU

A Telugu headline and its English twin have to land in one cluster, or every
story is counted twice and corroboration means nothing. The textbook answer is
LaBSE; on a CPU-only laptop that is a bad trade. Instead `config.LEXICON` lists
the cast Telangana news actually revolves around — all 33 districts and their
towns, the cabinet, the BRS and BJP benches, AIMIM, the institutions
(HYDRAA, GHMC, TGSRTC, TGPSC, the Assembly, the High Court), the rivers and
projects, and the film and cricket names the state searches for — in both
scripts.

It was built from **985 live Telangana headlines** sampled on 9 September 2026,
so the cast is the one actually in the news rather than one from memory.

```
"BRS MLAs suspended from Telangana Assembly"
"అసెంబ్లీ నుంచి బీఆర్ఎస్ ఎమ్మెల్యేల సస్పెన్షన్"
                                        → one story
```

Its real limit: **a name absent from the lexicon cannot match across scripts.**
Adding one is two lines, and that is the tool's main upkeep.

```python
# radar/config.py
"harish_rao": ("person", ["harish rao", "t harish rao", "హరీశ్ రావు", "హరీష్ రావు"]),
```

**Aliases must be distinctive.** No bare `reddy`, `rao` or `kumar` — they are
among the commonest surnames in the state and would match half the wire. Bare
`కవిత` is excluded too: it is the Telugu word for *poem*.

Run the tests after editing:

```bash
python3 tests/test_matching.py
```

```bash
python3 tests/test_reliability.py
```

## Commands

```bash
./run.sh once
```

```bash
./run.sh check
```

`check` probes every source with status and latency, and says which Omarchy
theme it sees. A search that answers with nothing is reported `none` rather
than `DEAD` — a place can simply have had no news in the window.

```bash
python3 -m radar snapshot
```

Freezes the live board into `docs/index.html`, a single self-contained page for
showing someone who will not run it. `./publish.sh` does that and pushes it to
GitHub Pages; the timer runs it every 15 minutes.

## Data

One SQLite file, `radar.db`, in this folder — separate from the Andhra radar's.
Timestamps stored UTC, displayed IST. Story age comes from each report's
**published** time, never from when the radar found it.

## Scope

A monitoring tool, not a syndication tool. It stores headlines, links and
timestamps so a desk can decide what to chase; it does not copy article text.
Every source is an official RSS feed or a public API, polled below the rate any
of them ask for.
