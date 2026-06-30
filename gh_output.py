"""
Shared helper: resolve where to write the data JSON files.

On GitHub Actions: writes to data/ in the repo root (which the workflow
then commits and pushes). On a local Mac: still writes to the Scriptable
iCloud folder for backwards-compatibility (useful for manual test runs).
"""
import os
from pathlib import Path


def resolve_output_dir() -> Path:
    if os.environ.get("GITHUB_ACTIONS"):
        data_dir = Path(__file__).parent / "data"
        data_dir.mkdir(exist_ok=True)
        return data_dir

    # Local Mac fallback — keeps manual runs working exactly as before.
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
                return c
        except OSError:
            continue
    fb = home / "MLBSubTracker"
    fb.mkdir(parents=True, exist_ok=True)
    return fb
