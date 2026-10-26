from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from zipfile import BadZipFile, ZipFile


COMMON_TAG_NAMESPACES = {"c", "forge"}
FORM_ROOTS = {
    "ores": "ore",
    "raw_materials": "raw_material",
    "ingots": "ingot",
    "nuggets": "nugget",
    "dusts": "dust",
    "plates": "plate",
    "gears": "gear",
    "rods": "rod",
    "wires": "wire",
    "gems": "gem",
    "crystals": "crystal",
    "shards": "shard",
    "storage_blocks": "storage_block",
    "blocks": "storage_block",
}
ANCHOR_FORMS = {
    "ore",
    "raw_material",
    "ingot",
    "nugget",
    "dust",
    "plate",
    "gear",
    "wire",
    "gem",
    "crystal",
    "shard",
}
AGGREGATE_NAMES = {"all_metal", "all_metals"}


@dataclass(frozen=True)
class TagFragment:
    tag_id: str
    values: tuple[str, ...]
    source: str
    replace: bool


def tag_id_from_resource(resource_path: str) -> str | None:
    parts = resource_path.replace("\\", "/").split("/")
    if (
        len(parts) < 6
        or parts[0] != "data"
        or parts[2] != "tags"
        or parts[3] not in {"item", "items"}
        or not parts[-1].endswith(".json")
    ):
        return None
    namespace = parts[1]
    tag_path = "/".join(parts[4:])[:-5]
    return f"{namespace}:{tag_path}"


