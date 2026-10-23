import importlib.util
import sys
import types
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parents[1] / "status" / "status_labels.py"


class UIErr(Exception):
    pass


class ActionFailed(Exception):
    pass


@dataclass
class Rect:
    x: float
    y: float
    width: float
    height: float


class Element:
    def __init__(self, role, title=None, frame=None, children=(), actions=(), **attrs):
        self.attrs = {
            "AXRole": role,
            "AXTitle": title,
            "AXFrame": frame,
            "AXChildren": list(children),
            **attrs,
        }
        self.actions = dict.fromkeys(actions, "")
        self.perform = Mock()
        for child in children:
            child.attrs["AXParent"] = self

    def get(self, key):
        if key == "AXWindows":
            return [
                child
                for child in self.attrs["AXChildren"]
                if child.get("AXRole") == "AXWindow"
            ]
        if key == "AXExtrasMenuBar":
            return next(
                (
                    child
                    for child in self.attrs["AXChildren"]
                    if child.get("AXRole") == "AXMenuBar"
                ),
                None,
            )
        return self.attrs.get(key)


class Owner:
    def __init__(self, pid=2, name="Control Center", bundle="com.apple.controlcenter"):
        self.pid = pid
        self.name = name
        self.bundle = bundle
        self.element = Element("AXApplication")


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


