#!/usr/bin/env python3
"""
MLB Matchup Run Scheduler — decides WHEN to run mlb_matchups.py.

Game times shift daily, so a fixed clock schedule (like the sub-tracker's)
can't track "an hour before first pitch." Instead, this runs frequently
(every 10 minutes, via launchd) and checks whether "now" is close to one
of three targets, recomputed fresh each call from TODAY's actual
first-pitch time:

  1. Morning catch-all — fixed local time, 07:00.
  2. One hour before today's first game.
  3. Two hours after today's first game (this is the same clock moment
     described as "the night before, 2h after the previous game's start
     time" and "3h after the 1h-before mark" — both land here).

A small state file tracks which of today's three slots have already
fired, so polling every 10 minutes doesn't re-run the job repeatedly
within the same several-minute target window.
"""

import json
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, date
from pathlib import Path

API = "https://statsapi.mlb.com/api/v1"
CACHE_DIR = Path.home() / ".mlb_sub_tracker"
STATE_PATH = CACHE_DIR / "scheduler_state.json"
MATCHUPS_SCRIPT = "/Users/jamesmorris/Coding/MLBSubTracker/mlb_matchups.py"
LOG_PATH = "/Users/jamesmorris/Coding/MLBSubTracker/matchups.log"
MATCH_WINDOW_MINUTES = 6   # wider than half the 10-min poll interval, so nothing gets skipped
MORNING_HOUR = 7
MORNING_MINUTE = 0
USER_AGENT = "mlb-scheduler/1.0 (personal use)"


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


def first_pitch_today_utc():
    """Earliest gameDate among today's games, as a naive UTC datetime.
    Returns None on an off day (no games)."""
    today = date.today()
    sched = fetch_json(f"{API}/schedule?sportId=1&date={today}")
    times = []
    for day in sched.get("dates", []):
        for g in day.get("games", []):
            gd = g.get("gameDate")
            if gd:
                times.append(gd)
    if not times:
        return None
    earliest = min(times)  # ISO strings sort correctly lexicographically here
    return datetime.strptime(earliest, "%Y-%m-%dT%H:%M:%SZ")


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


def run_matchups():
    with open(LOG_PATH, "a") as log:
        log.write(f"\n-- scheduler-triggered run at {datetime.now()}\n")
        subprocess.run(["python3", MATCHUPS_SCRIPT], stdout=log, stderr=log)


def main():
    today_str = str(date.today())
    state = load_state()
    fired_today = set(state.get(today_str, []))

    now_local = datetime.now()
    now_utc = datetime.utcnow()

    try:
        fp_utc = first_pitch_today_utc()
    except Exception as e:
        print(f"couldn't fetch today's schedule: {e}", file=sys.stderr)
        fp_utc = None

    # (slot_name, "local" or "utc", target_datetime)
    targets = [("morning", "local", now_local.replace(
        hour=MORNING_HOUR, minute=MORNING_MINUTE, second=0, microsecond=0))]
    if fp_utc:
        targets.append(("before_first_pitch", "utc", fp_utc - timedelta(hours=1)))
        targets.append(("after_first_pitch", "utc", fp_utc + timedelta(hours=2)))
    else:
        print("No games today — skipping the two first-pitch-relative slots.")

    for slot, kind, target in targets:
        if slot in fired_today:
            continue
        now_ref = now_local if kind == "local" else now_utc
        delta_minutes = abs((now_ref - target).total_seconds()) / 60
        if delta_minutes <= MATCH_WINDOW_MINUTES:
            print(f"Firing slot '{slot}' (target {target}, now {now_ref})")
            run_matchups()
            fired_today.add(slot)

    state[today_str] = sorted(fired_today)
    # prune anything older than 2 days so the state file doesn't grow forever
    cutoff = str(date.today() - timedelta(days=2))
    state = {k: v for k, v in state.items() if k >= cutoff}
    save_state(state)


if __name__ == "__main__":
    main()
