#!/usr/bin/env python3
"""
MLB Daily Matchups — lightweight job (zero third-party dependencies).

Run several times a day. Pitcher stats are only re-fetched the FIRST time
a pitcher is seen each day; later same-day runs just re-check the
probable-starter list and reuse cached stats for anyone unchanged.

Requires team_splits_cache.json to already exist (written once daily by
mlb_team_splits.py).

avgIpPerOuting: computed from the pitcher's game log, only averaging
innings over games actually flagged as a start (gamesStarted==1) — not
total season innings divided by total starts, which would be skewed by
any relief outings. isOpener is set when that average is <= 2.0 IP.

Team abbreviation note: this script and mlb_team_splits.py BOTH apply the
same ABBR_CANON map before matching team abbreviations between the two
data sources (Stats API vs Statcast), since canonicalizing only one side
doesn't help if they disagree on which abbreviation a team uses.

Weather: best-effort, from the live game feed. Pregame forecasts for
games far in the future are sometimes sparse — this degrades to null
rather than guessing, and only ever shows up in the in-app view, never
the widget.

Output: mlb_matchups.json, written to the Scriptable iCloud folder.
"""

import json
import sys
import time
import urllib.request
import urllib.error
from datetime import date
from pathlib import Path

API = "https://statsapi.mlb.com/api/v1"
LIVE_API = "https://statsapi.mlb.com/api/v1.1"
CACHE_DIR = Path.home() / ".mlb_sub_tracker"
TEAM_SPLITS_PATH = CACHE_DIR / "team_splits_cache.json"
STATE_PATH = CACHE_DIR / "matchup_state.json"
OUTPUT_FILENAME = "mlb_matchups.json"
USER_AGENT = "mlb-matchups/1.0 (personal use)"
OPENER_IP_THRESHOLD = 2.0

# Must match the dict in mlb_team_splits.py.
ABBR_CANON = {
    "OAK": "ATH",
    "AZ": "ARI",
}


def canon(abbr):
    return ABBR_CANON.get(abbr, abbr)


def fetch_json(url, retries=3, timeout=20):
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = e
            time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last_err}")


def resolve_output_dir():
    from gh_output import resolve_output_dir as _r
    return _r()


def innings_to_decimal(ip_str):
    if not ip_str:
        return 0.0
    parts = str(ip_str).split(".")
    whole = int(parts[0]) if parts[0] else 0
    outs = int(parts[1]) if len(parts) > 1 and parts[1] else 0
    return whole + outs / 3.0


def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(state):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state))


def fetch_starts_avg_ip(pid, season):
    try:
        log = fetch_json(
            f"{API}/people/{pid}/stats?stats=gameLog&group=pitching&season={season}"
        )
        splits = log.get("stats", [{}])[0].get("splits", [])
    except Exception as e:
        print(f"  ! couldn't fetch gameLog for {pid}: {e}", file=sys.stderr)
        return None

    starts_ip = []
    for sp in splits:
        s = sp.get("stat", {})
        gs = s.get("gamesStarted")
        if gs in (1, "1"):
            ip = s.get("inningsPitched")
            if ip is not None:
                starts_ip.append(innings_to_decimal(ip))
    if not starts_ip:
        return None
    return round(sum(starts_ip) / len(starts_ip), 1)


def fetch_pitcher_stats(pid, season):
    try:
        person = fetch_json(f"{API}/people/{pid}")
        p = person["people"][0]
        hand = p.get("pitchHand", {}).get("code")
        name = p.get("fullName")
    except Exception as e:
        print(f"  ! couldn't fetch person {pid}: {e}", file=sys.stderr)
        return None

    try:
        stats = fetch_json(
            f"{API}/people/{pid}/stats?stats=season&group=pitching&season={season}"
        )
        splits = stats.get("stats", [{}])[0].get("splits", [])
        if not splits:
            era, ip_display, gs = None, None, None
        else:
            s = splits[0]["stat"]
            era = s.get("era")
            ip_display = s.get("inningsPitched")
            gs = s.get("gamesStarted")
    except Exception as e:
        print(f"  ! couldn't fetch season stats for {pid}: {e}", file=sys.stderr)
        era, ip_display, gs = None, None, None

    avg_ip = fetch_starts_avg_ip(pid, season)
    if avg_ip is None and ip_display and gs:
        avg_ip = round(innings_to_decimal(ip_display) / gs, 1)

    return {
        "name": name,
        "hand": hand,
        "era": era,
        "ipDisplay": ip_display,
        "gamesStarted": gs,
        "avgIpPerOuting": avg_ip,
        "isOpener": bool(avg_ip is not None and avg_ip <= OPENER_IP_THRESHOLD),
        "fetchedDate": str(date.today()),
    }


