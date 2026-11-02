import unittest
from unittest.mock import Mock, patch

# Talon imports packages; unittest discovery can load these modules top-level.
if __package__:
    from .accessibility_support import (
        ApplicationTestCase,
        Element,
        frame,
    )
else:
    from accessibility_support import (
        ApplicationTestCase,
        Element,
        frame,
    )


class ApplicationWebAreasTests(ApplicationTestCase):
    def staged_window(self):
        self.talon.settings["user.accessibility_defer_web_areas"] = True
        self.close = Element(
            AXRole="AXButton", AXPosition=(0, 0), AXFrame=frame(x=1, width=10)
        )
        self.workbench = Element(AXRole="AXWebArea", AXTitle="Doc", AXFrame=frame())
        self.page = Element(
            AXRole="AXWebArea", AXTitle="Page", AXFrame=frame(width=200, height=200)
        )
        container = Element(AXRole="AXGroup", AXChildren=[self.workbench, self.page])
        container.actions = []
        self.window.attrs.update(AXTitle="Doc", AXChildren=[self.close, container])
        self.button.attrs["AXParent"] = self.workbench
        self.popup.attrs["AXParent"] = self.page
        results = {id(self.workbench): [self.button], id(self.page): [self.popup]}
        return Mock(side_effect=lambda *args, root, **kwargs: results[id(root)])

    def run_deferred(self):
        callback = self.talon.cron.after.call_args.args[1]
        callback()

    def test_deferred_web_areas_append_after_primary_numbers(self):
        query = self.staged_window()
        hit = Element(AXRole="AXStaticText", AXParent=self.page)
        with patch.object(self.collection.axquery, "query_all", query):
            with patch.object(self.module.ui, "element_at", return_value=hit) as at:
                self.actions.accessibility_show_application_numbers()
                self.assertEqual(
                    self.talon.native_calls[-1], ("show", ([self.close, self.button],))
                )
                at.assert_not_called()
                self.run_deferred()
        self.assertEqual(
            self.module._session.targets, [self.close, self.button, self.popup]
        )
        self.assertEqual(
            self.talon.native_calls[-1],
            ("show", ([self.close, self.button, self.popup],)),
        )
        self.assertEqual(at.call_count, 1)
        self.assertEqual(query.call_count, 2)

    def test_covered_deferred_web_area_is_not_walked(self):
        query = self.staged_window()
        for hit in (
            Element(AXRole="AXTextArea", AXParent=self.workbench),
            RuntimeError("No element found."),
        ):
            with self.subTest(hit=hit):
                query.reset_mock()
                self.talon.native_calls.clear()
                with patch.object(self.collection.axquery, "query_all", query):
                    with patch.object(
                        self.module.ui,
                        "element_at",
                        **(
                            {"side_effect": hit}
                            if isinstance(hit, Exception)
                            else {"return_value": hit}
                        ),
                    ):
                        self.actions.accessibility_show_application_numbers()
                        self.run_deferred()
                self.assertEqual(
                    self.module._session.targets, [self.close, self.button]
                )
                self.assertEqual(
                    self.talon.native_calls,
                    [("hide", ()), ("show", ([self.close, self.button],))],
                )
                self.assertEqual(query.call_count, 1)

    def test_deferred_web_area_errors_are_surfaced(self):
        query = self.staged_window()
        with patch.object(self.collection.axquery, "query_all", query):
            with patch.object(
                self.module.ui, "element_at", side_effect=RuntimeError("Provider")
            ):
                self.actions.accessibility_show_application_numbers()
                self.run_deferred()
        self.assertIsNone(self.module._session)
        self.talon.notify.assert_called_with(
            "Application control labels",
            "Unable to query the focused accessibility window.",
        )

    def test_deferred_append_waits_for_window_and_session(self):
        query = self.staged_window()
        with patch.object(self.collection.axquery, "query_all", query):
            self.actions.accessibility_show_application_numbers()
            session = self.module._session
            self.application.attrs["AXFocusedWindow"] = Element(AXRole="AXWindow")
            with patch.object(session, "request_refresh") as refresh:
                self.run_deferred()
            refresh.assert_called_once_with("0ms")
            self.assertEqual(session.targets, [self.close, self.button])

            self.application.attrs["AXFocusedWindow"] = self.window
            self.actions.accessibility_show_application_numbers()
            job = self.module._session.deferred_job
            self.module._stop()
            self.talon.cron.cancel.assert_any_call(job)

    def test_refresh_collects_deferred_web_areas_synchronously(self):
        query = self.staged_window()
        hit = Element(AXRole="AXStaticText", AXParent=self.page)
        with patch.object(self.collection.axquery, "query_all", query):
            with patch.object(self.module.ui, "element_at", return_value=hit):
                self.actions.accessibility_show_application_numbers()
                session = self.module._session
                job = session.deferred_job
                session.refresh()
        self.talon.cron.cancel.assert_called_with(job)
        self.assertIsNone(session.deferred_job)
        self.assertEqual(session.targets, [self.close, self.button, self.popup])

    def test_window_without_matching_primary_web_area_is_queried_whole(self):
        query = self.staged_window()
        self.window.attrs["AXTitle"] = "Other"
        with patch.object(self.collection.axquery, "query_all", query):
            with patch.object(self.module.ui, "element_at") as at:
                query.side_effect = lambda *args, root, **kwargs: [self.button]
                self.actions.accessibility_show_application_numbers()
        query.assert_called_once()
        self.assertIs(query.call_args.kwargs["root"], self.window)
        at.assert_not_called()
        self.talon.cron.after.assert_not_called()

    def test_deferred_web_areas_are_opt_in(self):
        self.staged_window()
        self.talon.settings["user.accessibility_defer_web_areas"] = False
        with patch.object(self.module.ui, "element_at") as at:
            self.actions.accessibility_show_application_numbers()
        at.assert_not_called()
        self.talon.cron.after.assert_not_called()
        self.assertEqual(self.module._session.targets, [self.button, self.popup])

    def test_deferred_web_areas_use_the_window_clip(self):
        query = self.staged_window()
        self.talon.settings["user.accessibility_clip_to_surface"] = True
        self.window.attrs["AXFrame"] = frame(x=0, y=0, width=500, height=500)
        below = Element(AXRole="AXLink", AXFrame=frame(y=900), AXParent=self.page)
        results = {
            id(self.workbench): [self.button],
            id(self.page): [self.popup, below],
        }
        query.side_effect = lambda *args, root, **kwargs: results[id(root)]
        hit = Element(AXRole="AXStaticText", AXParent=self.page)
        with patch.object(self.collection.axquery, "query_all", query):
            with patch.object(self.module.ui, "element_at", return_value=hit):
                self.actions.accessibility_show_application_numbers()
                self.run_deferred()
        self.assertEqual(
            self.module._session.targets, [self.close, self.button, self.popup]
        )
        self.assertTrue(
            all(call.kwargs["visible_only"] is False for call in query.call_args_list)
        )

    def test_web_area_cache_uses_equality_for_unhashable_elements(self):
        class UnhashableElement(Element):
            __hash__ = None

            def __eq__(self, other):
                return (
                    isinstance(other, UnhashableElement) and self.attrs is other.attrs
                )

        area = UnhashableElement(AXRole="AXWebArea")
        child = UnhashableElement(AXParent=area)
        cache = []
        self.assertIs(self.collection._web_area(child, cache), area)
        alias = UnhashableElement()
        alias.attrs = child.attrs
        with patch.object(alias, "get", side_effect=AssertionError("not cached")):
            self.assertIs(self.collection._web_area(alias, cache), area)
        self.assertIsNone(self.collection._web_area(None, cache))

    def test_web_area_ancestry_cycle_surfaces_an_error(self):
        cyclic = Element(AXRole="AXGroup")
        cyclic.attrs["AXParent"] = cyclic
        with self.assertRaisesRegex(RuntimeError, "ancestry"):
            self.collection._web_area(cyclic, [])

    def test_selection_rechecks_web_area_after_tab_changes(self):
        self.talon.settings["user.accessibility_defer_web_areas"] = True
        area = Element(AXRole="AXWebArea")
        self.button.attrs["AXParent"] = area
        self.talon.query_results = [self.button]
        with patch.object(self.module.ui, "element_at", return_value=self.button):
            self.actions.accessibility_show_application_numbers()
        unrelated = Element(AXRole="AXWebArea")
        with patch.object(self.module.ui, "element_at", return_value=unrelated):
            self.talon.dispatch_labels("select", 1)
        self.assertNotIn(("select", (1,)), self.talon.native_calls)
        self.assertIsNone(self.module._session)
        self.assertIn("web area is covered", self.talon.notify.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
