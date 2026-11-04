from __future__ import annotations

import argparse
import csv
import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable

from assistant_core import DEFAULT_TOP_N, PersonalQuantAssistant
from local_store import LocalStore


DEPENDENCIES = (
    ("flet", "flet"),
    ("flet-desktop", "flet_desktop"),
    ("pandas", "pandas"),
    ("akshare", "akshare"),
)


def ensure_local_data_files(data_dir: str | Path) -> None:
    LocalStore(Path(data_dir)).ensure_files()


def build_environment_report(
    data_dir: str | Path,
    module_loader: Callable[[str], object] | None = None,
) -> dict:
    loader = module_loader or importlib.import_module
    base_dir = Path(data_dir)
    ensure_local_data_files(base_dir)

    dependency_report = {}
    all_installed = True
    for package_name, module_name in DEPENDENCIES:
        try:
            module = loader(module_name)
            dependency_report[package_name] = {
                "installed": True,
                "version": getattr(module, "__version__", "unknown"),
            }
        except ImportError:
            dependency_report[package_name] = {
                "installed": False,
                "version": None,
            }
            all_installed = False

    data_files = {
        "holdings.csv": (base_dir / "holdings.csv").exists(),
        "watchlist.csv": (base_dir / "watchlist.csv").exists(),
    }
    snapshot_count = len(list((base_dir / "snapshots").rglob("scan-*.json"))) if (base_dir / "snapshots").exists() else 0

    return {
        "ready": all_installed and all(data_files.values()),
        "dependencies": dependency_report,
        "data_files": data_files,
        "snapshot_count": snapshot_count,
        "launch_command": get_launch_command(Path(__file__).resolve().parent),
    }


def format_environment_report(report: dict) -> str:
    lines = ["Quant Assistant Environment Report", ""]
    lines.append("Dependencies:")
    for module_name, status in report["dependencies"].items():
        if status["installed"]:
            lines.append(f"- {module_name}: OK ({status['version']})")
        else:
            lines.append(f"- {module_name}: MISSING")

    lines.append("")
    lines.append("Data Files:")
    for file_name, exists in report["data_files"].items():
        lines.append(f"- {file_name}: {'OK' if exists else 'MISSING'}")

    lines.append("")
    lines.append(f"Snapshots: {report['snapshot_count']}")
    lines.append(f"Ready: {'YES' if report['ready'] else 'NO'}")
    lines.append(f"Launch: {report['launch_command']}")
    return "\n".join(lines)


def format_backup_report(result: dict) -> str:
    lines = ["Quant Assistant Data Backup", ""]
    lines.append(f"backup_name: {result.get('backup_name', '-')}")
    lines.append(f"backup_dir: {result.get('backup_dir', '-')}")
    files = result.get("files", {})
    for name, path in files.items():
        lines.append(f"{name}: {path}")
    return "\n".join(lines)


def format_backup_list_report(backups: list[dict]) -> str:
    lines = ["Quant Assistant Backup List", ""]
    if not backups:
        lines.append("No backups found.")
        return "\n".join(lines)

    for index, item in enumerate(backups, start=1):
        lines.append(f"{index}. {item.get('backup_name', '-')} | {item.get('backup_dir', '-')}")
    return "\n".join(lines)


def format_restore_report(result: dict) -> str:
    lines = ["Quant Assistant Data Restore", ""]
    lines.append(f"restored_from: {result.get('restored_from', '-')}")
    for name, path in result.get("files", {}).items():
        lines.append(f"{name}: {path}")
    return "\n".join(lines)


def format_state_export_report(result: dict) -> str:
    lines = ["Quant Assistant State Export", ""]
    lines.append(f"export_dir: {result.get('export_dir', '-')}")
    for name, path in result.get("files", {}).items():
        lines.append(f"{name}: {path}")
    return "\n".join(lines)


def format_state_summary_report(result: dict) -> str:
    lines = ["Quant Assistant State Summary", ""]
    lines.append(f"holdings_count: {result.get('holdings_count', 0)}")
    lines.append(f"watchlist_count: {result.get('watchlist_count', 0)}")
    lines.append(f"latest_snapshot_path: {result.get('latest_snapshot_path', '-') or '-'}")
    lines.append(f"latest_backup_dir: {result.get('latest_backup_dir', '-') or '-'}")
    return "\n".join(lines)


def format_snapshot_history_report(items: list[dict]) -> str:
    lines = ["Quant Assistant Snapshot History", ""]
    if not items:
        lines.append("No snapshots found.")
        return "\n".join(lines)

    for index, item in enumerate(items, start=1):
        lines.append(
            f"{index}. {item.get('scan_time', '-')} | "
            f"candidate_count={item.get('candidate_count', 0)} | "
            f"{item.get('snapshot_path', '-')}"
        )
    return "\n".join(lines)


