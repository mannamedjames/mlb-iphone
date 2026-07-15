"""
Shared helpers for the matchup-results database.

The DB is a single JSON array at data/matchup_results.json. One row per
(gamePk, pitcherId). Rows are created pregame with the ranking signal and
filled postgame with the actual pitching line. Rows from the first 30 days
of the season have null ranks — they exist purely as baseline material for
computing each pitcher's rolling last-N-starts form.

Row schema (nulls where unknown/not yet filled):
  gamePk, date, pitcherId, pitcherName, hand, team, opponent,
  isHome (bool),
  -- pregame signal --
  woba30Rank, woba7Rank, kPct30Rank,        # opponent ranks vs this hand
  woba30, woba7, kPct30,                     # the underlying values
  -- postgame actuals --
  ip (decimal), hits, er, bb, k, hr, pitches, battersFaced,
  oppHandPctLeft (share of PAs vs LHB, when derivable),
  final (bool)  # true once actuals are filled
"""

import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "matchup_results.json"


def load_db():
    if DB_PATH.exists():
        try:
            return json.loads(DB_PATH.read_text())
        except json.JSONDecodeError:
            return []
    return []


def save_db(rows):
    DB_PATH.parent.mkdir(exist_ok=True)
    rows.sort(key=lambda r: (r.get("date") or "", r.get("gamePk") or 0))
    DB_PATH.write_text(json.dumps(rows, indent=1, allow_nan=False))


def upsert_pregame(rows, new_row):
    """Insert or update a pregame row keyed on (gamePk, pitcherId). Never
    overwrites a row that already has actuals filled (final=True)."""
    for r in rows:
        if r.get("gamePk") == new_row["gamePk"] and r.get("pitcherId") == new_row["pitcherId"]:
            if not r.get("final"):
                r.update(new_row)
            return rows
    base = {
        "ip": None, "hits": None, "er": None, "bb": None, "k": None,
        "hr": None, "pitches": None, "battersFaced": None,
        "oppHandPctLeft": None, "final": False,
    }
    base.update(new_row)
    rows.append(base)
    return rows


def innings_to_decimal(ip_str):
    """MLB IP notation: digit after the decimal is OUTS (.1 = 1/3)."""
    if ip_str in (None, ""):
        return None
    parts = str(ip_str).split(".")
    whole = int(parts[0]) if parts[0] else 0
    outs = int(parts[1]) if len(parts) > 1 and parts[1] else 0
    return round(whole + outs / 3.0, 3)
