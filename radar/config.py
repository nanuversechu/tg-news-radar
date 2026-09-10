"""Sources, lexicon and tuning knobs for the Telangana news radar.

Everything a human might want to change lives here. No other file needs editing
to add a newspaper, a YouTube channel or a name to watch.
"""

from __future__ import annotations

import os

# --------------------------------------------------------------------------
# Which state this radar watches.
#
# Everything region-specific lives in this file. The rest of the package is
# byte-identical between the Andhra Pradesh and Telangana radars, so a fix in
# one is a file copy away from the other.
# --------------------------------------------------------------------------

REGION_NAME = "Telangana"
REGION_SLUG = "tg-radar"
LOCAL_LABEL = "TG"            # locality tag and the badge for the home state
HOME_GEO = "IN-TG"
GEO_BADGES = {"IN-TG": "TG", "IN-AP": "AP", "IN": "IN"}

# --------------------------------------------------------------------------
# Identity / politeness
# --------------------------------------------------------------------------

# Sent in the User-Agent so a webmaster can reach a human. Set RADAR_CONTACT
# to your own address; the systemd unit does this. Kept out of the source so
# the repository carries no personal address.
CONTACT = os.environ.get("RADAR_CONTACT", "tg-news-radar@localhost")
USER_AGENT = (
    "TGNewsRadar/1.0 (newsroom monitoring; +mailto:%s) "
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
    % CONTACT
)

# Seconds to wait between two requests to the same host.
HOST_DELAY = 1.2
FETCH_TIMEOUT = 25
MAX_PARALLEL = 6
# How long to leave a host alone after it pushes back. A 429 obeyed now is a
# ban avoided later.
COOLDOWN_429 = 30 * 60
COOLDOWN_5XX = 5 * 60

# --------------------------------------------------------------------------
# Omarchy — the dashboard reads the live desktop theme from here.
# --------------------------------------------------------------------------

# "neon" is the curated palette in theme.py; "omarchy" follows the desktop
# theme's own colours instead. Either way the light/dark mode follows Omarchy.
PALETTE = os.environ.get("RADAR_PALETTE", "neon")

OMARCHY_STATE_DIR = os.environ.get(
    "OMARCHY_STATE", os.path.expanduser("~/.local/state/omarchy/current"))
OMARCHY_THEME_DIR = os.path.join(OMARCHY_STATE_DIR, "theme")
# What the status bar calls a theme. Omarchy names generated themes after the
# wallpaper file; this maps that to a name worth reading. Keys are the theme
# name lower-cased with spaces as hyphens. RADAR_THEME_LABEL overrides all.
THEME_LABELS = {
    "wallhaven-w5ly": "Prometheus",
}

# --------------------------------------------------------------------------
# Poll cadence (seconds)
# --------------------------------------------------------------------------

TICK_SECONDS = int(os.environ.get("RADAR_TICK", "300"))  # 5 minutes
# Wait this long before the first poll. Two radars on one machine are offset so
# they do not fetch from Google in the same second.
START_DELAY_SECONDS = int(os.environ.get("RADAR_START_DELAY", "150"))
SLOW_EVERY_N_TICKS = 3    # publishers, sections, most-read: every 3rd tick (~15 min)
HOURLY_EVERY_N_TICKS = 12  # Wikipedia top pages change once a day; once an hour is plenty

# The freshness contract. Anything published longer ago than this is refused at
# ingest and never reaches the board — this is a "what is breaking now" radar,
# not an archive. Raise it if the board ever looks too thin.
MAX_ITEM_AGE_HOURS = float(os.environ.get("RADAR_MAX_AGE_HOURS", "2"))

# How long a story stays on the live board. Kept equal to the ingest window so
# the board cannot outlive the material it is built from.
BOARD_WINDOW_HOURS = MAX_ITEM_AGE_HOURS
# Rows older than this are deleted on housekeeping (history for the baseline).
RETENTION_DAYS = 14
# The per-tick score history is only useful for recent trajectory, and it is by
# far the biggest table, so it is pruned much harder than everything else.
HISTORY_RETENTION_DAYS = 2
# Below this score a cluster's trajectory is not worth recording.
HISTORY_MIN_SCORE = 20.0

# --------------------------------------------------------------------------
# Google Trends — the "what is Telangana searching for right now" signal.
# Free, keyless RSS. IN-TG is the Telangana sub-region.
# --------------------------------------------------------------------------

TREND_FEEDS = [
    # (geo code, human label, weight applied to the trend's score)
    ("IN-TG", "Telangana", 1.0),
    ("IN-AP", "Andhra Pradesh", 0.55),  # Telugu stories cross the border constantly
    ("IN", "India", 0.45),
]

# --------------------------------------------------------------------------
# Google News RSS — standing queries. `when:` forces freshness.
# Each entry: (query, hl, ceid, freshness window)
# --------------------------------------------------------------------------

