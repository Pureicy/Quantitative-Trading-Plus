# Personal Quant Assistant Phase 1 Design

## Goal

Turn the current Flet demo into a low-cost, local-first assistant for daily convertible bond idea scanning. The app should scan the market, rank "double-low" candidates, show filterable results, and mark the user's local watchlist and holdings without relying on paid infrastructure.

## Recommended Approach

### Option A: Keep everything in one file

- Lowest short-term edit cost.
- Highest risk of making `mod.py` harder to test and extend.

### Option B: Keep Flet UI in `mod.py`, extract pure logic into local modules

- Slightly more work now.
- Much better for testing ranking, storage, and filtering logic without a GUI.
- Best fit for a personal tool that will keep evolving.

### Option C: Introduce a local database and background jobs now

- More complete long term.
- Too much complexity for phase 1 and not justified for a single-user budget.

### Decision

Use Option B.

## Scope

### In scope

- Market scan for convertible bonds using AkShare.
- Double-low score ranking using `price + premium_pct`.
- Risk filters for price cap and forced redemption.
- A larger candidate table instead of only top 10.
- Local watchlist and holdings loaded from CSV files.
- UI markers showing whether a bond is in holdings or watchlist.
- Basic filter controls for max price, max premium, top N, and "only unheld".
- Clear status and warning messages when the data source is partial or degraded.

### Out of scope

- Brokerage integration.
- Automated trading.
- Paid APIs.
- Cloud sync.
- Full portfolio analytics and PnL history.

## Architecture

### `mod.py`

Flet entrypoint and page layout only. It should wire controls to the backend services and render results, but avoid owning business rules.

### `assistant_core.py`

Pure scanning and ranking logic:

- fetch market data
- normalize columns
- detect degraded source quality
- apply market filters
- merge local tags
- return rows plus summary metadata

### `local_store.py`

Local CSV-backed personal data:

- ensure default files exist
- load holdings
- load watchlist
- normalize bond codes

### `tests/`

Unit tests for ranking, filtering, degraded-source handling, and local tag merging. Tests should target pure Python modules, not the GUI.

## Data Flow

1. User launches the app.
2. The app ensures local CSV files exist under `data/`.
3. User clicks the scan button.
4. Scanner fetches market data from AkShare.
5. Scanner normalizes fields and checks whether the source looks incomplete.
6. Scanner loads local holdings and watchlist from CSV.
7. Scanner filters, scores, sorts, and tags rows.
8. UI renders summary cards, warnings, and a `DataTable`.

## Local Data Model

### `data/holdings.csv`

Columns:

- `bond_code`
- `bond_name`
- `quantity`
- `note`

### `data/watchlist.csv`

Columns:

- `bond_code`
- `bond_name`
- `note`

Missing files should be auto-created with headers so the tool stays easy to start.

## UI Design

Keep the existing light/dark toggle and loading behavior. Replace the old single-result flow with:

- filter row
- scan button
- status area
- summary card
- warning card
- results table

The results table should include:

- rank
- bond code
- bond name
- latest price
- premium rate
- double-low score
- held flag
- watchlist flag

## Error Handling

- If AkShare packages are missing, show a direct install message.
- If the primary source returns suspiciously few rows, continue but mark the result as degraded.
- If fallback sources also fail, show a visible warning with the attempted source names.
- If local CSV files are malformed, show an actionable message naming the file and expected columns.

## Testing Strategy

- Add unit tests before implementation changes.
- Cover score calculation, price filtering, redeemed-bond exclusion, holding/watchlist tagging, and degraded-source warnings.
- Keep GUI verification lightweight and rely on import plus smoke tests for the Flet layer.

## Success Criteria

- App runs locally with free dependencies only.
- User can scan and see more than a fixed top-10 view.
- User can maintain holdings/watchlist in CSV files.
- Result rows clearly show whether a bond is already held or watched.
- App warns when market data looks incomplete instead of silently pretending coverage is full.
