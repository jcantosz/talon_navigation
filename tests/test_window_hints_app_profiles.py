import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from .test_window_hints_profile import P, Rect
except ImportError:
    from test_window_hints_profile import P, Rect


def node(path, role, frame, **kwargs):
    return P.Node(path, Rect(*frame), role=role, ref=object(), **kwargs)


class AppProfiles(unittest.TestCase):
    def test_central_mapping_preserves_all_existing_mac_app_matches(self):
        source = (P.PROFILE_DIRECTORY.parent / "window_hints.talon").read_text()
        value = source.split("user.window_hints_applications =", 1)[1].split('"""', 2)[1]
        mapping = P.application_mapping(value)
        self.assertEqual(
            {bundle for bundle, profile in mapping.items() if profile == "vscode"},
            {
                "com.microsoft.VSCode",
                "com.microsoft.VSCodeInsiders",
                "com.vscodium",
                "co.posit.positron",
                "com.visualstudio.code.oss",
                "com.todesktop.230313mzl4w4u92",
                "com.exafunction.windsurf",
            },
        )
        self.assertEqual(mapping["com.tinyspeck.slackmacgap"], "slack")
        self.assertEqual(mapping["com.microsoft.Outlook"], "outlook")
        self.assertEqual(len(mapping), 9)

    def test_mapping_rejects_malformed_duplicate_and_missing_profiles(self):
        for value in (
            "bundle",
            "=slack",
            "bundle=",
            "bundle=../slack",
            "bundle=slack=outlook",
            "bad bundle=slack",
            "bundle=slack,",
            "bundle=slack,bundle=outlook",
            "bundle=nonexistent-profile",
        ):
            with self.subTest(value=value), self.assertRaises(P.ProfileError):
                P.application_mapping(value)

    def test_mapping_is_exact_and_empty_mapping_is_supported(self):
        self.assertEqual(P.application_mapping("  "), {})
        mapping = P.application_mapping(" bundle = slack , other = outlook ")
        self.assertEqual(mapping, {"bundle": "slack", "other": "outlook"})
        self.assertNotIn("Bundle", mapping)
        self.assertNotIn("bundle.other", mapping)

    def test_warmed_mapping_does_not_read_files_and_setting_edits_take_effect(self):
        P.application_mapping.cache_clear()
        mapping = P.application_mapping("bundle=slack")
        with patch.object(Path, "is_file", side_effect=AssertionError("Hot-path IO")):
            for _ in range(20):
                self.assertIs(P.application_mapping("bundle=slack"), mapping)
        self.assertEqual(P.application_mapping("bundle=outlook"), {"bundle": "outlook"})

    def test_slack_current_channel_and_thread_without_content_names(self):
        nodes = [
            node(
                (0,),
                "AXButton",
                (300, 30, 600, 28),
                classes=frozenset({"p-top_nav__search"}),
            ),
            node(
                (1,),
                "AXTabGroup",
                (0, 130, 50, 450),
                classes=frozenset({"p-tab_rail__tab_menu"}),
            ),
            node(
                (2,),
                "AXToolbar",
                (0, 800, 70, 160),
                classes=frozenset({"p-control_strip"}),
            ),
            node(
                (3,),
                "AXOutline",
                (70, 150, 230, 800),
                description="Channels and direct messages",
            ),
            node(
                (4,),
                "AXGroup",
                (300, 150, 800, 650),
                classes=frozenset({"p-message_pane"}),
            ),
            node(
                (5,),
                "AXGroup",
                (1100, 150, 500, 800),
                classes=frozenset({"p-threads_flexpane"}),
            ),
            node(
                (6,),
                "AXTextArea",
                (320, 850, 760, 40),
                classes=frozenset({"ql-editor"}),
            ),
            node(
                (7,),
                "AXTextArea",
                (1120, 850, 460, 40),
                classes=frozenset({"ql-editor"}),
            ),
            node(
                (8,),
                "AXGroup",
                (300, 150, 800, 600),
                classes=frozenset({"c-message_kit__hover"}),
                title="Private content sentinel",
            ),
        ]
        panes = P.find_panes(nodes, P.load_profile("slack"))
        self.assertEqual(
            [p.name for p in panes],
            [
                "search",
                "sidebar",
                "manage",
                "channels",
                "messages",
                "thread",
                "compose 1",
                "compose 2",
            ],
        )
        self.assertTrue(all(p.ref is n.ref for p, n in zip(panes, nodes)))
        single = P.find_panes(nodes[:5] + [nodes[6]], P.load_profile("slack"))
        self.assertEqual(single[-1].name, "compose")
        self.assertNotIn("thread", [p.name for p in single])

    def test_outlook_mail_uses_visible_containers_not_oversized_content(self):
        nodes = [
            node((), "AXWindow", (0, 0, 1500, 900)),
            node((0,), "AXTextField", (500, 20, 600, 30), identifier="Search Bar"),
            node((1,), "AXGroup", (0, 150, 40, 350)),
            node((1, 0), "AXButton", (0, 150, 36, 36), help="Mail"),
            node((2,), "AXScrollArea", (50, 150, 250, 700)),
            node((2, 0), "AXOutline", (49, 149, 252, 702)),
            node((3,), "AXGroup", (310, 150, 300, 700), description="Message List"),
            node(
                (3, 0), "AXTable", (310, -400, 300, 65000), description="Message List"
            ),
            node((4,), "AXScrollArea", (620, 350, 800, 450)),
            node(
                (4, 0),
                "AXWebArea",
                (620, 350, 1200, 3600),
                title="Private message sentinel",
            ),
            node((5,), "AXButton", (5, 800, 30, 30), help="Calendar"),
        ]
        panes = P.find_panes(nodes, P.load_profile("outlook"))
        self.assertEqual(
            [p.name for p in panes], ["search", "sidebar", "inboxes", "mail", "message"]
        )
        self.assertEqual(panes[3].frame, nodes[6].frame)
        self.assertEqual(panes[4].frame, nodes[8].frame)
        self.assertIs(panes[3].ref, nodes[6].ref)
        self.assertIs(panes[4].ref, nodes[8].ref)
        moved = [
            P.Node(
                n.path,
                Rect(n.frame.x + 100, n.frame.y + 50, n.frame.width, n.frame.height),
                n.role,
                n.subrole,
                n.dom,
                n.classes,
                n.title,
                n.description,
                n.ref,
                n.identifier,
                n.help,
            )
            for n in nodes
        ]
        shifted = P.find_panes(moved, P.load_profile("outlook"))
        self.assertEqual([p.name for p in shifted], [p.name for p in panes])
        self.assertEqual(shifted[3].frame.x, panes[3].frame.x + 100)

    def test_native_help_and_identifier_are_exact_and_not_dom_identifiers(self):
        target = node(
            (0,), "AXButton", (0, 0, 40, 40), identifier="Search Bar", help="Mail"
        )
        self.assertTrue(P.matches(target, {"identifier": "Search Bar", "help": "Mail"}))
        self.assertFalse(P.matches(target, {"identifier": "search bar"}))
        self.assertFalse(P.matches(target, {"dom_id": "Search Bar"}))

    def test_other_view_markers_do_not_invent_mail_or_channel_panes(self):
        nodes = [node((0,), "AXGroup", (0, 0, 100, 100), title="Calendar")]
        for name in ("slack", "outlook"):
            self.assertEqual(P.find_panes(nodes, P.load_profile(name)), [])