_TE = ("te-IN", "IN:te")
_EN = ("en-IN", "IN:en")

STANDING_QUERIES: list[tuple[str, tuple[str, str], str]] = [
    # Broad state sweeps. "Telangana" and "Hyderabad" themselves live in
    # TOP_SECTIONS below, so they are not repeated here.
    ("తెలంగాణ వార్తలు", _TE, "2h"),
    ("Telangana news", _EN, "2h"),
    ("Telangana government", _EN, "2h"),
    ("తెలంగాణ ప్రభుత్వం", _TE, "2h"),
    # Politics — government
    ("Revanth Reddy", _EN, "2h"),
    ("రేవంత్ రెడ్డి", _TE, "2h"),
    ("Bhatti Vikramarka", _EN, "2h"),
    ("Telangana Congress", _EN, "2h"),
    # Politics — opposition
    ("KTR BRS", _EN, "2h"),
    ("కేటీఆర్", _TE, "2h"),
    ("KCR Harish Rao", _EN, "2h"),
    ("కేసీఆర్", _TE, "2h"),
    ("Telangana BJP Bandi Sanjay Kishan Reddy", _EN, "2h"),
    ("Owaisi AIMIM Hyderabad", _EN, "2h"),
    # Assembly and courts
    ("Telangana Assembly session", _EN, "2h"),
    ("తెలంగాణ అసెంబ్లీ", _TE, "2h"),
    ("Telangana High Court", _EN, "2h"),
    # City government — the Hyderabad engine
    ("HYDRAA GHMC Hyderabad", _EN, "2h"),
    ("హైడ్రా జీహెచ్ఎంసీ", _TE, "2h"),
    ("Musi riverfront", _EN, "2h"),
    ("Hyderabad Metro Rail", _EN, "2h"),
    ("Cyberabad police", _EN, "2h"),
    # Water and irrigation — the recurring Telangana fight
    ("Kaleshwaram project", _EN, "2h"),
    ("కాళేశ్వరం", _TE, "2h"),
    # Weather / disaster
    ("Telangana rains IMD warning", _EN, "2h"),
    ("వర్షాలు హెచ్చరిక", _TE, "2h"),
    # Exams / jobs — huge search volume
    ("TGPSC Group 1 notification result", _EN, "2h"),
    ("తెలంగాణ ఫలితాలు నోటిఫికేషన్", _TE, "2h"),
    # Farming and welfare schemes
    ("Rythu Bharosa Telangana farmers", _EN, "2h"),
    ("రైతు భరోసా", _TE, "2h"),
    # Entertainment
    ("Tollywood", _EN, "2h"),
    ("టాలీవుడ్", _TE, "2h"),
    # Crime / accidents
    ("Telangana accident police arrest", _EN, "2h"),
    # Official announcements (PIB serves no working RSS of its own)
    ("site:pib.gov.in Telangana", _EN, "2h"),
    ("Telangana government GO announcement", _EN, "2h"),
]

# District sweeps. Thirty more requests to one host every tick would add load
# without adding much signal, so a third of this list runs each tick: every
# district is covered every 15 minutes at constant per-tick cost.
DISTRICT_QUERIES: list[tuple[str, tuple[str, str], str]] = [
    ("Karimnagar", _EN, "2h"), ("Nizamabad", _EN, "2h"), ("Khammam", _EN, "2h"),
    ("Nalgonda", _EN, "2h"), ("Mahabubnagar", _EN, "2h"), ("Adilabad", _EN, "2h"),
    ("Siddipet", _EN, "2h"), ("Sangareddy", _EN, "2h"), ("Medak", _EN, "2h"),
    ("Suryapet", _EN, "2h"), ("Ramagundam Peddapalli", _EN, "2h"),
    ("Bhadrachalam Kothagudem", _EN, "2h"), ("Rangareddy", _EN, "2h"),
    ("Vikarabad", _EN, "2h"), ("Jagtial", _EN, "2h"), ("Mancherial", _EN, "2h"),
    ("Nirmal", _EN, "2h"), ("Wanaparthy Nagarkurnool", _EN, "2h"),
    ("కరీంనగర్", _TE, "2h"), ("నిజామాబాద్", _TE, "2h"), ("ఖమ్మం", _TE, "2h"),
    ("నల్గొండ", _TE, "2h"), ("మహబూబ్‌నగర్", _TE, "2h"), ("ఆదిలాబాద్", _TE, "2h"),
    ("సిద్దిపేట", _TE, "2h"), ("సంగారెడ్డి", _TE, "2h"), ("హనుమకొండ", _TE, "2h"),
]
DISTRICT_ROTATION = 3

