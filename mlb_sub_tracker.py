#!/usr/bin/env python3
"""
MLB Substitution Tracker — daily Mac job (zero third-party dependencies).

What it does
------------
Looks at the last 30 calendar days of completed MLB games and builds two
leaderboards:

  * Top 5 batters by number of DISTINCT games they were SUBBED OUT of
    (started in the lineup, then were replaced / exited the game).
  * Top 5 batters by number of DISTINCT games they were SUBBED IN to
    (entered as a pinch hitter, pinch runner, or defensive replacement).

Each row also includes:
  * pctStarted — of their team's completed games in the window, what
    percentage did this player start. (started / team_games_in_window * 100)
  * teamId, teamName, team (abbreviation) — for display, including looking
    up a team logo on the phone side.

Tiebreakers (both lists): more games STARTED in the window wins; if still
tied, more HITS in the window wins.

How substitution is detected
----------------------------
Each hitter in a boxscore has a 3-digit `battingOrder` string. The hundreds
digit is the lineup slot (1-9); the last two digits are the sub index.
  "400" -> slot 4, sub index 0  => STARTER
  "401" -> slot 4, sub index 1  => first replacement in that slot
A starter (sub index 0) who shares a slot with a higher sub index was replaced
=> subbed out. Anyone with sub index > 0 entered as a sub => subbed in. A
player who merely changes fielding position keeps the same batting-order entry,
so position shifts are NOT counted as substitutions.

Output
------
Writes a small compiled JSON to your Scriptable iCloud folder (auto-detected),
which your phone reads. Per-game boxscores are cached locally on the Mac so
each daily run only fetches the new day's games.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import date, timedelta
from pathlib import Path

API = "https://statsapi.mlb.com/api/v1"
WINDOW_DAYS = 30
# Game types to include: R=regular season + postseason rounds. (Excludes
# spring training, exhibition, and the All-Star game.)
INCLUDE_GAME_TYPES = {"R", "F", "D", "L", "W"}
CACHE_DIR = Path.home() / ".mlb_sub_tracker" / "cache"
OUTPUT_FILENAME = "mlb_sub_tracker.json"
USER_AGENT = "mlb-sub-tracker/1.0 (personal use)"


# ---------------------------------------------------------------- networking
def fetch_json(url, retries=3, timeout=30):
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last_err}")


# -------------------------------------------------------------- output location
def resolve_output_dir():
    from gh_output import resolve_output_dir as _r
    return _r()


# ------------------------------------------------------------------- boxscores
def get_boxscore(game_pk):
    """Return a boxscore dict, using the local cache for completed games."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{game_pk}.json"
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text())
        except json.JSONDecodeError:
            pass  # corrupt cache, refetch
    data = fetch_json(f"{API}/game/{game_pk}/boxscore")
    cache_file.write_text(json.dumps(data))
    return data


def team_info_map():
    """Returns {team_id: {"abbr": "...", "name": "..."}}"""
    data = fetch_json(f"{API}/teams?sportId=1")
    out = {}
    for t in data.get("teams", []):
        out[t["id"]] = {
            "abbr": t.get("abbreviation") or t.get("teamCode", "").upper(),
            "name": t.get("name") or t.get("teamName", ""),
        }
    return out


