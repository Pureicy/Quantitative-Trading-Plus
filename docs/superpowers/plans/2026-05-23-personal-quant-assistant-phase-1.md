# Personal Quant Assistant Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-first convertible bond assistant that scans the market, supports filterable double-low candidates, and tags local holdings/watchlist data from CSV files.

**Architecture:** Keep the Flet UI in `mod.py`, move pure market-scanning logic into `assistant_core.py`, and move local CSV persistence into `local_store.py`. Verify the new behavior with unit tests against pure Python code, then reconnect the GUI to the tested services.

**Tech Stack:** Python 3.13, Flet, Pandas, AkShare, built-in `unittest`, CSV files

---

### Task 1: Create tests for local CSV storage

**Files:**
- Create: `D:\Project\Quantitative Trading\tests\test_local_store.py`
- Create: `D:\Project\Quantitative Trading\local_store.py`

- [ ] **Step 1: Write the failing test**

```python
import tempfile
import unittest
from pathlib import Path

from local_store import LocalStore


class LocalStoreTests(unittest.TestCase):
    def test_creates_default_csv_files_with_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalStore(Path(tmp))
            store.ensure_files()

            self.assertTrue((Path(tmp) / "holdings.csv").exists())
            self.assertTrue((Path(tmp) / "watchlist.csv").exists())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_local_store -v`
Expected: FAIL with `ModuleNotFoundError` or missing `LocalStore`

- [ ] **Step 3: Write minimal implementation**

```python
from pathlib import Path


class LocalStore:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)

    def ensure_files(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "holdings.csv").write_text("bond_code,bond_name,quantity,note\n", encoding="utf-8")
        (self.data_dir / "watchlist.csv").write_text("bond_code,bond_name,note\n", encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_local_store -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_local_store.py local_store.py
git commit -m "test: add csv storage bootstrap"
```

### Task 2: Add tested loading and normalization for holdings and watchlist

**Files:**
- Modify: `D:\Project\Quantitative Trading\tests\test_local_store.py`
- Modify: `D:\Project\Quantitative Trading\local_store.py`

- [ ] **Step 1: Write the failing tests**

```python
    def test_load_holdings_and_watchlist_normalizes_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "holdings.csv").write_text(
                "bond_code,bond_name,quantity,note\n110001,Alpha,3,test\n",
                encoding="utf-8",
            )
            (base / "watchlist.csv").write_text(
                "bond_code,bond_name,note\n127001,Beta,watch\n",
                encoding="utf-8",
            )

            store = LocalStore(base)
            holdings = store.load_holdings()
            watchlist = store.load_watchlist()

            self.assertEqual(holdings[0]["bond_code"], "110001")
            self.assertEqual(watchlist[0]["bond_code"], "127001")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_local_store -v`
Expected: FAIL because `load_holdings` and `load_watchlist` do not exist yet

- [ ] **Step 3: Write minimal implementation**

```python
import csv

    def load_holdings(self):
        return self._read_rows("holdings.csv")

    def load_watchlist(self):
        return self._read_rows("watchlist.csv")

    def _read_rows(self, filename):
        path = self.data_dir / filename
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = []
            for row in reader:
                row["bond_code"] = str(row.get("bond_code", "")).strip().zfill(6)
                rows.append(row)
            return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_local_store -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_local_store.py local_store.py
git commit -m "feat: load holdings and watchlist from csv"
```

### Task 3: Create tests for scanner ranking, filtering, and tagging

**Files:**
- Create: `D:\Project\Quantitative Trading\tests\test_assistant_core.py`
- Create: `D:\Project\Quantitative Trading\assistant_core.py`

- [ ] **Step 1: Write the failing tests**

```python
import unittest

import pandas as pd

from assistant_core import rank_market_rows


class RankMarketRowsTests(unittest.TestCase):
    def test_filters_price_and_redeem_then_sorts_and_tags(self):
        market_df = pd.DataFrame(
            [
                {"bond_code": "110001", "bond_name": "A", "price": 120.0, "premium_pct": 10.0},
                {"bond_code": "110002", "bond_name": "B", "price": 131.0, "premium_pct": 1.0},
                {"bond_code": "110003", "bond_name": "C", "price": 118.0, "premium_pct": 15.0},
            ]
        )

        rows = rank_market_rows(
            market_df=market_df,
            redeem_codes={"110003"},
            holdings={"110001"},
            watchlist={"110003"},
            max_price=130.0,
            max_premium_pct=None,
            top_n=20,
            only_unheld=False,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["bond_code"], "110001")
        self.assertTrue(rows[0]["is_held"])
        self.assertFalse(rows[0]["is_watchlist"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_assistant_core -v`
Expected: FAIL with missing module or missing `rank_market_rows`

- [ ] **Step 3: Write minimal implementation**

```python
def rank_market_rows(...):
    # filter, score, sort, and tag
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_assistant_core -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_assistant_core.py assistant_core.py
git commit -m "feat: rank and tag market candidates"
```

### Task 4: Add degraded-source detection and summary metadata

**Files:**
- Modify: `D:\Project\Quantitative Trading\tests\test_assistant_core.py`
- Modify: `D:\Project\Quantitative Trading\assistant_core.py`

- [ ] **Step 1: Write the failing test**

```python
    def test_marks_snapshot_as_degraded_when_market_rows_are_too_low(self):
        summary = build_scan_summary(
            source_name="集思录 bond_cb_jsl",
            market_count=30,
            redeem_count=5,
            candidate_rows=[],
            min_expected_market_rows=100,
        )

        self.assertTrue(summary["is_degraded"])
        self.assertIn("30", summary["warning"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_assistant_core -v`
Expected: FAIL because `build_scan_summary` does not exist yet

- [ ] **Step 3: Write minimal implementation**

```python
def build_scan_summary(...):
    if market_count < min_expected_market_rows:
        return {"is_degraded": True, "warning": ...}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_assistant_core -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_assistant_core.py assistant_core.py
git commit -m "feat: surface degraded market source warnings"
```

### Task 5: Reconnect the Flet UI to the new services

**Files:**
- Modify: `D:\Project\Quantitative Trading\mod.py`
- Modify: `D:\Project\Quantitative Trading\assistant_core.py`
- Modify: `D:\Project\Quantitative Trading\local_store.py`

- [ ] **Step 1: Write the failing integration smoke test**

```python
import unittest

from assistant_core import PersonalQuantAssistant


class PersonalQuantAssistantTests(unittest.TestCase):
    def test_scan_result_contains_rows_and_summary_keys(self):
        assistant = PersonalQuantAssistant(...)
        result = assistant.scan_market()
        self.assertIn("rows", result)
        self.assertIn("warning", result)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_assistant_core -v`
Expected: FAIL because the service class does not exist yet

- [ ] **Step 3: Write minimal implementation and UI wiring**

```python
class PersonalQuantAssistant:
    def scan_market(self):
        ...
```

Update `mod.py` so the page shows:

- filter controls
- warning area
- held/watchlist columns
- CSV bootstrap hint in status text

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest discover -s tests -v`
Expected: PASS

- [ ] **Step 5: Run the app smoke test**

Run: `python -c "from mod import main; print('import ok')"`
Expected: prints `import ok`

- [ ] **Step 6: Commit**

```bash
git add mod.py assistant_core.py local_store.py tests
git commit -m "feat: ship local-first personal quant assistant phase 1"
```