# Google News "top stories" for the state and its two big cities.
#
# Google's own geo sections (/headlines/section/geo/<place>) were tried on the
# Andhra radar and dropped: they carried 12- to 60-hour-old items and nothing
# inside the freshness window, in either language. A search with `when:2h`
# returns what Google ranks for the place *right now*, in both languages, and
# that is what these panels show. Fetched without an account or cookies, so it
# is what Google shows a stranger, not what it shows you.
TOP_SECTIONS: list[tuple[str, list[tuple[str, tuple[str, str], str]]]] = [
    ("Telangana",  [("Telangana", _EN, "2h"), ("తెలంగాణ", _TE, "2h")]),
    ("Hyderabad",  [("Hyderabad", _EN, "2h"), ("హైదరాబాద్", _TE, "2h")]),
    # Warangal is the second city but a thinner feed, so it gets the extra
    # Hanumakonda query — the twin district that shares its news.
    ("Warangal",   [("Warangal", _EN, "2h"), ("వరంగల్", _TE, "2h"),
                    ("Hanumakonda", _EN, "2h"), ("హనుమకొండ", _TE, "2h")]),
]
SECTION_ROWS = 10

# Google News front page and sections, per language. Rank within the top
# stories feed is Google's own reading-behaviour signal and is kept.
# Verified 8 Sep 2026: every one of these answers with 22–70 items.
_GN = "https://news.google.com/rss"
GOOGLE_NEWS_TOP: list[tuple[str, str]] = [
    ("Google News · top stories (te)", f"{_GN}?hl=te-IN&gl=IN&ceid=IN:te"),
    ("Google News · top stories (en)", f"{_GN}?hl=en-IN&gl=IN&ceid=IN:en"),
]
GOOGLE_NEWS_TOPICS: list[tuple[str, str]] = [
    (f"Google News · {t.lower()} (te)", f"{_GN}/headlines/section/topic/{t}?hl=te-IN&gl=IN&ceid=IN:te")
    for t in ("NATION", "WORLD", "BUSINESS", "TECHNOLOGY", "ENTERTAINMENT", "SPORTS", "SCIENCE", "HEALTH")
] + [
    (f"Google News · {t.lower()} (en)", f"{_GN}/headlines/section/topic/{t}?hl=en-IN&gl=IN&ceid=IN:en")
    for t in ("NATION", "BUSINESS", "ENTERTAINMENT", "SPORTS")
]

# Wikipedia's most-viewed pages. The pageviews API is daily-only per article,
# so this is yesterday, and is labelled as such — it is still the clearest
# free read on what Telugu readers went looking for.
WIKI_PROJECTS: list[tuple[str, str]] = [
    ("te.wikipedia", "Telugu Wikipedia"),
]
WIKI_TOP_N = 15

# Reddit's unauthenticated RSS is real but tight: three subreddit fetches in a
# row drew a 429. One feed, every 15 minutes, with the host cooled down on any
# push-back, stays well inside that. Kind "social" so the desk can tell chatter
# from reporting.
SOCIAL_FEEDS: list[tuple[str, str]] = [
    ("Reddit r/hyderabad", "https://www.reddit.com/r/hyderabad/new.rss"),
]

# Direction arrows compare a trend against this long ago, not the last poll.
TREND_LOOKBACK_MIN = 30
# Stories likewise, and a score has to move this much to earn an arrow.
STORY_LOOKBACK_MIN = 15
STORY_DELTA = 6.0
# A query that vanished from the feed within this window is shown as trailing.
TRAILING_WINDOW_MIN = 90

# When a Google Trends query is rising, we immediately search news for it.
# This is what turns "people are searching X" into "here is the coverage of X".
TREND_CHASE_WINDOW = "2h"
MAX_TREND_CHASES = 12  # per tick, highest-scoring rising trends first

# --------------------------------------------------------------------------
# Publisher RSS — every one verified live and fresh on 9 Sep 2026.
# --------------------------------------------------------------------------

PUBLISHER_FEEDS: list[tuple[str, str, str]] = [
    # (outlet name, language, url)
    # Telangana mastheads
    ("Namasthe Telangana", "te", "https://ntnews.com/feed"),
    ("Telangana Today", "en", "https://telanganatoday.com/feed"),
    ("Siasat", "en", "https://www.siasat.com/feed/"),
    ("V6 Velugu", "te", "https://www.v6velugu.com/feed"),
    ("HMTV", "te", "https://www.hmtvlive.com/feed"),
    ("Hans India Telangana", "en", "https://www.thehansindia.com/rss/telangana"),
    ("The Hindu Telangana", "en", "https://www.thehindu.com/news/national/telangana/feeder/default.rss"),
    ("The Hindu Hyderabad", "en", "https://www.thehindu.com/news/cities/Hyderabad/feeder/default.rss"),
    # Telugu titles that cover both states
    ("TV9 Telugu", "te", "https://tv9telugu.com/feed"),
    ("NTV Telugu", "te", "https://ntvtelugu.com/feed"),
    ("10TV", "te", "https://10tv.in/latest/feed"),
    ("Sakshi", "te", "https://www.sakshi.com/rss.xml"),
    ("Vaartha", "te", "https://www.vaartha.com/feed/"),
    ("Oneindia Telugu", "te", "https://telugu.oneindia.com/rss/telugu-news-fb.xml"),
    ("Gulte", "te", "https://telugu.gulte.com/feed"),
    ("Deccan Chronicle", "en", "https://www.deccanchronicle.com/rss_feed/"),
    # PIB's ViewRss.aspx answers 200 with an empty body, so official releases
    # are covered by the site: query in STANDING_QUERIES instead.
    # Tried and dead on 8-9 Sep 2026: Eenadu, Samayam, Zee Telugu, News18
    # Telugu, Deccan Herald, New Indian Express, Andhra Prabha, HT Telugu.
]

