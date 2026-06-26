# MLB Daily Metrics Tracker — Requirements Document

## 1. Overview
A personal iPhone widget/dashboard system that surfaces daily MLB metrics, built on Scriptable (iOS), with all heavy data processing run automatically on a Mac and synced to the phone via iCloud. The phone never fetches or computes data directly — it only reads a small, pre-compiled JSON file.

## 2. Goals
- Track meaningful, otherwise-hard-to-see MLB metrics on a recurring basis.
- Keep the phone fast and battery-friendly: zero on-device crawling or heavy computation.
- Build incrementally: a small proof of concept first, then expand toward a full daily matchup dashboard.

## 3. Phase 1 — Proof of Concept

### 3.1 Functional requirements
- **FR1.** Identify all completed MLB games (regular season + postseason) in a rolling 30 calendar-day window ending today.
- **FR2.** For each game, determine, per batter: whether they started, whether they were subbed out (started, then removed from the game at any point), and whether they were subbed in (entered as pinch hitter, pinch runner, or defensive replacement — all three combined into one category).
- **FR3.** A player who starts and changes fielding position but stays in the game the whole time must NOT be counted as subbed out.
- **FR4.** Produce two leaderboards across the window: top 5 players by distinct games subbed out, and top 5 by distinct games subbed in.
- **FR5.** No minimum-games floor for inclusion (pure volume ranking).
- **FR6.** Tiebreaker order: (1) most games subbed out/in, (2) most games started in the window, (3) most hits in the window.
- **FR7.** Output a compact JSON artifact containing both leaderboards, a generation timestamp, and the date window covered.
- **FR8.** The phone app must render: (a) a home-screen widget showing a condensed view of both leaderboards, and (b) a fuller in-app table view with the same data plus secondary stats (started count, hits).

### 3.2 Non-functional requirements
- **NFR1.** All MLB API fetching and computation happens on the Mac, on a daily automated schedule, with no manual trigger required.
- **NFR2.** Per-game data is cached locally on the Mac so daily runs only fetch new games, not the full 30-day window each time.
- **NFR3.** The phone-side script must run in well under iOS's widget execution time budget (effectively instant, since it only reads one small file).
- **NFR4.** A single bad/missing game record must not crash the full run; it should be skipped and logged.
- **NFR5.** The system should clearly surface staleness (e.g., a visible "last updated" timestamp) if the Mac job hasn't run recently.

### 3.3 Out of scope (Phase 1)
- Any Statcast/xwOBA metrics.
- Pitcher-specific data.
- Historical trend charts or comparisons across multiple time windows.

## 4. Phase 2 — Daily Matchup Dashboard (future)

### 4.1 Functional requirements (draft, subject to refinement)
- **FR9.** For each day's matchups, show each starting pitcher's name, ERA, and handedness.
- **FR10.** Show the opposing team's performance (xwOBA) against that handedness over the trailing 30 days, expressed as a rank among all MLB teams.
- **FR11.** Refresh once daily ahead of that day's games.

### 4.2 Known dependency
- xwOBA is a Statcast/Baseball Savant metric, not available from the basic MLB Stats API. This phase will require pulling and aggregating Statcast data (e.g., via `pybaseball` on the Mac) rather than relying solely on Stats API calls.

### 4.3 Open questions to resolve before building
- Rank population: all 30 MLB teams, or just upcoming opponents?
- Minimum sample size for a team's xwOBA-vs-handedness split to be considered reliable?
- Should probable (pre-game) starters be used, or only confirmed/announced ones?

## 5. System Architecture
- **Compute layer (Mac):** Python script, scheduled via `launchd`, calls the MLB Stats API, applies business logic, caches per-game results locally, and writes a compiled summary JSON.
- **Sync layer:** Scriptable's iCloud Documents folder (`FileManager.iCloud()`), shared between Mac and iPhone.
- **Presentation layer (iPhone):** Scriptable JavaScript script reads the JSON and renders a widget (Home Screen) and a UITable (in-app), with no network calls.

## 6. Data Sources
- MLB Stats API (`statsapi.mlb.com`) — schedules, boxscores, batting order / substitution data. Free, no key required.
- Baseball Savant / Statcast (Phase 2 only) — xwOBA splits, via `pybaseball` or direct CSV export endpoints.

## 7. Assumptions
- The Mac is on and awake at the scheduled run time (no catch-up-on-wake logic in Phase 1).
- iCloud is enabled and signed in to the same account on both Mac and iPhone, with Scriptable installed on iOS.
- "Last 30 days" means rolling calendar days, not last-30-days-with-games.

## 8. Success Criteria
- Phase 1 is complete when: the Mac job runs unattended daily, the JSON updates automatically, and the iPhone widget + in-app view both reflect current data with no manual steps on the phone.
