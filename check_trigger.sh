#!/bin/zsh
# Checks for a flag file dropped by the phone's refresh button. The
# file's content is the requested target ("all", "subs", "matchups", or
# "splits") — empty or unrecognized content falls back to "subs+matchups"
# only, NOT the slow splits job, to match the original safety intent.
TRIGGER="/Users/jamesmorris/Library/Mobile Documents/iCloud~dk~simonbs~Scriptable/Documents/refresh_request.txt"
SUBTRACKER="/Users/jamesmorris/Coding/MLBSubTracker/mlb_sub_tracker.py"
MATCHUPS="/Users/jamesmorris/Coding/MLBSubTracker/mlb_matchups.py"
SPLITS="/Users/jamesmorris/Coding/MLBSubTracker/mlb_team_splits.py"
LOG="/Users/jamesmorris/Coding/MLBSubTracker/run.log"
SPLITS_LOG="/Users/jamesmorris/Coding/MLBSubTracker/team_splits.log"

if [ -f "$TRIGGER" ]; then
  REQUEST=$(cat "$TRIGGER" | tr -d '[:space:]')
  rm -f "$TRIGGER"
  echo "--" >> "$LOG"
  echo "$(date): on-demand refresh requested from phone (target: ${REQUEST:-<empty>})" >> "$LOG"

  case "$REQUEST" in
    subs)
      /usr/bin/python3 "$SUBTRACKER" >> "$LOG" 2>&1
      ;;
    matchups)
      /usr/bin/python3 "$MATCHUPS" >> "$LOG" 2>&1
      ;;
    splits)
      /usr/bin/python3 "$SPLITS" >> "$SPLITS_LOG" 2>&1
      ;;
    all)
      /usr/bin/python3 "$SUBTRACKER" >> "$LOG" 2>&1
      /usr/bin/python3 "$MATCHUPS" >> "$LOG" 2>&1
      /usr/bin/python3 "$SPLITS" >> "$SPLITS_LOG" 2>&1
      ;;
    *)
      echo "$(date): unrecognized/empty target — defaulting to subs+matchups only" >> "$LOG"
      /usr/bin/python3 "$SUBTRACKER" >> "$LOG" 2>&1
      /usr/bin/python3 "$MATCHUPS" >> "$LOG" 2>&1
      ;;
  esac
fi