# --------------------------------------------------------------------------
# YouTube channel RSS.
#
# The endpoint 404'd for every channel between 18 Aug and 9 Sep 2026, then
# came back: on 9 Sep every channel below answered with 15 entries, the newest
# six minutes old. Re-enabled, with the freshness gate deciding what shows.
# If it dies again, set this to False; `./run.sh check` keeps probing either way.
# --------------------------------------------------------------------------

YOUTUBE_ENABLED = True

YOUTUBE_CHANNELS: list[tuple[str, str]] = [
    ("V6 News", "UCcQ10GNXaBBtr2IWavGWMWg"),
    ("T News", "UClMlGnpuMYDPKwpBufpjfMA"),
    ("TV9 Telugu", "UCfaww9Q8C_-EaM0sXI8o-fA"),
    ("NTV Telugu", "UCtzYV2L-m8ew93mZb3qhf5w"),
    ("TV5 News", "UCxiv-IYyYR725C2apG_w6fQ"),
    ("10TV News", "UCcFQmmbb439JyfMjRokn_ww"),
]

# --------------------------------------------------------------------------
# Bilingual Telangana lexicon.
#
# This does the job LaBSE would do, without a 2 GB model on a CPU-only laptop:
# it collapses a Telugu headline and its English twin onto the same canonical
# entity, and it tells us whether a story is actually about Telangana.
#
# Built from 985 live Telangana headlines sampled on 9 Sep 2026, so the cast
# is the one actually in the news, not the one from memory.
#
# key -> (kind, [surface forms in en and te])
#   kind: person | place | org | topic
# --------------------------------------------------------------------------