# ----------------------------------------------------------------- core logic
def process_game(game_pk, players, team_info, team_games):
    """Update the players accumulator from one game's boxscore."""
    box = get_boxscore(game_pk)
    teams = box.get("teams", {})
    for side in ("home", "away"):
        side_data = teams.get(side, {})
        team_id = side_data.get("team", {}).get("id")
        info = team_info.get(team_id, {})
        team_abbr = info.get("abbr", "")
        team_name = info.get("name", "")
        roster = side_data.get("players", {})

        if team_id is not None:
            team_games[team_id] = team_games.get(team_id, 0) + 1

        # First pass: find the max sub index present in each lineup slot.
        slot_max = {}
        parsed = []
        for pdata in roster.values():
            bo = pdata.get("battingOrder")
            if not bo:
                continue  # not in the batting order (e.g. a non-hitting pitcher)
            try:
                bo_int = int(bo)
            except (TypeError, ValueError):
                continue
            slot = bo_int // 100
            sub_idx = bo_int % 100
            slot_max[slot] = max(slot_max.get(slot, 0), sub_idx)
            person = pdata.get("person", {})
            hits = (
                pdata.get("stats", {})
                .get("batting", {})
                .get("hits", 0)
            ) or 0
            parsed.append((person.get("id"), person.get("fullName"), slot,
                           sub_idx, hits))

        # Second pass: classify each hitter.
        for pid, name, slot, sub_idx, hits in parsed:
            if pid is None:
                continue
            rec = players.setdefault(pid, {
                "name": name, "team": team_abbr, "teamId": team_id,
                "teamName": team_name,
                "subbed_out": set(), "subbed_in": set(),
                "started": set(), "hits": 0,
            })
            rec["name"] = name
            if team_id is not None:
                rec["team"] = team_abbr
                rec["teamId"] = team_id
                rec["teamName"] = team_name
            rec["hits"] += hits

            if sub_idx == 0:
                rec["started"].add(game_pk)
                if slot_max.get(slot, 0) > 0:        # a sub took this slot later
                    rec["subbed_out"].add(game_pk)
            else:
                rec["subbed_in"].add(game_pk)


def build_leaderboard(players, key, team_games):
    rows = []
    for pid, rec in players.items():
        team_id = rec.get("teamId")
        games_for_team = team_games.get(team_id, 0)
        started = len(rec["started"])
        pct_started = (
            round(100 * started / games_for_team) if games_for_team else None
        )
        rows.append({
            "playerId": pid,
            "name": rec["name"],
            "team": rec["team"],
            "teamId": team_id,
            "teamName": rec.get("teamName", ""),
            "games": len(rec[key]),
            "started": started,
            "pctStarted": pct_started,
            "hits": rec["hits"],
        })
    rows = [r for r in rows if r["games"] > 0]
    rows.sort(key=lambda r: (r["games"], r["started"], r["hits"]), reverse=True)
    top = rows[:5]
    for i, r in enumerate(top, 1):
        r["rank"] = i
    return top


# ------------------------------------------------------------------------ main
def main():
    today = date.today()
    start = today - timedelta(days=WINDOW_DAYS)
    print(f"Window: {start} -> {today}")

    sched = fetch_json(
        f"{API}/schedule?sportId=1&startDate={start}&endDate={today}"
    )
    game_pks = []
    for day in sched.get("dates", []):
        for g in day.get("games", []):
            if g.get("gameType") not in INCLUDE_GAME_TYPES:
                continue
            state = g.get("status", {}).get("abstractGameState")
            if state != "Final":
                continue
            game_pks.append(g["gamePk"])
    print(f"Completed games in window: {len(game_pks)}")

    team_info = team_info_map()
    players = {}
    team_games = {}
    for i, pk in enumerate(game_pks, 1):
        try:
            process_game(pk, players, team_info, team_games)
        except Exception as e:                       # one bad game shouldn't kill the run
            print(f"  ! skipped game {pk}: {e}", file=sys.stderr)
        if i % 25 == 0:
            print(f"  processed {i}/{len(game_pks)}")
        time.sleep(0.05)                             # be polite to the API

    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M"),
        "window_start": str(start),
        "window_end": str(today),
        "games_processed": len(game_pks),
        "subbed_out": build_leaderboard(players, "subbed_out", team_games),
        "subbed_in": build_leaderboard(players, "subbed_in", team_games),
    }

    out_dir = resolve_output_dir()
    out_path = out_dir / OUTPUT_FILENAME
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {out_path}")
    print("\nTop subbed OUT:")
    for r in payload["subbed_out"]:
        pct = f"{r['pctStarted']}%" if r["pctStarted"] is not None else "n/a"
        print(f"  {r['rank']}. {r['name']} ({r['team']}) — {r['games']} games "
              f"[started {r['started']} = {pct}, hits {r['hits']}]")
    print("Top subbed IN:")
    for r in payload["subbed_in"]:
        pct = f"{r['pctStarted']}%" if r["pctStarted"] is not None else "n/a"
        print(f"  {r['rank']}. {r['name']} ({r['team']}) — {r['games']} games "
              f"[started {r['started']} = {pct}, hits {r['hits']}]")


if __name__ == "__main__":
    main()
