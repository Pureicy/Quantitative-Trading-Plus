import unittest
from datetime import datetime

import pandas as pd

from assistant_core import (
    PersonalQuantAssistant,
    build_snapshot_review,
    build_scan_summary,
    build_spot_cov_snapshot,
    choose_preferred_market_snapshot,
    rank_market_rows,
)


HELD_GROUP = "\u6301\u4ed3\u89c2\u5bdf"
UNHELD_GROUP = "\u65b0\u673a\u4f1a"
PROFIT_STATUS = "\u6d6e\u76c8"
NEAR_COST_SIGNAL = "\u63a5\u8fd1\u6210\u672c"
FOCUS_SIGNAL = "\u91cd\u70b9\u673a\u4f1a"
LOSS_SIGNAL = "\u6d6e\u4e8f\u5173\u6ce8"


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
            holdings={
                "110001": {
                    "bond_code": "110001",
                    "bond_name": "A",
                    "quantity": 2.0,
                    "avg_cost": 118.5,
                    "note": "core",
                }
            },
            watchlist={"110003"},
            max_price=130.0,
            max_premium_pct=None,
            top_n=20,
            only_unheld=False,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["bond_code"], "110001")
        self.assertAlmostEqual(rows[0]["double_low_score"], 130.0)
        self.assertTrue(rows[0]["is_held"])
        self.assertEqual(rows[0]["held_quantity"], 2.0)
        self.assertEqual(rows[0]["held_avg_cost"], 118.5)
        self.assertEqual(rows[0]["cost_diff"], 1.5)
        self.assertEqual(rows[0]["cost_diff_pct"], 1.27)
        self.assertEqual(rows[0]["holding_status"], PROFIT_STATUS)
        self.assertEqual(rows[0]["position_group"], HELD_GROUP)
        self.assertEqual(rows[0]["signal_label"], NEAR_COST_SIGNAL)
        self.assertFalse(rows[0]["is_watchlist"])

    def test_only_unheld_and_max_premium_filters_are_applied(self):
        market_df = pd.DataFrame(
            [
                {"bond_code": "110001", "bond_name": "A", "price": 120.0, "premium_pct": 10.0},
                {"bond_code": "110004", "bond_name": "D", "price": 119.0, "premium_pct": 30.0},
                {"bond_code": "110005", "bond_name": "E", "price": 117.0, "premium_pct": 8.0},
            ]
        )

        rows = rank_market_rows(
            market_df=market_df,
            redeem_codes=set(),
            holdings={"110001": {"bond_code": "110001", "quantity": 1.0, "avg_cost": None, "note": ""}},
            watchlist={"110004"},
            max_price=130.0,
            max_premium_pct=20.0,
            top_n=20,
            only_unheld=True,
        )

        self.assertEqual([row["bond_code"] for row in rows], ["110005"])
        self.assertIsNone(rows[0]["cost_diff"])
        self.assertEqual(rows[0]["holding_status"], "")
        self.assertEqual(rows[0]["position_group"], UNHELD_GROUP)
        self.assertEqual(rows[0]["signal_label"], "")

    def test_position_filter_can_return_only_held_rows(self):
        market_df = pd.DataFrame(
            [
                {"bond_code": "110001", "bond_name": "A", "price": 120.0, "premium_pct": 10.0},
                {"bond_code": "110005", "bond_name": "E", "price": 117.0, "premium_pct": 8.0},
            ]
        )

        rows = rank_market_rows(
            market_df=market_df,
            redeem_codes=set(),
            holdings={"110001": {"bond_code": "110001", "quantity": 1.0, "avg_cost": 119.0, "note": ""}},
            watchlist=set(),
            max_price=130.0,
            max_premium_pct=None,
            top_n=20,
            only_unheld=False,
            position_filter="held",
        )

        self.assertEqual([row["bond_code"] for row in rows], ["110001"])

    def test_position_filter_can_return_only_watchlist_rows(self):
        market_df = pd.DataFrame(
            [
                {"bond_code": "110001", "bond_name": "A", "price": 120.0, "premium_pct": 10.0},
                {"bond_code": "110005", "bond_name": "E", "price": 117.0, "premium_pct": 8.0},
            ]
        )

        rows = rank_market_rows(
            market_df=market_df,
            redeem_codes=set(),
            holdings={},
            watchlist={"110005"},
            max_price=130.0,
            max_premium_pct=None,
            top_n=20,
            only_unheld=False,
            position_filter="watchlist",
        )

        self.assertEqual([row["bond_code"] for row in rows], ["110005"])

    def test_marks_unheld_low_score_rows_as_focus_opportunities(self):
        market_df = pd.DataFrame(
            [
                {"bond_code": "110010", "bond_name": "F", "price": 100.0, "premium_pct": 15.0},
            ]
        )

        rows = rank_market_rows(
            market_df=market_df,
            redeem_codes=set(),
            holdings={},
            watchlist=set(),
            max_price=130.0,
            max_premium_pct=None,
            top_n=20,
            only_unheld=False,
        )

        self.assertEqual(rows[0]["double_low_score"], 115.0)
        self.assertEqual(rows[0]["signal_label"], FOCUS_SIGNAL)

    def test_marks_deep_loss_held_rows_as_risk_watch(self):
        market_df = pd.DataFrame(
            [
                {"bond_code": "110020", "bond_name": "G", "price": 90.0, "premium_pct": 20.0},
            ]
        )

        rows = rank_market_rows(
            market_df=market_df,
            redeem_codes=set(),
            holdings={"110020": {"bond_code": "110020", "quantity": 1.0, "avg_cost": 100.0, "note": ""}},
            watchlist=set(),
            max_price=130.0,
            max_premium_pct=None,
            top_n=20,
            only_unheld=False,
        )

        self.assertEqual(rows[0]["cost_diff_pct"], -10.0)
        self.assertEqual(rows[0]["signal_label"], LOSS_SIGNAL)

    def test_signal_rows_are_sorted_ahead_of_non_signal_rows(self):
        market_df = pd.DataFrame(
            [
                {"bond_code": "110030", "bond_name": "H", "price": 95.0, "premium_pct": 30.0},
                {"bond_code": "110031", "bond_name": "I", "price": 100.0, "premium_pct": 15.0},
            ]
        )

        rows = rank_market_rows(
            market_df=market_df,
            redeem_codes=set(),
            holdings={},
            watchlist=set(),
            max_price=130.0,
            max_premium_pct=None,
            top_n=20,
            only_unheld=False,
        )

        self.assertEqual(rows[0]["bond_code"], "110031")
        self.assertEqual(rows[0]["signal_label"], FOCUS_SIGNAL)
        self.assertEqual(rows[1]["bond_code"], "110030")
        self.assertEqual(rows[1]["signal_label"], "")

    def test_excludes_retired_bond_names_from_candidates(self):
        market_df = pd.DataFrame(
            [
                {"bond_code": "404004", "bond_name": "\u6c47\u8f66\u9000\u503a", "price": 58.07, "premium_pct": -1705.0},
                {"bond_code": "111013", "bond_name": "\u65b0\u6e2f\u8f6c\u503a", "price": 122.78, "premium_pct": -51.0},
            ]
        )

        rows = rank_market_rows(
            market_df=market_df,
            redeem_codes=set(),
            holdings={},
            watchlist=set(),
            max_price=130.0,
            max_premium_pct=None,
            top_n=20,
            only_unheld=False,
        )

        self.assertEqual([row["bond_code"] for row in rows], ["111013"])