LEXICON: dict[str, tuple[str, list[str]]] = {
    # ===================== people: government (Congress) =====================
    # No bare "reddy", "rao" or "kumar": they are among the commonest surnames
    # in the state and would match half the wire.
    "revanth_reddy": ("person", [
        "revanth reddy", "revanth", "cm revanth", "a revanth reddy",
        "రేవంత్ రెడ్డి", "రేవంత్",
    ]),
    "bhatti_vikramarka": ("person", [
        "bhatti vikramarka", "mallu bhatti", "bhatti", "deputy cm bhatti",
        "భట్టి విక్రమార్క", "భట్టి",
    ]),
    "uttam_kumar_reddy": ("person", ["uttam kumar reddy", "n uttam kumar", "ఉత్తమ్ కుమార్ రెడ్డి", "ఉత్తమ్"]),
    "komatireddy": ("person", ["komatireddy venkat reddy", "komatireddy", "కోమటిరెడ్డి"]),
    "ponnam_prabhakar": ("person", ["ponnam prabhakar", "ponnam", "పొన్నం ప్రభాకర్", "పొన్నం"]),
    "seethakka": ("person", ["seethakka", "danasari anasuya", "సీతక్క"]),
    "sridhar_babu": ("person", ["sridhar babu", "duddilla sridhar", "శ్రీధర్ బాబు"]),
    "damodar_rajanarsimha": ("person", ["damodar raja narasimha", "damodar rajanarsimha", "దామోదర రాజనర్సింహ"]),
    "tummala": ("person", ["tummala nageswara rao", "tummala", "తుమ్మల"]),
    "jupally": ("person", ["jupally krishna rao", "jupally", "జూపల్లి"]),
    "konda_surekha": ("person", ["konda surekha", "కొండా సురేఖ"]),
    "ponguleti": ("person", ["ponguleti srinivas reddy", "ponguleti", "పొంగులేటి"]),
    "vivek_venkatswamy": ("person", ["vivek venkatswamy", "g vivek", "వివేక్ వెంకటస్వామి"]),
    "vakiti_srihari": ("person", ["vakiti srihari", "వాకిటి శ్రీహరి"]),
    "adluri_laxman": ("person", ["adluri laxman", "అడ్లూరి లక్ష్మణ్"]),
    "srinivas_goud": ("person", ["srinivas goud", "v srinivas goud", "శ్రీనివాస్ గౌడ్"]),
    "mahesh_kumar_goud": ("person", ["mahesh kumar goud", "tpcc chief mahesh", "మహేష్ కుమార్ గౌడ్"]),
    "governor_tg": ("person", ["jishnu dev varma", "governor jishnu", "జిష్ణు దేవ్ వర్మ"]),
    # ===================== people: opposition BRS =====================
    "kcr": ("person", ["kcr", "k chandrashekar rao", "chandrashekhar rao", "chandrasekhar rao", "కేసీఆర్"]),
    "ktr": ("person", ["ktr", "kt rama rao", "k t rama rao", "కేటీఆర్"]),
    "harish_rao": ("person", ["harish rao", "t harish rao", "హరీశ్ రావు", "హరీష్ రావు"]),
    # Bare "కవిత" is the Telugu word for "poem": only the full names are safe.
    "kavitha": ("person", ["k kavitha", "kalvakuntla kavitha", "mlc kavitha", "కల్వకుంట్ల కవిత"]),
    # ===================== people: BJP and AIMIM =====================
    "kishan_reddy": ("person", ["kishan reddy", "g kishan reddy", "కిషన్ రెడ్డి"]),
    "bandi_sanjay": ("person", ["bandi sanjay", "బండి సంజయ్"]),
    "raja_singh": ("person", ["raja singh", "t raja singh", "రాజాసింగ్", "రాజా సింగ్"]),
    "eatala": ("person", ["eatala rajender", "etela rajender", "ఈటల రాజేందర్", "ఈటల"]),
    "dk_aruna": ("person", ["dk aruna", "d k aruna", "డీకే అరుణ"]),
    "owaisi": ("person", ["asaduddin owaisi", "owaisi", "ఒవైసీ", "అసదుద్దీన్ ఒవైసీ"]),
    "akbaruddin": ("person", ["akbaruddin owaisi", "akbaruddin", "అక్బరుద్దీన్"]),
    # ===================== people: national =====================
    "modi": ("person", ["narendra modi", "modi", "prime minister", "మోదీ", "ప్రధాని"]),
    "amit_shah": ("person", ["amit shah", "అమిత్ షా"]),
    "rahul_gandhi": ("person", ["rahul gandhi", "రాహుల్ గాంధీ"]),
    # ===================== people: Andhra Pradesh (the neighbour) ===========
    "chandrababu_naidu": ("person", ["chandrababu", "chandra babu", "cbn", "cm naidu", "చంద్రబాబు"]),
    "jagan": ("person", ["jagan", "ys jagan", "jagan mohan reddy", "జగన్"]),
    "pawan_kalyan": ("person", ["pawan kalyan", "పవన్ కళ్యాణ్", "పవన్"]),
    "lokesh": ("person", ["nara lokesh", "లోకేష్"]),
    # ===================== people: film & sport =====================
    "prabhas": ("person", ["prabhas", "ప్రభాస్"]),
    "mahesh_babu": ("person", ["mahesh babu", "మహేష్ బాబు", "మహేశ్ బాబు"]),
    "ntr_jr": ("person", ["jr ntr", "ntr", "tarak", "ఎన్టీఆర్", "తారక్"]),
    "ram_charan": ("person", ["ram charan", "రామ్ చరణ్"]),
    "allu_arjun": ("person", ["allu arjun", "bunny", "అల్లు అర్జున్"]),
    "chiranjeevi": ("person", ["chiranjeevi", "megastar", "చిరంజీవి", "మెగాస్టార్"]),
    "balakrishna": ("person", ["balakrishna", "balayya", "బాలకృష్ణ", "బాలయ్య"]),
    "nagarjuna": ("person", ["nagarjuna", "నాగార్జున"]),
    "vijay_deverakonda": ("person", ["vijay deverakonda", "విజయ్ దేవరకొండ"]),
    "rajamouli": ("person", ["rajamouli", "రాజమౌళి"]),
    "samantha": ("person", ["samantha", "సమంత"]),
    "rashmika": ("person", ["rashmika", "రష్మిక"]),
    "kohli": ("person", ["virat kohli", "kohli", "కోహ్లీ"]),
    "siraj": ("person", ["mohammed siraj", "siraj", "సిరాజ్"]),
    "rohit": ("person", ["rohit sharma", "రోహిత్ శర్మ"]),
    # ===================== places: the state and its capital ===============
    "telangana": ("place", ["telangana", "తెలంగాణ", "తెలంగాణా"]),
    "hyderabad": ("place", ["hyderabad", "hyd", "భాగ్యనగరం", "హైదరాబాద్"]),
    "secunderabad": ("place", ["secunderabad", "సికింద్రాబాద్"]),
    "cyberabad": ("place", ["cyberabad", "gachibowli", "hitec city", "madhapur", "సైబరాబాద్", "గచ్చిబౌలి", "మాదాపూర్"]),
    "jubilee_hills": ("place", ["jubilee hills", "banjara hills", "జూబ్లీహిల్స్", "బంజారాహిల్స్"]),
    "charminar": ("place", ["charminar", "old city", "చార్మినార్"]),
    "shamshabad": ("place", ["shamshabad", "rajiv gandhi international airport", "శంషాబాద్"]),
    # ===================== places: the 33 districts ========================
    "adilabad": ("place", ["adilabad", "ఆదిలాబాద్"]),
    "kothagudem": ("place", ["bhadradri kothagudem", "kothagudem", "కొత్తగూడెం"]),
    "bhadrachalam": ("place", ["bhadrachalam", "భద్రాచలం"]),
    "hanumakonda": ("place", ["hanumakonda", "hanamkonda", "హనుమకొండ"]),
    "jagtial": ("place", ["jagtial", "జగిత్యాల"]),
    "jangaon": ("place", ["jangaon", "జనగామ"]),
    "bhupalpally": ("place", ["jayashankar bhupalpally", "bhupalpally", "భూపాలపల్లి"]),
    "gadwal": ("place", ["jogulamba gadwal", "gadwal", "గద్వాల"]),
    "kamareddy": ("place", ["kamareddy", "కామారెడ్డి"]),
    "karimnagar": ("place", ["karimnagar", "కరీంనగర్"]),
    "khammam": ("place", ["khammam", "ఖమ్మం"]),
    "asifabad": ("place", ["komaram bheem asifabad", "asifabad", "ఆసిఫాబాద్"]),
    "mahabubabad": ("place", ["mahabubabad", "mahbubabad", "మహబూబాబాద్"]),
    "mahabubnagar": ("place", ["mahabubnagar", "mahbubnagar", "palamuru", "మహబూబ్‌నగర్", "పాలమూరు"]),
    "mancherial": ("place", ["mancherial", "మంచిర్యాల"]),
    "medak": ("place", ["medak", "మెదక్"]),
    "medchal": ("place", ["medchal", "malkajgiri", "మేడ్చల్", "మల్కాజ్‌గిరి"]),
    "mulugu": ("place", ["mulugu", "ములుగు"]),
    "nagarkurnool": ("place", ["nagarkurnool", "నాగర్‌కర్నూల్"]),
    "nalgonda": ("place", ["nalgonda", "నల్గొండ", "నల్లగొండ"]),
    "narayanpet": ("place", ["narayanpet", "నారాయణపేట"]),
    "nirmal": ("place", ["nirmal", "నిర్మల్"]),
    "nizamabad": ("place", ["nizamabad", "నిజామాబాద్"]),
    "peddapalli": ("place", ["peddapalli", "పెద్దపల్లి"]),
    "ramagundam": ("place", ["ramagundam", "రామగుండం"]),
    "sircilla": ("place", ["rajanna sircilla", "sircilla", "సిరిసిల్ల"]),
    "rangareddy": ("place", ["rangareddy", "ranga reddy", "రంగారెడ్డి"]),
    "sangareddy": ("place", ["sangareddy", "సంగారెడ్డి"]),
    "siddipet": ("place", ["siddipet", "సిద్దిపేట"]),
    "suryapet": ("place", ["suryapet", "సూర్యాపేట"]),
    "vikarabad": ("place", ["vikarabad", "వికారాబాద్"]),
    "wanaparthy": ("place", ["wanaparthy", "వనపర్తి"]),
    "warangal": ("place", ["warangal", "వరంగల్"]),
    "yadadri": ("place", ["yadadri", "bhuvanagiri", "yadagirigutta", "యాదాద్రి", "భువనగిరి"]),
    # ===================== places: landmarks, rivers, projects =============
    "kaleshwaram": ("place", ["kaleshwaram", "medigadda", "కాళేశ్వరం", "మేడిగడ్డ"]),
    "musi": ("place", ["musi river", "musi riverfront", "musi", "మూసీ"]),
    "godavari": ("place", ["godavari", "గోదావరి"]),
    "krishna_river": ("place", ["krishna river", "కృష్ణా నది"]),
    "nagarjuna_sagar": ("place", ["nagarjuna sagar", "నాగార్జునసాగర్"]),
    "srisailam": ("place", ["srisailam", "శ్రీశైలం"]),
    "medaram": ("place", ["medaram", "sammakka saralamma", "మేడారం", "సమ్మక్క సారలమ్మ"]),
    "basara": ("place", ["basara", "బాసర"]),
    "erravelli": ("place", ["erravelli", "ఎర్రవల్లి"]),
    "future_city": ("place", ["future city", "ఫ్యూచర్ సిటీ"]),
    # ===================== orgs =====================
    "brs": ("org", ["brs", "bharat rashtra samithi", "trs", "బీఆర్ఎస్", "బీఆర్‌ఎస్"]),
    "congress": ("org", ["congress", "tpcc", "కాంగ్రెస్"]),
    "bjp": ("org", ["bjp", "బీజేపీ", "భాజపా"]),
    "aimim": ("org", ["aimim", "mim", "majlis", "ఎంఐఎం", "మజ్లిస్"]),
    "tg_assembly": ("org", ["telangana assembly", "assembly session", "legislative council",
                            "శాసనసభ", "అసెంబ్లీ", "మండలి"]),
    "tg_cabinet": ("org", ["telangana cabinet", "state cabinet", "cabinet meeting", "క్యాబినెట్", "మంత్రివర్గం"]),
    "tg_high_court": ("org", ["telangana high court", "తెలంగాణ హైకోర్టు", "హైకోర్టు"]),
    "hydraa": ("org", ["hydraa", "hydra commissioner", "హైడ్రా"]),
    "ghmc": ("org", ["ghmc", "greater hyderabad municipal", "జీహెచ్ఎంసీ"]),
    "hmda": ("org", ["hmda", "హెచ్ఎండీఏ"]),
    "tgsrtc": ("org", ["tgsrtc", "tsrtc", "rtc", "ఆర్టీసీ"]),
    "tgpsc": ("org", ["tgpsc", "tspsc", "టీజీపీఎస్సీ", "టీఎస్‌పీఎస్సీ"]),
    "osmania": ("org", ["osmania university", "ఉస్మానియా"]),
    "kakatiya_university": ("org", ["kakatiya university", "కాకతీయ యూనివర్సిటీ"]),
    "acb": ("org", ["anti corruption bureau", "acb", "ఏసీబీ"]),
    "cbi": ("org", ["cbi", "సీబీఐ"]),
    "ed": ("org", ["enforcement directorate", "ఈడీ"]),
    "imd": ("org", ["imd", "met department", "weather department", "వాతావరణ శాఖ"]),
    "metro_rail": ("org", ["hyderabad metro", "metro rail", "మెట్రో రైల్"]),
    # Andhra Pradesh bodies, so a cross-border story is recognised as theirs.
    "tdp": ("org", ["tdp", "telugu desam", "టీడీపీ", "తెలుగుదేశం"]),
    "ysrcp": ("org", ["ysrcp", "ysr congress", "వైసీపీ"]),
    "janasena": ("org", ["jana sena", "janasena", "జనసేన"]),
    "ttd": ("org", ["ttd", "tirumala tirupati devasthanams", "టీటీడీ"]),
    # ===================== topics =====================
    "flood": ("topic", ["flood", "floods", "inundation", "వరద", "వరదలు", "ముంపు"]),
    "rain": ("topic", ["rain", "rains", "rainfall", "downpour", "వర్షం", "వర్షాలు", "వాన"]),
    "cyclone": ("topic", ["cyclone", "depression", "low pressure", "తుఫాన్", "అల్పపీడనం"]),
    "heatwave": ("topic", ["heatwave", "heat wave", "వడగాలులు", "ఎండలు"]),
    "results": ("topic", ["result", "results", "merit list", "rank", "ఫలితాలు", "ర్యాంక్"]),
    "exam": ("topic", ["exam", "exams", "group 1", "group 2", "eamcet", "neet", "పరీక్ష", "పరీక్షలు"]),
    "jobs": ("topic", ["recruitment", "notification", "vacancy", "నోటిఫికేషన్", "ఉద్యోగాలు"]),
    "arrest": ("topic", ["arrest", "arrested", "remand", "custody", "అరెస్ట్", "రిమాండ్"]),
    "murder": ("topic", ["murder", "killed", "death", "హత్య", "మృతి", "మరణం"]),
    "accident": ("topic", ["accident", "crash", "collision", "ప్రమాదం", "రోడ్డు ప్రమాదం"]),
    "protest": ("topic", ["protest", "dharna", "strike", "bandh", "ధర్నా", "ఆందోళన", "బంద్"]),
    "court": ("topic", ["supreme court", "verdict", "bail", "సుప్రీంకోర్టు", "బెయిల్"]),
    "cinema": ("topic", ["movie", "film", "box office", "teaser", "trailer", "ott", "సినిమా", "చిత్రం", "టీజర్"]),
    "cricket": ("topic", ["cricket", "ipl", "match", "క్రికెట్", "మ్యాచ్"]),
    "power_cut": ("topic", ["power cut", "electricity tariff", "కరెంట్", "విద్యుత్"]),
    "farmer": ("topic", ["farmer", "farmers", "crop", "paddy", "rythu", "రైతు", "రైతులు", "పంట"]),
    "gold_price": ("topic", ["gold rate", "gold price", "బంగారం ధర"]),
    "local_body": ("topic", ["local body elections", "panchayat elections", "municipal elections",
                             "స్థానిక ఎన్నికలు", "పంచాయతీ ఎన్నికలు"]),
    "sir_rolls": ("topic", ["special intensive revision", "sir electoral", "electoral rolls",
                            "ఓటర్ల జాబితా"]),
    "phone_tapping": ("topic", ["phone tapping", "ఫోన్ ట్యాపింగ్"]),
    "formula_e": ("topic", ["formula e", "ఫార్ములా ఈ"]),
    "dharani": ("topic", ["dharani portal", "bhu bharati", "ధరణి", "భూ భారతి"]),
    "rythu_bharosa": ("topic", ["rythu bharosa", "rythu bandhu", "రైతు భరోసా", "రైతు బంధు"]),
    "gruha_jyothi": ("topic", ["gruha jyothi", "mahalakshmi scheme", "indiramma", "గృహజ్యోతి", "ఇందిరమ్మ"]),
    "reservations": ("topic", ["bc reservation", "reservations", "రిజర్వేషన్", "బీసీ రిజర్వేషన్లు"]),
    "bathukamma": ("topic", ["bathukamma", "బతుకమ్మ"]),
    "bonalu": ("topic", ["bonalu", "బోనాలు"]),
    "ganesh": ("topic", ["ganesh immersion", "vinayaka", "khairatabad ganesh", "గణేష్", "వినాయక"]),
}

