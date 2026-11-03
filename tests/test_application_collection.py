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


class ApplicationCollectionTests(ApplicationTestCase):
    def test_application_query_keeps_all_shared_control_roles(self):
        controls = [
            Element(AXRole=role, AXFrame=frame())
            for role in sorted(self.collection.CONTROL_ROLES)
        ]
        self.talon.query_results = controls

        self.actions.accessibility_show_application_numbers()

        self.assertEqual(self.module._session.targets, controls)

    def test_application_query_uses_configured_depth(self):
        for configured, expected in ((0, -1), (13, 13), (40, 40)):
            with self.subTest(depth=configured):
                self.talon.settings["user.accessibility_query_max_depth"] = configured
                query = Mock(return_value=[self.button])
                with patch.object(self.collection.axquery, "query_all", query):
                    self.actions.accessibility_show_application_numbers()
                query.assert_called_once_with(
                    self.collection.QUERY,
                    root=self.window,
                    visible_only=True,
                    max_depth=expected,
                    timeout=1,
                )
                self.assertEqual(self.module._session.targets, [self.button])

    def test_application_query_uses_configured_timeout(self):
        self.talon.settings["user.accessibility_query_timeout"] = 3.0
        query = Mock(return_value=[self.button])
        with patch.object(self.collection.axquery, "query_all", query):
            self.actions.accessibility_show_application_numbers()
        self.assertEqual(query.call_args.kwargs["timeout"], 3.0)
        self.assertEqual(self.module._session.targets, [self.button])

    def test_invalid_query_budgets_are_rejected_before_querying(self):
        cases = [
            ("user.accessibility_query_max_depth", -1),
            *(
                ("user.accessibility_query_timeout", value)
                for value in (0, -1, float("nan"), float("inf"))
            ),
        ]
        for setting, value in cases:
            with self.subTest(setting=setting, value=value):
                original = self.talon.settings[setting]
                self.talon.settings[setting] = value
                query = Mock()
                try:
                    with patch.object(self.collection.axquery, "query_all", query):
                        with self.assertRaises(RuntimeError):
                            self.collection.collect(self.talon.active_app)
                    query.assert_not_called()
                finally:
                    self.talon.settings[setting] = original

    def test_unusable_frames_are_not_numbered(self):
        for invalid_frame in (
            None,
            frame(width=0),
            frame(height=0),
            frame(width=-1),
            frame(height=-1),
            frame(x=float("nan")),
            frame(y=float("inf")),
            frame(width=float("inf")),
            frame(height=float("nan")),
        ):
            with self.subTest(frame=invalid_frame):
                invalid = Element(AXRole="AXButton", AXFrame=invalid_frame)
                self.talon.query_results = [invalid, self.button, self.popup]

                self.actions.accessibility_show_application_numbers()

                self.assertEqual(
                    self.module._session.targets, [self.button, self.popup]
                )
                self.assertEqual(
                    self.talon.native_calls[-1],
                    ("show", ([self.button, self.popup],)),
                )

    def test_explicitly_hidden_and_disabled_targets_are_not_numbered(self):
        hidden = Element(AXRole="AXButton", AXFrame=frame(), AXHidden=True)
        disabled = Element(AXRole="AXButton", AXFrame=frame(), AXEnabled=False)
        self.talon.query_results = [hidden, disabled, self.button]

        self.actions.accessibility_show_application_numbers()

        self.assertEqual(self.module._session.targets, [self.button])

    def test_transient_query_attribute_error_is_retried_once(self):
        query = Mock(side_effect=[AttributeError("AXRole"), [self.button]])
        with patch.object(self.collection.axquery, "query_all", query):
            self.actions.accessibility_show_application_numbers()

        self.assertEqual(query.call_count, 2)
        self.assertEqual(self.module._session.targets, [self.button])
        self.talon.notify.assert_not_called()

    def test_query_attribute_error_notifies_and_stops_session(self):
        for during_refresh in (False, True):
            with self.subTest(during_refresh=during_refresh):
                self.actions.accessibility_show_application_numbers()
                session = self.module._session
                session.request_refresh()
                query = Mock(side_effect=AttributeError("AXRole"))
                with patch.object(self.collection.axquery, "query_all", query):
                    if during_refresh:
                        session.refresh()
                    else:
                        self.actions.accessibility_show_application_numbers()
                self.assertIsNone(self.module._session)
                self.assertTrue(session.stopped)
                self.assert_session_active(False)
                self.talon.notify.assert_called_with(
                    "Application control labels",
                    "Unable to query the focused accessibility window.",
                )

    def test_empty_initial_query_does_not_leave_an_inactive_session(self):
        self.talon.query_results = []
        self.actions.accessibility_show_application_numbers()
        self.assertIsNone(self.module._session)
        self.assert_session_active(False)
        self.talon.notify.assert_called_with(
            "Application control labels",
            "The focused window exposes no visible pressable controls.",
        )

    def test_surface_clip_replaces_talon_pruning(self):
        self.talon.settings["user.accessibility_clip_to_surface"] = True
        self.window.attrs["AXFrame"] = frame(x=0, y=0, width=500, height=500)
        outside = Element(AXRole="AXButton", AXFrame=frame(x=600))
        touching = Element(AXRole="AXButton", AXFrame=frame(x=500))
        removed = Element(AXRole="AXButton", AXFrame=frame())
        removed.attrs = {}
        query = Mock(return_value=[removed, outside, touching, self.button])
        with patch.object(self.collection.axquery, "query_all", query):
            self.actions.accessibility_show_application_numbers()
        self.assertFalse(query.call_args.kwargs["visible_only"])
        self.assertEqual(self.module._session.targets, [self.button])

    def test_surface_clip_without_frame_is_surfaced(self):
        self.talon.settings["user.accessibility_clip_to_surface"] = True
        query = Mock(return_value=[self.button])
        with patch.object(self.collection.axquery, "query_all", query):
            self.actions.accessibility_show_application_numbers()
        query.assert_not_called()
        self.assertIsNone(self.module._session)
        self.talon.notify.assert_called_with(
            "Application control labels",
            "Unable to query the focused accessibility window.",
        )

    def test_overlapping_distinct_controls_are_preserved(self):
        overlapping = Element(
            AXRole="AXButton", AXTitle="Other action", AXFrame=frame()
        )
        self.talon.query_results = [self.button, self.button, overlapping]

        self.actions.accessibility_show_application_numbers()

        self.assertEqual(self.module._session.targets, [self.button, overlapping])


if __name__ == "__main__":
    unittest.main()
