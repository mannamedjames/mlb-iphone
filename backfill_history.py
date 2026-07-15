#!/usr/bin/env python3
"""
One-time backfill — reconstructs the matchup-results DB for this season.

For every date from SEASON_START+30d to yesterday, recomputes what the
30-day and 7-day opponent splits (wOBA, K%, ranks, per handedness) would
have been ON that date, then joins them to that date's ACTUAL starting
pitchers and their real pitching lines from boxscores.

Also ingests starts from the first 30 days (with null ranks) purely as
baseline material for rolling-form calculations in the dashboard.

Notes on honesty of the reconstruction:
- Uses actual starters, not that morning's probable starters. These are
  the same person the overwhelming majority of the time; scratched
  probables are the one thing this can't recover.
- Ranks are recomputed from the same Statcast methodology the live
  pipeline uses, so past and future rows are directly comparable.

Heavy: one full-season Statcast pull + ~1 boxscore fetch per game.
Expect several minutes on GitHub Actions. Run once via the manual
backfill workflow; safe to re-run (upserts, never duplicates).
"""

import json
import sys
import time
import urllib.request
import urllib.error
from datetime import date, timedelta
from pathlib import Path

from matchup_db import load_db, save_db, upsert_pregame, innings_to_decimal

API = "https://statsapi.mlb.com/api/v1"
USER_AGENT = "mlb-backfill/1.0 (personal use)"
SEASON_START = date(2026, 3, 26)      # adjust if opening day differed
RANKED_FROM = SEASON_START + timedelta(days=30)

ABBR_CANON = {"OAK": "ATH", "AZ": "ARI"}
def canon(a): return ABBR_CANON.get(a, a)


def fetch_json(url, retries=3, timeout=25):
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


def compute_splits_for_date(pa, target, short_days=7, long_days=30):
    """Splits as they would have stood on `target` morning (window ends
    the day BEFORE target). Returns {'30': {...}, '7': {...}} keyed
    RHP/LHP -> team -> {woba, k_pct, woba_rank, k_pct_rank}."""
    import pandas as pd
    out = {}
    for label, days in (("30", long_days), ("7", short_days)):
        lo = str(target - timedelta(days=days))
        hi = str(target - timedelta(days=1))
        win = pa[(pa["game_date"] >= lo) & (pa["game_date"] <= hi)]
        block = {"RHP": {}, "LHP": {}}
        for hand, key in (("R", "RHP"), ("L", "LHP")):
            sub = win[win["p_throws"] == hand]
            for team, g in sub.groupby("batting_team"):
                denom = g["woba_denom"].sum()
                if denom <= 0:
                    continue
                woba = g["woba_value"].sum() / denom
                pa_n = len(g)
                k_n = g["events"].isin(["strikeout", "strikeout_double_play"]).sum()
                block[key][team] = {
                    "woba": round(float(woba), 3),
                    "k_pct": round(float(k_n / pa_n * 100), 1) if pa_n else 0.0,
                }
            ranked_w = sorted(block[key].items(), key=lambda kv: kv[1]["woba"])
            for i, (t, v) in enumerate(ranked_w, 1):
                v["woba_rank"] = i
            ranked_k = sorted(block[key].items(), key=lambda kv: kv[1]["k_pct"], reverse=True)
            for i, (t, v) in enumerate(ranked_k, 1):
                v["k_pct_rank"] = i
        out[label] = block
    return out


