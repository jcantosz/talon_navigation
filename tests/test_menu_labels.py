import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parents[1] / "menus" / "menu_labels.py"


class UIErr(Exception):
    pass


class ActionFailed(Exception):
    pass


class Element:
    def __init__(self, role, title="", children=(), enabled=True):
        self.attrs = {"AXRole": role, "AXTitle": title, "AXEnabled": enabled}
        self.children = list(children)

    def get(self, key):
        return self.attrs.get(key)


class Children(list):
    def find_one(self, **query):
        for child in self:
            if child.get("AXRole") == query["AXRole"]:
                return child
        raise UIErr("No menu bar")


class Context:
    def __init__(self):
        self.tags = []

    def action_class(self, namespace):
        return lambda cls: cls


class Module(Context):
    def tag(self, *args, **kwargs):
        pass

    def action_class(self, cls):
        return cls


class MenuLabelsTests(unittest.TestCase):
    def test_number_override_keeps_an_exact_rule_separate_from_aliases(self):
        grammar = SOURCE.with_suffix(".talon").read_text()
        self.assertRegex(
            grammar,
            r"(?m)^show menu numbers:\n[ \t]+user\.menu_labels_show\(false\)$",
        )
        headers = [
            line[:-1]
            for line in grammar.splitlines()
            if line and not line[0].isspace() and line.endswith(":")
        ]
        for header in headers:
            if header != "show menu numbers":
                self.assertNotIn("show menu numbers", header.split(" | "))

    def setUp(self):
        self.file = Element("AXMenuBarItem", "File")
        self.edit = Element("AXMenuBarItem", "Edit")
        self.bar = Element("AXMenuBar", children=[self.file, self.edit])
        self.application = types.SimpleNamespace(pid=1, children=Children([self.bar]))
        self.menu = None
        self.visible = []
        self.style = None
        self.dispatch_stack = []
        self.selected = []
        self.notify = Mock()
        self.cron = types.SimpleNamespace(
            interval=Mock(return_value=object()), cancel=Mock()
        )
        self.ui = types.SimpleNamespace(
            UIErr=UIErr,
            ActionFailed=ActionFailed,
            active_app=lambda: self.application,
            active_menu=lambda: self.menu,
        )
        self.labels = types.SimpleNamespace(
            show=lambda targets: self.show(targets, "numbers"),
            show_names=lambda targets: self.show(targets, "names"),
            hide=lambda: self.dispatch("hide"),
            select=lambda label: self.dispatch("select", label),
            mouse_move=Mock(),
        )
        talon = types.SimpleNamespace(
            Module=Module,
            Context=Context,
            actions=types.SimpleNamespace(labels=self.labels, next=self.next_action),
            app=types.SimpleNamespace(notify=self.notify),
            cron=self.cron,
            ui=self.ui,
        )
        root_package = types.ModuleType("talon_navigation_under_test")
        root_package.__path__ = [str(SOURCE.parents[1])]
        package = types.ModuleType("talon_navigation_under_test.menus")
        package.__path__ = [str(SOURCE.parent)]
        spec = importlib.util.spec_from_file_location(
            "talon_navigation_under_test.menus.menu_labels", SOURCE
        )
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(
            sys.modules,
            {
                "talon": talon,
                root_package.__name__: root_package,
                package.__name__: package,
                spec.name: self.module,
            },
        ):
            spec.loader.exec_module(self.module)
        self.actions = self.module.MenuLabelsActions
        self.module.actions.key = Mock()

    def prepare_back(self, parent):
        self.menu = self.submenu()
        owner = Element("AXMenuItem", "Owner")
        owner.attrs["AXParent"] = parent
        self.menu.attrs["AXParent"] = owner

    def test_back_to_parent_preserves_both_label_styles(self):
        for names in (True, False):
            with self.subTest(names=names):
                self.labels.hide()
                parent = self.submenu("Parent item")
                self.prepare_back(parent)
                self.actions.menu_labels_show(names)
                self.actions.menu_labels_back()
                self.assertEqual(self.visible, [])
                self.module.actions.key.assert_called_with("left")
                self.module._session.update()
                self.assertTrue(self.module._session.waiting)
                self.menu = parent
                self.module._session.update()
                self.assertEqual(self.visible, parent.children)
                self.assertEqual(self.style, "names" if names else "numbers")
                self.assertIsNone(self.module._session.back_parent)

    def test_back_from_top_menu_relabels_menu_bar(self):
        self.prepare_back(self.bar)
        self.actions.menu_labels_show(False)
        self.actions.menu_labels_back()
        self.module.actions.key.assert_called_with("esc")
        self.menu = None
        self.module._session.update()
        self.assertEqual(self.visible, self.bar.children)
        self.assertEqual(self.style, "numbers")
        self.assertIs(self.module._session.container, self.bar)

    def test_back_at_bar_does_not_send_escape(self):
        self.actions.menu_labels_show()
        self.actions.menu_labels_back()
        self.module.actions.key.assert_not_called()
        self.assertEqual(self.visible, self.bar.children)
        self.notify.assert_called_once()

    def test_back_timeout_reports_failure_and_cleans_up(self):
        self.prepare_back(self.bar)
        self.actions.menu_labels_show(False)
        self.actions.menu_labels_back()
        session = self.module._session
        for _ in range(15):
            session.update()
        self.assertIsNone(session.job)
        self.assertIsNone(session.back_parent)
        self.notify.assert_called_once_with(
            "Menu labels", "Unable to return to the parent menu."
        )

    def test_back_without_accessible_parent_does_not_close_menu(self):
        self.menu = self.submenu()
        self.actions.menu_labels_show(False)
        self.actions.menu_labels_back()
        self.module.actions.key.assert_not_called()
        self.assertEqual(self.visible, self.menu.children)
        self.notify.assert_called_once()

    def test_back_while_waiting_does_not_send_escape(self):
        self.actions.menu_labels_show(False)
        self.labels.select(1)
        self.actions.menu_labels_back()
        self.module.actions.key.assert_not_called()
        self.notify.assert_called_once()

    def show(self, targets, style):
        self.visible = list(targets)
        self.style = style

    def native(self, name, *args):
        if name == "select":
            self.selected.append(args[0])
        self.visible = []

    def dispatch(self, name, *args):
        if self.module.ctx.tags:
            self.dispatch_stack.append(name)
            try:
                getattr(self.module.MenuLabelOverrides, name)(*args)
            finally:
                self.dispatch_stack.pop()
        else:
            self.native(name, *args)

    def next_action(self, *args):
        # Talon resolves the next action against the currently active contexts.
        if not self.module.ctx.tags:
            raise IndexError("The override was removed before actions.next()")
        self.native(self.dispatch_stack[-1], *args)

    def submenu(self, title="Open Recent"):
        return Element("AXMenu", children=[Element("AXMenuItem", title)])

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

    def test_hide_clears_native_labels_before_removing_override(self):
        self.actions.menu_labels_show(False)
        session = self.module._session
        job = session.job
        self.labels.hide()
        self.assertEqual(self.visible, [])
        self.assertEqual(self.module.ctx.tags, [])
        self.assertIsNone(session.job)
        self.cron.cancel.assert_called_with(job)

    def test_leaf_selection_exits_without_relabeling_old_menu(self):
        self.menu = self.submenu("Leaf")
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.labels.select(1)
        self.menu = None
        for _ in range(15):
            session.update()
        self.assertEqual(self.visible, [])
        self.assertIsNone(session.job)
        self.notify.assert_not_called()

    def test_unchanged_menu_times_out_with_notification(self):
        self.menu = self.submenu()
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.labels.select(1)
        for _ in range(15):
            session.update()
        self.assertIsNone(session.job)
        self.notify.assert_called_once_with(
            "Menu labels", "No new selectable submenu appeared."
        )

    def test_app_switch_cancels_pending_relabel(self):
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.labels.select(1)
        self.application.pid = 2
        self.menu = self.submenu()
        session.update()
        self.assertEqual(self.visible, [])
        self.assertFalse(session.waiting)
        self.assertIsNone(session.job)

    def test_app_switch_before_selection_does_not_select_stale_item(self):
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.application.pid = 2
        self.labels.select(1)
        self.assertEqual(self.selected, [])
        self.notify.assert_called_once()
        self.assertIsNone(session.job)

    def test_external_menu_dismissal_clears_labels(self):
        self.menu = self.submenu()
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.menu = None
        session.update()
        self.assertEqual(self.visible, [])
        self.assertIsNone(session.job)

    def test_missing_menu_reports_accessibility_failure(self):
        self.application.children = Children()
        with self.assertLogs(level="ERROR"):
            self.actions.menu_labels_show(False)
        self.notify.assert_called_once()
        self.assertEqual(self.visible, [])
        self.assertIsNone(self.module._session)

    def test_accessibility_failure_while_waiting_cleans_up(self):
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.labels.select(1)
        self.ui.active_menu = Mock(side_effect=UIErr("Stale element"))
        with self.assertLogs(level="ERROR"):
            session.update()
        self.assertEqual(self.visible, [])
        self.assertIsNone(session.job)
        self.notify.assert_called_once()

    def test_accessibility_failure_before_selection_cleans_up(self):
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.ui.active_menu = Mock(side_effect=UIErr("Stale element"))
        with self.assertLogs(level="ERROR"):
            self.labels.select(1)
        self.assertEqual(self.visible, [])
        self.assertIsNone(session.job)
        self.assertEqual(self.selected, [])
        self.notify.assert_called_once()

    def test_failed_accessibility_press_cleans_up(self):
        self.actions.menu_labels_show(False)
        session = self.module._session
        native = self.native

        def fail_select(name, *args):
            if name == "select":
                raise ActionFailed("AXPress failed")
            native(name, *args)

        self.native = fail_select
        with self.assertLogs(level="ERROR"):
            self.labels.select(1)
        self.assertEqual(self.visible, [])
        self.assertIsNone(session.job)
        self.assertFalse(session.selecting)
        self.notify.assert_called_once()

    def test_invalid_numbers_report_error_without_selecting(self):
        self.actions.menu_labels_show(False)
        self.actions.menu_labels_click(0)
        self.actions.menu_labels_move(3)
        self.assertEqual(self.selected, [])
        self.labels.mouse_move.assert_not_called()
        self.assertEqual(self.notify.call_count, 2)

    def test_explicit_number_command_uses_the_same_selection_override(self):
        self.actions.menu_labels_show(False)
        self.actions.menu_labels_click(2)
        self.assertEqual(self.selected, [2])
        self.assertTrue(self.module._session.waiting)

    def test_number_command_in_title_mode_explains_how_to_switch(self):
        self.actions.menu_labels_show()
        self.actions.menu_labels_click(1)
        self.assertEqual(self.selected, [])
        self.notify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