def get_launcher_executable(launcher_executable: str | None = None) -> str:
    if launcher_executable:
        return launcher_executable

    executable_path = Path(sys.executable)
    pythonw_path = executable_path.with_name("pythonw.exe")
    if pythonw_path.exists():
        return str(pythonw_path)
    return str(executable_path)


def build_action_error(action: str, exc: Exception) -> dict:
    return {
        "action": action,
        "error": str(exc),
    }


def format_action_error_report(payload: dict) -> str:
    lines = ["Quant Assistant Error", ""]
    lines.append(f"action: {payload.get('action', '-')}")
    lines.append(f"error: {payload.get('error', '-')}")
    return "\n".join(lines)


def get_launch_command(
    base_dir: str | Path,
    launcher_executable: str | None = None,
) -> str:
    project_dir = Path(base_dir)
    target = project_dir / "mod.py"
    launcher = get_launcher_executable(launcher_executable)
    return f'"{launcher}" "{target}"'


def format_scan_report(result: dict) -> str:
    lines = ["Quant Assistant Scan Report", ""]
    lines.append(f"source_name: {result.get('source_name', '-')}")
    lines.append(f"scan_time: {result.get('scan_time', '-')}")
    lines.append(f"candidate_count: {result.get('candidate_count', 0)}")
    lines.append(f"held_candidate_count: {result.get('held_candidate_count', 0)}")
    lines.append(f"unheld_candidate_count: {result.get('unheld_candidate_count', 0)}")
    lines.append(f"signal_candidate_count: {result.get('signal_candidate_count', 0)}")
    lines.append(f"snapshot_path: {result.get('snapshot_path', '-')}")
    lines.append(f"snapshot_review: {result.get('snapshot_review', {}).get('summary', '-')}")

    warning = result.get("warning", "")
    if warning:
        lines.append(f"warning: {warning}")

    lines.append("")
    lines.append("Top Candidates:")
    rows = result.get("rows", [])
    if not rows:
        lines.append("- none")
        return "\n".join(lines)

    for row in rows:
        lines.append(
            " | ".join(
                [
                    f"rank={row.get('rank', '-')}",
                    f"code={row.get('bond_code', '-')}",
                    f"name={row.get('bond_name', '-')}",
                    f"price={row.get('price', '-')}",
                    f"premium={row.get('premium_pct', '-')}",
                    f"score={row.get('double_low_score', '-')}",
                    f"group={row.get('position_group', '-')}",
                    f"signal={row.get('signal_label', '-') or '-'}",
                ]
            )
        )
    return "\n".join(lines)


def export_scan_rows_csv(result: dict, output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    rows = result.get("rows", [])
    headers = [
        "rank",
        "bond_code",
        "bond_name",
        "price",
        "premium_pct",
        "double_low_score",
        "position_group",
        "signal_label",
        "is_watchlist",
        "is_held",
        "held_quantity",
        "held_avg_cost",
        "cost_diff",
        "cost_diff_pct",
        "holding_status",
    ]

    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})
    return target


def export_latest_snapshot_summary(store: LocalStore, output_path: str | Path) -> dict:
    recent_snapshots = store.load_recent_snapshots(limit=1)
    if not recent_snapshots:
        raise FileNotFoundError("No scan snapshots available")

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    summary_text = format_scan_report(recent_snapshots[0])
    target.write_text(summary_text, encoding="utf-8")
    return {
        "output_path": str(target),
    }


def run_console_scan(
    assistant: PersonalQuantAssistant,
    top_n: int = DEFAULT_TOP_N,
    max_premium_pct: float | None = None,
    only_unheld: bool = False,
    position_filter: str = "all",
    export_csv_path: str | Path | None = None,
) -> str:
    result = assistant.scan_market(
        top_n=top_n,
        max_premium_pct=max_premium_pct,
        only_unheld=only_unheld,
        position_filter=position_filter,
    )
    report_text = format_scan_report(result)
    if export_csv_path:
        exported_path = export_scan_rows_csv(result, export_csv_path)
        report_text += f"\nexport_csv: {exported_path}"
    return report_text


def run_data_backup(store: LocalStore) -> str:
    backup_result = store.create_data_backup()
    return format_backup_report(backup_result)


def run_backup_list(store: LocalStore, limit: int = 10) -> str:
    backups = store.list_data_backups(limit=limit)
    return format_backup_list_report(backups)


