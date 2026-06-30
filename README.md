# MLB iPhone Tracker

A set of Scriptable widgets for iPhone that show live MLB matchup data, substitution trends, and Cincinnati Reds home run tracking — powered by GitHub Actions running on a schedule so your phone always has fresh data without your Mac needing to be on.

## What's included

| Widget | What it shows |
|--------|---------------|
| `mlb-matchups-widget` | Today's starting pitchers, opponent wOBA/K% splits (30d + 7d), color-coded rankings. Switches to tomorrow's slate once all games are underway. |
| `mlb-sub-widget` | Last 30 days of MLB substitution leaders — most often subbed out and subbed in, with team logos and start rate. |
| `mlb-reds-hr-widget` | Last 10 Reds home runs with batter, distance, opponent, inning/outs. Full pitch detail in the in-app view. |
| `mlb-update-tracker` | Staleness status (green/amber/red) for all three data feeds, plus a history of observed updates. |
| `mlb-request-refresh` | On-demand refresh button — lets you trigger any job from your phone without opening GitHub. |

## Architecture

```
GitHub Actions (scheduled)
    ↓ runs Python scripts
    ↓ commits JSON to data/
    ↓
raw.githubusercontent.com (public HTTP)
    ↓
Scriptable widgets on iPhone (read-only fetch)
```

No Mac required after initial setup. Data updates automatically on GitHub's servers.

### Update schedule (Mountain Time)
- **6:00 AM** — Team splits + Reds HRs (heavy Statcast pull, ~5 min)
- **7:30 AM, 11:00 AM, 3:00 PM, 6:00 PM** — Matchups + subs (fast, ~60 sec)

---

## Setup

### 1. Fork this repo

Click **Fork** on GitHub. All subsequent steps refer to your fork.

### 2. Enable Actions write permissions

Your repo → **Settings → Actions → General → Workflow permissions → Read and write permissions → Save**

### 3. Create a GitHub Personal Access Token (PAT)

**github.com → avatar → Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token (classic)**

- Scopes: check **`repo`** and **`workflow`**
- Copy the token — you only see it once (`ghp_...`)

### 4. Update your username and repo name in the widget files

In every file inside `widgets/`, replace:
```
GITHUB_USER = "mannamedjames"
GITHUB_REPO = "mlb-iphone"
```
with your own GitHub username and repo name. Same two lines in each file.

### 5. Store your PAT in Scriptable

Open **Scriptable** on your iPhone → tap **+** → paste and run this one line (with your real token):

```javascript
Keychain.set("mlb_github_pat", "ghp_your_token_here");
```

Delete the script after running. The token is stored encrypted in iOS Keychain — it never touches the repo.

### 6. Copy widgets to Scriptable

Copy each `.js` file from the `widgets/` folder into your Scriptable iCloud Documents folder:

```
~/Library/Mobile Documents/iCloud~dk~simonbs~Scriptable/Documents/
```

Or use the Files app on your iPhone to copy them from iCloud Drive → Scriptable.

### 7. Trigger the first run

Go to your repo → **Actions tab → Daily Team Splits & Reds HRs → Run workflow**

Wait for it to go green (~5 minutes), then trigger **Matchups & Subs → Run workflow → target: all**.

Once both are green, open each widget in Scriptable and tap Run to confirm data loads.

### 8. Add widgets to your Home Screen

Long-press your Home Screen → **+** → **Scriptable** → pick a size → tap the widget → set the script name to match each `.js` file.

---

## Data sources

- **MLB Stats API** (`statsapi.mlb.com`) — schedules, probable pitchers, pitcher stats
- **Baseball Savant / Statcast** via [pybaseball](https://github.com/jldbc/pybaseball) — pitch-level data for wOBA, K%, and Reds home runs
- **MLB team logos** — `midfield.mlbstatic.com`

## Security note

The PAT is stored only in Scriptable's iOS Keychain and is never committed to this repo. All data in `data/` is public MLB statistics. The repo is safe to keep public — public repos also get unlimited free GitHub Actions minutes vs a 2,000/month cap on private repos.

## On-demand refresh

Open the **mlb-request-refresh** script in Scriptable and tap Run. Choose which job to trigger:

- **Subs / Matchups** — completes in ~60 seconds
- **Splits + Reds HRs** — takes ~5 minutes (full Statcast pull)

Requires your PAT to be stored in Keychain (Step 5 above).
