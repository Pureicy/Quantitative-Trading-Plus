import unittest
from types import SimpleNamespace

from assistant_core import ScanProgress
from scan_hud import ScanHUD


class ScanHUDTests(unittest.TestCase):
    def setUp(self):
        self.page = SimpleNamespace(update=lambda: None)
        self.hud = ScanHUD(self.page)
        self.hud.begin()
        self.overlay = self.hud.build()

    def test_market_stage_marks_current_row_as_scanning(self):
        self.hud.apply_progress(
            ScanProgress(
                stage="MARKET_MATRIX",
                label="拉取市场快照",
                percent=24,
                detail="source 2 / 3",
            )
        )

        self.assertEqual(self.hud.rows["MARKET_MATRIX"]["status"].value, "SCANNING")
        self.assertTrue(self.hud.rows["MARKET_MATRIX"]["spinner"].visible)
        self.assertEqual(self.hud.rows["REDEEM_SHIELD"]["status"].value, "WAITING")

    def test_advancing_stage_marks_previous_row_done(self):
        self.hud.metrics["market_count"] = 1832
        self.hud.apply_progress(
            ScanProgress(
                stage="REDEEM_SHIELD",
                label="同步强赎名单",
                percent=51,
            )
        )

        self.assertEqual(self.hud.rows["MARKET_MATRIX"]["status"].value, "1832 只")
        self.assertEqual(self.hud.rows["REDEEM_SHIELD"]["status"].value, "SCANNING")

    def test_complete_and_error_states_are_recoverable(self):
        self.hud.apply_progress(
            ScanProgress(
                stage="MARKET_MATRIX",
                label="拉取市场快照",
                percent=36,
            )
        )
        self.hud.show_error("network timeout")
        self.assertEqual(self.hud.stage_text.value, "SCAN INTERRUPTED")
        self.assertEqual(self.hud.rows["MARKET_MATRIX"]["status"].value, "FAILED")
        self.assertTrue(self.hud.error_actions.visible)

        self.hud.show_complete()
        self.assertEqual(self.hud.stage_text.value, "SCAN COMPLETE")
        self.assertEqual(self.hud.progress_bar.value, 1)


if __name__ == "__main__":
    unittest.main()
