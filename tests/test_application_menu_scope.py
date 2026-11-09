import types
import unittest
from unittest.mock import patch

# Talon imports packages; unittest discovery can load these modules top-level.
if __package__:
    from .accessibility_support import (
        SESSION_TAG,
        ApplicationMenuTestCase,
        Element,
        UIErr,
        frame,
    )
else:
    from accessibility_support import (
        SESSION_TAG,
        ApplicationMenuTestCase,
        Element,
        UIErr,
        frame,
    )


class ApplicationMenuScopeTests(ApplicationMenuTestCase):
    def test_flat_menu_uses_bounds_and_does_not_walk_submenus(self):
        self.item.attrs["AXPosition"] = (10, 20)
        outside = Element(AXRole="AXMenuItem", AXFrame=frame(x=400))
        closed = Element(AXRole="AXMenu")
        self.item.attrs["AXChildren"] = [closed]
        self.menu.attrs["AXChildren"] = [self.item, outside]
        original_get = closed.get

        def closed_get(attribute):
            if attribute == "AXChildren":
                self.fail("Closed submenu was traversed")
            return original_get(attribute)

        closed.get = closed_get

        session = self.start(self.menu)

        self.assertEqual(session.targets, [self.item])
        self.query.assert_not_called()

    def test_invalid_active_menu_resolves_to_unique_visible_window_menu(self):
        self.item.attrs["AXPosition"] = (10, 20)
        reported = Element(AXRole="AXMenu", AXFrame=frame(width=0, height=0))
        self.window.attrs["AXChildren"] = [self.menu]
        self.menu.attrs["AXChildren"] = [self.item]

        session = self.start(reported)

        self.assertIs(session.menu, self.menu)
        self.assertEqual(session.targets, [self.item])
        self.query.assert_not_called()
        with patch.object(
            self.collection, "visible_menu", side_effect=AssertionError("Rescanned")
        ):
            session._check_menu()
        self.talon.active_menu = None
        session._check_menu()
        self.finish_refresh()
        self.assertIsNone(session.menu)

    def test_stale_menu_from_another_application_is_ignored(self):
        other = Element(AXRole="AXApplication")
        other_window = Element(AXRole="AXWindow", AXParent=other)
        stale = Element(
            AXRole="AXGroup",
            AXFrame=frame(width=500, height=0),
            AXTopLevelUIElement=other_window,
        )
        self.window.attrs["AXChildren"] = [self.button]

        with patch.object(
            self.collection, "visible_menu", side_effect=AssertionError("Searched")
        ):
            session = self.start(stale)

        self.assertIsNone(session.menu)
        self.assertEqual(session.targets, [self.button])

    def test_menu_owned_by_the_active_application_is_used(self):
        self.window.attrs["AXParent"] = self.application
        self.menu.attrs["AXTopLevelUIElement"] = self.window

        session = self.start(self.menu)

        self.assertIs(session.menu, self.menu)
        self.assertEqual(session.targets, [self.item])

    def test_visible_menu_resolution_does_not_guess_between_two_popups(self):
        second = Element(AXRole="AXMenu", AXFrame=frame())
        self.window.attrs["AXChildren"] = [self.menu, second]

        self.assertIsNone(self.collection.visible_menu(self.window))

    def test_grouped_menu_retains_recursive_query_path(self):
        wrapper = Element(AXRole="AXGroup", AXChildren=[self.item])
        self.menu.attrs["AXChildren"] = [wrapper]

        session = self.start(self.menu)

        self.assertEqual(session.targets, [self.item])
        self.query.assert_called_once()
        self.assertIs(self.query.call_args.kwargs["root"], self.menu)

    def test_flat_menu_keeps_overlapping_items_but_requires_position(self):
        self.item.attrs.update(AXPosition=(10, 20), AXFrame=frame(x=290, width=20))
        no_position = Element(AXRole="AXMenuItem", AXFrame=frame())
        self.menu.attrs["AXChildren"] = [self.item, no_position]

        session = self.start(self.menu)

        self.assertEqual(session.targets, [self.item])
        self.query.assert_not_called()

    def test_initially_open_menu_numbers_only_menu_controls(self):
        session = self.start(self.menu)

        self.assertIs(session.menu, self.menu)
        self.assertEqual(session.targets, [self.item])
        self.assertEqual(self.talon.native_calls[-1], ("show", ([self.item],)))
        self.assertEqual(self.query.call_count, 1)
        self.assertIs(self.query.call_args.kwargs["root"], self.menu)

    def test_menu_text_anchor_labels_and_presses_the_logical_item(self):
        shortcut = Element(AXRole="AXStaticText", AXFrame=frame(x=70))
        title = Element(AXRole="AXStaticText", AXFrame=frame(x=25))
        group = Element(AXRole="AXGroup", AXChildren=[shortcut, title])
        self.item.attrs["AXChildren"] = [group]

        session = self.start(self.menu)

        self.assertEqual(session.targets, [self.item])
        self.assertEqual(session.labelled, [title])
        self.assertEqual(self.talon.native_calls[-1], ("show", ([title],)))
        self.talon.native_calls.clear()
        self.talon.dispatch_labels("select", 1)
        self.assertEqual(self.item.performed, ["AXPress"])
        self.assertNotIn(("select", (1,)), self.talon.native_calls)
        self.assertEqual(self.talon.native_calls.count(("hide", ())), 1)

    def test_menu_text_anchor_ignores_nested_controls_and_menus(self):
        nested_text = Element(AXRole="AXStaticText", AXFrame=frame())
        button = Element(AXRole="AXButton", AXChildren=[nested_text])
        submenu = Element(AXRole="AXMenu", AXChildren=[nested_text])
        self.item.attrs["AXChildren"] = [button, submenu]

        session = self.start(self.menu)

        self.assertEqual(session.labelled, [self.item])

    def test_menu_text_anchor_ignores_hidden_and_outside_text(self):
        hidden = Element(AXRole="AXStaticText", AXHidden=True, AXFrame=frame())
        outside = Element(AXRole="AXStaticText", AXFrame=frame(x=500))
        self.item.attrs["AXChildren"] = [hidden, outside]

        session = self.start(self.menu)

        self.assertEqual(session.labelled, [self.item])

    def test_window_menu_item_keeps_native_label_and_selection(self):
        text = Element(AXRole="AXStaticText", AXFrame=frame())
        self.item.attrs["AXChildren"] = [text]
        self.results[id(self.window)] = [self.item]

        session = self.start()

        self.assertEqual(session.labelled, [self.item])
        self.talon.dispatch_labels("select", 1)
        self.assertIn(("select", (1,)), self.talon.native_calls)

    def test_menu_query_uses_menu_clip_not_window_clip(self):
        self.talon.settings["user.accessibility_clip_to_surface"] = True
        outside = Element(AXRole="AXMenuItem", AXFrame=frame(x=400))
        self.results[id(self.menu)] = [self.item, outside]

        session = self.start(self.menu)

        self.assertEqual(session.targets, [self.item])
        self.assertIs(self.query.call_args.kwargs["root"], self.menu)
        self.assertFalse(self.query.call_args.kwargs["visible_only"])

    def test_menu_poll_does_not_repeat_window_queries(self):
        session = self.start()

        self.talon.cron.interval.assert_called_once_with("100ms", session._check_menu)
        for _ in range(10):
            session._check_menu()

        self.assertEqual(self.query.call_count, 1)
        self.talon.cron.after.assert_not_called()

    def test_stopped_menu_poll_does_not_hide_replacement_session(self):
        session = self.start()
        switched = False

        def switch_during_poll():
            nonlocal switched
            if not switched:
                switched = True
                self.talon.dispatch_labels("hide")
                self.actions.accessibility_show_application_numbers()
                self.talon.native_calls.clear()
                return self.menu
            return None

        with patch.object(
            self.module.ui, "active_menu", side_effect=switch_during_poll
        ):
            session._check_menu()

        self.assertTrue(session.stopped)
        self.assertIsNot(self.module._session, session)
        self.assertNotIn(("hide", ()), self.talon.native_calls)
        self.assertIn(SESSION_TAG, self.talon.active_tags())

    def test_stopped_menu_poll_error_does_not_stop_replacement_session(self):
        session = self.start()
        switched = False

        def fail_after_switch():
            nonlocal switched
            if not switched:
                switched = True
                self.talon.dispatch_labels("hide")
                self.actions.accessibility_show_application_numbers()
                self.talon.native_calls.clear()
                raise UIErr("old session failed")
            return None

        with patch.object(self.module.ui, "active_menu", side_effect=fail_after_switch):
            session._check_menu()

        self.assertTrue(session.stopped)
        self.assertIsNot(self.module._session, session)
        self.assertNotIn(("hide", ()), self.talon.native_calls)
        self.talon.notify.assert_not_called()

    def test_stopped_refresh_does_not_stop_replacement_on_empty_result(self):
        session = self.start()
        switched = False

        def finish_after_switch(owner, menu, window):
            nonlocal switched
            if not switched:
                switched = True
                self.talon.dispatch_labels("hide")
                self.actions.accessibility_show_application_numbers()
                self.talon.native_calls.clear()
                return [], []
            return [self.button], []

        with patch.object(self.collection, "collect", side_effect=finish_after_switch):
            session.refresh(force=True)

        self.assertTrue(session.stopped)
        self.assertIsNot(self.module._session, session)
        self.assertEqual(self.module._session.targets, [self.button])
        self.assertNotIn(("hide", ()), self.talon.native_calls)
        self.talon.notify.assert_not_called()

    def test_stopped_focus_check_does_not_hide_replacement_session(self):
        for operation in ("select", "back", "refresh"):
            with self.subTest(operation=operation):
                session = self.start(self.menu)
                switched = False

                def change_session_during_focus_check():
                    nonlocal switched
                    if not switched:
                        switched = True
                        self.talon.dispatch_labels("hide")
                        self.actions.accessibility_show_application_numbers()
                        self.talon.native_calls.clear()
                        return types.SimpleNamespace(pid=2)
                    return self.talon.active_app

                with patch.object(
                    self.module.ui,
                    "active_app",
                    side_effect=change_session_during_focus_check,
                ):
                    if operation == "select":
                        self.talon.dispatch_labels("select", 1)
                    elif operation == "back":
                        self.actions.accessibility_application_numbers_back()
                    else:
                        session.refresh()

                self.assertTrue(session.stopped)
                self.assertIsNot(self.module._session, session)
                self.assertNotIn(("hide", ()), self.talon.native_calls)
                self.talon.notify.assert_not_called()

    def test_mouse_opened_menu_replaces_window_and_close_restores_it(self):
        session = self.start()
        self.talon.active_menu = self.menu

        session._check_menu()
        self.assertEqual(self.talon.native_calls[-1], ("hide", ()))
        self.assertIs(self.module._session, session)
        self.assertEqual(self.query.call_count, 1)
        self.finish_refresh()

        self.assertIs(session.menu, self.menu)
        self.assertEqual(session.targets, [self.item])
        self.assertIs(self.query.call_args.kwargs["root"], self.menu)

        self.talon.active_menu = None
        session._check_menu()
        self.finish_refresh()

        self.assertIsNone(session.menu)
        self.assertEqual(session.targets, [self.button])
        self.assertIs(self.query.call_args.kwargs["root"], self.window)

    def test_manual_submenu_transition_only_numbers_current_menu(self):
        session = self.start(self.menu)
        submenu, item = self.nested_menu()
        self.talon.active_menu = submenu

        session._check_menu()
        self.finish_refresh()

        self.assertIs(session.menu, submenu)
        self.assertEqual(session.targets, [item])
        self.assertIs(self.query.call_args.kwargs["root"], submenu)

    def test_selection_rejects_stale_window_labels_after_menu_opens(self):
        session = self.start()
        self.talon.active_menu = self.menu

        self.talon.dispatch_labels("select", 1)

        self.assertNotIn(("select", (1,)), self.talon.native_calls)
        self.assertIs(self.module._session, session)
        self.assertIn("menu changed", self.talon.notify.call_args.args[1].lower())
        self.finish_refresh()
        self.assertEqual(session.targets, [self.item])

    def test_select_and_back_wait_for_in_progress_refresh(self):
        session = self.start(self.menu)
        session.refreshing = True

        self.talon.dispatch_labels("select", 1)
        self.actions.accessibility_application_numbers_back()

        self.assertNotIn(("select", (1,)), self.talon.native_calls)
        self.module.actions.key.assert_not_called()
        self.assertIs(self.module._session, session)
        self.assertEqual(self.talon.notify.call_count, 2)
        self.assertTrue(
            all(
                "refresh" in call.args[1].lower()
                for call in self.talon.notify.call_args_list
            )
        )

    def test_menu_monitor_is_cancelled_with_session(self):
        session = self.start()
        job = session.job
        self.talon.dispatch_labels("hide")
        self.assertTrue(session.stopped)
        self.talon.cron.cancel.assert_any_call(job)

    def test_menu_change_prevents_stale_deferred_append(self):
        session = self.start()
        self.talon.active_menu = self.menu
        with patch.object(self.collection, "collect_deferred") as deferred:
            session._append_deferred(self.window, [self.button], [])
        deferred.assert_not_called()
        self.finish_refresh()
        self.assertEqual(session.targets, [self.item])

    def test_menu_change_during_query_never_renders_stale_targets(self):
        session = self.start()
        self.talon.active_menu = self.menu

        def query(*args, root, **kwargs):
            if root is self.menu:
                self.talon.active_menu = None
            return self.results[id(root)]

        self.query.side_effect = query
        session._check_menu()
        self.finish_refresh()

        self.assertNotIn(("show", ([self.item],)), self.talon.native_calls)
        self.finish_refresh()
        self.assertEqual(session.targets, [self.button])

    def test_temporarily_empty_menu_is_retried_without_stopping(self):
        session = self.start()
        self.talon.active_menu = self.menu
        self.results[id(self.menu)] = []
        session._check_menu()
        self.finish_refresh()

        self.assertIs(self.module._session, session)
        self.assertEqual(self.talon.cron.after.call_args.args[0], "100ms")
        self.results[id(self.menu)] = [self.item]
        self.finish_refresh()
        self.assertEqual(session.targets, [self.item])

    def test_transition_hide_preserves_an_existing_hide_guard(self):
        session = self.start()
        session.preserve_hide = True

        session.hide_for_transition()

        self.assertTrue(session.preserve_hide)
        self.assertIs(self.module._session, session)
        session.preserve_hide = False

    def test_menu_monitor_error_stops_and_notifies(self):
        session = self.start()
        with patch.object(self.module.ui, "active_menu", side_effect=UIErr("failed")):
            session._check_menu()
        self.assertTrue(session.stopped)
        self.assertIsNone(self.module._session)
        self.talon.notify.assert_called_once_with(
            "Application control labels",
            "Unable to query the focused accessibility window.",
        )


if __name__ == "__main__":
    unittest.main()
