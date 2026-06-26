#!/usr/bin/env python3
"""
MLB Team Splits — heavy daily job (requires pybaseball, pandas, numpy).

Run ONCE per day. Pulls every pitch thrown league-wide over the trailing
30 days via Statcast, then aggregates per team and per opposing-pitcher
handedness, over both a 30-day and a 7-day window:

  * wOBA   — actual wOBA against that handedness, ranked 1-30 across MLB.
             Rank 1 = LOWEST wOBA = best matchup for the PITCHER (hardest
             team to hit against that handedness). Rank 30 = easiest.
             (Using actual wOBA, not xwOBA — simpler: a direct average of
             woba_value, no need to fall back between an estimated and an
             actual number depending on play type.)
  * K%     — strikeout rate against that handedness. Only the 30-day
             window is ranked (rank 1 = HIGHEST K% = best for the
             pitcher); 7-day K% is stored but not ranked, to match what's
             actually shown on the widget.

Team-abbreviation note: Statcast data can occasionally use a different
abbreviation for a team than the Stats API does (e.g. around the
Athletics' 2025 relocation/rebrand), which would silently split one
team's games across two keys and badly shrink its sample. TEAM_ALIASES
below merges known cases — extend it if another mismatched team turns up.

Output: a small local cache (NOT synced to iCloud — read by
mlb_matchups.py on the same Mac).
"""

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

CACHE_DIR = Path.home() / ".mlb_sub_tracker"
OUTPUT_PATH = CACHE_DIR / "team_splits_cache.json"
WINDOW_DAYS = 30
SHORT_WINDOW_DAYS = 7

# Known cases where Statcast's raw team abbreviation can differ from the
# one the Stats API returns (e.g. around the Athletics' 2025 relocation,
# or Arizona using AZ in some sources vs ARI in others). This same dict
# also lives in mlb_matchups.py and MUST be applied on both sides of the
# join — canonicalizing only one side (which is what the previous version
# did) doesn't help if the two source APIs disagree on which abbreviation
# to use.
ABBR_CANON = {
    "OAK": "ATH",
    "AZ": "ARI",
}


def canon(abbr):
    return ABBR_CANON.get(abbr, abbr)


