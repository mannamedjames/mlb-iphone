#!/usr/bin/env python3
"""
Pregame capture — run right after mlb_matchups.py in the same workflow.

Reads the freshly-written data/mlb_matchups.json (today's slate with ranks
already computed) and upserts one pregame row per confirmed starter into
the results DB. Running multiple times a day is safe: rows are keyed on
(gamePk, pitcherId) and re-upserting just refreshes the ranks, which is
what we want if a probable starter or the rankings shift during the day.
"""

import json
import sys
from pathlib import Path

from matchup_db import load_db, save_db, upsert_pregame

MATCHUPS_PATH = Path(__file__).parent / "data" / "mlb_matchups.json"


def main():
    if not MATCHUPS_PATH.exists():
        print("No mlb_matchups.json found — run mlb_matchups.py first.", file=sys.stderr)
        sys.exit(1)

    data = json.loads(MATCHUPS_PATH.read_text())
    rows = load_db()
    added = 0

    for g in data.get("games", []):
        for side_key, opp_key in (("home", "away"), ("away", "home")):
            side = g[side_key]
            opp = g[opp_key]
            s = side.get("starter", {})
            if not s.get("confirmed") or not s.get("name"):
                continue
            splits = s.get("oppSplits") or {}
            row = {
                "gamePk": g.get("gamePk"),
                "date": (g.get("gameTime") or "")[:10],
                "pitcherId": None,   # filled below if derivable; boxscore fill also matches by name
                "pitcherName": s.get("name"),
                "hand": s.get("hand"),
                "team": side.get("teamAbbr"),
                "opponent": opp.get("teamAbbr"),
                "isHome": side_key == "home",
                "woba30Rank": splits.get("woba30Rank"),
                "woba7Rank": splits.get("woba7Rank"),
                "kPct30Rank": splits.get("kPct30Rank"),
                "woba30": splits.get("woba30"),
                "woba7": splits.get("woba7"),
                "kPct30": splits.get("kPct30"),
            }
            # matchup JSON doesn't carry pitcher ids; use name+game as key
            # surrogate: derive a stable pseudo-id so upserts still match.
            row["pitcherId"] = f"{row['pitcherName']}|{row['team']}"
            rows = upsert_pregame(rows, row)
            added += 1

    save_db(rows)
    print(f"Captured/updated {added} pregame rows. DB now has {len(rows)} rows.")


if __name__ == "__main__":
    main()
