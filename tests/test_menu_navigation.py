import types
import unittest
from unittest.mock import patch

if __package__:
    from .menu_support import Element, MenuLabelsTestCase
else:
    from menu_support import Element, MenuLabelsTestCase


class NavigationTests(MenuLabelsTestCase):
    def test_global_start_uses_application_menu_bar(self):
        self.actions.menu_labels_show()
        self.assertEqual(self.visible, [self.file, self.edit])
        self.assertEqual(self.style, "names")
        self.cron.interval.assert_called_once_with("100ms", self.module._session.update)

    def test_numbers_follow_multiple_delayed_submenus(self):
        self.actions.menu_labels_show(False)
        self.labels.select(1)
        self.assertEqual(self.visible, [])
        self.module._session.update()
        self.assertTrue(self.module._session.waiting)
        self.menu = self.submenu()
        self.module._session.update()
        self.assertEqual(self.visible, self.menu.children)
        self.assertEqual(self.style, "numbers")
        self.labels.select(1)
        self.menu = self.submenu("Recent file")
        self.module._session.update()
        self.assertEqual(self.visible, self.menu.children)
        self.assertEqual(self.style, "numbers")
        self.assertEqual(self.selected, [1, 1])

    def test_titles_follow_submenus(self):
        self.actions.menu_labels_show()
        self.labels.select("File")
        self.menu = self.submenu()
        self.module._session.update()
        self.labels.select("Open Recent")
        self.menu = self.submenu("Recent file")
        self.module._session.update()
        self.assertEqual(self.style, "names")
        self.assertEqual(self.visible, self.menu.children)
        self.assertEqual(self.selected, ["File", "Open Recent"])

    def test_three_eight_five_activates_leaf_and_clears_labels(self):
        self.bar.children = [
            Element("AXMenuBarItem", "Apple"),
            Element("AXMenuBarItem", "App"),
            self.file,
        ]
        recent = Element("AXMenuItem", "Open Recent")
        recent.submenu = Element(
            "AXMenu",
            children=[Element("AXMenuItem", f"Recent {i}") for i in range(1, 6)],
        )
        self.file.submenu = Element(
            "AXMenu",
            children=[
                *[Element("AXMenuItem", f"Item {i}") for i in range(1, 8)],
                recent,
            ],
        )
        native = self.native

        def activate(name, *args):
            target = self.visible[int(args[0]) - 1] if name == "select" else None
            native(name, *args)
            if target is not None:
                self.menu = getattr(target, "submenu", None)

        self.native = activate
        self.actions.menu_labels_show(False)
        session = self.module._session
        for number in (3, 8, 5):
            self.labels.select(number)
            session.update()
            self.assertEqual(self.style, "numbers")
        for _ in range(14):
            session.update()
        self.assertEqual(self.selected, [3, 8, 5])
        self.assertEqual(self.visible, [])
        self.assertIsNone(session.job)
        self.notify.assert_not_called()

    def test_existing_open_menu_is_used(self):
        self.menu = self.submenu()
        self.actions.menu_labels_show(False)
        self.assertIs(self.module._session.container, self.menu)

    def test_numbered_menu_anchors_text_and_presses_its_logical_item(self):
        _, target = self.hoverable_menu()
        text = Element("AXStaticText", "Tools")
        text.attrs["AXFrame"] = types.SimpleNamespace(x=25, y=20, width=50, height=20)
        target.children = [text]

        self.actions.menu_labels_show(False)
        session = self.module._session

        self.assertEqual(self.visible, [text])
        self.assertEqual(session.targets, [target])
        self.labels.select(1)
        self.assertEqual(target.performed, ["AXPress"])
        self.assertEqual(self.selected, [])
        for _ in range(self.menu_session.MENU_HOVER_DELAY_TICKS):
            session.update()
        self.module.actions.mouse_move.assert_called_once_with(50, 35)

    def test_named_menu_keeps_its_original_label_and_native_selection(self):
        _, target = self.hoverable_menu()
        text = Element("AXStaticText", "Tools")
        text.attrs["AXFrame"] = types.SimpleNamespace(x=25, y=20, width=50, height=20)
        target.children = [text]

        self.actions.menu_labels_show()

        self.assertEqual(self.visible, [target])
        self.labels.select("Tools")
        self.assertEqual(self.selected, ["Tools"])
        self.assertEqual(target.performed, [])

    def test_select_rejects_menu_labels_after_the_menu_changes(self):
        self.menu = self.submenu()
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.menu = self.submenu("Another menu")

        self.labels.select(1)

        self.assertEqual(self.selected, [])
        self.assertTrue(session.stopped)
        self.assertIn("menu changed", self.notify.call_args.args[1].lower())

    def test_select_waits_for_the_previous_menu_transition(self):
        self.actions.menu_labels_show(False)
        self.labels.select(1)

        self.labels.select(2)

        self.assertEqual(self.selected, [1])
        self.assertIn("wait", self.notify.call_args.args[1].lower())

    def test_anchored_item_is_not_pressed_if_menu_changes_during_selection(self):
        _, target = self.hoverable_menu()
        text = Element("AXStaticText", "Tools")
        text.attrs["AXFrame"] = types.SimpleNamespace(x=25, y=20, width=50, height=20)
        target.children = [text]
        self.actions.menu_labels_show(False)
        session = self.module._session
        current = self.menu
        changed = self.submenu("Another menu")

        with patch.object(self.ui, "active_menu", side_effect=[current, changed]):
            self.labels.select(1)

        self.assertEqual(target.performed, [])
        self.assertTrue(session.stopped)
        self.assertIn("menu changed", self.notify.call_args.args[1].lower())

    def test_replaced_session_cannot_press_an_old_anchored_item(self):
        _, target = self.hoverable_menu()
        text = Element("AXStaticText", "Tools")
        text.attrs["AXFrame"] = types.SimpleNamespace(x=25, y=20, width=50, height=20)
        target.children = [text]
        self.actions.menu_labels_show(False)
        session = self.module._session
        original = self.menu
        calls = 0

        def replace_during_recheck():
            nonlocal calls
            calls += 1
            if calls == 2:
                self.actions.menu_labels_show(False)
            return original

        with patch.object(self.ui, "active_menu", side_effect=replace_during_recheck):
            self.labels.select(1)

        self.assertTrue(session.stopped)
        self.assertIsNot(self.module._session, session)
        self.assertEqual(target.performed, [])
        self.assertEqual(self.visible, [text])
        self.notify.assert_not_called()

    def test_excludes_separators_disabled_and_non_menu_elements(self):
        good = Element("AXMenuItem", "Open")
        menu = Element(
            "AXMenu",
            children=[
                good,
                Element("AXMenuItem", ""),
                Element("AXMenuItem", "  "),
                Element("AXMenuItem", "Disabled", enabled=False),
                Element("AXButton", "Not a menu"),
            ],
        )
        self.assertEqual(self.module._targets_in(menu), [good])


if __name__ == "__main__":
    unittest.main()
