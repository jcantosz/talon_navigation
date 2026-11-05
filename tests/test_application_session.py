import types
import unittest
from unittest.mock import Mock, patch

# Talon imports packages; unittest discovery can load these modules top-level.
if __package__:
    from .accessibility_support import (
        ROOT,
        SESSION_TAG,
        ApplicationTestCase,
        Element,
        FakeTalon,
        frame,
        load,
    )
else:
    from accessibility_support import (
        ROOT,
        SESSION_TAG,
        ApplicationTestCase,
        Element,
        FakeTalon,
        frame,
        load,
    )


class ApplicationSessionTests(ApplicationTestCase):
    def test_helpers_do_not_register_talon_contexts_or_events(self):
        for filename in ("controls.py", "activation.py", "application_session.py"):
            with self.subTest(filename=filename):
                fake = FakeTalon()
                module = load(fake, f"application_controls/{filename}")
                self.assertEqual(fake.contexts, [])
                self.assertEqual(fake.declared_tags, [])
                self.assertEqual(fake.declared_settings, {})
                module.ui.register.assert_not_called()

    def test_show_numbers_overrides_default_and_keeps_legacy_query(self):
        self.assertIn("user.application_numbers_enabled", self.talon.active_tags())
        grammar = (
            ROOT / "application_controls" / "inventory_enabled.talon"
        ).read_text()
        default = (
            "show numbers [once]:\n    user.accessibility_show_application_numbers()"
        )
        self.assertIn("tag: user.application_numbers_enabled", grammar)
        self.assertIn(default, grammar)
        self.assertIn(
            "show (legacy | native | talon) numbers [once]:\n"
            '    labels.show_query("[AXPosition]:action(AXPress)")',
            grammar,
        )
        backup = (ROOT / "application_controls" / "inventory.talon").read_text()
        self.assertIn("show application numbers:", backup)

    def test_entrypoint_preserves_command_settings_and_event_registrations(self):
        self.assertEqual(len(self.talon.contexts), 4)
        self.assertEqual(
            self.talon.declared_tags,
            [
                "application_numbers_enabled",
                "application_labels_active",
                "application_labels_session",
            ],
        )
        self.assertEqual(
            {
                name: (setting["type"], setting["default"])
                for name, setting in self.talon.declared_settings.items()
            },
            {
                "accessibility_activation_disallowed_bundles": (str, ""),
                "accessibility_query_max_depth": (int, 0),
                "accessibility_query_timeout": (float, 1.0),
                "accessibility_defer_web_areas": (bool, False),
                "accessibility_clip_to_surface": (bool, False),
            },
        )
        self.assertEqual(
            {name for name, value in vars(self.actions).items() if callable(value)},
            {
                "accessibility_prepare_active_app",
                "accessibility_show_application_numbers",
                "accessibility_refresh_application_numbers",
                "accessibility_application_numbers_back",
                "accessibility_set_interfaces",
            },
        )
        self.assertEqual(
            [call.args for call in self.module.ui.register.call_args_list],
            [
                ("win_focus", self.module._focus_changed),
                ("app_activate", self.module._focus_changed),
                ("win_open", self.module._window_changed),
                ("win_close", self.module._window_changed),
                ("element", self.module._element_changed),
            ],
        )

    def test_application_numbers_stop_an_existing_label_session(self):
        for tag in ("user.menu_labels_active", "user.status_labels_active"):
            with self.subTest(tag=tag):
                self.talon.dispatch_labels("hide")
                publisher = self.talon.Context()
                publisher.tags = [tag]
                context = self.talon.Context()
                context.matches = f"tag: {tag}"
                stopped = Mock()

                def hide_foreign():
                    self.talon.next_action()
                    publisher.tags = []
                    stopped()

                self.talon.overrides[(id(context), "labels")] = type(
                    "ForeignLabels", (), {"hide": staticmethod(hide_foreign)}
                )

                self.actions.accessibility_show_application_numbers()

                stopped.assert_called_once()
                self.assertNotIn(tag, self.talon.active_tags())
                self.assert_session_active(True)

    def test_stopped_session_cannot_clear_replacement_session_tag(self):
        self.actions.accessibility_show_application_numbers()
        previous = self.module._session
        self.actions.accessibility_show_application_numbers()
        replacement = self.module._session

        previous.stop()

        self.assertTrue(previous.stopped)
        self.assertIs(self.module._session, replacement)
        self.assertIn(SESSION_TAG, self.talon.active_tags())

    def test_stopped_render_does_not_hide_a_replacement_session(self):
        self.actions.accessibility_show_application_numbers()
        session = self.module._session
        native_show = self.module.actions.labels.show
        switched = False

        def show_then_replace(targets):
            nonlocal switched
            native_show(targets)
            if not switched:
                switched = True
                self.talon.dispatch_labels("hide")
                self.actions.accessibility_show_application_numbers()
                self.talon.native_calls.clear()

        with patch.object(
            self.module.actions.labels, "show", side_effect=show_then_replace
        ):
            session.refresh(force=True)

        self.assertTrue(session.stopped)
        self.assertIsNotNone(self.module._session)
        self.assertIsNot(self.module._session, session)
        self.assertNotIn(("hide", ()), self.talon.native_calls)
        self.assertIn(SESSION_TAG, self.talon.active_tags())

    def test_stopped_render_hides_its_own_orphaned_labels(self):
        self.actions.accessibility_show_application_numbers()
        session = self.module._session
        native_show = self.module.actions.labels.show

        def show_then_stop(targets):
            native_show(targets)
            self.module._stop()

        with patch.object(
            self.module.actions.labels, "show", side_effect=show_then_stop
        ):
            session.refresh(force=True)

        self.assertTrue(session.stopped)
        self.assertIsNone(self.module._session)
        self.assertEqual(self.talon.native_calls[-1], ("hide", ()))

    def test_replaced_session_does_not_select_new_session_label(self):
        self.actions.accessibility_show_application_numbers()
        previous = self.module._session

        def replace_session(target):
            self.talon.dispatch_labels("hide")
            self.actions.accessibility_show_application_numbers()
            return target

        with patch.object(
            self.collection, "row_activation_target", side_effect=replace_session
        ):
            self.talon.dispatch_labels("select", 1)

        self.assertTrue(previous.stopped)
        self.assertIsNot(self.module._session, previous)
        self.assertNotIn(("select", (1,)), self.talon.native_calls)
        self.assertIn(SESSION_TAG, self.talon.active_tags())

    def test_row_activation_does_not_hide_a_replacement_session(self):
        row, _ = self.text_row(frame(x=40, y=25, width=60, height=18))
        self.talon.query_results = [row]
        self.actions.accessibility_show_application_numbers()
        previous = self.module._session

        def replace_session(action):
            self.talon.dispatch_labels("hide")
            self.actions.accessibility_show_application_numbers()
            self.talon.native_calls.clear()

        with patch.object(row, "perform", side_effect=replace_session):
            self.talon.dispatch_labels("select", 1)

        self.assertTrue(previous.stopped)
        self.assertIsNot(self.module._session, previous)
        self.assertNotIn(("hide", ()), self.talon.native_calls)
        self.assertIn(SESSION_TAG, self.talon.active_tags())

    def test_tag_activates_overrides_and_hide_clears_it(self):
        self.actions.accessibility_show_application_numbers()
        self.assertIn(("show", ([self.button, self.popup],)), self.talon.native_calls)
        self.assert_session_active(True)

        self.talon.modules()[0].actions.labels.select(1)
        self.assertIn(("select", (1,)), self.talon.native_calls)

        self.talon.modules()[0].actions.labels.hide()
        self.assertIn(("hide", ()), self.talon.native_calls)
        self.assertIsNone(self.module._session)
        self.assert_session_active(False)

    def test_expanding_selection_keeps_session_and_schedules_refresh(self):
        self.actions.accessibility_show_application_numbers()
        session = self.module._session

        self.talon.modules()[0].actions.labels.select(2)

        self.assertIn(("select", (2,)), self.talon.native_calls)
        self.assertIs(self.module._session, session)
        self.talon.cron.after.assert_called_once()
        self.assert_session_active(True)

    def test_reload_stops_previous_session_and_cancels_refresh(self):
        self.actions.accessibility_show_application_numbers()
        session = self.module._session
        previous_context = self.module.session_ctx
        session.request_refresh()
        job = session.refresh_job

        load(self.talon, "application_controls/inventory.py", self.module)

        self.assertTrue(session.stopped)
        self.talon.cron.cancel.assert_any_call(job)
        self.assertIsNone(self.module._session)
        self.assertEqual(previous_context.tags, [])
        self.assert_session_active(False)
        self.assertNotIn(SESSION_TAG, self.talon.active_tags())

    def test_selection_after_window_change_is_rejected(self):
        self.actions.accessibility_show_application_numbers()
        self.application.attrs["AXFocusedWindow"] = Element(AXRole="AXWindow")

        self.talon.modules()[0].actions.labels.select(1)

        self.assertNotIn(("select", (1,)), self.talon.native_calls)
        self.assertIsNone(self.module._session)
        self.assertIn("focused window changed", self.talon.notify.call_args[0][1])

    def test_stale_target_reports_error_without_raising(self):
        self.actions.accessibility_show_application_numbers()
        self.popup.dead = True

        self.talon.modules()[0].actions.labels.select(2)

        self.assertIsNone(self.module._session)
        self.talon.notify.assert_called_with(
            "Application control labels",
            "Unable to activate the selected control.",
        )

    def test_normal_selection_cleans_up_when_native_labels_hide(self):
        self.talon.hide_after_select = True
        self.actions.accessibility_show_application_numbers()

        self.talon.dispatch_labels("select", 1)

        self.assertIn(("select", (1,)), self.talon.native_calls)
        self.assertIsNone(self.module._session)
        self.assert_session_active(False)

    def test_normal_selection_cleans_up_when_native_labels_do_not_hide(self):
        self.actions.accessibility_show_application_numbers()

        self.talon.dispatch_labels("select", 1)

        self.assertIsNone(self.module._session)
        self.assert_session_active(False)
        self.assertEqual(self.talon.native_calls[-1], ("hide", ()))

    def test_failed_expansion_keeps_session_and_numbers_opened_menu(self):
        self.actions.accessibility_show_application_numbers()
        session = self.module._session
        menu_item = Element(
            AXRole="AXMenuItem",
            AXPosition=(10, 10),
            AXFrame=frame(x=10, y=10, width=100, height=20),
        )
        menu = Element(
            AXRole="AXMenu",
            AXFrame=frame(width=200, height=200),
            AXChildren=[menu_item],
        )
        menu_item.attrs["AXParent"] = menu

        def open_then_fail(*args):
            if not args:
                return self.talon.next_action()
            self.talon.active_menu = menu
            raise self.module.ui.ActionFailed()

        self.talon.native_calls.clear()
        with patch.object(self.module.actions, "next", side_effect=open_then_fail):
            self.talon.dispatch_labels("select", 2)

        self.assertIs(self.module._session, session)
        self.assertFalse(session.stopped)
        self.assertFalse(session.selecting)
        self.assertEqual(self.talon.native_calls, [("hide", ())])
        self.talon.notify.assert_not_called()
        self.talon.cron.after.assert_called_once_with(
            "100ms", session._refresh_after_event
        )

        self.talon.cron.after.call_args.args[1]()

        self.assertIs(self.module._session, session)
        self.assertIs(session.menu, menu)
        self.assertEqual(self.talon.native_calls[-1], ("show", ([menu_item],)))

    def test_failed_ordinary_selection_cancels_refresh_and_stops_session(self):
        self.actions.accessibility_show_application_numbers()
        session = self.module._session
        session.request_refresh()
        job = session.refresh_job
        with patch.object(
            self.module.actions, "next", side_effect=self.module.ui.ActionFailed()
        ):
            self.talon.dispatch_labels("select", 1)

        self.assertTrue(session.stopped)
        self.assertIsNone(self.module._session)
        self.talon.cron.cancel.assert_any_call(job)
        self.assertNotIn(SESSION_TAG, self.talon.active_tags())
        self.talon.notify.assert_called_with(
            "Application control labels", "Unable to activate the selected control."
        )

    def test_tab_selection_survives_hide_and_redraws(self):
        self.button.attrs["AXRole"] = "AXTab"
        self.talon.hide_after_select = True
        self.actions.accessibility_show_application_numbers()
        session = self.module._session

        self.talon.dispatch_labels("select", 1)
        self.talon.cron.after.call_args.args[1]()

        self.assertIs(self.module._session, session)
        self.assertEqual(
            self.talon.native_calls[-1], ("show", ([self.button, self.popup],))
        )

    def test_expansion_does_not_render_during_native_press(self):
        self.actions.accessibility_show_application_numbers()
        session = self.module._session

        def press_with_events(*args):
            if not args:
                return self.talon.next_action()
            self.talon.active_menu = Element(
                AXRole="AXMenu", AXFrame=frame(width=200, height=200)
            )
            session._check_menu()
            session.refresh()
            self.module._element_changed()
            self.assertIsNone(session.refresh_job)
            self.talon.dispatch_labels("hide")

        self.talon.native_calls.clear()
        with patch.object(self.module.actions, "next", side_effect=press_with_events):
            self.talon.dispatch_labels("select", 2)

        self.assertIs(self.module._session, session)
        self.assertFalse(session.selecting)
        self.assertEqual(session.signature, ())
        self.assertEqual(self.talon.native_calls, [("hide", ())])
        self.talon.cron.after.assert_called_once_with(
            "100ms", session._refresh_after_event
        )

    def test_radio_tab_refreshes_but_ordinary_radio_dismisses(self):
        for parent_role in ("AXTabGroup", "AXGroup"):
            with self.subTest(parent_role=parent_role):
                self.button.attrs.update(
                    AXRole="AXRadioButton", AXParent=Element(AXRole=parent_role)
                )
                self.talon.hide_after_select = True
                self.actions.accessibility_show_application_numbers()
                session = self.module._session

                self.talon.dispatch_labels("select", 1)

                if parent_role == "AXTabGroup":
                    self.assertIs(self.module._session, session)
                    self.talon.cron.after.call_args.args[1]()
                    self.assertEqual(
                        self.talon.native_calls[-1],
                        ("show", ([self.button, self.popup],)),
                    )
                else:
                    self.assertIsNone(self.module._session)

    def test_expansion_survives_native_hide_and_refreshes_new_targets(self):
        self.talon.hide_after_select = True
        self.actions.accessibility_show_application_numbers()
        session = self.module._session

        self.talon.dispatch_labels("select", 2)

        self.assertIs(self.module._session, session)
        self.assert_session_active(True)
        self.talon.cron.after.assert_called_once_with(
            "100ms", session._refresh_after_event
        )
        self.talon.query_results = [self.button]
        self.talon.cron.after.call_args.args[1]()
        self.assertEqual(session.targets, [self.button])
        self.assertIsNone(session.refresh_job)
        self.assertEqual(self.talon.native_calls[-1], ("show", ([self.button],)))

    def test_expansion_restores_labels_when_targets_do_not_change(self):
        self.talon.hide_after_select = True
        self.actions.accessibility_show_application_numbers()
        session = self.module._session

        self.talon.dispatch_labels("select", 2)
        self.talon.cron.after.call_args.args[1]()

        self.assertIs(self.module._session, session)
        self.assertEqual(
            self.talon.native_calls[-1], ("show", ([self.button, self.popup],))
        )

    def test_invalid_number_is_rejected_without_native_selection(self):
        self.actions.accessibility_show_application_numbers()

        self.talon.dispatch_labels("select", 99)

        self.assertNotIn(("select", (99,)), self.talon.native_calls)
        self.assertIsNone(self.module._session)
        self.talon.notify.assert_called_with(
            "Application control labels", "That number no longer matches a control."
        )

    def test_app_change_stops_session_and_cancels_pending_refresh(self):
        self.actions.accessibility_show_application_numbers()
        session = self.module._session
        session.request_refresh()
        job = session.refresh_job

        self.module._focus_changed(types.SimpleNamespace(pid=2))

        self.assertTrue(session.stopped)
        self.assertIsNone(self.module._session)
        self.talon.cron.cancel.assert_any_call(job)
        self.assert_session_active(False)


if __name__ == "__main__":
    unittest.main()
