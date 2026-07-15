#!/usr/bin/env python3
"""
Postgame fill — run in the same workflow after capture_matchups.py.

Finds DB rows whose game date is in the past and actuals aren't filled,
fetches each game's boxscore once, and fills the starting pitchers' actual
lines (IP, H, ER, BB, K, HR, pitches, batters faced). Matches rows to
boxscore starters by pitcher name + team side, since pregame rows carry a
name-based surrogate id.
"""

import json
import sys
import time
import urllib.request
import urllib.error
from datetime import date, datetime
from pathlib import Path

from matchup_db import load_db, save_db, innings_to_decimal

API = "https://statsapi.mlb.com/api/v1"
USER_AGENT = "mlb-fill-results/1.0 (personal use)"


def fetch_json(url, retries=3, timeout=20):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last = e
            time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"fetch failed {url}: {last}")


def extract_starters(box):
    """Returns {'home': {...line}, 'away': {...line}} for each side's
    starting pitcher (the pitcher with gamesStarted == 1 in this game)."""
    out = {}
    for side in ("home", "away"):
        players = box.get("teams", {}).get(side, {}).get("players", {})
        for p in players.values():
            st = p.get("stats", {}).get("pitching", {})
            if not st:
                continue
            if st.get("gamesStarted") in (1, "1"):
                out[side] = {
                    "name": p.get("person", {}).get("fullName"),
                    "ip": innings_to_decimal(st.get("inningsPitched")),
                    "hits": st.get("hits"),
                    "er": st.get("earnedRuns"),
                    "bb": st.get("baseOnBalls"),
                    "k": st.get("strikeOuts"),
                    "hr": st.get("homeRuns"),
                    "pitches": st.get("numberOfPitches") or st.get("pitchesThrown"),
                    "battersFaced": st.get("battersFaced"),
                }
                break
    return out


def game_is_final(game_pk):
    try:
        g = fetch_json(f"{API}/game/{game_pk}/boxscore")
        return g
    except Exception:
        return None


def main():
    rows = load_db()
    today = str(date.today())
    pending = [r for r in rows if not r.get("final") and (r.get("date") or "9999") < today]
    if not pending:
        print("No pending rows to fill.")
        return

    by_game = {}
    for r in pending:
        by_game.setdefault(r["gamePk"], []).append(r)

    filled = 0
    for game_pk, game_rows in by_game.items():
        box = game_is_final(game_pk)
        if not box:
            continue
        starters = extract_starters(box)
        for r in game_rows:
            side = "home" if r.get("isHome") else "away"
            line = starters.get(side)
            if not line or not line.get("name"):
                continue
            # Match by name — guards against the probable starter having
            # been scratched for someone else (in which case the pregame
            # signal never applied and the row stays unfilled/excluded).
            if line["name"] != r.get("pitcherName"):
                continue
            r.update({k: v for k, v in line.items() if k != "name"})
            r["final"] = True
            filled += 1
        time.sleep(0.05)

    save_db(rows)
    print(f"Filled {filled} rows across {len(by_game)} games. "
          f"{sum(1 for r in rows if not r.get('final'))} still pending.")


if __name__ == "__main__":
    main()
