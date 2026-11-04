import tempfile
import unittest
from pathlib import Path
import json
from datetime import datetime

from local_store import LocalStore


class LocalStoreTests(unittest.TestCase):
    def test_creates_default_csv_files_with_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = LocalStore(base)

            store.ensure_files()

            self.assertEqual(
                (base / "holdings.csv").read_text(encoding="utf-8"),
                "bond_code,bond_name,quantity,avg_cost,note\n",
            )
            self.assertEqual(
                (base / "watchlist.csv").read_text(encoding="utf-8"),
                "bond_code,bond_name,note\n",
            )

    def test_load_holdings_and_watchlist_normalizes_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "holdings.csv").write_text(
                "bond_code,bond_name,quantity,avg_cost,note\n11001,Alpha,3,118.5,test\n",
                encoding="utf-8",
            )
            (base / "watchlist.csv").write_text(
                "bond_code,bond_name,note\n127001,Beta,watch\n",
                encoding="utf-8",
            )
            store = LocalStore(base)

            holdings = store.load_holdings()
            watchlist = store.load_watchlist()

            self.assertEqual(holdings[0]["bond_code"], "011001")
            self.assertEqual(holdings[0]["quantity"], 3.0)
            self.assertEqual(holdings[0]["avg_cost"], 118.5)
            self.assertEqual(watchlist[0]["bond_code"], "127001")

    def test_load_holdings_accepts_legacy_header_without_avg_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "holdings.csv").write_text(
                "bond_code,bond_name,quantity,note\n110001,Alpha,3,test\n",
                encoding="utf-8",
            )
            store = LocalStore(base)

            holdings = store.load_holdings()

            self.assertEqual(holdings[0]["bond_code"], "110001")
            self.assertEqual(holdings[0]["quantity"], 3.0)
            self.assertIsNone(holdings[0]["avg_cost"])

    def test_ensure_files_upgrades_legacy_holdings_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "holdings.csv").write_text(
                "bond_code,bond_name,quantity,note\n110001,Alpha,3,test\n",
                encoding="utf-8",
            )
            store = LocalStore(base)

            store.ensure_files()

            self.assertEqual(
                (base / "holdings.csv").read_text(encoding="utf-8"),
                "bond_code,bond_name,quantity,avg_cost,note\n110001,Alpha,3,,test\n",
            )

    def test_upsert_watchlist_appends_new_code_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = LocalStore(base)
            store.ensure_files()

            store.upsert_watchlist("127001", "Beta转债")
            store.upsert_watchlist("127001", "Beta转债")

            watchlist = store.load_watchlist()
            self.assertEqual(len(watchlist), 1)
            self.assertEqual(watchlist[0]["bond_code"], "127001")
            self.assertEqual(watchlist[0]["bond_name"], "Beta转债")


    def test_upsert_holding_creates_and_updates_single_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = LocalStore(base)
            store.ensure_files()

            store.upsert_holding("127041", "Alpha", 2, 121.5, "first")
            store.upsert_holding("127041", "Alpha", 3, 119.8, "updated")

            holdings = store.load_holdings()
            self.assertEqual(len(holdings), 1)
            self.assertEqual(holdings[0]["bond_code"], "127041")
            self.assertEqual(holdings[0]["quantity"], 3.0)
            self.assertEqual(holdings[0]["avg_cost"], 119.8)
            self.assertEqual(holdings[0]["note"], "updated")

    def test_upsert_holding_with_zero_quantity_removes_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = LocalStore(base)
            store.ensure_files()

            store.upsert_holding("127041", "Alpha", 2, 121.5, "first")
            store.upsert_holding("127041", "Alpha", 0, 121.5, "clear")

            holdings = store.load_holdings()
            self.assertEqual(holdings, [])

    def test_save_scan_snapshot_writes_json_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = LocalStore(base)
            snapshot = {
                "source_name": "fake_source",
                "scan_time": "2026-05-23 12:00:00",
                "candidate_count": 1,
                "rows": [{"bond_code": "110001", "bond_name": "Alpha"}],
            }

            path = store.save_scan_snapshot(snapshot)

            self.assertTrue(path.exists())
            self.assertEqual(path.parent.name, "2026-05-23")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["source_name"], "fake_source")
            self.assertEqual(data["rows"][0]["bond_code"], "110001")

    def test_load_recent_snapshots_returns_latest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = LocalStore(base)
            older = {
                "source_name": "fake_source",
                "scan_time": "2026-05-23 12:00:00",
                "candidate_count": 1,
                "rows": [{"bond_code": "110001", "bond_name": "Alpha", "rank": 1}],
            }
            newer = {
                "source_name": "fake_source",
                "scan_time": "2026-05-24 09:30:00",
                "candidate_count": 2,
                "rows": [{"bond_code": "110002", "bond_name": "Beta", "rank": 1}],
            }

            store.save_scan_snapshot(older)
            store.save_scan_snapshot(newer)

            recent = store.load_recent_snapshots(limit=5)

            self.assertEqual(len(recent), 2)
            self.assertEqual(recent[0]["scan_time"], "2026-05-24 09:30:00")
            self.assertEqual(recent[0]["snapshot_path"].replace("\\", "/"), "snapshots/2026-05-24/scan-093000.json")
            self.assertEqual(recent[1]["scan_time"], "2026-05-23 12:00:00")

    def test_load_recent_snapshots_respects_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = LocalStore(base)

            for day in ("2026-05-22", "2026-05-23", "2026-05-24"):
                store.save_scan_snapshot(
                    {
                        "source_name": "fake_source",
                        "scan_time": f"{day} 12:00:00",
                        "candidate_count": 1,
                        "rows": [{"bond_code": day[-2:], "bond_name": "Bond", "rank": 1}],
                    }
                )

            recent = store.load_recent_snapshots(limit=2)

            self.assertEqual(len(recent), 2)
            self.assertEqual(
                [item["scan_time"] for item in recent],
                ["2026-05-24 12:00:00", "2026-05-23 12:00:00"],
            )

    def test_remove_from_watchlist_deletes_matching_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = LocalStore(base)
            store.ensure_files()
            store.upsert_watchlist("127001", "Alpha")
            store.upsert_watchlist("127002", "Beta")

            store.remove_from_watchlist("127001")

            watchlist = store.load_watchlist()
            self.assertEqual(len(watchlist), 1)
            self.assertEqual(watchlist[0]["bond_code"], "127002")

    def test_create_data_backup_copies_holdings_and_watchlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = LocalStore(base)
            store.ensure_files()
            (base / "holdings.csv").write_text(
                "bond_code,bond_name,quantity,avg_cost,note\n110001,Alpha,2,120,core\n",
                encoding="utf-8",
            )
            (base / "watchlist.csv").write_text(
                "bond_code,bond_name,note\n127001,Beta,watch\n",
                encoding="utf-8",
            )

            backup = store.create_data_backup(now=datetime(2026, 5, 24, 13, 15, 0))

            self.assertEqual(backup["backup_name"], "backup-131500")
            self.assertTrue((Path(backup["backup_dir"]) / "holdings.csv").exists())
            self.assertTrue((Path(backup["backup_dir"]) / "watchlist.csv").exists())
            self.assertIn("110001", (Path(backup["backup_dir"]) / "holdings.csv").read_text(encoding="utf-8"))
            self.assertIn("127001", (Path(backup["backup_dir"]) / "watchlist.csv").read_text(encoding="utf-8"))

    def test_restore_data_backup_replaces_current_holdings_and_watchlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = LocalStore(base)
            store.ensure_files()
            (base / "holdings.csv").write_text(
                "bond_code,bond_name,quantity,avg_cost,note\n110001,Alpha,2,120,core\n",
                encoding="utf-8",
            )
            (base / "watchlist.csv").write_text(
                "bond_code,bond_name,note\n127001,Beta,watch\n",
                encoding="utf-8",
            )

            backup = store.create_data_backup(now=datetime(2026, 5, 24, 13, 20, 0))

            (base / "holdings.csv").write_text(
                "bond_code,bond_name,quantity,avg_cost,note\n110002,Gamma,1,99,test\n",
                encoding="utf-8",
            )
            (base / "watchlist.csv").write_text(
                "bond_code,bond_name,note\n127002,Delta,tmp\n",
                encoding="utf-8",
            )

            restore = store.restore_data_backup(backup["backup_dir"])

            self.assertEqual(restore["restored_from"], backup["backup_dir"])
            self.assertIn("110001", (base / "holdings.csv").read_text(encoding="utf-8"))
            self.assertIn("127001", (base / "watchlist.csv").read_text(encoding="utf-8"))

    def test_list_data_backups_returns_latest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = LocalStore(base)
            store.ensure_files()

            first = store.create_data_backup(now=datetime(2026, 5, 24, 13, 10, 0))
            second = store.create_data_backup(now=datetime(2026, 5, 24, 13, 20, 0))

            backups = store.list_data_backups(limit=5)

            self.assertEqual(len(backups), 2)
            self.assertEqual(backups[0]["backup_name"], second["backup_name"])
            self.assertEqual(backups[1]["backup_name"], first["backup_name"])

    def test_restore_latest_data_backup_uses_newest_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = LocalStore(base)
            store.ensure_files()
            (base / "holdings.csv").write_text(
                "bond_code,bond_name,quantity,avg_cost,note\n110001,Alpha,2,120,first\n",
                encoding="utf-8",
            )
            (base / "watchlist.csv").write_text(
                "bond_code,bond_name,note\n127001,Beta,first\n",
                encoding="utf-8",
            )
            store.create_data_backup(now=datetime(2026, 5, 24, 13, 10, 0))

            (base / "holdings.csv").write_text(
                "bond_code,bond_name,quantity,avg_cost,note\n110002,Gamma,3,121,second\n",
                encoding="utf-8",
            )
            (base / "watchlist.csv").write_text(
                "bond_code,bond_name,note\n127002,Delta,second\n",
                encoding="utf-8",
            )
            latest = store.create_data_backup(now=datetime(2026, 5, 24, 13, 20, 0))

            (base / "holdings.csv").write_text(
                "bond_code,bond_name,quantity,avg_cost,note\n110003,Temp,1,99,current\n",
                encoding="utf-8",
            )
            (base / "watchlist.csv").write_text(
                "bond_code,bond_name,note\n127003,Temp,current\n",
                encoding="utf-8",
            )

            restored = store.restore_latest_data_backup()

            self.assertEqual(restored["restored_from"], latest["backup_dir"])
            self.assertIn("110002", (base / "holdings.csv").read_text(encoding="utf-8"))
            self.assertIn("127002", (base / "watchlist.csv").read_text(encoding="utf-8"))

    def test_export_current_state_copies_holdings_and_watchlist_to_target_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            export_dir = base / "exports" / "state"
            store = LocalStore(base)
            store.ensure_files()
            (base / "holdings.csv").write_text(
                "bond_code,bond_name,quantity,avg_cost,note\n110001,Alpha,2,120,core\n",
                encoding="utf-8",
            )
            (base / "watchlist.csv").write_text(
                "bond_code,bond_name,note\n127001,Beta,watch\n",
                encoding="utf-8",
            )

            exported = store.export_current_state(export_dir)

            self.assertEqual(exported["export_dir"], str(export_dir))
            self.assertTrue((export_dir / "holdings.csv").exists())
            self.assertTrue((export_dir / "watchlist.csv").exists())
            self.assertIn("110001", (export_dir / "holdings.csv").read_text(encoding="utf-8"))
            self.assertIn("127001", (export_dir / "watchlist.csv").read_text(encoding="utf-8"))

    def test_get_state_summary_reports_counts_and_latest_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = LocalStore(base)
            store.ensure_files()
            (base / "holdings.csv").write_text(
                "bond_code,bond_name,quantity,avg_cost,note\n110001,Alpha,2,120,core\n110002,Beta,3,121,watch\n",
                encoding="utf-8",
            )
            (base / "watchlist.csv").write_text(
                "bond_code,bond_name,note\n127001,Gamma,watch\n127002,Delta,watch\n",
                encoding="utf-8",
            )
            snapshot = store.save_scan_snapshot(
                {
                    "scan_time": "2026-05-24 13:30:00",
                    "rows": [],
                }
            )
            backup = store.create_data_backup(now=datetime(2026, 5, 24, 13, 31, 0))

            summary = store.get_state_summary()

            self.assertEqual(summary["holdings_count"], 2)
            self.assertEqual(summary["watchlist_count"], 2)
            self.assertEqual(summary["latest_snapshot_path"], str(snapshot))
            self.assertEqual(summary["latest_backup_dir"], backup["backup_dir"])


if __name__ == "__main__":
    unittest.main()
