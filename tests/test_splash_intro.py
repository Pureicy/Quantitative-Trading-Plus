import unittest
from types import SimpleNamespace

import flet as ft

from splash_intro import SplashScreen


class SplashScreenTests(unittest.TestCase):
    def test_build_contains_warp_animation_and_status_sequence(self):
        calls = []
        splash = SplashScreen(
            SimpleNamespace(update=lambda: None),
            on_finish=lambda: calls.append("finished"),
        )

        overlay = splash.build()

        self.assertTrue(splash.active)
        self.assertEqual(len(splash.status_lines), 4)
        self.assertIsInstance(overlay.content.controls[1], ft.Stack)
        self.assertGreater(splash.ray_target_length, 1400)
        self.assertEqual(overlay.content.controls[2].content.src, "assets/intro/intro-hud.webp")

        splash.skip()

        self.assertFalse(splash.active)
        self.assertTrue(splash.finished)
        self.assertEqual(calls, ["finished"])

    def test_finish_is_idempotent(self):
        calls = []
        splash = SplashScreen(
            SimpleNamespace(update=lambda: None),
            on_finish=lambda: calls.append("finished"),
        )

        splash.finish()
        splash.finish()

        self.assertEqual(calls, ["finished"])


if __name__ == "__main__":
    unittest.main()
