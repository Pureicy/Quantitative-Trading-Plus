import unittest
import flet as ft

from mod import (
    _border_all,
    _border_side,
    _button_content_kwargs,
    _card_bgcolor_kwargs,
    _set_button_content,
)


class ModCompatibilityTests(unittest.TestCase):
    def test_card_background_uses_bgcolor_keyword(self):
        self.assertEqual(_card_bgcolor_kwargs("amber"), {"bgcolor": "amber"})

    def test_border_side_builds_flet_border_side(self):
        side = _border_side(2, "blue")

        self.assertEqual(type(side).__name__, "BorderSide")
        self.assertEqual(side.width, 2)
        self.assertEqual(side.color, "blue")

    def test_border_all_builds_full_flet_border(self):
        border = _border_all(1, "gray")

        self.assertEqual(type(border).__name__, "Border")
        self.assertEqual(border.top.width, 1)
        self.assertEqual(border.right.color, "gray")
        self.assertEqual(border.bottom.width, 1)
        self.assertEqual(border.left.color, "gray")

    def test_button_content_uses_content_keyword(self):
        self.assertEqual(_button_content_kwargs("scan"), {"content": "scan"})

    def test_set_button_content_updates_button_label(self):
        button = ft.ElevatedButton(content="before")

        _set_button_content(button, "after")

        self.assertEqual(button.content, "after")


if __name__ == "__main__":
    unittest.main()