def tag_values(payload: dict[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for raw_value in payload.get("values", []):
        if isinstance(raw_value, str):
            value = raw_value
        elif isinstance(raw_value, dict):
            value = raw_value.get("id")
        else:
            value = None
        if isinstance(value, str) and value:
            values.append(value)
    return tuple(values)


def scan_jar_tags(mods_directory: Path) -> tuple[list[TagFragment], list[str], int]:
    fragments: list[TagFragment] = []
    issues: list[str] = []
    jars_scanned = 0
    for jar in sorted(mods_directory.glob("*.jar")):
        jars_scanned += 1
        try:
            with ZipFile(jar) as archive:
                for resource_path in sorted(archive.namelist()):
                    tag_id = tag_id_from_resource(resource_path)
                    if not tag_id:
                        continue
                    try:
                        payload = json.loads(archive.read(resource_path))
                    except (UnicodeDecodeError, json.JSONDecodeError) as error:
                        issues.append(f"{jar.name}!/{resource_path}: {error}")
                        continue
                    fragments.append(
                        TagFragment(
                            tag_id=tag_id,
                            values=tag_values(payload),
                            source=f"mods/{jar.name}!/{resource_path}",
                            replace=bool(payload.get("replace", False)),
                        )
                    )
        except BadZipFile as error:
            issues.append(f"mods/{jar.name}: {error}")
    return fragments, issues, jars_scanned


def scan_data_directory(data_directory: Path) -> tuple[list[TagFragment], list[str]]:
    fragments: list[TagFragment] = []
    issues: list[str] = []
    if not data_directory.is_dir():
        return fragments, issues
    for path in sorted(data_directory.rglob("*.json")):
        relative_path = path.relative_to(data_directory).as_posix()
        resource_path = f"data/{relative_path}"
        tag_id = tag_id_from_resource(resource_path)
        if not tag_id:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            issues.append(f"overrides/kubejs/data/{relative_path}: {error}")
            continue
        fragments.append(
            TagFragment(
                tag_id=tag_id,
                values=tag_values(payload),
                source=f"overrides/kubejs/data/{relative_path}",
                replace=bool(payload.get("replace", False)),
            )
        )
    return fragments, issues


def group_fragments(fragments: Iterable[TagFragment]) -> dict[str, list[TagFragment]]:
    grouped: dict[str, list[TagFragment]] = defaultdict(list)
    for fragment in fragments:
        grouped[fragment.tag_id].append(fragment)
    return dict(grouped)


def resolve_tag(
    tag_id: str,
    fragments: dict[str, list[TagFragment]],
    trail: tuple[str, ...] = (),
) -> tuple[set[str], set[str], set[str], set[str]]:
    if tag_id in trail:
        return set(), set(), set(), {" -> ".join((*trail, tag_id))}
    definitions = fragments.get(tag_id)
    if not definitions:
        return set(), {tag_id}, set(), set()

    items: set[str] = set()
    unresolved: set[str] = set()
    visited: set[str] = {tag_id}
    cycles: set[str] = set()
    for fragment in definitions:
        for value in fragment.values:
            if value.startswith("#"):
                nested = value[1:]
                nested_items, nested_unresolved, nested_visited, nested_cycles = resolve_tag(
                    nested, fragments, (*trail, tag_id)
                )
                items.update(nested_items)
                unresolved.update(nested_unresolved)
                visited.update(nested_visited)
                cycles.update(nested_cycles)
            elif ":" in value:
                items.add(value)
    return items, unresolved, visited, cycles


def material_form(tag_id: str) -> tuple[str, str] | None:
    namespace, separator, tag_path = tag_id.partition(":")
    if not separator or namespace not in COMMON_TAG_NAMESPACES:
        return None
    root, separator, material = tag_path.partition("/")
    if not separator or root not in FORM_ROOTS or "/" in material:
        return None
    if material in AGGREGATE_NAMES:
        return None
    form = FORM_ROOTS[root]
    if form == "storage_block" and material.startswith("raw_"):
        material = material.removeprefix("raw_")
        form = "raw_storage_block"
    return material, form


def build_material_catalog(
    mods_directory: Path,
    overlay_data_directory: Path,
) -> dict[str, Any]:
    jar_fragments, jar_issues, jars_scanned = scan_jar_tags(mods_directory)
    overlay_fragments, overlay_issues = scan_data_directory(overlay_data_directory)
    all_fragments = [*jar_fragments, *overlay_fragments]
    grouped = group_fragments(all_fragments)

    discovered: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for tag_id in sorted(grouped):
        matched = material_form(tag_id)
        if not matched:
            continue
        material, form = matched
        items, unresolved, visited, cycles = resolve_tag(tag_id, grouped)
        sources = sorted(
            {
                fragment.source
                for visited_tag in visited
                for fragment in grouped.get(visited_tag, [])
            }
        )
        replace_sources = sorted(
            fragment.source
            for visited_tag in visited
            for fragment in grouped.get(visited_tag, [])
            if fragment.replace
        )
        form_data = discovered[material].setdefault(
            form,
            {
                "tags": set(),
                "items": set(),
                "sources": set(),
                "unresolved_tags": set(),
                "cycles": set(),
                "replace_sources": set(),
            },
        )
        form_data["tags"].add(tag_id)
        form_data["items"].update(items)
        form_data["sources"].update(sources)
        form_data["unresolved_tags"].update(unresolved)
        form_data["cycles"].update(cycles)
        form_data["replace_sources"].update(replace_sources)

    materials: list[dict[str, Any]] = []
    multi_item_forms = 0
    cross_namespace_conflicts = 0
    unresolved_forms = 0
    for material in sorted(discovered):
        forms = discovered[material]
        if not ANCHOR_FORMS.intersection(forms):
            continue
        serialized_forms: dict[str, Any] = {}
        for form in sorted(forms):
            data = forms[form]
            items = sorted(data["items"])
            provider_namespaces = sorted({item.partition(":")[0] for item in items})
            cross_namespace_conflict = len(provider_namespaces) > 1
            unresolved = sorted(data["unresolved_tags"])
            if len(items) > 1:
                multi_item_forms += 1
            if cross_namespace_conflict:
                cross_namespace_conflicts += 1
            if unresolved:
                unresolved_forms += 1
            serialized_forms[form] = {
                "tags": sorted(data["tags"]),
                "items": items,
                "sources": sorted(data["sources"]),
                "unresolved_tags": unresolved,
                "cycles": sorted(data["cycles"]),
                "replace_sources": sorted(data["replace_sources"]),
                "candidate_count": len(items),
                "provider_namespaces": provider_namespaces,
                "cross_namespace_conflict": cross_namespace_conflict,
            }
        materials.append(
            {
                "material": material,
                "forms": serialized_forms,
                "needs_review": any(
                    form["cross_namespace_conflict"]
                    or form["unresolved_tags"]
                    or form["cycles"]
                    or form["replace_sources"]
                    for form in serialized_forms.values()
                ),
            }
        )

    return {
        "schema_version": 1,
        "method": "static item-tag audit",
        "summary": {
            "jars_scanned": jars_scanned,
            "tag_fragments": len(all_fragments),
            "materials": len(materials),
            "forms": sum(len(item["forms"]) for item in materials),
            "multi_item_forms": multi_item_forms,
            "cross_namespace_conflicts": cross_namespace_conflicts,
            "unresolved_forms": unresolved_forms,
            "parse_issues": len(jar_issues) + len(overlay_issues),
        },
        "limitations": [
            "Static JAR resources do not include tags or items registered only by Java code at runtime.",
            "Tag fragments using replace=true are reported conservatively because resource-pack order is not simulated.",
            "Multiple tagged items are review candidates, not automatic proof that one item should be removed.",
        ],
        "parse_issues": sorted([*jar_issues, *overlay_issues]),
        "materials": materials,
    }


def markdown_material_report(catalog: dict[str, Any]) -> str:
    summary = catalog["summary"]
    lines = [
        "# Material audit",
        "",
        "> Generated by `./nexvvs materials`. Do not edit manually.",
        "",
        "This is a static discovery report, not the canonicalization policy. The curated source of truth remains `catalog/materials.json`.",
        "",
        f"- JARs scanned: **{summary['jars_scanned']}**",
        f"- Materials discovered: **{summary['materials']}**",
        f"- Material forms: **{summary['forms']}**",
        f"- Forms with multiple tagged items: **{summary['multi_item_forms']}**",
        f"- Cross-mod provider conflicts: **{summary['cross_namespace_conflicts']}**",
        f"- Forms with unresolved nested tags: **{summary['unresolved_forms']}**",
        f"- Parse issues: **{summary['parse_issues']}**",
        "",
        "## Inventory",
        "",
        "| Material | Forms | Tagged items | Review |",
        "| --- | --- | ---: | --- |",
    ]
    conflicts: list[tuple[str, str, dict[str, Any]]] = []
    for material in catalog["materials"]:
        forms = material["forms"]
        form_names = ", ".join(forms)
        item_count = len({item for form in forms.values() for item in form["items"]})
        review = "yes" if material["needs_review"] else "no"
        lines.append(f"| `{material['material']}` | {form_names} | {item_count} | {review} |")
        for form_name, form in forms.items():
            if form["cross_namespace_conflict"]:
                conflicts.append((material["material"], form_name, form))

    lines.extend(
        [
            "",
            "## Duplicate candidates",
            "",
            "These entries have candidate items from more than one namespace and require design review. Sharing a tag establishes material equivalence for recipes, but does not establish functional equivalence.",
            "",
            "| Material | Form | Tags | Candidate items |",
            "| --- | --- | --- | --- |",
        ]
    )
    if conflicts:
        for material, form_name, form in conflicts:
            tags = "<br>".join(f"`{tag}`" for tag in form["tags"])
            items = "<br>".join(f"`{item}`" for item in form["items"])
            lines.append(f"| `{material}` | {form_name} | {tags} | {items} |")
    else:
        lines.append("| — | — | — | No duplicate candidates found |")

    lines.extend(["", "## Limitations", ""])
    for limitation in catalog["limitations"]:
        lines.append(f"- {limitation}")
    return "\n".join(lines) + "\n"