def starters_for_game(game_pk, hand_cache):
    """Actual starters + their lines from the boxscore. Also resolves each
    pitcher's throwing hand via the people API (cached)."""
    try:
        box = fetch_json(f"{API}/game/{game_pk}/boxscore")
    except Exception as e:
        print(f"  ! boxscore {game_pk} failed: {e}", file=sys.stderr)
        return {}
    result = {}
    for side in ("home", "away"):
        players = box.get("teams", {}).get(side, {}).get("players", {})
        team_abbr = box.get("teams", {}).get(side, {}).get("team", {}).get("abbreviation", "")
        for p in players.values():
            st = p.get("stats", {}).get("pitching", {})
            if st and st.get("gamesStarted") in (1, "1"):
                pid = p.get("person", {}).get("id")
                if pid not in hand_cache:
                    try:
                        person = fetch_json(f"{API}/people/{pid}")
                        hand_cache[pid] = person["people"][0].get("pitchHand", {}).get("code")
                    except Exception:
                        hand_cache[pid] = None
                result[side] = {
                    "pid": pid,
                    "name": p.get("person", {}).get("fullName"),
                    "hand": hand_cache[pid],
                    "team": team_abbr,
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
    return result


def main():
    try:
        from pybaseball import statcast
    except ImportError:
        print("pip install pybaseball pandas numpy first", file=sys.stderr)
        sys.exit(1)

    yesterday = date.today() - timedelta(days=1)
    print(f"Statcast pull {SEASON_START} -> {yesterday} (several minutes)...")
    df = statcast(start_dt=str(SEASON_START), end_dt=str(yesterday))
    df = df.reset_index(drop=True)
    pa = df[df["events"].notna()].copy()
    pa["batting_team"] = pa.apply(
        lambda r: r["away_team"] if r["inning_topbot"] == "Top" else r["home_team"], axis=1)
    pa["batting_team"] = pa["batting_team"].apply(canon)
    pa["game_date"] = pa["game_date"].astype(str)
    print(f"{len(pa)} plate appearances loaded.")

    # Per-pitcher L/R exposure per game (opposing lineup handedness).
    import pandas as pd
    stand_share = (
        pa.groupby(["game_pk", "pitcher"])["stand"]
        .apply(lambda s: round(float((s == "L").mean()), 3))
        .to_dict()
    )

    rows = load_db()
    hand_cache = {}
    d = SEASON_START
    n_days = 0
    while d <= yesterday:
        splits = compute_splits_for_date(pa, d) if d >= RANKED_FROM else None
        try:
            sched = fetch_json(f"{API}/schedule?sportId=1&date={d}")
        except Exception as e:
            print(f"  ! schedule {d} failed: {e}", file=sys.stderr)
            d += timedelta(days=1)
            continue
        for day in sched.get("dates", []):
            for g in day.get("games", []):
                if g.get("status", {}).get("abstractGameState") != "Final":
                    continue
                game_pk = g.get("gamePk")
                starters = starters_for_game(game_pk, hand_cache)
                teams = g.get("teams", {})
                for side in ("home", "away"):
                    s = starters.get(side)
                    if not s or not s.get("name"):
                        continue
                    opp_side = "away" if side == "home" else "home"
                    opp_abbr = canon(teams.get(opp_side, {}).get("team", {}).get("abbreviation", ""))
                    row = {
                        "gamePk": game_pk,
                        "date": str(d),
                        "pitcherId": f"{s['name']}|{canon(s['team'])}",
                        "pitcherName": s["name"],
                        "hand": s["hand"],
                        "team": canon(s["team"]),
                        "opponent": opp_abbr,
                        "isHome": side == "home",
                        "woba30Rank": None, "woba7Rank": None, "kPct30Rank": None,
                        "woba30": None, "woba7": None, "kPct30": None,
                        "ip": s["ip"], "hits": s["hits"], "er": s["er"],
                        "bb": s["bb"], "k": s["k"], "hr": s["hr"],
                        "pitches": s["pitches"], "battersFaced": s["battersFaced"],
                        "oppHandPctLeft": stand_share.get((game_pk, s["pid"])),
                        "final": True,
                    }
                    if splits and s.get("hand") in ("R", "L"):
                        hk = "RHP" if s["hand"] == "R" else "LHP"
                        t30 = splits["30"][hk].get(opp_abbr)
                        t7 = splits["7"][hk].get(opp_abbr)
                        if t30:
                            row.update({
                                "woba30Rank": t30["woba_rank"], "woba30": t30["woba"],
                                "kPct30Rank": t30["k_pct_rank"], "kPct30": t30["k_pct"],
                            })
                        if t7:
                            row.update({"woba7Rank": t7["woba_rank"], "woba7": t7["woba"]})
                    rows = upsert_pregame(rows, row)
                time.sleep(0.03)
        n_days += 1
        if n_days % 10 == 0:
            print(f"  ...through {d} ({len(rows)} rows)")
            save_db(rows)   # checkpoint
        d += timedelta(days=1)

    save_db(rows)
    ranked = sum(1 for r in rows if r.get("woba30Rank") is not None)
    print(f"Done. {len(rows)} total rows, {ranked} with rankings.")


if __name__ == "__main__":
    main()
