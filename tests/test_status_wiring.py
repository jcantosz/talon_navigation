import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


class StatusWiringTests(unittest.TestCase):
    def test_helpers_import_without_registering_actions_or_contexts(self):
        talon = types.SimpleNamespace(
            Module=Mock(),
            Context=Mock(),
            actions=types.SimpleNamespace(),
            app=types.SimpleNamespace(),
            cron=types.SimpleNamespace(),
            ctrl=types.SimpleNamespace(),
            ui=types.SimpleNamespace(Element=object, App=object, Rect=object),
        )
        root = types.ModuleType("status_wiring_under_test")
        root.__path__ = [str(ROOT)]
        package = types.ModuleType(f"{root.__name__}.status")
        package.__path__ = [str(ROOT / "status")]

        with patch.dict(
            sys.modules,
            {"talon": talon, root.__name__: root, package.__name__: package},
        ):
            importlib.import_module(f"{package.__name__}.surfaces")
            importlib.import_module(f"{package.__name__}.status_session")

        talon.Module.assert_not_called()
        talon.Context.assert_not_called()

    def test_entrypoint_registers_the_existing_tag_and_actions(self):
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
            ui=types.SimpleNamespace(Element=object, App=object, Rect=object),
        )
        root = types.ModuleType("status_entrypoint_under_test")
        root.__path__ = [str(ROOT)]
        package = types.ModuleType(f"{root.__name__}.status")
        package.__path__ = [str(ROOT / "status")]

        with patch.dict(
            sys.modules,
            {"talon": talon, root.__name__: root, package.__name__: package},
        ):
            module = importlib.import_module(f"{package.__name__}.status_labels")

        self.assertEqual(tags, ["status_labels_active"])
        self.assertEqual(contexts, [module.ctx, module.controls_ctx])
        self.assertEqual(module.ctx.matches, "os: mac")
        self.assertIn("tag: user.status_labels_active", module.controls_ctx.matches)
        self.assertEqual(action_classes, [module.StatusLabelsActions])
        self.assertEqual(
            overrides, [(module.controls_ctx, "labels", module.StatusLabelOverrides)]
        )
        self.assertEqual(
            {
                name
                for name in vars(module.StatusLabelsActions)
                if name.startswith("status_labels_")
            },
            {
                "status_labels_refresh",
                "status_labels_show",
                "status_labels_back",
                "status_labels_adjust",
            },
        )


if __name__ == "__main__":
    unittest.main()