# Named in local news constantly without the story being about this state.
NATIONAL_KEYS = {"modi", "amit_shah", "rahul_gandhi", "kohli", "rohit", "siraj",
                 "bjp", "congress", "imd", "cbi", "ed"}
# Telugu-sphere but not Telangana: Andhra Pradesh politics, and film stars
# whose stories are Telugu-reader interest rather than state news.
NEIGHBOUR_KEYS = {"chandrababu_naidu", "jagan", "pawan_kalyan", "lokesh",
                  "tdp", "ysrcp", "janasena", "ttd",
                  "prabhas", "mahesh_babu", "ntr_jr", "ram_charan", "allu_arjun",
                  "chiranjeevi", "balakrishna", "nagarjuna", "vijay_deverakonda",
                  "rajamouli", "samantha", "rashmika"}
NEIGHBOUR_LABEL = "Telugu"

# Words too common to be worth clustering on.
STOPWORDS = set("""
a an the and or of in on at to for from with by is are was were be been being as
that this these those it its his her their our your my he she they we you i not
no yes new latest news update updates says said say after before over under into
telangana hyderabad india indian live video watch photos photo full big top
కోసం మరియు అని ఒక ఈ ఆ లో కు తో పై నుంచి వరకు గా చేసిన చేసే అయిన ఉన్న
""".split())