def run_data_restore(store: LocalStore, backup_dir: str | Path) -> str:
    restore_result = store.restore_data_backup(backup_dir)
    return format_restore_report(restore_result)


def run_restore_latest(store: LocalStore) -> str:
    restore_result = store.restore_latest_data_backup()
    return format_restore_report(restore_result)


def run_export_current_state(store: LocalStore, export_dir: str | Path) -> str:
    export_result = store.export_current_state(export_dir)
    return format_state_export_report(export_result)


def run_state_summary(store: LocalStore) -> str:
    summary = store.get_state_summary()
    return format_state_summary_report(summary)


def run_export_latest_summary(store: LocalStore, output_path: str | Path) -> str:
    result = export_latest_snapshot_summary(store, output_path)
    return f"latest_summary: {result['output_path']}"


def run_snapshot_history(store: LocalStore, limit: int = 5) -> str:
    items = store.load_recent_snapshots(limit=limit)
    return format_snapshot_history_report(items)


def launch_app(base_dir: str | Path) -> int:
    project_dir = Path(base_dir)
    command = [get_launcher_executable(), str(project_dir / "mod.py")]
    subprocess.Popen(command, cwd=str(project_dir))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Personal quantitative assistant bootstrap")
    parser.add_argument("--prepare", action="store_true", help="Ensure local data files exist and print report")
    parser.add_argument("--launch", action="store_true", help="Launch the Flet app after preparation")
    parser.add_argument("--scan", action="store_true", help="Run a terminal scan and print the result")
    parser.add_argument("--backup-data", action="store_true", help="Backup holdings and watchlist CSV files")
    parser.add_argument("--list-backups", action="store_true", help="List local backup directories")
    parser.add_argument("--restore-data", type=str, default=None, help="Restore holdings and watchlist from a backup directory")
    parser.add_argument("--restore-latest", action="store_true", help="Restore holdings and watchlist from the latest backup")
    parser.add_argument("--export-data", type=str, default=None, help="Export current holdings and watchlist to a directory")
    parser.add_argument("--state-summary", action="store_true", help="Show a compact local state summary")
    parser.add_argument("--export-latest-summary", type=str, default=None, help="Export the latest scan summary to a text file")
    parser.add_argument("--list-snapshots", action="store_true", help="List recent local scan snapshots")
    parser.add_argument("--json", action="store_true", help="Print scan result in JSON when used with --scan")
    parser.add_argument("--export-csv", type=str, default=None, help="Export scan rows to a CSV file")
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N, help="Number of candidate rows to show")
    parser.add_argument("--max-premium", type=float, default=None, help="Maximum premium percentage filter")
    parser.add_argument("--only-unheld", action="store_true", help="Show only unheld candidates")
    parser.add_argument(
        "--position-filter",
        choices=("all", "unheld", "held", "watchlist"),
        default="all",
        help="Candidate view filter",
    )
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parent
    data_dir = project_dir / "data"
    ensure_local_data_files(data_dir)
    report = build_environment_report(data_dir)
    print(format_environment_report(report))

    store = LocalStore(data_dir)

    if args.backup_data:
        print("")
        print(run_data_backup(store))

    if args.list_backups:
        print("")
        print(run_backup_list(store, limit=10))

    if args.restore_data:
        print("")
        print(run_data_restore(store, args.restore_data))

    if args.restore_latest:
        print("")
        print(run_restore_latest(store))

    if args.export_data:
        print("")
        print(run_export_current_state(store, args.export_data))

    if args.state_summary:
        print("")
        print(run_state_summary(store))

    if args.export_latest_summary:
        print("")
        print(run_export_latest_summary(store, args.export_latest_summary))

    if args.list_snapshots:
        print("")
        print(run_snapshot_history(store, limit=10))

    if args.scan:
        assistant = PersonalQuantAssistant(data_dir=data_dir)
        try:
            result = assistant.scan_market(
                top_n=args.top_n,
                max_premium_pct=args.max_premium,
                only_unheld=args.only_unheld,
                position_filter=args.position_filter,
            )
            exported_path = None
            if args.export_csv:
                exported_path = export_scan_rows_csv(result, args.export_csv)
            print("")
            if args.json:
                payload = dict(result)
                if exported_path:
                    payload["export_csv"] = str(exported_path)
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                text = format_scan_report(result)
                if exported_path:
                    text += f"\nexport_csv: {exported_path}"
                print(text)
        except Exception as exc:
            print("")
            error_payload = build_action_error("scan", exc)
            if args.json:
                print(json.dumps(error_payload, ensure_ascii=False, indent=2))
            else:
                print(format_action_error_report(error_payload))
            return 1

    if args.launch:
        return launch_app(project_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