class BuildScanSummaryTests(unittest.TestCase):
    def test_marks_snapshot_as_degraded_when_market_rows_are_too_low(self):
        summary = build_scan_summary(
            source_name="\u96c6\u601d\u5f55 bond_cb_jsl",
            market_count=30,
            redeem_count=5,
            candidate_rows=[{"bond_code": "110001"}],
            min_expected_market_rows=100,
            source_errors=["bond_cov_comparison: timeout"],
        )

        self.assertTrue(summary["is_degraded"])
        self.assertIn("30", summary["warning"])
        self.assertIn("bond_cov_comparison", summary["warning"])


class BuildSpotCovSnapshotTests(unittest.TestCase):
    def test_merges_active_spot_rows_with_premium_data_and_filters_invalid_rows(self):
        spot_df = pd.DataFrame(
            [
                {"symbol": "sh110001", "name": "Alpha\u8f6c\u503a", "trade": 101.5},
                {"symbol": "sh110002", "name": "Beta\u5b9a\u8f6c", "trade": 99.0},
                {"symbol": "sh110003", "name": "Gamma\u8f6c\u503a", "trade": 0.0},
            ]
        )
        cov_df = pd.DataFrame(
            [
                {"债券代码": "110001", "债券简称": "Alpha\u8f6c\u503a", "债现价": 100.0, "转股溢价率": 12.0},
                {"债券代码": "110002", "债券简称": "Beta\u5b9a\u8f6c", "债现价": 99.0, "转股溢价率": 10.0},
                {"债券代码": "110003", "债券简称": "Gamma\u8f6c\u503a", "债现价": 88.0, "转股溢价率": 8.0},
            ]
        )

        snapshot = build_spot_cov_snapshot(spot_df, cov_df)

        self.assertEqual(len(snapshot), 1)
        self.assertEqual(snapshot.iloc[0]["bond_code"], "110001")
        self.assertEqual(snapshot.iloc[0]["bond_name"], "Alpha\u8f6c\u503a")
        self.assertAlmostEqual(snapshot.iloc[0]["price"], 101.5)
        self.assertAlmostEqual(snapshot.iloc[0]["premium_pct"], 12.0)


