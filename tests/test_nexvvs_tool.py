import json
import tempfile
import unittest
from zipfile import ZipFile
from pathlib import Path, PurePosixPath

from tools.nexvvs_tool import (
    NexvvsError,
    check_snbt_balance,
    collect_managed_files,
    overlay_issues,
    plan_sync,
    safe_relative_path,
)
from tools.material_audit import (
    build_material_catalog,
    material_form,
    resolve_tag,
    TagFragment,
)
from tools.material_focus import analyze_recipe, build_material_focus


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


class MaterialAuditTests(unittest.TestCase):
    def test_normalizes_raw_storage_blocks(self):
        self.assertEqual(
            material_form("c:storage_blocks/raw_copper"),
            ("copper", "raw_storage_block"),
        )

    def test_resolves_nested_tags(self):
        fragments = {
            "c:ingots/copper": [
                TagFragment("c:ingots/copper", ("minecraft:copper_ingot", "#example:copper"), "a", False)
            ],
            "example:copper": [
                TagFragment("example:copper", ("example:copper_ingot",), "b", False)
            ],
        }

        items, unresolved, visited, cycles = resolve_tag("c:ingots/copper", fragments)

        self.assertEqual(items, {"minecraft:copper_ingot", "example:copper_ingot"})
        self.assertEqual(unresolved, set())
        self.assertEqual(visited, {"c:ingots/copper", "example:copper"})
        self.assertEqual(cycles, set())

    def test_discovers_duplicate_ingots_from_jar(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mods = root / "mods"
            data = root / "data"
            mods.mkdir()
            data.mkdir()
            with ZipFile(mods / "example.jar", "w") as archive:
                archive.writestr(
                    "data/c/tags/item/ingots/tin.json",
                    json.dumps({"values": ["a:tin_ingot", "b:tin_ingot"]}),
                )

            catalog = build_material_catalog(mods, data)

            self.assertEqual(catalog["summary"]["materials"], 1)
            self.assertEqual(catalog["summary"]["multi_item_forms"], 1)
            self.assertEqual(catalog["summary"]["cross_namespace_conflicts"], 1)
            tin = catalog["materials"][0]
            self.assertEqual(tin["material"], "tin")
            self.assertEqual(tin["forms"]["ingot"]["candidate_count"], 2)
            self.assertTrue(tin["forms"]["ingot"]["cross_namespace_conflict"])


class MaterialFocusTests(unittest.TestCase):
    def test_classifies_tagged_recipe_as_conversion(self):
        recipe = analyze_recipe(
            "mods/example.jar",
            "data/example/recipe/tin_ingot.json",
            {
                "type": "minecraft:smelting",
                "ingredient": {"tag": "c:ores/tin"},
                "result": {"id": "example:tin_ingot"},
            },
            "tin",
            {"example:tin_ingot", "example:tin_ore"},
            {"c:ores/tin", "c:ingots/tin"},
            {"example"},
        )

        self.assertIsNotNone(recipe)
        self.assertEqual(recipe["role"], "conversion")
        self.assertEqual(recipe["matched_outputs"], ["example:tin_ingot"])

    def test_builds_focused_recipe_and_worldgen_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mods = root / "mods"
            data = root / "data"
            instance = root / "instance"
            mods.mkdir()
            data.mkdir()
            (instance / "config").mkdir(parents=True)
            with ZipFile(mods / "example.jar", "w") as archive:
                archive.writestr(
                    "data/example/recipe/tin_ingot.json",
                    json.dumps(
                        {
                            "type": "minecraft:smelting",
                            "ingredient": {"tag": "c:ores/tin"},
                            "result": {"id": "example:tin_ingot"},
                        }
                    ),
                )
                archive.writestr(
                    "data/example/worldgen/configured_feature/tin_ore.json",
                    json.dumps(
                        {
                            "type": "minecraft:ore",
                            "config": {"state": {"Name": "example:tin_ore"}},
                        }
                    ),
                )
            material = {
                "material": "tin",
                "forms": {
                    "ingot": {
                        "items": ["example:tin_ingot"],
                        "tags": ["c:ingots/tin"],
                        "provider_namespaces": ["example"],
                    },
                    "ore": {
                        "items": ["example:tin_ore"],
                        "tags": ["c:ores/tin"],
                        "provider_namespaces": ["example"],
                    },
                },
            }

            report = build_material_focus(material, mods, data, instance)

            self.assertEqual(report["summary"]["recipes"], 1)
            self.assertEqual(report["summary"]["worldgen_resources"], 1)
            self.assertEqual(report["summary"]["worldgen_namespaces"], ["example"])


if __name__ == "__main__":
    unittest.main()