class StatusLabelsTests(unittest.TestCase):
    def setUp(self):
        self.owner = Owner()
        self.front = Owner(1, "Editor", "editor")
        self.front_bar = Element(
            "AXMenuBar", frame=Rect(0, 0, 1000, 24), AXParent=self.front.element
        )
        self.front.element.attrs["AXMenuBar"] = self.front_bar
        self.icon = Element(
            "AXMenuBarItem",
            frame=Rect(700, 0, 25, 24),
            actions=("AXPress",),
            AXSubrole="AXMenuExtra",
            AXDescription="Control Center",
            AXIdentifier="com.apple.menuextra.controlcenter",
        )
        self.bar = Element("AXMenuBar", children=[self.icon])
        self.bar.attrs["AXParent"] = self.owner.element
        self.owner.element.attrs["AXChildren"] = [self.bar]
        self.menu = None
        self.apps = [self.owner]
        self.visible = []
        self.names = None
        self.stack = []
        self.native_selections = []
        self.on_show = None
        self.mouse_target = None
        self.ui = types.SimpleNamespace(
            Element=Element,
            App=Owner,
            Rect=Rect,
            UIErr=UIErr,
            ActionFailed=ActionFailed,
            active_app=lambda: self.front,
            active_menu=lambda: self.menu,
            element_at=self.element_at,
            apps=lambda: self.apps,
            screens=lambda: [types.SimpleNamespace(rect=Rect(0, 0, 1000, 700))],
        )
        self.cron = types.SimpleNamespace(
            interval=Mock(return_value=object()), cancel=Mock()
        )
        self.notify = Mock()
        self.labels = types.SimpleNamespace(
            show=lambda elements: self.show(elements, False),
            show_names=lambda elements: self.show(elements, True),
            hide=lambda: self.dispatch("hide"),
            select=lambda label: self.dispatch("select", label),
            rect=self.label_rect,
            mouse_move=lambda label: setattr(self, "mouse_target", self.resolve(label)),
        )
        self.actions = types.SimpleNamespace(
            labels=self.labels,
            next=self.next_action,
            key=Mock(),
            mouse_click=lambda: self.mouse_target.perform("AXPress"),
        )
        talon = types.SimpleNamespace(
            Module=Module,
            Context=Context,
            actions=self.actions,
            app=types.SimpleNamespace(notify=self.notify),
            cron=self.cron,
            ui=self.ui,
        )
        root_package = types.ModuleType("talon_navigation_under_test")
        root_package.__path__ = [str(SOURCE.parents[1])]
        package = types.ModuleType("talon_navigation_under_test.status")
        package.__path__ = [str(SOURCE.parent)]
        spec = importlib.util.spec_from_file_location(
            "talon_navigation_under_test.status.status_labels", SOURCE
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
        self.commands = self.module.StatusLabelsActions

    def element_at(self, x, y):
        def hit(element):
            if element.get("AXHidden"):
                return None
            for child in element.get("AXChildren") or ():
                found = hit(child)
                if found is not None:
                    return found
            frame = element.get("AXFrame")
            if (
                frame is not None
                and frame.x <= x < frame.x + frame.width
                and frame.y <= y < frame.y + frame.height
            ):
                return element
            return None

        roots = [self.menu] if self.menu is not None else []
        for owner in self.apps:
            roots.extend(
                root
                for root in owner.element.attrs["AXChildren"]
                if root.get("AXRole") == "AXWindow"
            )
            for bar in owner.element.attrs["AXChildren"]:
                if bar.get("AXRole") == "AXMenuBar":
                    roots.extend(
                        root
                        for element in bar.get("AXChildren")
                        for root in element.get("AXChildren") or ()
                        if root.get("AXRole") == "AXMenu"
                        and self.module._visible_frame(root) is not None
                    )
        for root in roots:
            found = hit(root)
            if found is not None:
                return found
        for owner in self.apps:
            for bar in owner.element.attrs["AXChildren"]:
                if bar.get("AXRole") != "AXMenuBar":
                    continue
                bar.attrs["AXParent"] = owner.element
                if bar.get("AXFrame") is None:
                    bar.attrs["AXFrame"] = self.front_bar.get("AXFrame")
                for element in bar.get("AXChildren"):
                    element.attrs["AXParent"] = bar
                    frame = element.get("AXFrame")
                    if (
                        frame is not None
                        and not element.get("AXHidden")
                        and frame.x <= x < frame.x + frame.width
                        and frame.y <= y < frame.y + frame.height
                    ):
                        return element
        if self.front_bar.get("AXFrame").x <= x < 1000 and 0 <= y < 24:
            return self.front_bar
        return self.front.element

    def show(self, elements, names):
        self.visible = list(elements)
        self.names = names
        if self.on_show is not None:
            self.on_show()

    def resolve(self, label):
        if isinstance(label, int):
            return self.visible[label - 1]
        return next(
            element
            for element in self.visible
            if label in (element.get("AXTitle"), element.get("AXDescription"))
        )

    def label_rect(self, label):
        element = self.resolve(label)
        frame = element.get("AXFrame")
        if element.get("AXRole") == "AXSlider":
            return Rect(frame.x + 1, frame.y + 1, frame.width - 2, frame.height - 2)
        return frame

    def dispatch(self, name, *args):
        if self.module.ctx.tags:
            self.stack.append(name)
            try:
                getattr(self.module.StatusLabelOverrides, name)(*args)
            finally:
                self.stack.pop()
        else:
            self.native(name, *args)

    def native(self, name, *args):
        if name == "select":
            target = self.resolve(args[0])
            self.native_selections.append(target)
            target.perform("AXPress")
            self.labels.hide()
        else:
            self.visible = []

    def next_action(self, *args):
        self.assertTrue(self.module.ctx.tags)
        self.native(self.stack[-1], *args)

    def button(self, title="Sound", role="AXButton", **attrs):
        return Element(
            role, title, Rect(700, 60, 80, 30), actions=("AXPress",), **attrs
        )

    def panel(self, *controls):
        return Element(
            "AXWindow",
            "Control Center",
            Rect(600, 30, 400, 400),
            children=[Element("AXGroup", children=controls)],
            AXSubrole="AXSystemDialog",
        )

    def open_panel(self, names=False, controls=None):
        panel = self.panel(*(controls or [self.button()]))

        def toggle(action):
            roots = self.owner.element.attrs["AXChildren"]
            if panel in roots:
                roots.remove(panel)
            else:
                roots.append(panel)

        self.icon.perform.side_effect = toggle
        self.commands.status_labels_show(names)
        self.labels.select("Control Center" if names else 1)
        session = self.module._session
        self.tick(session, 3)
        self.assertIs(session.surface.root, panel)
        return session, panel

    def tick(self, session, count=1):
        for _ in range(count):
            session.update()

    def test_description_only_icon_is_available_in_title_mode(self):
        self.commands.status_labels_show()
        self.assertEqual(self.visible, [self.icon])
        self.assertTrue(self.names)
        self.assertTrue(self.module.ctx.tags)

    def test_hidden_zero_size_offscreen_and_application_menus_are_excluded(self):
        self.bar.attrs["AXChildren"].extend(
            [
                Element("AXMenuBarItem", "File", Rect(30, 0, 30, 20)),
                Element("AXMenuExtra", "Hidden", Rect(600, 0, 20, 20), AXHidden=True),
                Element("AXMenuExtra", "Empty", Rect(0, 0, 0, 0)),
                Element("AXMenuExtra", "Offscreen", Rect(1001, 0, 20, 20)),
                Element(
                    "AXMenuExtra", "Disabled", Rect(650, 0, 20, 20), AXEnabled=False
                ),
            ]
        )
        self.commands.status_labels_show(False)
        self.assertEqual(self.visible, [self.icon])

    def test_icons_are_sorted_left_to_right_across_owners(self):
        other = Owner(3, "Other", "other")
        extra = Element("AXMenuExtra", "Other", Rect(650, 2, 20, 20))
        other.element.attrs["AXChildren"] = [Element("AXMenuBar", children=[extra])]
        self.apps.append(other)
        self.commands.status_labels_show(False)
        self.assertEqual(self.visible, [extra, self.icon])

    def test_first_discovery_never_queries_unrelated_app_accessibility(self):
        other = Owner(3, "No status icons", "other")
        original = other.element.get
        other.element.get = Mock(side_effect=original)
        self.apps.append(other)
        self.module._icons()
        other.element.get.assert_not_called()

    def test_covered_icon_geometry_is_not_treated_as_a_visible_target(self):
        self.ui.element_at = lambda x, y: self.front.element
        self.assertEqual(self.module._icons(), [])

    def test_descendant_hit_still_identifies_the_status_icon(self):
        image = Element("AXImage", AXParent=self.icon)
        self.ui.element_at = lambda x, y: image
        self.assertEqual(
            [target.element for target in self.module._icons()], [self.icon]
        )

    def test_empty_accessibility_hit_excludes_the_icon(self):
        self.ui.element_at = Mock(side_effect=RuntimeError("No element found."))
        self.assertEqual(self.module._icons(), [])

    def test_unexpected_hit_test_error_is_not_silently_ignored(self):
        self.ui.element_at = Mock(side_effect=RuntimeError("Unexpected failure"))
        with self.assertRaisesRegex(RuntimeError, "Unexpected failure"):
            self.module._icons()

    def test_clock_discovers_notification_centers_separate_process(self):
        notification_center = Owner(
            3, "Notification Center", "com.apple.notificationcenterui"
        )
        self.apps.append(notification_center)
        self.icon.attrs["AXIdentifier"] = "com.apple.menuextra.clock"
        panel = self.panel(self.button("Notifications"))
        self.icon.perform.side_effect = lambda action: (
            notification_center.element.attrs["AXChildren"].append(panel)
        )
        self.commands.status_labels_show(False)
        self.labels.select(1)
        session = self.module._session
        self.tick(session, 3)
        self.assertIs(session.surface.owner, notification_center)
        self.assertIs(session.surface.root, panel)

    def test_newly_started_apps_are_discovered_on_the_next_scan(self):
        self.module._icons()
        other = Owner(3, "New app", "new")
        extra = Element("AXMenuExtra", "New", Rect(650, 0, 20, 20))
        other.element.attrs["AXChildren"] = [Element("AXMenuBar", children=[extra])]
        self.apps.append(other)
        self.assertIn(extra, [target.element for target in self.module._icons()])

    def test_new_status_bars_in_existing_apps_are_discovered_without_cache_expiry(self):
        other = Owner(3, "Other", "other")
        self.apps.append(other)
        self.module._icons()
        extra = Element("AXMenuExtra", "New", Rect(650, 0, 20, 20))
        other.element.attrs["AXChildren"] = [Element("AXMenuBar", children=[extra])]
        self.assertIn(extra, [target.element for target in self.module._icons()])

    def test_every_normal_request_performs_fresh_parent_discovery(self):
        with patch.object(
            self.module, "discover", wraps=self.module.discover
        ) as discover:
            self.module._icons()
            self.module._icons()
        self.assertEqual(discover.call_count, 2)
        for call in discover.call_args_list:
            self.assertIsNone(call.kwargs["parents"])
            self.assertEqual(call.kwargs["step"], 8)

    def test_refresh_uses_the_same_parent_scan_not_a_legacy_lookup(self):
        self.actions.user = types.SimpleNamespace(
            status_labels_show=self.commands.status_labels_show
        )
        with patch.object(
            self.module, "discover", wraps=self.module.discover
        ) as discover:
            self.commands.status_labels_refresh(False)
        discover.assert_called_once()
        self.assertEqual(discover.call_args.kwargs["step"], 8)
        self.assertIsNone(discover.call_args.kwargs["parents"])
        self.assertEqual(self.visible, [self.icon])

    def test_discovery_failure_reports_error_without_trying_an_app_scan(self):
        self.ui.element_at = Mock(side_effect=RuntimeError("Discovery failed"))
        self.ui.apps = Mock(side_effect=AssertionError("Unexpected fallback"))
        with self.assertLogs(level="ERROR"):
            self.commands.status_labels_show(False)
        self.ui.apps.assert_not_called()
        self.assertIsNone(self.module._session)
        self.assertEqual(self.visible, [])
        self.notify.assert_called_once()

    def test_inaccessible_unrelated_app_is_not_queried(self):
        other = Owner(3)
        other.element.get = Mock(side_effect=UIErr("Unavailable"))
        self.apps.append(other)
        self.commands.status_labels_show(False)
        self.assertEqual(self.visible, [self.icon])
        other.element.get.assert_not_called()

    def test_no_accessible_icons_notifies_without_starting_a_job(self):
        self.apps.clear()
        self.commands.status_labels_show()
        self.assertIsNone(self.module._session)
        self.notify.assert_called_once()
        self.cron.interval.assert_not_called()

    def test_selection_replaces_icons_with_panel_controls_in_both_modes(self):
        for names in (False, True):
            with self.subTest(names=names):
                self.owner.element.attrs["AXChildren"] = [self.bar]
                self.labels.hide()
                session, panel = self.open_panel(names)
                self.assertEqual(
                    self.visible, [panel.get("AXChildren")[0].get("AXChildren")[0]]
                )
                self.assertEqual(self.names, names)
                self.assertFalse(session.waiting)
                self.assertFalse(session.internal)

    def test_leaves_without_children_do_not_raise(self):
        control = self.button()
        del control.attrs["AXChildren"]
        _, _ = self.open_panel(controls=[control])
        self.assertEqual(self.visible, [control])

    def test_hidden_and_disabled_panel_controls_are_excluded(self):
        enabled = self.button()
        disabled = self.button("Disabled", AXEnabled=False)
        hidden = self.button("Hidden", AXHidden=True)
        self.open_panel(controls=[enabled, disabled, hidden])
        self.assertEqual(self.visible, [enabled])

    def test_panel_scan_reads_screen_bounds_once(self):
        screens = Mock(return_value=[types.SimpleNamespace(rect=Rect(0, 0, 1000, 700))])
        self.ui.screens = screens
        panel = self.panel(self.button("One"), self.button("Two"), self.button("Three"))
        self.module._panel_targets(panel, self.owner)
        screens.assert_called_once_with()

    def test_existing_application_windows_are_not_labeled_as_status_panels(self):
        old = self.panel(self.button("Old document"))
        old.attrs["AXSubrole"] = "AXStandardWindow"
        self.owner.element.attrs["AXChildren"].append(old)
        session, new = self.open_panel()
        self.assertIs(session.surface.root, new)
        self.assertNotEqual(self.visible[0].get("AXTitle"), "Old document")

    def test_show_switches_style_on_the_current_panel_without_resetting_navigation(
        self,
    ):
        session, panel = self.open_panel()
        for names in (True, False):
            self.commands.status_labels_show(names)
            self.assertIs(self.module._session, session)
            self.assertIs(session.surface.root, panel)
            self.assertEqual(self.names, names)
            self.assertEqual(self.visible, [session.targets[0].element])
            self.assertIs(session.opener, self.icon)
        self.cron.interval.assert_called_once()
        self.icon.perform.assert_called_once()
        self.commands.status_labels_back()
        self.tick(session, 3)
        self.assertEqual(self.visible, [self.icon])

    def test_show_during_opening_changes_style_without_cancelling_the_transition(self):
        panel = self.panel(self.button())
        self.icon.perform.side_effect = lambda action: self.owner.element.attrs[
            "AXChildren"
        ].append(panel)
        self.commands.status_labels_show(False)
        self.labels.select(1)
        session = self.module._session
        self.commands.status_labels_show(True)
        self.assertIs(self.module._session, session)
        self.assertTrue(session.waiting)
        self.tick(session, 3)
        self.assertIs(session.surface.root, panel)
        self.assertTrue(self.names)

    def test_show_after_hiding_labels_adopts_the_still_open_panel(self):
        old_session, panel = self.open_panel()
        self.labels.hide()
        self.commands.status_labels_show(True)
        session = self.module._session
        self.assertIsNot(session, old_session)
        self.assertIs(session.surface.root, panel)
        self.assertIs(session.opener, self.icon)
        self.assertNotIn(panel, session.baseline)
        self.assertTrue(self.names)
        self.commands.status_labels_back()
        self.tick(session, 3)
        self.assertEqual(self.visible, [self.icon])

    def test_show_adopts_an_already_open_native_status_menu(self):
        entry = Element("AXMenuItem", "About", Rect(700, 60, 80, 30))
        self.menu = Element("AXMenu", children=[entry], AXParent=self.icon)
        self.commands.status_labels_show(False)
        self.assertIs(self.module._session.surface.root, self.menu)
        self.assertEqual(self.visible, [entry])
        self.icon.perform.assert_not_called()
        session = self.module._session
        self.commands.status_labels_show(True)
        self.assertIs(self.module._session, session)
        self.assertEqual(self.visible, [entry])
        self.assertTrue(self.names)

    def test_show_adopts_a_visible_direct_status_menu_without_active_menu(self):
        entry = Element("AXMenuItem", "About", Rect(700, 60, 80, 30))
        menu = Element("AXMenu", frame=Rect(690, 30, 200, 150), children=[entry])
        self.icon.attrs["AXChildren"] = [menu]
        self.commands.status_labels_show(False)
        self.assertIs(self.module._session.surface.root, menu)
        self.assertEqual(self.visible, [entry])

    def test_show_does_not_adopt_a_regular_application_menu(self):
        entry = Element("AXMenuItem", "Open", Rect(30, 60, 80, 30))
        self.menu = Element("AXMenu", children=[entry], AXParent=self.front.element)
        self.commands.status_labels_show(False)
        self.assertIsNone(self.module._session.surface)
        self.assertEqual(self.visible, [self.icon])

    def test_show_adopts_an_open_clock_panel_from_notification_center(self):
        notification_center = Owner(
            3, "Notification Center", "com.apple.notificationcenterui"
        )
        self.apps.append(notification_center)
        self.icon.attrs["AXIdentifier"] = "com.apple.menuextra.clock"
        panel = self.panel(self.button("Notifications"))
        notification_center.element.attrs["AXChildren"] = [panel]
        self.commands.status_labels_show(False)
        session = self.module._session
        self.assertIs(session.surface.root, panel)
        self.assertIs(session.surface.owner, notification_center)
        self.assertIs(session.opener, self.icon)
        self.assertEqual({provider.pid for provider in session.providers}, {2, 3})

    def test_unknown_adopted_panel_opener_does_not_guess_a_toggle_for_back(self):
        panel = self.panel(self.button())
        panel.attrs["AXTitle"] = "Unknown panel"
        self.owner.element.attrs["AXChildren"].append(panel)
        self.commands.status_labels_show(False)
        session = self.module._session
        self.commands.status_labels_back()
        self.assertIsNone(session.opener)
        self.assertFalse(session.waiting)
        self.assertTrue(self.visible)
        self.icon.perform.assert_not_called()
        self.notify.assert_called_once()

    def test_unrelated_third_party_system_dialog_is_not_adopted(self):
        other = Owner(3, "Other app", "other")
        extra = Element("AXMenuExtra", "Other app", Rect(650, 0, 20, 20))
        panel = self.panel(self.button("Confirm"))
        panel.attrs["AXTitle"] = "Unrelated alert"
        other.element.attrs["AXChildren"] = [
            Element("AXMenuBar", children=[extra]),
            panel,
        ]
        self.apps.append(other)
        self.commands.status_labels_show(False)
        self.assertIsNone(self.module._session.surface)
        self.assertEqual(self.visible, [extra, self.icon])

    def test_adopted_panel_without_opener_can_use_its_own_close_action(self):
        for method in ("cancel", "close_button"):
            with self.subTest(method=method):
                self.labels.hide()
                panel = self.panel(self.button())
                panel.attrs["AXTitle"] = "Unknown panel"
                self.owner.element.attrs["AXChildren"] = [self.bar, panel]
                close = Element("AXButton", "Close", actions=("AXPress",))
                if method == "cancel":
                    panel.actions = {"AXCancel": "cancel"}
                    action = panel.perform
                else:
                    panel.attrs["AXCloseButton"] = close
                    action = close.perform
                action.side_effect = lambda operation: self.owner.element.attrs[
                    "AXChildren"
                ].remove(panel)
                self.commands.status_labels_show(False)
                session = self.module._session
                self.commands.status_labels_back()
                self.tick(session, 3)
                self.assertEqual(self.visible, [self.icon])
                action.assert_called_once()
                self.icon.perform.assert_not_called()
                self.notify.assert_not_called()

    def test_back_closes_panel_and_relabels_icons_without_escape(self):
        session, _ = self.open_panel()
        self.commands.status_labels_back()
        self.tick(session, 3)
        self.assertEqual(self.visible, [self.icon])
        self.assertIsNone(session.surface)
        self.assertFalse(session.waiting)
        self.assertEqual(self.icon.perform.call_count, 2)
        self.actions.key.assert_not_called()

    def test_back_reuses_known_icon_providers_without_rescanning_every_app(self):
        session, _ = self.open_panel()
        self.commands.status_labels_back()
        self.ui.apps = Mock(side_effect=AssertionError("Unexpected full app scan"))
        self.tick(session, 3)
        self.assertEqual(self.visible, [self.icon])

    def test_back_at_icons_is_explicit_and_does_not_press_anything(self):
        self.commands.status_labels_show()
        self.commands.status_labels_back()
        self.icon.perform.assert_not_called()
        self.notify.assert_called_once()

    def test_hide_stops_job_and_removes_override_after_native_hide(self):
        self.commands.status_labels_show(False)
        session = self.module._session
        self.labels.hide()
        self.assertIsNone(self.module._session)
        self.assertTrue(session.stopped)
        self.assertEqual(self.visible, [])
        self.assertFalse(self.module.ctx.tags)
        self.cron.cancel.assert_called_once()

    def test_stopped_callback_cannot_resurrect_labels(self):
        self.commands.status_labels_show(False)
        session = self.module._session
        self.labels.hide()
        self.tick(session)
        session.show(
            [self.module.Target(self.icon, self.owner, self.icon.get("AXFrame"))]
        )
        self.assertEqual(self.visible, [])

    def test_cancellation_during_label_rendering_does_not_resurrect_labels(self):
        session, panel = self.open_panel()
        self.on_show = self.module._stop
        session.show(session.targets, session.surface)
        self.assertEqual(self.visible, [])
        self.assertTrue(session.stopped)
        self.assertFalse(self.module.ctx.tags)

    def test_focus_change_cancels_selection_before_any_press(self):
        self.commands.status_labels_show(False)
        self.front = Owner(99, "Other app", "other")
        self.labels.select(1)
        self.icon.perform.assert_not_called()
        self.assertIsNone(self.module._session)
        self.notify.assert_called_once()

    def test_owner_can_take_focus_without_canceling_panel(self):
        session, _ = self.open_panel()
        self.front = self.owner
        self.tick(session)
        self.assertIs(self.module._session, session)

    def test_external_panel_dismissal_stops_labels(self):
        session, panel = self.open_panel()
        self.owner.element.attrs["AXChildren"].remove(panel)
        self.tick(session)
        self.assertIsNone(self.module._session)
        self.assertEqual(self.visible, [])

    def test_no_panel_transition_times_out_with_a_notification(self):
        self.commands.status_labels_show(False)
        self.labels.select(1)
        session = self.module._session
        self.tick(session, 17)
        self.assertIsNone(self.module._session)
        self.notify.assert_called_once()

    def test_leaf_action_closing_panel_finishes_without_false_error(self):
        control = self.button("Done")
        session, panel = self.open_panel(controls=[control])
        control.perform.side_effect = lambda action: self.owner.element.attrs[
            "AXChildren"
        ].remove(panel)
        self.labels.select(1)
        self.tick(session, 17)
        self.assertIsNone(self.module._session)
        self.notify.assert_not_called()

    def test_slider_selection_does_not_change_value(self):
        slider = self.button("Volume", role="AXSlider")
        self.open_panel(controls=[slider])
        self.labels.select(1)
        slider.perform.assert_not_called()
        self.assertEqual(self.visible, [slider])
        self.notify.assert_called_once()

    def test_explicit_slider_adjustment_uses_accessibility_increment(self):
        slider = self.button("Volume", role="AXSlider")
        slider.actions = {"AXIncrement": "increment", "AXDecrement": "decrement"}
        session, _ = self.open_panel(controls=[slider])
        self.commands.status_labels_adjust(1, "increase")
        slider.perform.assert_called_once_with("AXIncrement")
        self.tick(session, 3)
        self.assertEqual(self.visible, [slider])

    def test_repeated_adjustments_keep_labels_visible_without_waiting_for_a_transition(
        self,
    ):
        for names in (False, True):
            with self.subTest(names=names):
                self.labels.hide()
                self.owner.element.attrs["AXChildren"] = [self.bar]
                slider = self.button("Volume", role="AXSlider", AXValue=5)
                slider.actions = {
                    "AXIncrement": "increment",
                    "AXDecrement": "decrement",
                }

                def adjust(action):
                    slider.attrs["AXValue"] += 1 if action == "AXIncrement" else -1

                slider.perform.side_effect = adjust
                session, _ = self.open_panel(names, [slider])
                label = "Volume" if names else 1
                for operation in ("increase", "increase", "decrease"):
                    self.commands.status_labels_adjust(label, operation)
                    self.assertEqual(self.visible, [slider])
                    self.assertFalse(session.waiting)
                    self.assertIs(self.module._session, session)
                    self.tick(session)
                    self.assertEqual(self.visible, [slider])
                self.assertEqual(slider.get("AXValue"), 6)
                self.assertEqual(slider.perform.call_count, 3)
                self.notify.assert_not_called()

    def test_slider_resolution_uses_current_geometry_with_native_inset_rectangles(self):
        for names in (False, True):
            with self.subTest(names=names):
                self.labels.hide()
                self.owner.element.attrs["AXChildren"] = [self.bar]
                slider = self.button("Volume", role="AXSlider")
                slider.actions = {"AXIncrement": "increment"}
                session, _ = self.open_panel(names, [slider])
                slider.attrs["AXFrame"] = Rect(702.1, 60.2, 80, 6)
                self.commands.status_labels_adjust("Volume" if names else 1, "increase")
                slider.perform.assert_called_once_with("AXIncrement")
                self.assertEqual(self.visible, [slider])
                self.assertIs(self.module._session, session)
                self.notify.assert_not_called()

    def test_title_resolution_chooses_slider_not_a_larger_overlapping_button(self):
        slider = self.button("Volume", role="AXSlider")
        slider.actions = {"AXIncrement": "increment"}
        parent = Element(
            "AXButton",
            "Sound",
            Rect(680, 40, 150, 100),
            children=[slider],
            actions=("AXPress",),
        )
        self.open_panel(True, [parent])
        self.commands.status_labels_adjust("Volume", "increase")
        slider.perform.assert_called_once_with("AXIncrement")
        parent.perform.assert_not_called()
        self.notify.assert_not_called()

    def test_value_changes_do_not_rerender_or_hide_the_overlay(self):
        slider = self.button("Volume", role="AXSlider", AXValue=5)
        session, _ = self.open_panel(controls=[slider])
        session.show = Mock(wraps=session.show)
        for value in (6, 7, 8):
            slider.attrs["AXValue"] = value
            self.tick(session)
        session.show.assert_not_called()
        self.assertEqual(self.visible, [slider])

    def test_subpixel_frame_jitter_does_not_rerender_or_hide_the_overlay(self):
        control = self.button()
        session, _ = self.open_panel(controls=[control])
        session.show = Mock(wraps=session.show)
        for shift in (0.02, -0.03, 0.04):
            control.attrs["AXFrame"] = Rect(700 + shift, 60 + shift, 80 + shift, 30)
            self.tick(session)
        session.show.assert_not_called()
        self.assertEqual(self.visible, [control])

    def test_meaningful_geometry_change_updates_labels_without_explicit_hide(self):
        control = self.button()
        session, _ = self.open_panel(controls=[control])
        hide = self.labels.hide
        self.labels.hide = Mock(wraps=hide)
        session.show = Mock(wraps=session.show)
        control.attrs["AXFrame"] = Rect(720, 60, 80, 30)
        self.tick(session)
        session.show.assert_called_once()
        self.labels.hide.assert_not_called()
        self.assertEqual(self.visible, [control])

    def test_unsupported_adjustment_does_not_hide_labels_or_press_a_toggle(self):
        control = self.button("Wi-Fi", role="AXCheckBox")
        session, _ = self.open_panel(controls=[control])
        self.commands.status_labels_adjust(1, "increase")
        self.assertEqual(self.visible, [control])
        self.assertFalse(session.waiting)
        control.perform.assert_not_called()
        self.notify.assert_called_once()

    def test_repeated_adjustments_at_a_limit_do_not_time_out_or_hide_labels(self):
        slider = self.button("Volume", role="AXSlider", AXValue=0)
        slider.actions = {"AXDecrement": "decrement"}
        session, _ = self.open_panel(controls=[slider])
        for _ in range(2):
            self.commands.status_labels_adjust(1, "decrease")
            self.assertEqual(self.visible, [slider])
        self.tick(session, 25)
        self.assertIs(self.module._session, session)
        self.assertEqual(self.visible, [slider])
        self.assertFalse(session.waiting)
        self.notify.assert_not_called()

    def test_failed_adjustment_is_reported_and_cleans_up(self):
        slider = self.button("Volume", role="AXSlider")
        slider.actions = {"AXIncrement": "increment"}
        self.open_panel(controls=[slider])
        slider.perform.side_effect = ActionFailed("Cannot adjust")
        with self.assertLogs(level="ERROR"):
            self.commands.status_labels_adjust(1, "increase")
        self.assertIsNone(self.module._session)
        self.assertEqual(self.visible, [])
        self.notify.assert_called_once()

    def test_explicit_details_uses_only_the_advertised_action(self):
        control = self.button("Wi-Fi", role="AXCheckBox")
        control.actions["custom-details"] = "show details"
        self.open_panel(controls=[control])
        self.commands.status_labels_adjust(1, "details")
        control.perform.assert_called_once_with("custom-details")

    def test_details_without_a_real_panel_change_times_out_explicitly(self):
        control = self.button("Wi-Fi", role="AXCheckBox")
        control.actions["custom-details"] = "show details"
        session, _ = self.open_panel(controls=[control])
        self.commands.status_labels_adjust(1, "details")
        self.tick(session, 17)
        self.assertIsNone(self.module._session)
        self.notify.assert_called_once()

    def test_direct_icon_menu_is_found_even_when_active_menu_is_unavailable(self):
        entry = Element("AXMenuItem", "About", Rect(700, 60, 80, 30))
        menu = Element("AXMenu", children=[entry])
        menu.attrs["AXParent"] = self.icon
        self.icon.perform.side_effect = lambda action: self.icon.attrs.update(
            AXChildren=[menu]
        )
        self.commands.status_labels_show(False)
        self.labels.select(1)
        self.tick(self.module._session, 3)
        self.assertEqual(self.visible, [entry])

    def test_unsupported_details_does_not_guess_or_toggle_control(self):
        control = self.button("Wi-Fi", role="AXCheckBox")
        self.open_panel(controls=[control])
        self.commands.status_labels_adjust(1, "details")
        control.perform.assert_not_called()
        self.notify.assert_called_once()
        self.assertEqual(self.visible, [control])

    def test_accessibility_press_failure_cleans_up_and_notifies(self):
        self.commands.status_labels_show(False)
        self.icon.perform.side_effect = ActionFailed()
        with self.assertLogs(level="ERROR"):
            self.labels.select(1)
        self.assertIsNone(self.module._session)
        self.assertEqual(self.visible, [])
        self.notify.assert_called_once()

    def test_unmatched_label_bounds_is_an_explicit_stale_label_error(self):
        self.commands.status_labels_show(False)
        self.labels.rect = lambda label: Rect(1, 1, 1, 1)
        with self.assertLogs(level="ERROR"):
            self.labels.select(1)
        self.assertIsNone(self.module._session)
        self.icon.perform.assert_not_called()
        self.notify.assert_called_once()

    def test_menu_surface_only_labels_the_current_level(self):
        child = Element("AXMenu", children=[self.button("Deeper")])
        entry = Element(
            "AXMenuItem", "Submenu", Rect(700, 60, 80, 30), children=[child]
        )
        menu = Element("AXMenu", children=[entry])
        menu.attrs["AXParent"] = self.icon
        self.icon.perform.side_effect = lambda action: setattr(self, "menu", menu)
        self.commands.status_labels_show(False)
        self.labels.select(1)
        self.tick(self.module._session, 3)
        self.assertEqual(self.visible, [entry])

    def test_top_menu_back_uses_menu_cancel_and_restores_icons(self):
        entry = Element("AXMenuItem", "About", Rect(700, 60, 80, 30))
        menu = Element("AXMenu", children=[entry], actions=("AXCancel",))
        menu.attrs["AXParent"] = self.icon
        menu.perform.side_effect = lambda action: setattr(self, "menu", None)
        self.icon.perform.side_effect = lambda action: setattr(self, "menu", menu)
        self.commands.status_labels_show(False)
        self.labels.select(1)
        session = self.module._session
        self.tick(session, 3)
        self.commands.status_labels_back()
        self.tick(session, 3)
        menu.perform.assert_called_once_with("AXCancel")
        self.assertEqual(self.visible, [self.icon])


if __name__ == "__main__":
    unittest.main()