class ChoosePreferredMarketSnapshotTests(unittest.TestCase):
    def test_prefers_snapshot_with_more_rows(self):
        smaller = pd.DataFrame([{"bond_code": "110001", "bond_name": "A", "price": 100.0, "premium_pct": 10.0}])
        larger = pd.DataFrame(
            [
                {"bond_code": "110001", "bond_name": "A", "price": 100.0, "premium_pct": 10.0},
                {"bond_code": "110002", "bond_name": "B", "price": 101.0, "premium_pct": 11.0},
            ]
        )

        selected_df, selected_name, errors = choose_preferred_market_snapshot(
            [
                (smaller, "\u96c6\u601d\u5f55 bond_cb_jsl", []),
                (larger, "\u514d\u8d39\u5408\u5e76\u5feb\u7167 bond_zh_hs_cov_spot+bond_zh_cov", ["bond_cb_jsl partial"]),
            ]
        )

        self.assertEqual(selected_name, "\u514d\u8d39\u5408\u5e76\u5feb\u7167 bond_zh_hs_cov_spot+bond_zh_cov")
        self.assertEqual(len(selected_df), 2)
        self.assertEqual(errors, ["bond_cb_jsl partial"])


class PersonalQuantAssistantTests(unittest.TestCase):
    def test_scan_market_returns_rows_summary_and_personal_tags(self):
        class FakeStore:
            def __init__(self):
                self.saved_snapshot = None

            def ensure_files(self):
                return None

            def load_holdings(self):
                return [{"bond_code": "110001", "bond_name": "Alpha", "quantity": 2.0, "avg_cost": 119.2, "note": ""}]

            def load_watchlist(self):
                return [{"bond_code": "110003", "bond_name": "Gamma", "note": "watch"}]

            def save_scan_snapshot(self, snapshot):
                self.saved_snapshot = snapshot
                return "data/snapshots/2026-05-23/scan-120000.json"

            def load_recent_snapshots(self, limit=5):
                return [
                    {
                        "scan_time": "2026-05-23 12:00:00",
                        "snapshot_path": "data/snapshots/2026-05-23/scan-120000.json",
                        "rows": snapshot_rows(self.saved_snapshot),
                    },
                    {
                        "scan_time": "2026-05-22 12:00:00",
                        "snapshot_path": "data/snapshots/2026-05-22/scan-120000.json",
                        "rows": [
                            {
                                "bond_code": "110003",
                                "bond_name": "Gamma",
                                "rank": 1,
                                "double_low_score": 127.0,
                            }
                        ],
                    },
                ]

        class FakeGateway:
            def fetch_market_snapshot(self):
                market_df = pd.DataFrame(
                    [
                        {"bond_code": "110001", "bond_name": "Alpha", "price": 120.0, "premium_pct": 10.0},
                        {"bond_code": "110003", "bond_name": "Gamma", "price": 118.0, "premium_pct": 8.0},
                    ]
                )
                return market_df, "fake_source", []

            def fetch_redeem_codes(self):
                return set()

        store = FakeStore()
        assistant = PersonalQuantAssistant(
            market_gateway=FakeGateway(),
            local_store=store,
            now_provider=lambda: datetime(2026, 5, 23, 12, 0, 0),
            max_price=130.0,
            min_expected_market_rows=100,
        )

        progress_events = []
        result = assistant.scan_market(
            max_premium_pct=20.0,
            top_n=10,
            only_unheld=False,
            progress_callback=progress_events.append,
        )

        self.assertEqual(result["source_name"], "fake_source")
        self.assertEqual(result["scan_time"], "2026-05-23 12:00:00")
        self.assertEqual([row["bond_code"] for row in result["rows"]], ["110001", "110003"])
        self.assertTrue(result["rows"][0]["is_held"])
        self.assertEqual(result["rows"][0]["held_quantity"], 2.0)
        self.assertEqual(result["rows"][0]["held_avg_cost"], 119.2)
        self.assertEqual(result["rows"][0]["cost_diff"], 0.8)
        self.assertEqual(result["rows"][0]["cost_diff_pct"], 0.67)
        self.assertEqual(result["rows"][0]["holding_status"], PROFIT_STATUS)
        self.assertEqual(result["rows"][0]["signal_label"], NEAR_COST_SIGNAL)
        self.assertTrue(result["rows"][1]["is_watchlist"])
        self.assertEqual(result["held_candidate_count"], 1)
        self.assertEqual(result["unheld_candidate_count"], 1)
        self.assertEqual(result["signal_candidate_count"], 1)
        self.assertEqual(result["snapshot_path"], "data/snapshots/2026-05-23/scan-120000.json")
        self.assertEqual(result["snapshot_review"]["new_count"], 1)
        self.assertEqual(result["snapshot_review"]["changed_count"], 1)
        self.assertEqual(len(result["recent_snapshots"]), 2)
        self.assertIsNotNone(store.saved_snapshot)
        self.assertTrue(result["is_degraded"])
        self.assertEqual(
            [item.percent for item in progress_events],
            sorted(item.percent for item in progress_events),
        )
        self.assertEqual(progress_events[-1].stage, "PUBLISH")
        self.assertEqual(progress_events[-1].percent, 100)

    def test_scan_market_can_filter_to_only_new_opportunities(self):
        class FakeStore:
            def ensure_files(self):
                return None

            def load_holdings(self):
                return [{"bond_code": "110001", "bond_name": "Alpha", "quantity": 2.0, "avg_cost": 119.2, "note": ""}]

            def load_watchlist(self):
                return []

            def save_scan_snapshot(self, snapshot):
                return "data/snapshots/2026-05-23/scan-120000.json"

        class FakeGateway:
            def fetch_market_snapshot(self):
                market_df = pd.DataFrame(
                    [
                        {"bond_code": "110001", "bond_name": "Alpha", "price": 120.0, "premium_pct": 10.0},
                        {"bond_code": "110003", "bond_name": "Gamma", "price": 118.0, "premium_pct": 8.0},
                    ]
                )
                return market_df, "fake_source", []

            def fetch_redeem_codes(self):
                return set()

        assistant = PersonalQuantAssistant(
            market_gateway=FakeGateway(),
            local_store=FakeStore(),
            now_provider=lambda: datetime(2026, 5, 23, 12, 0, 0),
            max_price=130.0,
            min_expected_market_rows=100,
        )

        result = assistant.scan_market(
            max_premium_pct=20.0,
            top_n=10,
            only_unheld=False,
            position_filter="unheld",
        )

        self.assertEqual([row["bond_code"] for row in result["rows"]], ["110003"])

    def test_add_to_watchlist_delegates_to_local_store(self):
        class FakeStore:
            def __init__(self):
                self.calls = []

            def ensure_files(self):
                return None

            def load_holdings(self):
                return []

            def load_watchlist(self):
                return []

            def upsert_watchlist(self, bond_code, bond_name, note=""):
                self.calls.append((bond_code, bond_name, note))

        class FakeGateway:
            def fetch_market_snapshot(self):
                return pd.DataFrame(), "fake", []

            def fetch_redeem_codes(self):
                return set()

        store = FakeStore()
        assistant = PersonalQuantAssistant(
            market_gateway=FakeGateway(),
            local_store=store,
            now_provider=lambda: datetime(2026, 5, 23, 12, 0, 0),
        )

        assistant.add_to_watchlist("127041", "Hongya")

        self.assertEqual(store.calls, [("127041", "Hongya", "")])

    def test_remove_from_watchlist_delegates_to_local_store(self):
        class FakeStore:
            def __init__(self):
                self.removed_codes = []

            def ensure_files(self):
                return None

            def load_holdings(self):
                return []

            def load_watchlist(self):
                return []

            def remove_from_watchlist(self, bond_code):
                self.removed_codes.append(bond_code)

        class FakeGateway:
            def fetch_market_snapshot(self):
                return pd.DataFrame(), "fake", []

            def fetch_redeem_codes(self):
                return set()

        store = FakeStore()
        assistant = PersonalQuantAssistant(
            market_gateway=FakeGateway(),
            local_store=store,
            now_provider=lambda: datetime(2026, 5, 23, 12, 0, 0),
        )

        assistant.remove_from_watchlist("127041")

        self.assertEqual(store.removed_codes, ["127041"])

    def test_get_watchlist_returns_local_rows(self):
        class FakeStore:
            def ensure_files(self):
                return None

            def load_holdings(self):
                return []

            def load_watchlist(self):
                return [{"bond_code": "127041", "bond_name": "Hongya", "note": "core"}]

        class FakeGateway:
            def fetch_market_snapshot(self):
                return pd.DataFrame(), "fake", []

            def fetch_redeem_codes(self):
                return set()

        assistant = PersonalQuantAssistant(
            market_gateway=FakeGateway(),
            local_store=FakeStore(),
            now_provider=lambda: datetime(2026, 5, 23, 12, 0, 0),
        )

        rows = assistant.get_watchlist()

        self.assertEqual(rows, [{"bond_code": "127041", "bond_name": "Hongya", "note": "core"}])

    def test_add_or_update_holding_delegates_to_local_store(self):
        class FakeStore:
            def __init__(self):
                self.calls = []

            def ensure_files(self):
                return None

            def load_holdings(self):
                return []

            def load_watchlist(self):
                return []

            def upsert_holding(self, bond_code, bond_name, quantity, avg_cost, note=""):
                self.calls.append((bond_code, bond_name, quantity, avg_cost, note))

        class FakeGateway:
            def fetch_market_snapshot(self):
                return pd.DataFrame(), "fake", []

            def fetch_redeem_codes(self):
                return set()

        store = FakeStore()
        assistant = PersonalQuantAssistant(
            market_gateway=FakeGateway(),
            local_store=store,
            now_provider=lambda: datetime(2026, 5, 23, 12, 0, 0),
        )

        assistant.add_or_update_holding("127041", "Hongya", 2.0, 121.5, "core")

        self.assertEqual(store.calls, [("127041", "Hongya", 2.0, 121.5, "core")])

    def test_clear_holding_delegates_zero_quantity_to_local_store(self):
        class FakeStore:
            def __init__(self):
                self.calls = []

            def ensure_files(self):
                return None

            def load_holdings(self):
                return []

            def load_watchlist(self):
                return []

            def upsert_holding(self, bond_code, bond_name, quantity, avg_cost, note=""):
                self.calls.append((bond_code, bond_name, quantity, avg_cost, note))

        class FakeGateway:
            def fetch_market_snapshot(self):
                return pd.DataFrame(), "fake", []

            def fetch_redeem_codes(self):
                return set()

        store = FakeStore()
        assistant = PersonalQuantAssistant(
            market_gateway=FakeGateway(),
            local_store=store,
            now_provider=lambda: datetime(2026, 5, 23, 12, 0, 0),
        )

        assistant.clear_holding("127041", "Hongya")

        self.assertEqual(store.calls, [("127041", "Hongya", 0.0, None, "")])

    def test_get_recent_snapshot_review_uses_latest_two_snapshots(self):
        class FakeStore:
            def ensure_files(self):
                return None

            def load_recent_snapshots(self, limit=5):
                return [
                    {
                        "scan_time": "2026-05-24 09:30:00",
                        "snapshot_path": "data/snapshots/2026-05-24/scan-093000.json",
                        "rows": [
                            {
                                "bond_code": "110001",
                                "bond_name": "Alpha",
                                "rank": 1,
                                "double_low_score": 100.0,
                            }
                        ],
                    },
                    {
                        "scan_time": "2026-05-23 09:30:00",
                        "snapshot_path": "data/snapshots/2026-05-23/scan-093000.json",
                        "rows": [
                            {
                                "bond_code": "110002",
                                "bond_name": "Beta",
                                "rank": 1,
                                "double_low_score": 101.0,
                            }
                        ],
                    },
                ]

            def load_holdings(self):
                return []

            def load_watchlist(self):
                return []

        class FakeGateway:
            def fetch_market_snapshot(self):
                return pd.DataFrame(), "fake", []

            def fetch_redeem_codes(self):
                return set()

        assistant = PersonalQuantAssistant(
            market_gateway=FakeGateway(),
            local_store=FakeStore(),
            now_provider=lambda: datetime(2026, 5, 24, 12, 0, 0),
        )

        review_bundle = assistant.get_recent_snapshot_review(limit=5)

        self.assertEqual(len(review_bundle["recent_snapshots"]), 2)
        self.assertEqual(review_bundle["snapshot_review"]["new_count"], 1)
        self.assertEqual(review_bundle["snapshot_review"]["dropped_count"], 1)


