from unittest.mock import Mock, patch

if __package__:
    from .accessibility_support import ApplicationTestCase, Element, frame
else:
    from accessibility_support import ApplicationTestCase, Element, frame


class SectionNumberTests(ApplicationTestCase):
    def setUp(self):
        super().setUp()
        self.section = Element(
            AXRole="AXGroup", AXFrame=frame(x=0, y=0, width=200, height=400)
        )
        self.section.actions = []
        self.resolve = Mock(return_value=self.section)
        self.button.attrs["AXParent"] = self.section
        self.popup.attrs["AXParent"] = self.section

    def test_scoped_query_uses_real_root_clips_and_reuses_selection(self):
        outside = Element(AXRole="AXButton", AXFrame=frame(x=300))
        self.talon.query_results = [self.button, outside]
        query = Mock(return_value=self.talon.query_results)
        with patch.object(self.collection.axquery, "query_all", query):
            self.actions.accessibility_show_section_numbers(self.resolve)
            session = self.module._session
            self.assertEqual(session.targets, [self.button])
            self.assertIs(session.scope_root, self.section)
            query.assert_called_with(
                self.collection.QUERY,
                root=self.section,
                visible_only=False,
                max_depth=-1,
                timeout=1.0,
            )
            query.assert_called_once()
            self.resolve.assert_called_once_with()
            self.talon.dispatch_labels("select", 1)
            query.assert_called_once()
        self.assertIn(("select", (1,)), self.talon.native_calls)

    def test_replaced_section_refuses_old_number_and_refreshes(self):
        self.actions.accessibility_show_section_numbers(self.resolve)
        original = self.module._session
        self.resolve.return_value = Element(
            AXRole="AXGroup", AXFrame=self.section.get("AXFrame")
        )
        self.talon.dispatch_labels("select", 1)
        self.assertNotIn(("select", (1,)), self.talon.native_calls)
        self.assertIsNotNone(original.refresh_job)
        self.assertIn("section changed", self.talon.notify.call_args.args[1])

    def test_unrelated_control_set_change_does_not_requery_or_block_unchanged_target(
        self,
    ):
        self.actions.accessibility_show_section_numbers(self.resolve)
        self.talon.query_results = [self.popup]
        with patch.object(
            self.collection,
            "collect_section",
            side_effect=AssertionError("Unnecessary requery"),
        ):
            self.talon.dispatch_labels("select", 1)
        self.assertIn(("select", (1,)), self.talon.native_calls)

    def test_missing_section_stops_without_window_fallback(self):
        self.actions.accessibility_show_section_numbers(self.resolve)
        self.resolve.side_effect = RuntimeError("Section disappeared")
        with self.assertLogs(level="ERROR"):
            self.module._session.refresh()
        self.assertIsNone(self.module._session)
        self.assert_session_active(False)

    def test_full_window_command_replaces_scope_and_hide_stops_it(self):
        self.actions.accessibility_show_section_numbers(self.resolve)
        scoped = self.module._session
        self.actions.accessibility_show_application_numbers()
        self.assertTrue(scoped.stopped)
        self.assertIsNone(self.module._session.scope)
        self.talon.dispatch_labels("hide")
        self.assertIsNone(self.module._session)

    def test_initial_empty_section_retries_then_renders_without_window_fallback(self):
        self.talon.query_results = []
        self.actions.accessibility_show_section_numbers(self.resolve)
        scoped = self.module._session
        self.assertIsNotNone(scoped)
        self.assertIsNotNone(scoped.start_retry_job)
        self.talon.query_results = [self.button]
        scoped._retry_start()
        self.assertEqual(scoped.targets, [self.button])
        self.assert_session_active(True)

    def test_persistently_empty_section_stops_after_startup_deadline(self):
        self.talon.query_results = []
        self.actions.accessibility_show_section_numbers(self.resolve)
        scoped = self.module._session
        scoped.start_deadline = 0
        scoped._retry_start()
        self.assertIsNone(self.module._session)
        self.assertIn("no visible pressable", self.talon.notify.call_args.args[1])

    def test_scroll_hides_without_stopping_then_schedules_refresh(self):
        self.actions.accessibility_show_section_numbers(self.resolve)
        scoped = self.module._session
        self.actions.accessibility_invalidate_numbers_for_scroll()
        self.assertIs(self.module._session, scoped)
        self.assertFalse(scoped.stopped)
        self.assertIsNotNone(scoped.refresh_job)

    def test_visible_table_rows_query_nested_cells_not_thousands_of_hidden_rows(self):
        row = Element(AXRole="AXRow", AXFrame=frame())
        row.actions = []
        cell = Element(AXRole="AXCell", AXParent=row, AXFrame=frame())
        row.attrs["AXChildren"] = [cell]
        table = Element(
            AXRole="AXTable", AXFrame=self.section.get("AXFrame"), AXVisibleRows=[row]
        )
        self.section.attrs["AXChildren"] = [table]
        query = Mock(return_value=[cell])
        with patch.object(self.collection.axquery, "query_all", query):
            found = self.collection.collect_section(self.section)
        self.assertEqual(found, [cell])
        self.assertIs(query.call_args.kwargs["root"], row)
        self.assertNotIn(table, [call.kwargs["root"] for call in query.call_args_list])

    def test_pressable_cell_is_not_duplicated_when_row_is_pressable(self):
        row = Element(AXRole="AXRow", AXFrame=frame())
        cell = Element(AXRole="AXCell", AXParent=row, AXFrame=frame())
        self.talon.query_results = [row, cell]
        self.assertEqual(self.collection.collect_section(self.section), [row])

    def test_visible_row_queries_respect_depth_limit_and_disabled_filter(self):
        row = Element(AXRole="AXRow", AXFrame=frame())
        row.actions = []
        cell = Element(AXRole="AXCell", AXParent=row, AXFrame=frame(), AXEnabled=False)
        table = Element(AXRole="AXTable", AXVisibleRows=[row])
        self.section.attrs["AXChildren"] = [table]
        self.talon.settings["user.accessibility_query_max_depth"] = 2
        query = Mock(return_value=[cell])
        with patch.object(self.collection.axquery, "query_all", query):
            self.assertEqual(self.collection.collect_section(self.section), [])
            query.assert_not_called()
            self.talon.settings["user.accessibility_query_max_depth"] = 3
            self.assertEqual(self.collection.collect_section(self.section), [])
            self.assertEqual(query.call_args.kwargs["max_depth"], 1)

    def test_focus_change_during_query_does_not_publish_stale_numbers(self):
        def changed(_):
            self.talon.active_app = None
            return [self.button]

        with patch.object(self.collection, "collect_section", side_effect=changed):
            self.actions.accessibility_show_section_numbers(self.resolve)
        self.assert_session_active(False)
        self.assertFalse(any(name == "show" for name, _ in self.talon.native_calls))

    def test_window_change_during_selection_recheck_does_not_press(self):
        self.actions.accessibility_show_section_numbers(self.resolve)

        def changed(*_):
            self.application.attrs["AXFocusedWindow"] = Element()
            return True

        with patch.object(self.collection, "section_target_valid", side_effect=changed):
            self.talon.dispatch_labels("select", 1)
        self.assertNotIn(("select", (1,)), self.talon.native_calls)
        self.assertIsNone(self.module._session)

    def test_detached_changed_hidden_disabled_unpressable_or_offscreen_target_is_not_pressed(
        self,
    ):
        attributes = self.button.attrs.copy()
        actions = self.button.actions[:]
        for change in (
            "detach",
            "title",
            "frame",
            "hidden",
            "disabled",
            "action",
            "offscreen",
        ):
            with self.subTest(change=change):
                self.button.attrs = attributes.copy()
                self.button.actions = actions[:]
                self.actions.accessibility_show_section_numbers(self.resolve)
                if change == "detach":
                    self.button.attrs["AXParent"] = None
                elif change == "title":
                    self.button.attrs["AXTitle"] = "Different control"
                elif change == "frame":
                    self.button.attrs["AXFrame"] = frame(x=50)
                elif change == "hidden":
                    self.button.attrs["AXHidden"] = True
                elif change == "disabled":
                    self.button.attrs["AXEnabled"] = False
                elif change == "action":
                    self.button.actions = []
                else:
                    self.button.attrs["AXFrame"] = frame(x=400)
                with patch.object(
                    self.collection,
                    "collect_section",
                    side_effect=AssertionError("Unnecessary requery"),
                ):
                    self.talon.dispatch_labels("select", 1)
                self.assertNotIn(("select", (1,)), self.talon.native_calls)
                self.assertIsNotNone(self.module._session.refresh_job)

    def test_dead_selected_target_is_reported_without_pressing(self):
        self.actions.accessibility_show_section_numbers(self.resolve)
        self.button.dead = True
        with (
            self.assertLogs(level="ERROR"),
            patch.object(
                self.collection,
                "collect_section",
                side_effect=AssertionError("Unnecessary requery"),
            ),
        ):
            self.talon.dispatch_labels("select", 1)
        self.assertNotIn(("select", (1,)), self.talon.native_calls)
        self.assertIsNone(self.module._session)

    def test_scoped_selection_does_not_depend_on_electron_hit_test_precision(self):
        self.actions.accessibility_show_section_numbers(self.resolve)
        with patch.object(
            self.collection.ui,
            "element_at",
            side_effect=AssertionError("Electron may return a generic ancestor"),
        ):
            self.talon.dispatch_labels("select", 1)
        self.assertIn(("select", (1,)), self.talon.native_calls)

    def test_pending_refresh_refuses_selection_until_new_numbers_are_rendered(self):
        self.actions.accessibility_show_section_numbers(self.resolve)
        self.module._session.request_refresh()
        with patch.object(self.collection, "section_target_valid") as validate:
            self.talon.dispatch_labels("select", 1)
            validate.assert_not_called()
        self.assertNotIn(("select", (1,)), self.talon.native_calls)
        self.assertIn("refreshing", self.talon.notify.call_args.args[1])
