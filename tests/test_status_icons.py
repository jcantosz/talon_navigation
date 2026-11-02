import types
import unittest
from unittest.mock import Mock, patch

if __package__:
    from .status_support import Element, Owner, Rect, StatusLabelsTestCase, UIErr
else:
    from status_support import Element, Owner, Rect, StatusLabelsTestCase, UIErr


class StatusIconTests(StatusLabelsTestCase):
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

    def test_group_backed_clock_opens_notification_center_and_reuses_cached_parents(
        self,
    ):
        clock, _ = self.add_window_group_icon()
        notification_center = Owner(
            3, "Notification Center", "com.apple.notificationcenterui"
        )
        self.apps.append(notification_center)
        panel = self.panel(self.button("Notifications"))

        def toggle(action):
            roots = notification_center.element.attrs["AXChildren"]
            if panel in roots:
                roots.remove(panel)
            else:
                roots.append(panel)

        clock.perform.side_effect = toggle
        self.commands.status_labels_show(False)
        self.assertEqual(self.visible, [self.icon, clock])
        self.labels.select(2)
        session = self.module._session
        self.tick(session, 3)
        self.assertIs(session.surface.owner, notification_center)
        self.assertIs(session.surface.root, panel)
        with patch.object(
            self.module.discovery, "discover", wraps=self.module.discovery.discover
        ) as scan:
            self.commands.status_labels_back()
            self.tick(session, 3)

        self.assertEqual(self.visible, [self.icon, clock])
        self.assertIsNotNone(scan.call_args.kwargs["parents"])

    def test_group_backed_icons_are_selectable_by_name_and_number(self):
        clock, _ = self.add_window_group_icon()
        for names in (True, False):
            with self.subTest(names=names):
                clock.perform.reset_mock()
                self.commands.status_labels_show(names)
                self.assertEqual(self.visible, [self.icon, clock])
                self.assertEqual(self.names, names)
                self.labels.select("Clock" if names else 2)
                clock.perform.assert_called_once_with("AXPress")
                self.labels.hide()

    def test_adopts_an_already_open_group_backed_clock_panel(self):
        clock, _ = self.add_window_group_icon()
        notification_center = Owner(
            3, "Notification Center", "com.apple.notificationcenterui"
        )
        panel = self.panel(self.button("Notifications"))
        notification_center.element.attrs["AXChildren"] = [panel]
        self.apps.append(notification_center)

        self.commands.status_labels_show(False)

        session = self.module._session
        self.assertIs(session.surface.root, panel)
        self.assertIs(session.surface.owner, notification_center)
        self.assertIs(session.opener, clock)
        self.assertEqual({provider.pid for provider in session.providers}, {2, 3})

    def test_unhit_group_sibling_is_not_used_to_adopt_an_open_menu(self):
        clock, group = self.add_window_group_icon()
        unrelated = Element("AXMenuExtra", "Unrelated", Rect(550, 100, 20, 20))
        unrelated.attrs["AXParent"] = group
        group.attrs["AXChildren"].append(unrelated)
        entry = Element("AXMenuItem", "About", Rect(550, 130, 80, 30))
        self.menu = Element("AXMenu", children=[entry], AXParent=unrelated)

        self.commands.status_labels_show(False)

        self.assertIsNone(self.module._session.surface)
        self.assertEqual(self.visible, [self.icon, clock])

    def test_a_missing_group_provider_reports_an_error(self):
        other = Owner(3, "Other provider", "other")
        icon = Element(
            "AXMenuExtra", "Other", Rect(800, 0, 25, 24), actions=("AXPress",)
        )
        group = Element("AXGroup", children=[icon])
        other.element.attrs["AXChildren"] = [
            Element(
                "AXWindow",
                frame=Rect(800, 0, 25, 24),
                children=[group],
                AXParent=other.element,
            )
        ]
        self.apps.append(other)
        self.ui.apps = lambda: [self.owner]

        with self.assertLogs(level="ERROR"):
            self.commands.status_labels_show(False)

        self.assertIsNone(self.module._session)
        self.assertEqual(self.visible, [])
        self.notify.assert_called_once_with(
            "Status labels", "Unable to access the status icons."
        )

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
            self.module.discovery, "discover", wraps=self.module.discovery.discover
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
            self.module.discovery, "discover", wraps=self.module.discovery.discover
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


if __name__ == "__main__":
    unittest.main()
