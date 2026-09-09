"""Regression tests for the matching layer.

    python3 tests/test_matching.py

These are the judgement calls the radar gets wrong most expensively: merging
two unrelated stories about the same politician, or failing to merge a Telugu
headline with its English twin.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from radar import lexicon as L  # noqa: E402

MERGE_CASES = [
    # (headline a, headline b, should they be one story?)
    ("Telangana govt announces Rythu Bharosa for farmers",
     "Telangana government announces farmer support under Rythu Bharosa", True),
    ("BRS MLAs suspended from Telangana Assembly",
     "అసెంబ్లీ నుంచి బీఆర్ఎస్ ఎమ్మెల్యేల సస్పెన్షన్", True),
    ("KTR slams Congress over Musi riverfront project",
     "కేటీఆర్: మూసీ ప్రాజెక్టుపై కాంగ్రెస్‌కు ఫైర్", True),
    ("Heavy rains lash Hyderabad, IMD issues warning",
     "Hyderabad records heavy rainfall as IMD warns", True),
    ("Revanth Reddy to visit Warangal today",
     "రేవంత్ రెడ్డి వరంగల్ పర్యటన", True),
    # Same person, different story — must stay apart.
    ("Revanth Reddy chairs cabinet meeting in Hyderabad",
     "KTR tours Karimnagar district", False),
    ("HYDRAA razes illegal structures at Jubilee Hills",
     "Hyderabad Metro phase two gets approval", False),
    ("Kaleshwaram commission summons former minister",
     "Bathukamma celebrations begin across Telangana", False),
]

LOCALITY_CASES = [
    # Telangana: place, politician, institution — in either script.
    ("Revanth Reddy chairs cabinet meeting", "TG"),
    ("HYDRAA demolishes structures near Musi", "TG"),
    ("BRS MLAs suspended from Assembly", "TG"),
    ("Warangal farmers march to collectorate", "TG"),
    ("మంత్రి పొన్నం ప్రభాకర్ సమీక్ష", "TG"),
    ("TGPSC releases Group 1 notification", "TG"),
    ("Owaisi speaks in Lok Sabha on Hyderabad", "TG"),
    # Andhra Pradesh and the film world: Telugu-sphere, not Telangana news.
    ("Chandrababu Naidu reviews Polavaram works", "Telugu"),
    ("Pawan Kalyan tours Pithapuram", "Telugu"),
    ("Prabhas' next film gets a release date", "Telugu"),
    # National.
    ("Kohli century seals series for India", "wider"),
    ("Amit Shah reviews security in Delhi", "wider"),
    # Topic words alone must not make something local news.
    ("JKM vs TKR Caribbean Premier League wicket", "wider"),
    ("Manchester United sign new striker", "wider"),
]

TREND_CASES = [
    ("కేటీఆర్", "KTR slams government over Musi project", True),
    ("రేవంత్ రెడ్డి", "Revanth Reddy launches Rythu Bharosa in Warangal", True),
    ("hydraa", "HYDRAA razes structures at Jubilee Hills", True),
    ("కేటీఆర్", "Revanth Reddy chairs cabinet meeting", False),
    # A common surname must not tie a query to every story that shares it:
    # "reddy" appears in half the Telangana cabinet.
    ("rohan reddy", "Revanth Reddy chairs cabinet meeting", False),
]


def main() -> int:
    failures = 0

    for a, b, expected in MERGE_CASES:
        score = L.similarity(a, b)
        got = score >= L.MERGE_THRESHOLD
        if got != expected:
            failures += 1
            print(f"FAIL merge={got} want={expected} ({score:.3f})\n  {a}\n  {b}")

    for headline, expected in LOCALITY_CASES:
        _, label = L.locality(L.entities(headline))
        if label != expected:
            failures += 1
            print(f"FAIL locality={label} want={expected}\n  {headline}")

    for query, headline, expected in TREND_CASES:
        got = L.matches_trend(query, headline) >= 0.55
        if got != expected:
            failures += 1
            print(f"FAIL trend={got} want={expected}\n  {query} / {headline}")

    total = len(MERGE_CASES) + len(LOCALITY_CASES) + len(TREND_CASES)
    print(f"{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
