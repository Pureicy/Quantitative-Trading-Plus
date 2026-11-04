# Personal Convertible Bond Assistant

Local-first Flet app for personal convertible-bond scanning.

## What It Does

- Scans the full convertible-bond market with AkShare
- Filters out high-price and forced-redemption candidates
- Ranks by double-low score
- Tracks local holdings and watchlist
- Saves scan snapshots for later review

## Core Formula

`double_low_score = price + premium_pct`

Lower is better.

## Local Files

- `data/holdings.csv`
- `data/watchlist.csv`
- `data/snapshots/`

`holdings.csv` columns:

`bond_code,bond_name,quantity,avg_cost,note`

`watchlist.csv` columns:

`bond_code,bond_name,note`

## Install

Windows:

```powershell
setup.bat
```

macOS / Linux:

```bash
./setup.sh
```

Both scripts create a local `.venv`, install the dependencies and initialise the local
CSV files. To install into the current interpreter instead:

```powershell
pip install -r requirements.txt
```

`requirements.txt` includes both `flet` and `flet-desktop`, because the desktop window cannot open with the base `flet` package alone.

## Check Environment

```powershell
python app_bootstrap.py
```

This will:

- ensure local CSV files exist
- check `flet`, `pandas`, and `akshare`
- show the launch command

## Launch

Option 1:

```powershell
python app_bootstrap.py --launch
```

Option 2:

```powershell
start_quant_assistant.bat
```

## Terminal Scan

Run a scan without opening the Flet window:

```powershell
python app_bootstrap.py --scan
```

Example with filters:

```powershell
python app_bootstrap.py --scan --top-n 10 --position-filter watchlist --max-premium 25
```

Export to CSV:

```powershell
python app_bootstrap.py --scan --top-n 10 --export-csv exports\latest-scan.csv
```

JSON output:

```powershell
python app_bootstrap.py --scan --json
```

## Backup Local Data

Backup holdings and watchlist CSV files:

```powershell
python app_bootstrap.py --backup-data
```

List available backups:

```powershell
python app_bootstrap.py --list-backups
```

The backup files are stored under:

`data/backups/YYYY-MM-DD/backup-HHMMSS/`

Restore holdings and watchlist from a backup directory:

```powershell
python app_bootstrap.py --restore-data data\backups\YYYY-MM-DD\backup-HHMMSS
```

Restore the latest backup directly:

```powershell
python app_bootstrap.py --restore-latest
```

## Export Current Holdings And Watchlist

Export the current local state to a target directory:

```powershell
python app_bootstrap.py --export-data exports\state
```

## Show Local State Summary

Show a compact local summary of holdings, watchlist, latest snapshot, and latest backup:

```powershell
python app_bootstrap.py --state-summary
```

## Export Latest Scan Summary

Export the latest scan summary to a readable text file:

```powershell
python app_bootstrap.py --export-latest-summary exports\latest-summary.txt
```

## List Recent Scan Snapshots

List recent local scan snapshots:

```powershell
python app_bootstrap.py --list-snapshots
```

## Recommended Daily Flow

For low-budget personal use, this is the recommended daily routine:

1. Check current local state:

```powershell
python app_bootstrap.py --state-summary
```

2. Run the latest market scan and export the top candidates:

```powershell
python app_bootstrap.py --scan --top-n 10 --export-csv exports\latest-scan.csv
```

3. Export a readable text summary of the latest snapshot:

```powershell
python app_bootstrap.py --export-latest-summary exports\latest-summary.txt
```

4. Backup your local holdings and watchlist:

```powershell
python app_bootstrap.py --backup-data
```

If you want a single entry point for this routine, run:

```powershell
daily_quant_assistant.bat
```

The daily batch will stop immediately if the scan step fails, so it will not accidentally export a stale summary as if it were a fresh result.

## Interface

The desktop UI was redesigned around a fixed navigation rail plus a single scrolling canvas:

- **概览** — KPI tiles (market size, candidates, held, forced-redemption exclusions) + formula / summary / snapshot panels
- **候选池** — the double-low table with monospaced numerals, rank badges and signal chips
- **快照复盘** — rank/score deltas between two consecutive scans
- **自选池** / **持仓维护** — local watchlist and holdings editors
- **MARKET RADAR SCAN** — staged progress overlay with a client-side radar animation, background execution and recoverable errors

Design tokens live in `ui_theme.py`: deep-space blue-black surfaces, ice-cyan and
violet accents, monospaced telemetry labels, holographic borders and rounded cards.

## Startup Sequence

The desktop app opens with a client-side `星际跃迁` sequence: warp stars, HUD rings,
the `双低量化 / DOUBLE-LOW QUANT ENGINE` title and four boot status lines. It plays for
7.5 seconds on every launch and can be skipped by clicking anywhere.

The complex motion is a pre-rendered WebP layer; Flet only animates the headline,
progress and status text. No browser or WebGL window is created.

## Console Particle Effects

The desktop console has a client-side particle layer, so the visual effect is visible
inside the normal Flet window without opening a Web UI:

- a full-window transparent looping particle animation behind the control console;
- 36 independent particles inside every card on every workspace page;
- a fixed count of 4000 background particles;
- brighter cool-white/cyan star cores while preserving the reduced particle size;
- floating sine/Lissajous constellation curves with bright 1px lines that fade in and out;
- hover lift, accent border and stronger shadow on every card;
- Navbar switches only for `粒子` and `省电`;
- dark theme only.

The normal console never launches a browser or a second window. Particle frames are
animated by Flutter from pre-rendered transparent WebP loops, so Python does not send
thousands of coordinates over the Flet event channel every frame. Particle visibility
and power-saver mode are controlled only by the two Navbar switches.

The exact Three.js implementation (`BufferGeometry + PointsMaterial + THREE.Points`,
`Raycaster`, NDC mouse parallax) remains under `background/` only as optional source
material for another website. The desktop app has no entry point that launches it.

`three.module.js` is vendored under `background/vendor/`, so the scene works offline.
Full implementation notes and the acceptance checklist: `docs/particle-background.md`.

## Development Preview

Useful environment switches (development only):

| Variable | Effect |
| --- | --- |
| `QUANT_VIEW` | Open the app directly on a view (`overview`, `candidates`, `review`, `watchlist`, `holdings`) |
| `QUANT_PARTICLES` | `0` starts with console particle animation paused |
| `QUANT_SKIP_SPLASH` | `1` skips the startup animation during development |
| `QUANT_AUTOSCAN` | `1` runs one market scan at startup (useful for screenshots) |

```powershell
$env:QUANT_VIEW="candidates"; python mod.py
```

## Test

```powershell
python -m unittest discover -s tests -v
```

## Notes

- This project is designed for low-cost personal use.
- Market data availability depends on AkShare upstream sources.
- Scan snapshots are stored locally and can be reviewed in the UI.
- Some Windows terminals may display UTF-8 source files with garbled Chinese text, but the runtime strings and app behavior are unaffected.
