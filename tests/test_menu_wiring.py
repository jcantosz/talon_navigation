import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


class MenuWiringTests(unittest.TestCase):
    def test_session_module_import_does_not_register_actions_or_contexts(self):
        talon = types.SimpleNamespace(
            Module=Mock(),
            Context=Mock(),
            actions=types.SimpleNamespace(),
            app=types.SimpleNamespace(),
            cron=types.SimpleNamespace(),
            ctrl=types.SimpleNamespace(),
            ui=types.SimpleNamespace(),
        )
        root = types.ModuleType("menu_wiring_under_test")
        root.__path__ = [str(ROOT)]
        package = types.ModuleType(f"{root.__name__}.menus")
        package.__path__ = [str(ROOT / "menus")]

        with patch.dict(
            sys.modules,
            {"talon": talon, root.__name__: root, package.__name__: package},
        ):
            importlib.import_module(f"{package.__name__}.menu_session")

        talon.Module.assert_not_called()
        talon.Context.assert_not_called()

    def test_entrypoint_registers_existing_tags_contexts_and_actions(self):
        contexts = []
        tags = []
        action_classes = []
        overrides = []

        class Context:
            def __init__(self):
                self.matches = ""
                self.tags = []
                contexts.append(self)

            def action_class(self, namespace):
                def register(cls):
                    overrides.append((self, namespace, cls))
                    return cls

                return register

        class Module:
            def tag(self, name, **kwargs):
                tags.append(name)

            def action_class(self, cls):
                action_classes.append(cls)
                return cls

        talon = types.SimpleNamespace(
            Module=Module,
            Context=Context,
            actions=types.SimpleNamespace(),
            app=types.SimpleNamespace(),
            cron=types.SimpleNamespace(),
            ctrl=types.SimpleNamespace(),
            ui=types.SimpleNamespace(),
        )
        root = types.ModuleType("menu_entrypoint_under_test")
        root.__path__ = [str(ROOT)]
        package = types.ModuleType(f"{root.__name__}.menus")
        package.__path__ = [str(ROOT / "menus")]

        with patch.dict(
            sys.modules,
            {"talon": talon, root.__name__: root, package.__name__: package},
        ):
            module = importlib.import_module(f"{package.__name__}.menu_labels")

        self.assertEqual(tags, ["menu_labels_enabled", "menu_labels_active"])
        self.assertEqual(contexts, [module.enabled_ctx, module.ctx, module.menu_ctx])
        self.assertEqual(module.enabled_ctx.matches, "os: mac")
        self.assertEqual(module.enabled_ctx.tags, ["user.menu_labels_enabled"])
        self.assertEqual(module.ctx.matches, "os: mac")
        self.assertEqual(
            module.menu_ctx.matches.strip(), "os: mac\ntag: user.menu_labels_active"
        )
        self.assertEqual(action_classes, [module.MenuLabelsActions])
        self.assertEqual(
            overrides, [(module.menu_ctx, "labels", module.MenuLabelOverrides)]
        )
        self.assertEqual(
            {
                name
                for name in vars(module.MenuLabelsActions)
                if name.startswith("menu_labels_")
            },
            {
                "menu_labels_back",
                "menu_labels_show",
                "menu_labels_click",
                "menu_labels_move",
            },
        )
        self.assertEqual(
            module.MenuSession.__module__, f"{package.__name__}.menu_session"
        )


if __name__ == "__main__":
    unittest.main()