class BuildSnapshotReviewTests(unittest.TestCase):
    def test_detects_new_dropped_and_rank_changed_rows(self):
        previous = {
            "scan_time": "2026-05-23 09:30:00",
            "rows": [
                {"bond_code": "110010", "bond_name": "Old Bond", "rank": 1, "double_low_score": 101.0},
                {"bond_code": "110020", "bond_name": "Move Up", "rank": 3, "double_low_score": 105.0},
                {"bond_code": "110030", "bond_name": "Move Down", "rank": 2, "double_low_score": 103.0},
            ],
        }
        current = {
            "scan_time": "2026-05-24 09:30:00",
            "rows": [
                {"bond_code": "110001", "bond_name": "New Bond", "rank": 1, "double_low_score": 99.5},
                {"bond_code": "110020", "bond_name": "Move Up", "rank": 2, "double_low_score": 102.0},
                {"bond_code": "110030", "bond_name": "Move Down", "rank": 3, "double_low_score": 104.5},
            ],
        }

        review = build_snapshot_review(current, previous)

        self.assertEqual(review["current_scan_time"], "2026-05-24 09:30:00")
        self.assertEqual(review["previous_scan_time"], "2026-05-23 09:30:00")
        self.assertEqual(review["new_count"], 1)
        self.assertEqual(review["dropped_count"], 1)
        self.assertEqual(review["changed_count"], 2)
        self.assertEqual(review["new_rows"][0]["bond_code"], "110001")
        self.assertEqual(review["dropped_rows"][0]["bond_code"], "110010")
        self.assertEqual(review["changed_rows"][0]["bond_code"], "110020")
        self.assertEqual(review["changed_rows"][0]["rank_delta"], 1)
        self.assertEqual(review["changed_rows"][0]["score_delta"], -3.0)
        self.assertEqual(review["changed_rows"][1]["bond_code"], "110030")
        self.assertEqual(review["changed_rows"][1]["rank_delta"], -1)
        self.assertEqual(review["changed_rows"][1]["score_delta"], 1.5)

    def test_returns_empty_review_when_previous_snapshot_missing(self):
        current = {
            "scan_time": "2026-05-24 09:30:00",
            "rows": [{"bond_code": "110001", "bond_name": "New Bond", "rank": 1, "double_low_score": 99.5}],
        }

        review = build_snapshot_review(current, None)

        self.assertEqual(review["new_count"], 0)
        self.assertEqual(review["dropped_count"], 0)
        self.assertEqual(review["changed_count"], 0)
        self.assertEqual(review["changed_rows"], [])
        self.assertIn("首次", review["summary"])


def snapshot_rows(snapshot):
    return list((snapshot or {}).get("rows", []))


if __name__ == "__main__":
    unittest.main()
