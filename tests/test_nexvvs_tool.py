import json
import tempfile
import unittest
from pathlib import Path, PurePosixPath

from tools.nexvvs_tool import (
    NexvvsError,
    check_snbt_balance,
    collect_managed_files,
    overlay_issues,
    plan_sync,
    safe_relative_path,
)


class RepositorySafetyTests(unittest.TestCase):
    def test_rejects_parent_traversal(self):
        with self.assertRaises(NexvvsError):
            safe_relative_path("../saves/world")

    def test_collects_only_declared_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = root / "overrides/kubejs/server_scripts/nexvvs/test.js"
            script.parent.mkdir(parents=True)
            script.write_text("console.info('ok')\n", encoding="utf-8")
            ignored = root / "overrides/kubejs/server_scripts/.gitkeep"
            ignored.write_text("", encoding="utf-8")
            project = {
                "build": {"overrides_directory": "overrides"},
                "sync": {
                    "managed_roots": ["kubejs/server_scripts"],
                    "managed_files": [],
                    "protected_roots": ["saves"],
                },
            }

            managed = collect_managed_files(root, project)

            self.assertEqual(
                list(managed),
                [PurePosixPath("kubejs/server_scripts/nexvvs/test.js")],
            )

    def test_flags_unmanaged_override(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            file = root / "overrides/config/unreviewed.toml"
            file.parent.mkdir(parents=True)
            file.write_text("enabled = true\n", encoding="utf-8")
            project = {
                "build": {"overrides_directory": "overrides"},
                "sync": {
                    "managed_roots": [],
                    "managed_files": [],
                    "protected_roots": ["saves"],
                },
            }

            issues = overlay_issues(root, project, {})

            self.assertEqual(len(issues), 1)
            self.assertIn("Unmanaged override file", issues[0])


class SyncPlanTests(unittest.TestCase):
    def test_plans_create_update_and_same(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "source"
            target_root = root / "target"
            source_root.mkdir()
            target_root.mkdir()
            managed = {}
            for name, source_text, target_text in (
                ("create.json", "{}", None),
                ("same.json", '{"same":true}', '{"same":true}'),
                ("update.json", '{"new":true}', '{"old":true}'),
            ):
                source = source_root / name
                source.write_text(source_text, encoding="utf-8")
                managed[PurePosixPath(name)] = source
                if target_text is not None:
                    (target_root / name).write_text(target_text, encoding="utf-8")

            statuses = {entry.relative_path.name: entry.status for entry in plan_sync(managed, target_root)}

            self.assertEqual(
                statuses,
                {"create.json": "CREATE", "same.json": "SAME", "update.json": "UPDATE"},
            )


class SnbtTests(unittest.TestCase):
    def test_accepts_balanced_snbt(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "quest.snbt"
            path.write_text('{ title: "A [safe] quest", tasks: [{ id: 1 }] }', encoding="utf-8")
            self.assertIsNone(check_snbt_balance(path))

    def test_rejects_unbalanced_snbt(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "quest.snbt"
            path.write_text("{ tasks: [ }", encoding="utf-8")
            self.assertIsNotNone(check_snbt_balance(path))


if __name__ == "__main__":
    unittest.main()