def fetch_team_id_map():
    """{abbreviation: numeric team id} via the Stats API — used so the
    phone widget can fetch a reliable team logo for the opponent without
    needing a hardcoded abbreviation->id table (which is exactly the kind
    of thing that's quietly wrong for one team and breaks silently)."""
    import urllib.request
    try:
        req = urllib.request.Request(
            "https://statsapi.mlb.com/api/v1/teams?sportId=1",
            headers={"User-Agent": "mlb-team-splits/1.0 (personal use)"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return {t["abbreviation"]: t["id"] for t in data.get("teams", []) if t.get("abbreviation") and t.get("id")}
    except Exception as e:
        print(f"  ! couldn't fetch team ID map (logos will be skipped): {e}", file=sys.stderr)
        return {}


# --- Reds home-run extraction (rides along on the same Statcast pull) ----
HR_TEAM = "CIN"
HR_OUTPUT_FILENAME = "reds_hr.json"
HR_COUNT = 10


def hr_output_path():
    """Same iCloud-folder resolution as the matchups script uses."""
    home = Path.home()
    candidates = [
        home / "Library/Mobile Documents/iCloud~dk~simonbs~Scriptable/Documents",
        home / "Library/Mobile Documents/com~apple~CloudDocs/MLBSubTracker",
        home / "MLBSubTracker",
    ]
    for c in candidates:
        try:
            if c.parent.exists():
                c.mkdir(parents=True, exist_ok=True)
                return c / HR_OUTPUT_FILENAME
        except OSError:
            continue
    fb = home / "MLBSubTracker"
    fb.mkdir(parents=True, exist_ok=True)
    return fb / HR_OUTPUT_FILENAME


def spray_field(hc_x, hc_y, stand):
    """Approximate where the ball went using Statcast hit coords. Home plate
    sits near (125.42, 198.27); angle 0 = dead center, negative = toward the
    third-base/left side, positive = first-base/right side."""
    import math
    try:
        dx = float(hc_x) - 125.42
        dy = 198.27 - float(hc_y)
        ang = math.degrees(math.atan2(dx, dy))   # -45 (LF line) .. +45 (RF line)
    except (TypeError, ValueError):
        return None
    if ang < -18:
        return "LF"
    if ang < -6:
        return "LCF"
    if ang <= 6:
        return "CF"
    if ang <= 18:
        return "RCF"
    return "RF"


def extract_reds_hrs(pa, season, id_map):
    """Pull the most recent HOME_RUN events by HR_TEAM batters out of the
    plate-appearance dataframe and resolve batter/pitcher names. Returns a
    list of dicts, newest first."""
    hrs = pa[(pa["batting_team"] == HR_TEAM) & (pa["events"] == "home_run")].copy()
    if hrs.empty:
        return []

    # Newest first. game_date is a string (YYYY-MM-DD); within a day, a
    # higher at-bat / pitch sequence is later, but date-level ordering is
    # enough for "last 10" across a 30-day window.
    sort_cols = [c for c in ("game_date", "inning") if c in hrs.columns]
    hrs = hrs.sort_values(sort_cols, ascending=False).head(HR_COUNT)

    # Resolve names in one batch via pybaseball's reverse lookup.
    names = {}
    try:
        from pybaseball import playerid_reverse_lookup
        ids = []
        for col in ("batter", "pitcher"):
            ids += [int(v) for v in hrs[col].dropna().unique()]
        if ids:
            lk = playerid_reverse_lookup(list(set(ids)), key_type="mlbam")
            for _, r in lk.iterrows():
                full = f"{str(r['name_first']).title()} {str(r['name_last']).title()}"
                names[int(r["key_mlbam"])] = full
    except Exception as e:
        print(f"  ! name lookup failed (will fall back to IDs): {e}", file=sys.stderr)

    def nm(pid):
        try:
            return names.get(int(pid), f"#{int(pid)}")
        except (TypeError, ValueError):
            return "?"

    import pandas as pd

    def clean(v):
        """Convert any pandas-missing sentinel (NaN, None, pd.NA) to a
        plain Python None. Without this, a raw NaN can end up inside
        json.dumps() output as the bare token NaN — which Python's own
        json module accepts (non-standard leniency) but JavaScript's
        JSON.parse rejects outright, so the file looks fine here and
        fails consistently, every time, on the phone."""
        try:
            if pd.isna(v):
                return None
        except (TypeError, ValueError):
            pass
        return v

    out = []
    for _, r in hrs.iterrows():
        on_base = sum(1 for b in ("on_1b", "on_2b", "on_3b")
                      if b in r and not pd.isna(r[b]))
        rbi = on_base + 1
        dist = r.get("hit_distance_sc")
        ev = r.get("launch_speed")
        balls, strikes = r.get("balls"), r.get("strikes")
        away, home = clean(r.get("away_team")), clean(r.get("home_team"))
        opponent = home if away == HR_TEAM else away
        out.append({
            "batter": nm(r.get("batter")),
            "batterId": int(r["batter"]) if not pd.isna(r.get("batter")) else None,
            "pitcher": nm(r.get("pitcher")),
            "pitcherHand": clean(r.get("p_throws")),
            "count": f"{int(balls)}-{int(strikes)}" if not pd.isna(balls) and not pd.isna(strikes) else None,
            "pitch": clean(r.get("pitch_name")) or clean(r.get("pitch_type")),
            "pitchSpeed": round(float(r["release_speed"]), 1) if not pd.isna(r.get("release_speed")) else None,
            "rbi": rbi,
            "inning": int(r["inning"]) if not pd.isna(r.get("inning")) else None,
            "halfInning": clean(r.get("inning_topbot")),
            "outs": int(r["outs_when_up"]) if not pd.isna(r.get("outs_when_up")) else None,
            "date": str(r.get("game_date")),
            "away": away,
            "home": home,
            "opponent": opponent,
            "opponentId": id_map.get(opponent),
            "distanceFt": int(dist) if not pd.isna(dist) else None,
            "exitVeloMph": round(float(ev), 1) if not pd.isna(ev) else None,
            "field": spray_field(r.get("hc_x"), r.get("hc_y"), r.get("stand")),
            "desc": clean(r.get("des")),
        })
    return out


def aggregate(pa_subset, hand_col, denom_col, numer_col):
    """Returns {hand_key: {team: {woba, k_pct, pa}}} for R and L.

    K% is computed directly from each group's own rows (g["events"]),
    not via a separately-indexed lookup — a prior version cross-referenced
    a boolean mask by row label, which silently broke (and inflated K%
    several-fold) whenever pybaseball's day-by-day concatenation produced
    non-unique row labels across different days."""
    out = {"RHP": {}, "LHP": {}}
    for hand, key in (("R", "RHP"), ("L", "LHP")):
        sub = pa_subset[pa_subset[hand_col] == hand]
        for team, g in sub.groupby("batting_team"):
            denom = g[denom_col].sum()
            if denom <= 0:
                continue
            woba = g[numer_col].sum() / denom
            pa_count = len(g)
            k_count = g["events"].isin(["strikeout", "strikeout_double_play"]).sum()
            k_pct = (k_count / pa_count * 100) if pa_count else 0.0
            out[key][team] = {
                "woba": round(float(woba), 3),
                "k_pct": round(float(k_pct), 1),
                "pa": int(pa_count),
            }
    return out


def add_ranks(block, key_field, ascending):
    """ascending=True -> rank 1 is the lowest value; False -> rank 1 is highest."""
    for hand_key in block:
        ranked = sorted(
            block[hand_key].items(),
            key=lambda kv: kv[1][key_field],
            reverse=not ascending,
        )
        for i, (team, vals) in enumerate(ranked, 1):
            vals[f"{key_field}_rank"] = i


def main():
    try:
        from pybaseball import statcast
    except ImportError:
        print(
            "pybaseball isn't installed. Run:\n"
            "  pip3 install pybaseball --break-system-packages\n",
            file=sys.stderr,
        )
        sys.exit(1)

    today = date.today()
    start = today - timedelta(days=WINDOW_DAYS)
    short_start = today - timedelta(days=SHORT_WINDOW_DAYS)
    print(f"Pulling Statcast pitches: {start} -> {today} (this can take a few minutes)")

    df = statcast(start_dt=str(start), end_dt=str(today))
    print(f"Pulled {len(df)} pitches.")
    # statcast() concatenates day-by-day results, which can leave duplicate
    # row labels across different days. Reset so every row has a unique,
    # unambiguous index before any indexed lookups happen.
    df = df.reset_index(drop=True)

    pa = df[df["events"].notna()].copy()
    pa["batting_team"] = pa.apply(
        lambda r: r["away_team"] if r["inning_topbot"] == "Top" else r["home_team"],
        axis=1,
    )
    pa["batting_team"] = pa["batting_team"].apply(canon)
    pa["game_date"] = pa["game_date"].astype(str)

    splits_30 = aggregate(pa, "p_throws", "woba_denom", "woba_value")
    add_ranks(splits_30, "woba", ascending=True)
    add_ranks(splits_30, "k_pct", ascending=False)

    pa_7 = pa[pa["game_date"] >= str(short_start)]
    splits_7 = aggregate(pa_7, "p_throws", "woba_denom", "woba_value")
    add_ranks(splits_7, "woba", ascending=True)

    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M"),
        "window_30_start": str(start),
        "window_30_end": str(today),
        "window_7_start": str(short_start),
        "window_7_end": str(today),
        "teams_30": splits_30,
        "teams_7": splits_7,
    }

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, allow_nan=False))
    print(f"\nWrote {OUTPUT_PATH}")
    print("\nSample (30-day, vs RHP, best pitcher matchups by wOBA):")
    for team, vals in sorted(splits_30["RHP"].items(), key=lambda kv: kv[1]["woba_rank"])[:5]:
        print(f"  {vals['woba_rank']:>2}. {team}: wOBA {vals['woba']} (n={vals['pa']}) · K% {vals['k_pct']} (rank {vals['k_pct_rank']})")

    # Reds home runs — extracted from the same pull, written to iCloud.
    id_map = fetch_team_id_map()
    reds_hrs = extract_reds_hrs(pa, today.year, id_map)
    hr_payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M"),
        "team": HR_TEAM,
        "window_start": str(start),
        "window_end": str(today),
        "homers": reds_hrs,
    }
    hr_path = hr_output_path()
    hr_path.write_text(json.dumps(hr_payload, indent=2, allow_nan=False))
    print(f"\nWrote {hr_path} — {len(reds_hrs)} Reds HRs")
    for h in reds_hrs[:5]:
        print(f"  {h['date']} {h['batter']} — {h['distanceFt']}ft off {h['pitcher']} "
              f"({h['count']} {h['pitch']}), {h['rbi']} RBI, {h['field']}")


if __name__ == "__main__":
    main()
