import tempfile
import types
import unittest
from pathlib import Path

from app_bootstrap import (
    build_action_error,
    build_environment_report,
    ensure_local_data_files,
    export_scan_rows_csv,
    export_latest_snapshot_summary,
    format_action_error_report,
    format_snapshot_history_report,
    format_state_export_report,
    format_backup_report,
    format_backup_list_report,
    format_restore_report,
    format_state_summary_report,
    format_scan_report,
    get_launch_command,
    run_backup_list,
    run_data_backup,
    run_data_restore,
    run_export_current_state,
    run_export_latest_summary,
    run_snapshot_history,
    run_state_summary,
    run_restore_latest,
    run_console_scan,
)


class AppBootstrapTests(unittest.TestCase):
    def test_build_environment_report_marks_installed_and_missing_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            ensure_local_data_files(base)

            def fake_loader(module_name: str):
                if module_name == "flet":
                    return types.SimpleNamespace(__version__="1.0.0")
                if module_name == "flet_desktop":
                    raise ImportError(module_name)
                if module_name == "pandas":
                    return types.SimpleNamespace(__version__="2.0.0")
                raise ImportError(module_name)

            report = build_environment_report(base, module_loader=fake_loader)

            self.assertFalse(report["ready"])
            self.assertEqual(report["dependencies"]["flet"]["version"], "1.0.0")
            self.assertFalse(report["dependencies"]["flet-desktop"]["installed"])
            self.assertTrue(report["dependencies"]["pandas"]["installed"])
            self.assertFalse(report["dependencies"]["akshare"]["installed"])
            self.assertTrue(report["data_files"]["holdings.csv"])
            self.assertTrue(report["data_files"]["watchlist.csv"])

    def test_ensure_local_data_files_creates_required_csv_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)

            ensure_local_data_files(base)

            self.assertTrue((base / "holdings.csv").exists())
            self.assertTrue((base / "watchlist.csv").exists())

    def test_get_launch_command_points_to_mod_py(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)

            command = get_launch_command(base, launcher_executable="C:/Python/pythonw.exe")

            self.assertIn("pythonw.exe", command)
            self.assertIn("mod.py", command)
            self.assertNotIn("-m flet run", command)

    def test_format_scan_report_includes_summary_and_candidate_rows(self):
        report = format_scan_report(
            {
                "source_name": "fake_source",
                "scan_time": "2026-05-24 13:00:00",
                "candidate_count": 2,
                "held_candidate_count": 1,
                "unheld_candidate_count": 1,
                "signal_candidate_count": 1,
                "snapshot_path": "data/snapshots/2026-05-24/scan-130000.json",
                "snapshot_review": {"summary": "new 1"},
                "rows": [
                    {
                        "rank": 1,
                        "bond_code": "110001",
                        "bond_name": "Alpha",
                        "price": 100.0,
                        "premium_pct": 10.0,
                        "double_low_score": 110.0,
                        "position_group": "新机会",
                        "signal_label": "重点机会",
                    },
                    {
                        "rank": 2,
                        "bond_code": "110002",
                        "bond_name": "Beta",
                        "price": 101.0,
                        "premium_pct": 11.0,
                        "double_low_score": 112.0,
                        "position_group": "持仓观察",
                        "signal_label": "",
                    },
                ],
            }
        )

        self.assertIn("fake_source", report)
        self.assertIn("110001", report)
        self.assertIn("Alpha", report)
        self.assertIn("new 1", report)

    def test_run_console_scan_forwards_filter_arguments(self):
        class FakeAssistant:
            def __init__(self):
                self.calls = []

            def scan_market(self, **kwargs):
                self.calls.append(kwargs)
                return {
                    "source_name": "fake_source",
                    "scan_time": "2026-05-24 13:00:00",
                    "candidate_count": 0,
                    "held_candidate_count": 0,
                    "unheld_candidate_count": 0,
                    "signal_candidate_count": 0,
                    "snapshot_path": "data/snapshots/2026-05-24/scan-130000.json",
                    "snapshot_review": {"summary": "首次生成快照"},
                    "rows": [],
                }

        assistant = FakeAssistant()

        text = run_console_scan(
            assistant,
            top_n=15,
            max_premium_pct=20.0,
            only_unheld=True,
            position_filter="watchlist",
        )

        self.assertEqual(
            assistant.calls,
            [
                {
                    "top_n": 15,
                    "max_premium_pct": 20.0,
                    "only_unheld": True,
                    "position_filter": "watchlist",
                }
            ],
        )
        self.assertIn("candidate_count", text)

    def test_export_scan_rows_csv_writes_candidate_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            target = base / "scan.csv"

            export_scan_rows_csv(
                {
                    "rows": [
                        {
                            "rank": 1,
                            "bond_code": "110001",
                            "bond_name": "Alpha",
                            "price": 100.0,
                            "premium_pct": 10.0,
                            "double_low_score": 110.0,
                            "position_group": "新机会",
                            "signal_label": "重点机会",
                            "is_watchlist": False,
                            "is_held": False,
                        }
                    ]
                },
                target,
            )

            text = target.read_text(encoding="utf-8")
            self.assertIn("bond_code", text)
            self.assertIn("110001", text)
            self.assertIn("Alpha", text)

    def test_run_console_scan_can_export_csv_when_path_is_given(self):
        class FakeAssistant:
            def scan_market(self, **kwargs):
                return {
                    "source_name": "fake_source",
                    "scan_time": "2026-05-24 13:00:00",
                    "candidate_count": 1,
                    "held_candidate_count": 0,
                    "unheld_candidate_count": 1,
                    "signal_candidate_count": 1,
                    "snapshot_path": "data/snapshots/2026-05-24/scan-130000.json",
                    "snapshot_review": {"summary": "首次生成快照"},
                    "rows": [
                        {
                            "rank": 1,
                            "bond_code": "110001",
                            "bond_name": "Alpha",
                            "price": 100.0,
                            "premium_pct": 10.0,
                            "double_low_score": 110.0,
                            "position_group": "新机会",
                            "signal_label": "重点机会",
                            "is_watchlist": False,
                            "is_held": False,
                        }
                    ],
                }

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "scan.csv"

            text = run_console_scan(
                FakeAssistant(),
                export_csv_path=target,
            )

            self.assertTrue(target.exists())
            self.assertIn("export_csv", text)

    def test_format_backup_report_includes_backup_paths(self):
        text = format_backup_report(
            {
                "backup_name": "backup-131500",
                "backup_dir": "data/backups/2026-05-24/backup-131500",
                "files": {
                    "holdings.csv": "data/backups/2026-05-24/backup-131500/holdings.csv",
                    "watchlist.csv": "data/backups/2026-05-24/backup-131500/watchlist.csv",
                },
            }
        )

        self.assertIn("backup-131500", text)
        self.assertIn("holdings.csv", text)
        self.assertIn("watchlist.csv", text)

    def test_run_data_backup_returns_formatted_text(self):
        class FakeStore:
            def create_data_backup(self):
                return {
                    "backup_name": "backup-131500",
                    "backup_dir": "data/backups/2026-05-24/backup-131500",
                    "files": {
                        "holdings.csv": "data/backups/2026-05-24/backup-131500/holdings.csv",
                        "watchlist.csv": "data/backups/2026-05-24/backup-131500/watchlist.csv",
                    },
                }

        text = run_data_backup(FakeStore())

        self.assertIn("backup-131500", text)
        self.assertIn("backup_dir", text)

    def test_format_restore_report_includes_restore_paths(self):
        text = format_restore_report(
            {
                "restored_from": "data/backups/2026-05-24/backup-131500",
                "files": {
                    "holdings.csv": "data/holdings.csv",
                    "watchlist.csv": "data/watchlist.csv",
                },
            }
        )

        self.assertIn("restored_from", text)
        self.assertIn("holdings.csv", text)
        self.assertIn("watchlist.csv", text)

    def test_run_data_restore_returns_formatted_text(self):
        class FakeStore:
            def restore_data_backup(self, backup_dir):
                return {
                    "restored_from": backup_dir,
                    "files": {
                        "holdings.csv": "data/holdings.csv",
                        "watchlist.csv": "data/watchlist.csv",
                    },
                }

        text = run_data_restore(FakeStore(), "data/backups/2026-05-24/backup-131500")

        self.assertIn("restored_from", text)
        self.assertIn("backup-131500", text)

    def test_format_backup_list_report_includes_backup_entries(self):
        text = format_backup_list_report(
            [
                {
                    "backup_name": "backup-132000",
                    "backup_dir": "data/backups/2026-05-24/backup-132000",
                },
                {
                    "backup_name": "backup-131500",
                    "backup_dir": "data/backups/2026-05-24/backup-131500",
                },
            ]
        )

        self.assertIn("backup-132000", text)
        self.assertIn("backup-131500", text)

    def test_run_backup_list_returns_formatted_text(self):
        class FakeStore:
            def list_data_backups(self, limit=10):
                return [
                    {
                        "backup_name": "backup-132000",
                        "backup_dir": "data/backups/2026-05-24/backup-132000",
                    }
                ]

        text = run_backup_list(FakeStore(), limit=10)

        self.assertIn("backup-132000", text)

    def test_run_restore_latest_returns_formatted_text(self):
        class FakeStore:
            def restore_latest_data_backup(self):
                return {
                    "restored_from": "data/backups/2026-05-24/backup-132000",
                    "files": {
                        "holdings.csv": "data/holdings.csv",
                        "watchlist.csv": "data/watchlist.csv",
                    },
                }

        text = run_restore_latest(FakeStore())

        self.assertIn("backup-132000", text)
        self.assertIn("restored_from", text)

    def test_format_state_export_report_includes_export_paths(self):
        text = format_state_export_report(
            {
                "export_dir": "exports/state",
                "files": {
                    "holdings.csv": "exports/state/holdings.csv",
                    "watchlist.csv": "exports/state/watchlist.csv",
                },
            }
        )

        self.assertIn("export_dir", text)
        self.assertIn("holdings.csv", text)
        self.assertIn("watchlist.csv", text)

    def test_run_export_current_state_returns_formatted_text(self):
        class FakeStore:
            def export_current_state(self, export_dir):
                return {
                    "export_dir": str(export_dir),
                    "files": {
                        "holdings.csv": f"{export_dir}/holdings.csv",
                        "watchlist.csv": f"{export_dir}/watchlist.csv",
                    },
                }

        text = run_export_current_state(FakeStore(), "exports/state")

        self.assertIn("exports/state", text)
        self.assertIn("holdings.csv", text)

    def test_format_state_summary_report_includes_summary_values(self):
        text = format_state_summary_report(
            {
                "holdings_count": 2,
                "watchlist_count": 3,
                "latest_snapshot_path": "data/snapshots/2026-05-24/scan-133000.json",
                "latest_backup_dir": "data/backups/2026-05-24/backup-133100",
            }
        )

        self.assertIn("holdings_count: 2", text)
        self.assertIn("watchlist_count: 3", text)
        self.assertIn("scan-133000.json", text)
        self.assertIn("backup-133100", text)

    def test_run_state_summary_returns_formatted_text(self):
        class FakeStore:
            def get_state_summary(self):
                return {
                    "holdings_count": 2,
                    "watchlist_count": 3,
                    "latest_snapshot_path": "data/snapshots/2026-05-24/scan-133000.json",
                    "latest_backup_dir": "data/backups/2026-05-24/backup-133100",
                }

        text = run_state_summary(FakeStore())

        self.assertIn("holdings_count: 2", text)
        self.assertIn("backup-133100", text)

    def test_export_latest_snapshot_summary_writes_text_file(self):
        class FakeStore:
            def load_recent_snapshots(self, limit=1):
                return [
                    {
                        "source_name": "fake_source",
                        "scan_time": "2026-05-24 13:40:00",
                        "candidate_count": 1,
                        "held_candidate_count": 0,
                        "unheld_candidate_count": 1,
                        "signal_candidate_count": 1,
                        "snapshot_path": "snapshots/2026-05-24/scan-134000.json",
                        "snapshot_review": {"summary": "首次生成快照"},
                        "rows": [
                            {
                                "rank": 1,
                                "bond_code": "110001",
                                "bond_name": "Alpha",
                                "price": 100.0,
                                "premium_pct": 10.0,
                                "double_low_score": 110.0,
                                "position_group": "新机会",
                                "signal_label": "重点机会",
                            }
                        ],
                    }
                ]

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "latest-summary.txt"

            result = export_latest_snapshot_summary(FakeStore(), target)

            self.assertEqual(str(target), result["output_path"])
            self.assertTrue(target.exists())
            text = target.read_text(encoding="utf-8")
            self.assertIn("Quant Assistant Scan Report", text)
            self.assertIn("110001", text)

    def test_run_export_latest_summary_returns_formatted_text(self):
        class FakeStore:
            def load_recent_snapshots(self, limit=1):
                return [
                    {
                        "source_name": "fake_source",
                        "scan_time": "2026-05-24 13:40:00",
                        "candidate_count": 0,
                        "held_candidate_count": 0,
                        "unheld_candidate_count": 0,
                        "signal_candidate_count": 0,
                        "snapshot_path": "snapshots/2026-05-24/scan-134000.json",
                        "snapshot_review": {"summary": "首次生成快照"},
                        "rows": [],
                    }
                ]

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "latest-summary.txt"

            text = run_export_latest_summary(FakeStore(), target)

            self.assertIn("latest_summary", text)
            self.assertIn(str(target), text)

    def test_format_snapshot_history_report_includes_rows(self):
        text = format_snapshot_history_report(
            [
                {
                    "scan_time": "2026-05-24 13:40:00",
                    "candidate_count": 5,
                    "snapshot_path": "snapshots/2026-05-24/scan-134000.json",
                },
                {
                    "scan_time": "2026-05-24 13:30:00",
                    "candidate_count": 3,
                    "snapshot_path": "snapshots/2026-05-24/scan-133000.json",
                },
            ]
        )

        self.assertIn("2026-05-24 13:40:00", text)
        self.assertIn("candidate_count=5", text)
        self.assertIn("scan-133000.json", text)

    def test_run_snapshot_history_returns_formatted_text(self):
        class FakeStore:
            def load_recent_snapshots(self, limit=5):
                return [
                    {
                        "scan_time": "2026-05-24 13:40:00",
                        "candidate_count": 5,
                        "snapshot_path": "snapshots/2026-05-24/scan-134000.json",
                    }
                ]

        text = run_snapshot_history(FakeStore(), limit=5)

        self.assertIn("2026-05-24 13:40:00", text)
        self.assertIn("candidate_count=5", text)

    def test_format_action_error_report_includes_action_and_message(self):
        payload = build_action_error("scan", RuntimeError("network blocked"))

        text = format_action_error_report(payload)

        self.assertIn("Quant Assistant Error", text)
        self.assertIn("action: scan", text)
        self.assertIn("error: network blocked", text)


if __name__ == "__main__":
    unittest.main()
