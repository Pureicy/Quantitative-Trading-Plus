import unittest
from types import SimpleNamespace

import flet as ft

from console_particles import (
    BACKGROUND_PARTICLE_COUNT,
    CARD_PARTICLE_COUNT,
    ConsoleParticleController,
    begin_card_frame,
)
from ui_theme import DARK, card, with_alpha


class ConsoleParticleTests(unittest.TestCase):
    def test_alpha_helper_converts_flet_argb(self):
        self.assertEqual(with_alpha("#1C1B19", 0.5), "#801C1B19")
        self.assertEqual(with_alpha("transparent", 0.5), "transparent")

    def test_client_side_particle_counts_are_fixed(self):
        self.assertEqual(BACKGROUND_PARTICLE_COUNT, 4000)
        self.assertEqual(CARD_PARTICLE_COUNT, 36)

    def test_console_parallax_clamps_ndc_and_disables_on_narrow_screen(self):
        page = SimpleNamespace(
            platform="windows",
            client_user_agent="desktop",
            width=1200,
        )
        controller = ConsoleParticleController(page, quality="performance")

        controller.set_parallax_position(1200, 600, 1200, 600)

        self.assertEqual(controller.target_x, 0.5)
        self.assertAlmostEqual(controller.target_y, -0.3)
        controller.set_parallax_position(350, 300, 700, 600)
        self.assertEqual((controller.target_x, controller.target_y), (0.0, 0.0))

    def test_card_builder_adds_animated_client_image(self):
        begin_card_frame(True, "performance")

        surface = card(DARK, ft.Text("card body"))

        layer = surface.content.content
        self.assertIsInstance(layer, ft.Stack)
        self.assertIsInstance(layer.controls[0], ft.Image)
        self.assertTrue(layer.controls[0].visible)
        self.assertFalse(layer.controls[1].visible)

    def test_card_power_mode_uses_static_image(self):
        begin_card_frame(True, "power")

        surface = card(DARK, ft.Text("card body"))

        layer = surface.content.content
        self.assertFalse(layer.controls[0].visible)
        self.assertTrue(layer.controls[1].visible)

    def test_card_hover_lifts_and_restores_surface(self):
        begin_card_frame(True)
        surface = card(DARK, ft.Text("card body"))

        surface.on_hover(SimpleNamespace(data="true"))

        self.assertEqual(surface.offset.y, -0.025)
        surface.on_hover(SimpleNamespace(data="false"))
        self.assertEqual(surface.offset.y, 0)

    def test_card_particle_decoration_can_be_disabled(self):
        begin_card_frame(False)

        surface = card(DARK, ft.Text("card body"))

        self.assertIsInstance(surface.content.content, ft.Text)


if __name__ == "__main__":
    unittest.main()
