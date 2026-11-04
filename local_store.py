import csv
import shutil
import json
from datetime import datetime
from pathlib import Path


class LocalStore:
    HOLDINGS_HEADERS = ["bond_code", "bond_name", "quantity", "avg_cost", "note"]
    LEGACY_HOLDINGS_HEADERS = ["bond_code", "bond_name", "quantity", "note"]
    WATCHLIST_HEADERS = ["bond_code", "bond_name", "note"]

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.holdings_path = self.data_dir / "holdings.csv"
        self.watchlist_path = self.data_dir / "watchlist.csv"
        self.snapshots_dir = self.data_dir / "snapshots"
        self.backups_dir = self.data_dir / "backups"

    def ensure_files(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._upgrade_legacy_holdings_file()
        self._ensure_file(self.holdings_path, self.HOLDINGS_HEADERS)
        self._ensure_file(self.watchlist_path, self.WATCHLIST_HEADERS)

    def load_holdings(self) -> list[dict]:
        return self._read_rows(self.holdings_path, self.HOLDINGS_HEADERS, parse_quantity=True)

    def load_watchlist(self) -> list[dict]:
        return self._read_rows(self.watchlist_path, self.WATCHLIST_HEADERS, parse_quantity=False)

    def upsert_holding(
        self,
        bond_code: str,
        bond_name: str,
        quantity: float,
        avg_cost: float | None,
        note: str = "",
    ) -> None:
        rows = self.load_holdings()
        normalized_code = str(bond_code).strip().zfill(6)
        normalized_name = str(bond_name).strip()
        normalized_quantity = float(quantity)
        normalized_avg_cost = None if avg_cost is None else float(avg_cost)
        normalized_note = str(note).strip()

        if normalized_quantity <= 0:
            remaining_rows = [row for row in rows if row["bond_code"] != normalized_code]
            self._write_rows(self.holdings_path, self.HOLDINGS_HEADERS, remaining_rows)
            return

        for row in rows:
            if row["bond_code"] == normalized_code:
                row["bond_name"] = normalized_name or row["bond_name"]
                row["quantity"] = normalized_quantity
                row["avg_cost"] = normalized_avg_cost
                row["note"] = normalized_note
                self._write_rows(self.holdings_path, self.HOLDINGS_HEADERS, rows)
                return

        rows.append(
            {
                "bond_code": normalized_code,
                "bond_name": normalized_name,
                "quantity": normalized_quantity,
                "avg_cost": normalized_avg_cost,
                "note": normalized_note,
            }
        )
        self._write_rows(self.holdings_path, self.HOLDINGS_HEADERS, rows)

    def upsert_watchlist(self, bond_code: str, bond_name: str, note: str = "") -> None:
        rows = self.load_watchlist()
        normalized_code = str(bond_code).strip().zfill(6)
        normalized_name = str(bond_name).strip()
        normalized_note = str(note).strip()

        for row in rows:
            if row["bond_code"] == normalized_code:
                if normalized_name:
                    row["bond_name"] = normalized_name
                if normalized_note and not row["note"]:
                    row["note"] = normalized_note
                self._write_rows(self.watchlist_path, self.WATCHLIST_HEADERS, rows)
                return

        rows.append(
            {
                "bond_code": normalized_code,
                "bond_name": normalized_name,
                "note": normalized_note,
            }
        )
        self._write_rows(self.watchlist_path, self.WATCHLIST_HEADERS, rows)

    def remove_from_watchlist(self, bond_code: str) -> None:
        rows = self.load_watchlist()
        normalized_code = str(bond_code).strip().zfill(6)
        remaining_rows = [row for row in rows if row["bond_code"] != normalized_code]
        self._write_rows(self.watchlist_path, self.WATCHLIST_HEADERS, remaining_rows)

    def save_scan_snapshot(self, snapshot: dict) -> Path:
        scan_time = str(snapshot.get("scan_time") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        date_part, _, time_part = scan_time.partition(" ")
        safe_time = (time_part or "000000").replace(":", "")
        target_dir = self.snapshots_dir / date_part
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"scan-{safe_time}.json"
        path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def load_recent_snapshots(self, limit: int = 5) -> list[dict]:
        snapshot_paths = self._list_snapshot_paths(limit=limit)
        snapshots = []
        for path in snapshot_paths:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["snapshot_path"] = str(path.relative_to(self.data_dir))
            snapshots.append(data)
        return snapshots

    def create_data_backup(self, now: datetime | None = None) -> dict:
        self.ensure_files()
        current_time = now or datetime.now()
        date_part = current_time.strftime("%Y-%m-%d")
        backup_name = current_time.strftime("backup-%H%M%S")
        backup_dir = self.backups_dir / date_part / backup_name
        backup_dir.mkdir(parents=True, exist_ok=True)

        holdings_target = backup_dir / "holdings.csv"
        watchlist_target = backup_dir / "watchlist.csv"
        shutil.copy2(self.holdings_path, holdings_target)
        shutil.copy2(self.watchlist_path, watchlist_target)

        return {
            "backup_name": backup_name,
            "backup_dir": str(backup_dir),
            "files": {
                "holdings.csv": str(holdings_target),
                "watchlist.csv": str(watchlist_target),
            },
        }

    def restore_data_backup(self, backup_dir: str | Path) -> dict:
        self.ensure_files()
        source_dir = Path(backup_dir)
        holdings_source = source_dir / "holdings.csv"
        watchlist_source = source_dir / "watchlist.csv"
        if not holdings_source.exists() or not watchlist_source.exists():
            raise FileNotFoundError(f"Backup files not found in {source_dir}")

        shutil.copy2(holdings_source, self.holdings_path)
        shutil.copy2(watchlist_source, self.watchlist_path)
        return {
            "restored_from": str(source_dir),
            "files": {
                "holdings.csv": str(self.holdings_path),
                "watchlist.csv": str(self.watchlist_path),
            },
        }

    def list_data_backups(self, limit: int = 10) -> list[dict]:
        if not self.backups_dir.exists():
            return []

        backup_dirs = sorted(
            [path for path in self.backups_dir.rglob("backup-*") if path.is_dir()],
            reverse=True,
        )
        items = []
        for path in backup_dirs[: max(0, int(limit))]:
            items.append(
                {
                    "backup_name": path.name,
                    "backup_dir": str(path),
                }
            )
        return items

    def restore_latest_data_backup(self) -> dict:
        backups = self.list_data_backups(limit=1)
        if not backups:
            raise FileNotFoundError("No local backups available")
        return self.restore_data_backup(backups[0]["backup_dir"])

    def export_current_state(self, export_dir: str | Path) -> dict:
        self.ensure_files()
        target_dir = Path(export_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        holdings_target = target_dir / "holdings.csv"
        watchlist_target = target_dir / "watchlist.csv"
        shutil.copy2(self.holdings_path, holdings_target)
        shutil.copy2(self.watchlist_path, watchlist_target)

        return {
            "export_dir": str(target_dir),
            "files": {
                "holdings.csv": str(holdings_target),
                "watchlist.csv": str(watchlist_target),
            },
        }

    def get_state_summary(self) -> dict:
        self.ensure_files()
        holdings = self.load_holdings()
        watchlist = self.load_watchlist()
        recent_snapshots = self.load_recent_snapshots(limit=1)
        recent_backups = self.list_data_backups(limit=1)

        return {
            "holdings_count": len(holdings),
            "watchlist_count": len(watchlist),
            "latest_snapshot_path": (
                str((self.data_dir / recent_snapshots[0]["snapshot_path"]).resolve())
                if recent_snapshots
                else ""
            ),
            "latest_backup_dir": recent_backups[0]["backup_dir"] if recent_backups else "",
        }

    def _ensure_file(self, path: Path, headers: list[str]) -> None:
        if path.exists():
            return
        path.write_text(",".join(headers) + "\n", encoding="utf-8")

    def _list_snapshot_paths(self, limit: int) -> list[Path]:
        if not self.snapshots_dir.exists():
            return []

        paths = sorted(self.snapshots_dir.rglob("scan-*.json"), reverse=True)
        return paths[: max(0, int(limit))]

    def _upgrade_legacy_holdings_file(self) -> None:
        if not self.holdings_path.exists():
            return

        with self.holdings_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            if fieldnames != self.LEGACY_HOLDINGS_HEADERS:
                return
            rows = list(reader)

        migrated_rows = []
        for row in rows:
            migrated_rows.append(
                {
                    "bond_code": (row.get("bond_code", "") or "").strip(),
                    "bond_name": (row.get("bond_name", "") or "").strip(),
                    "quantity": (row.get("quantity", "") or "").strip(),
                    "avg_cost": "",
                    "note": (row.get("note", "") or "").strip(),
                }
            )
        self._write_rows(self.holdings_path, self.HOLDINGS_HEADERS, migrated_rows)

    def _read_rows(self, path: Path, headers: list[str], parse_quantity: bool) -> list[dict]:
        if not path.exists():
            self.ensure_files()

        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            if parse_quantity and fieldnames == self.LEGACY_HOLDINGS_HEADERS:
                rows = []
                for row in reader:
                    normalized = {
                        "bond_code": str((row.get("bond_code", "") or "")).strip().zfill(6),
                        "bond_name": str((row.get("bond_name", "") or "")).strip(),
                        "quantity": float((row.get("quantity", "") or 0) or 0),
                        "avg_cost": None,
                        "note": str((row.get("note", "") or "")).strip(),
                    }
                    rows.append(normalized)
                return rows

            if fieldnames != headers:
                raise ValueError(
                    f"{path.name} columns must be {headers}, got {fieldnames}"
                )

            rows = []
            for row in reader:
                normalized = {key: (row.get(key, "") or "").strip() for key in headers}
                normalized["bond_code"] = normalized["bond_code"].zfill(6)
                if parse_quantity:
                    normalized["quantity"] = float(normalized["quantity"] or 0)
                    normalized["avg_cost"] = (
                        float(normalized["avg_cost"]) if normalized["avg_cost"] else None
                    )
                rows.append(normalized)
            return rows

    def _write_rows(self, path: Path, headers: list[str], rows: list[dict]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                writer.writerow({header: row.get(header, "") for header in headers})
