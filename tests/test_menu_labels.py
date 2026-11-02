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
        self.actions = ["AXPress"]
        self.performed = []

    def get(self, key):
        if key == "AXChildren":
            return self.children
        return self.attrs.get(key)

    def perform(self, action):
        self.performed.append(action)


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
        self.window = Element("AXWindow")
        self.application_element = Element("AXApplication")
        self.application_element.attrs["AXFocusedWindow"] = self.window
        self.application = types.SimpleNamespace(
            pid=1, children=Children([self.bar]), element=self.application_element
        )
        self.menu = None
        self.visible = []
        self.style = None
        self.dispatch_stack = []
        self.selected = []
        self.notify = Mock()
        self.mouse_pos = Mock(return_value=(30, 40))
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
            ctrl=types.SimpleNamespace(mouse_pos=self.mouse_pos),
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
        self.module.actions.mouse_move = Mock()

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

    def test_back_recognizes_direct_menu_and_menu_bar_parents(self):
        for parent in (self.submenu("Parent item"), self.bar):
            with self.subTest(role=parent.get("AXRole")):
                self.labels.hide()
                self.menu = self.submenu()
                self.menu.attrs["AXParent"] = parent
                self.actions.menu_labels_show(False)

                self.actions.menu_labels_back()

                is_bar = parent.get("AXRole") == "AXMenuBar"
                self.module.actions.key.assert_called_with("esc" if is_bar else "left")
                self.menu = None if is_bar else parent
                self.module._session.update()
                self.assertEqual(self.visible, parent.children)
                self.assertIs(self.module._session.container, parent)

    def test_back_falls_back_to_menu_bar_when_parent_does_not_respond(self):
        parent = self.submenu("Parent")
        self.menu = self.submenu()
        self.menu.attrs["AXParent"] = parent
        self.actions.menu_labels_show(False)
        session = self.module._session

        self.actions.menu_labels_back()
        for _ in range(self.module.MENU_BACK_FALLBACK_TICKS):
            session.update()

        self.assertEqual(
            [call.args for call in self.module.actions.key.call_args_list],
            [("left",), ("esc",)],
        )
        self.menu = None
        session.update()
        self.assertIs(session.container, self.bar)
        self.assertEqual(self.visible, self.bar.children)
        self.assertEqual(self.style, "numbers")
        self.assertIn("menu bar", self.notify.call_args.args[1])

    def test_back_fallback_does_not_escape_after_window_changes(self):
        parent = self.submenu("Parent")
        self.prepare_back(parent)
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.actions.menu_labels_back()
        self.application_element.attrs["AXFocusedWindow"] = Element("AXWindow")

        for _ in range(self.module.MENU_BACK_FALLBACK_TICKS):
            session.update()

        self.module.actions.key.assert_called_once_with("left")
        self.assertTrue(session.stopped)
        self.assertIn("window changed", self.notify.call_args.args[1].lower())

    def test_back_fallback_does_not_escape_after_menu_changes(self):
        parent = self.submenu("Parent")
        self.prepare_back(parent)
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.actions.menu_labels_back()
        self.menu = self.submenu("Unrelated")

        for _ in range(self.module.MENU_BACK_FALLBACK_TICKS):
            session.update()

        self.module.actions.key.assert_called_once_with("left")

    def test_back_rejects_stale_labels_after_menu_changes(self):
        parent = self.submenu("Parent")
        self.prepare_back(parent)
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.menu = self.submenu("Another menu")

        self.actions.menu_labels_back()

        self.assertTrue(session.stopped)
        self.module.actions.key.assert_not_called()
        self.assertIn("menu changed", self.notify.call_args.args[1].lower())

    def test_replaced_session_cannot_press_a_parent_opener(self):
        parent = self.submenu("Parent")
        self.prepare_back(parent)
        self.actions.menu_labels_show(False)
        session = self.module._session
        opener = Element("AXMenuBarItem", "File")

        def replace_session(*args):
            self.actions.menu_labels_show(False)
            return opener

        with patch.object(self.module, "menu_opener", side_effect=replace_session):
            self.actions.menu_labels_back()

        self.assertTrue(session.stopped)
        self.assertIsNot(self.module._session, session)
        self.assertEqual(opener.performed, [])
        self.module.actions.key.assert_not_called()

    def test_back_does_not_press_an_opener_after_the_menu_changes(self):
        parent = self.submenu("Parent")
        self.prepare_back(parent)
        self.actions.menu_labels_show(False)
        session = self.module._session
        opener = Element("AXMenuBarItem", "File")

        def change_menu(*args):
            self.menu = self.submenu("Another menu")
            return opener

        with patch.object(self.module, "menu_opener", side_effect=change_menu):
            self.actions.menu_labels_back()

        self.assertTrue(session.stopped)
        self.assertEqual(opener.performed, [])
        self.module.actions.key.assert_not_called()
        self.assertIn("menu changed", self.notify.call_args.args[1].lower())

    def test_submenu_back_uses_verified_parent_menu_opener(self):
        parent = self.submenu("Parent item")
        opener = Element("AXMenuBarItem", "File", children=[parent])
        opener.actions = ["AXPress"]
        opener.perform = Mock()
        parent.attrs["AXParent"] = opener
        self.prepare_back(parent)
        self.actions.menu_labels_show(False)

        self.actions.menu_labels_back()

        opener.perform.assert_called_once_with("AXPress")
        self.module.actions.key.assert_not_called()
        self.menu = parent
        self.module._session.update()
        self.assertEqual(self.visible, parent.children)

    def test_menu_opener_rejects_unsafe_or_unrelated_owners(self):
        cases = (
            ("disabled", "AXMenuItem", False, False, ["AXPress"], True),
            ("hidden", "AXMenuItem", True, True, ["AXPress"], True),
            ("wrong role", "AXButton", True, False, ["AXPress"], True),
            ("not pressable", "AXMenuItem", True, False, [], True),
            ("not its child", "AXMenuItem", True, False, ["AXPress"], False),
        )
        for name, role, enabled, hidden, actions, has_child in cases:
            with self.subTest(name=name):
                menu = self.submenu()
                owner = Element(
                    role, children=[menu] if has_child else [], enabled=enabled
                )
                owner.attrs["AXHidden"] = hidden
                owner.actions = actions
                menu.attrs["AXParent"] = owner

                self.assertIsNone(self.module.menu_opener(menu))
        self.assertIsNone(self.module.menu_opener(self.submenu()))

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

    def hoverable_menu(self):
        target = Element("AXMenuItem", "Tools")
        menu = Element("AXMenu", children=[target])
        menu.attrs["AXFrame"] = types.SimpleNamespace(x=0, y=0, width=300, height=300)
        target.attrs.update(
            AXParent=menu,
            AXHasPopup=True,
            AXFrame=types.SimpleNamespace(x=10, y=20, width=80, height=30),
        )
        self.menu = menu
        return menu, target

    def test_numbered_submenu_hovers_only_if_native_selection_stalls(self):
        self.hoverable_menu()
        self.actions.menu_labels_show(False)
        session = self.module._session

        self.labels.select(1)

        self.assertEqual(self.selected, [1])
        for _ in range(self.module.MENU_HOVER_DELAY_TICKS - 1):
            session.update()
        self.module.actions.mouse_move.assert_not_called()
        session.update()
        self.module.actions.mouse_move.assert_called_once_with(50, 35)
        self.assertTrue(session.waiting)

        self.menu = self.submenu("Submenu item")
        session.update()
        self.assertIs(session.container, self.menu)
        self.assertEqual(self.visible, self.menu.children)

    def test_numbered_submenu_does_not_hover_if_native_selection_succeeds(self):
        self.hoverable_menu()
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.labels.select(1)

        self.menu = self.submenu("Submenu item")
        session.update()

        self.module.actions.mouse_move.assert_not_called()
        self.assertIs(session.container, self.menu)

    def test_named_submenu_hovers_when_its_title_uniquely_identifies_it(self):
        self.hoverable_menu()
        self.actions.menu_labels_show()
        session = self.module._session
        self.labels.select("Tools")

        for _ in range(self.module.MENU_HOVER_DELAY_TICKS):
            session.update()

        self.assertEqual(self.selected, ["Tools"])
        self.module.actions.mouse_move.assert_called_once_with(50, 35)

    def test_named_submenu_does_not_guess_between_duplicate_titles(self):
        menu, _ = self.hoverable_menu()
        menu.children.append(Element("AXMenuItem", "Tools"))
        self.actions.menu_labels_show()
        session = self.module._session
        self.labels.select("Tools")

        for _ in range(self.module.MENU_HOVER_DELAY_TICKS):
            session.update()

        self.assertEqual(self.selected, ["Tools"])
        self.module.actions.mouse_move.assert_not_called()

    def test_menu_number_hover_rejects_stale_or_unsafe_targets(self):
        for case in ("mouse_moved", "window_changed", "hidden", "outside"):
            with self.subTest(case=case):
                self.labels.hide()
                self.mouse_pos.return_value = (30, 40)
                self.application_element.attrs["AXFocusedWindow"] = self.window
                self.module.actions.mouse_move.reset_mock()
                _, target = self.hoverable_menu()
                self.actions.menu_labels_show(False)
                session = self.module._session
                self.labels.select(1)
                if case == "mouse_moved":
                    self.mouse_pos.return_value = (31, 40)
                elif case == "window_changed":
                    self.application_element.attrs["AXFocusedWindow"] = Element(
                        "AXWindow"
                    )
                elif case == "hidden":
                    target.attrs["AXHidden"] = True
                else:
                    target.attrs["AXFrame"] = types.SimpleNamespace(
                        x=400, y=20, width=80, height=30
                    )

                for _ in range(self.module.MENU_HOVER_DELAY_TICKS):
                    session.update()

                self.module.actions.mouse_move.assert_not_called()

    def test_menu_number_hover_does_not_move_after_session_replacement(self):
        self.hoverable_menu()
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.labels.select(1)

        def replace_session(*args):
            self.labels.hide()
            self.actions.menu_labels_show(False)
            return (50, 35)

        with patch.object(
            self.module, "submenu_hover_point", side_effect=replace_session
        ):
            for _ in range(self.module.MENU_HOVER_DELAY_TICKS):
                session.update()

        self.assertTrue(session.stopped)
        self.assertIsNot(self.module._session, session)
        self.module.actions.mouse_move.assert_not_called()

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
        for _ in range(self.module.MENU_HOVER_DELAY_TICKS):
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

    def test_hide_clears_native_labels_before_removing_override(self):
        self.actions.menu_labels_show(False)
        session = self.module._session
        job = session.job
        self.labels.hide()
        self.assertEqual(self.visible, [])
        self.assertEqual(self.module.ctx.tags, [])
        self.assertIsNone(session.job)
        self.cron.cancel.assert_called_with(job)

    def test_stopped_render_preserves_replacement_menu_labels(self):
        self.actions.menu_labels_show(False)
        previous = self.module._session
        native_show = self.labels.show
        switched = False

        def show_then_replace(targets):
            nonlocal switched
            native_show(targets)
            if not switched:
                switched = True
                self.actions.menu_labels_show(False)

        with patch.object(self.labels, "show", side_effect=show_then_replace):
            previous.show_container(self.bar, self.bar.children)

        self.assertTrue(previous.stopped)
        self.assertIsNotNone(self.module._session)
        self.assertIsNot(self.module._session, previous)
        self.assertEqual(self.visible, self.bar.children)

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