# --------------------------------------------------------------------------
# Scoring weights. Tune here after a week of watching the board.
# --------------------------------------------------------------------------

WEIGHTS = {
    "trend": 0.32,          # matches a live Google search trend
    "acceleration": 0.20,   # coverage rate rising vs its own recent baseline
    "corroboration": 0.18,  # independent outlets carrying it
    "prominence": 0.12,     # how high Google News ranks it on its front page
    "velocity": 0.10,       # raw items per hour
    "freshness": 0.08,      # decay
}

# Locality multiplier applied to the weighted sum. A clearly-local story scores
# at full strength; everything else is marked down from there, so the top of the
# board cannot saturate at 100.
LOCALITY_STRONG = 1.00   # Telangana place, politician or institution named
LOCALITY_WEAK = 0.55     # Telugu-sphere but not clearly Telangana
LOCALITY_NONE = 0.18     # no local signal at all

# Inside a two-hour window a 150-minute half-life barely separates anything.
FRESHNESS_HALFLIFE_MIN = 40.0

# Alert thresholds
ALERT_SCORE = int(os.environ.get("RADAR_ALERT_SCORE", "62"))
ALERT_MIN_OUTLETS = 2
ALERT_MAX_AGE_MIN = 100
ALERT_COOLDOWN_MIN = 90  # do not re-alert the same cluster within this window

# --------------------------------------------------------------------------
# Optional extras (all off unless you set the env var)
# --------------------------------------------------------------------------

# The key that unlocks the *published* page. Set in the publish service unit,
# never in this file — anything here is on GitHub. Empty means publish in the
# clear. The local board on 127.0.0.1 is never locked: it is already private.
PAGE_KEY = os.environ.get("RADAR_PAGE_KEY", "").strip()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

TELEGRAM_TOKEN = os.environ.get("RADAR_TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("RADAR_TELEGRAM_CHAT", "").strip()

DB_PATH = os.environ.get(
    "RADAR_DB",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "radar.db"),
)

SERVER_HOST = os.environ.get("RADAR_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("RADAR_PORT", "8788"))