def fetch_weather(game_pk):
    """Best-effort; returns None if unavailable (e.g. far-future game)."""
    try:
        feed = fetch_json(f"{LIVE_API}/game/{game_pk}/feed/live")
        w = feed.get("gameData", {}).get("weather", {})
        if not w or not w.get("condition"):
            return None
        return {
            "condition": w.get("condition"),
            "temp": w.get("temp"),
            "wind": w.get("wind"),
        }
    except Exception as e:
        print(f"  ! couldn't fetch weather for {game_pk}: {e}", file=sys.stderr)
        return None


def lookup_splits(team_splits, hand, opp_abbr):
    if hand not in ("R", "L"):
        return None
    opp_abbr = canon(opp_abbr)
    hand_key = "RHP" if hand == "R" else "LHP"
    t30 = team_splits.get("teams_30", {}).get(hand_key, {}).get(opp_abbr)
    t7 = team_splits.get("teams_7", {}).get(hand_key, {}).get(opp_abbr)
    if not t30:
        return None
    return {
        "woba30": t30.get("woba"),
        "woba30Rank": t30.get("woba_rank"),
        "woba7": t7.get("woba") if t7 else None,
        "woba7Rank": t7.get("woba_rank") if t7 else None,
        "kPct30": t30.get("k_pct"),
        "kPct30Rank": t30.get("k_pct_rank"),
    }


def build_starter(side_data, team_splits, opp_abbr, state, season):
    probable = side_data.get("probablePitcher")
    if not probable:
        return {"confirmed": False}

    pid = str(probable["id"])
    cached = state.get(pid)
    today_str = str(date.today())

    if cached and cached.get("fetchedDate") == today_str:
        info = cached
    else:
        info = fetch_pitcher_stats(pid, season)
        if info is None:
            return {"confirmed": False}
        state[pid] = info

    hand = info.get("hand")
    return {
        "confirmed": True,
        "name": info.get("name"),
        "hand": hand,
        "era": info.get("era"),
        "ipDisplay": info.get("ipDisplay"),
        "gamesStarted": info.get("gamesStarted"),
        "avgIpPerOuting": info.get("avgIpPerOuting"),
        "isOpener": info.get("isOpener", False),
        "oppSplits": lookup_splits(team_splits, hand, opp_abbr),
    }


def main():
    if not TEAM_SPLITS_PATH.exists():
        print(
            f"Missing {TEAM_SPLITS_PATH} — run mlb_team_splits.py at least "
            "once first.",
            file=sys.stderr,
        )
        sys.exit(1)
    team_splits = json.loads(TEAM_SPLITS_PATH.read_text())

    today = date.today()
    season = today.year
    sched = fetch_json(
        f"{API}/schedule?sportId=1&date={today}&hydrate=team,probablePitcher"
    )

    state = load_state()
    games_out = []

    for day in sched.get("dates", []):
        for g in day.get("games", []):
            teams = g.get("teams", {})
            home = teams.get("home", {})
            away = teams.get("away", {})
            home_team = home.get("team", {})
            away_team = away.get("team", {})

            home_starter = build_starter(home, team_splits, away_team.get("abbreviation", ""), state, season)
            away_starter = build_starter(away, team_splits, home_team.get("abbreviation", ""), state, season)

            weather = fetch_weather(g.get("gamePk"))

            games_out.append({
                "gamePk": g.get("gamePk"),
                "gameTime": g.get("gameDate"),
                "doubleHeader": g.get("doubleHeader", "N"),   # Y, N, or S
                "gameNumber": g.get("gameNumber", 1),
                "weather": weather,
                "home": {
                    "teamId": home_team.get("id"),
                    "teamAbbr": home_team.get("abbreviation", ""),
                    "teamName": home_team.get("name", ""),
                    "starter": home_starter,
                },
                "away": {
                    "teamId": away_team.get("id"),
                    "teamAbbr": away_team.get("abbreviation", ""),
                    "teamName": away_team.get("name", ""),
                    "starter": away_starter,
                },
            })

    games_out.sort(key=lambda g: g.get("gameTime") or "")
    save_state(state)

    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M"),
        "date": str(today),
        "games": games_out,
    }

    out_dir = resolve_output_dir()
    out_path = out_dir / OUTPUT_FILENAME
    out_path.write_text(json.dumps(payload, indent=2, allow_nan=False))
    print(f"Wrote {out_path} — {len(games_out)} games")
    for g in games_out:
        h = g["home"]["starter"]
        a = g["away"]["starter"]
        h_name = h.get("name", "TBD") if h.get("confirmed") else "TBD"
        a_name = a.get("name", "TBD") if a.get("confirmed") else "TBD"
        dh = f" (DH G{g['gameNumber']})" if g["doubleHeader"] != "N" else ""
        print(f"  {g['away']['teamAbbr']} ({a_name}) @ {g['home']['teamAbbr']} ({h_name}){dh} — {g['gameTime']}")


if __name__ == "__main__":
    main()
