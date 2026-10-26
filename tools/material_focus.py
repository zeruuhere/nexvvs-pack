from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterator
from zipfile import BadZipFile, ZipFile


OUTPUT_KEYS = {"result", "results", "output", "outputs"}
CONFIG_SUFFIXES = {".cfg", ".conf", ".ini", ".json", ".json5", ".properties", ".snbt", ".toml", ".yaml", ".yml"}


def walk_strings(value: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from walk_strings(child, (*path, str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk_strings(child, (*path, str(index)))


def contains_material_token(value: str, material: str) -> bool:
    pattern = rf"(?<![a-z0-9]){re.escape(material.casefold())}(?![a-z0-9])"
    return bool(re.search(pattern, value.casefold()))


def material_targets(material_entry: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    items: set[str] = set()
    tags: set[str] = set()
    providers: set[str] = set()
    for form in material_entry["forms"].values():
        items.update(form["items"])
        tags.update(form["tags"])
        providers.update(form["provider_namespaces"])
    return items, tags, providers


def matches_material_reference(
    value: str,
    material: str,
    items: set[str],
    tags: set[str],
    providers: set[str],
) -> bool:
    normalized = value.removeprefix("#")
    if normalized in items or normalized in tags:
        return True
    namespace, separator, path = normalized.partition(":")
    return bool(separator and namespace in providers and contains_material_token(path, material))


def raw_resource_may_match(
    raw_text: str,
    resource_path: str,
    material: str,
    items: set[str],
    tags: set[str],
    providers: set[str],
) -> bool:
    if any(target in raw_text for target in (*items, *tags)):
        return True
    parts = resource_path.split("/")
    namespace = parts[1] if len(parts) > 1 and parts[0] == "data" else ""
    if namespace in providers and contains_material_token(resource_path, material):
        return True
    return any(
        f"{provider}:" in raw_text and contains_material_token(raw_text, material)
        for provider in providers
    )


def recipe_id(resource_path: str) -> str | None:
    parts = resource_path.split("/")
    if len(parts) < 4 or parts[0] != "data" or parts[2] not in {"recipe", "recipes"} or not parts[-1].endswith(".json"):
        return None
    path = "/".join(parts[3:])[:-5]
    return f"{parts[1]}:{path}"


def is_worldgen_resource(resource_path: str) -> bool:
    parts = resource_path.split("/")
    if len(parts) < 5 or parts[0] != "data" or not parts[-1].endswith(".json"):
        return False
    joined = "/".join(parts[2:-1])
    return "worldgen" in parts or "biome_modifier" in joined


def output_strings(payload: dict[str, Any]) -> set[str]:
    outputs: set[str] = set()
    for path, value in walk_strings(payload):
        if any(segment.casefold() in OUTPUT_KEYS for segment in path):
            outputs.add(value)
    return outputs


def analyze_recipe(
    source: str,
    resource_path: str,
    payload: dict[str, Any],
    material: str,
    items: set[str],
    tags: set[str],
    providers: set[str],
) -> dict[str, Any] | None:
    identifier = recipe_id(resource_path)
    if not identifier:
        return None
    references = sorted(
        {
            value
            for _, value in walk_strings(payload)
            if matches_material_reference(value, material, items, tags, providers)
        }
    )
    recipe_namespace, _, recipe_path = identifier.partition(":")
    named = recipe_namespace in providers and contains_material_token(recipe_path, material)
    if not references and not named:
        return None
    outputs = output_strings(payload)
    matched_outputs = sorted(
        value
        for value in outputs
        if matches_material_reference(value, material, items, tags, providers)
    )
    matched_inputs = sorted(set(references) - set(matched_outputs))
    if matched_outputs and matched_inputs:
        role = "conversion"
    elif matched_outputs:
        role = "producer"
    elif matched_inputs:
        role = "consumer"
    else:
        role = "named_only"
    return {
        "id": identifier,
        "source": source,
        "resource": resource_path,
        "type": payload.get("type", "unknown"),
        "role": role,
        "references": references,
        "matched_inputs": matched_inputs,
        "matched_outputs": matched_outputs,
        "all_outputs": sorted(outputs),
    }


def scan_archives(
    mods_directory: Path,
    material: str,
    items: set[str],
    tags: set[str],
    providers: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], int]:
    recipes: list[dict[str, Any]] = []
    worldgen: list[dict[str, Any]] = []
    issues: list[str] = []
    jars_scanned = 0
    for jar in sorted(mods_directory.glob("*.jar")):
        jars_scanned += 1
        try:
            with ZipFile(jar) as archive:
                for path in sorted(archive.namelist()):
                    if not path.endswith(".json"):
                        continue
                    recipe = recipe_id(path)
                    worldgen_candidate = is_worldgen_resource(path)
                    if not recipe and not worldgen_candidate:
                        continue
                    try:
                        raw_text = archive.read(path).decode("utf-8")
                    except UnicodeDecodeError as error:
                        issues.append(f"mods/{jar.name}!/{path}: {error}")
                        continue
                    if not raw_resource_may_match(
                        raw_text, path, material, items, tags, providers
                    ):
                        continue
                    try:
                        payload = json.loads(raw_text)
                    except json.JSONDecodeError as error:
                        issues.append(f"mods/{jar.name}!/{path}: {error}")
                        continue
                    source = f"mods/{jar.name}"
                    if recipe:
                        analyzed = analyze_recipe(
                            source, path, payload, material, items, tags, providers
                        )
                        if analyzed:
                            recipes.append(analyzed)
                    if worldgen_candidate:
                        references = sorted(
                            {
                                value
                                for _, value in walk_strings(payload)
                                if matches_material_reference(
                                    value, material, items, tags, providers
                                )
                            }
                        )
                        identifier = path[:-5]
                        if references or (
                            path.split("/", 2)[1] in providers
                            and contains_material_token(identifier, material)
                        ):
                            worldgen.append(
                                {
                                    "resource": path,
                                    "source": source,
                                    "namespace": path.split("/", 2)[1],
                                    "type": payload.get("type", "unknown"),
                                    "references": references,
                                    "definition": payload,
                                }
                            )
        except BadZipFile as error:
            issues.append(f"mods/{jar.name}: {error}")
    return recipes, worldgen, issues, jars_scanned


def scan_overlay_recipes(
    data_directory: Path,
    material: str,
    items: set[str],
    tags: set[str],
    providers: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    recipes: list[dict[str, Any]] = []
    worldgen: list[dict[str, Any]] = []
    issues: list[str] = []
    if not data_directory.is_dir():
        return recipes, worldgen, issues
    for path in sorted(data_directory.rglob("*.json")):
        relative = path.relative_to(data_directory).as_posix()
        resource_path = f"data/{relative}"
        if not recipe_id(resource_path) and not is_worldgen_resource(resource_path):
            continue
        try:
            raw_text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            issues.append(f"overrides/kubejs/data/{relative}: {error}")
            continue
        if not raw_resource_may_match(
            raw_text, resource_path, material, items, tags, providers
        ):
            continue
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as error:
            issues.append(f"overrides/kubejs/data/{relative}: {error}")
            continue
        source = "overrides/kubejs/data"
        if recipe_id(resource_path):
            analyzed = analyze_recipe(
                source, resource_path, payload, material, items, tags, providers
            )
            if analyzed:
                recipes.append(analyzed)
        if is_worldgen_resource(resource_path):
            references = sorted(
                {
                    value
                    for _, value in walk_strings(payload)
                    if matches_material_reference(value, material, items, tags, providers)
                }
            )
            if references or (
                resource_path.split("/", 2)[1] in providers
                and contains_material_token(resource_path, material)
            ):
                worldgen.append(
                    {
                        "resource": resource_path,
                        "source": source,
                        "namespace": resource_path.split("/", 2)[1],
                        "type": payload.get("type", "unknown"),
                        "references": references,
                        "definition": payload,
                    }
                )
    return recipes, worldgen, issues


def scan_configs(
    instance: Path,
    material: str,
    items: set[str],
    providers: set[str],
) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    roots = [instance / "config", instance / "defaultconfigs"]
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.casefold() not in CONFIG_SUFFIXES:
                continue
            try:
                if path.stat().st_size > 2 * 1024 * 1024:
                    continue
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            provider_config = any(provider in path.name.casefold() for provider in providers)
            matches: list[dict[str, Any]] = []
            for line_number, line in enumerate(lines, start=1):
                exact_item = any(item in line for item in items)
                material_key = provider_config and contains_material_token(line, material)
                if exact_item or material_key:
                    matches.append({"line": line_number, "text": line.strip()[:500]})
                    if len(matches) >= 20:
                        break
            if matches:
                references.append(
                    {
                        "file": path.relative_to(instance).as_posix(),
                        "matches": matches,
                    }
                )
    return references


def provider_coverage(material_entry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    providers: dict[str, dict[str, Any]] = defaultdict(lambda: {"forms": set(), "items": set()})
    for form_name, form in material_entry["forms"].items():
        for item in form["items"]:
            namespace = item.partition(":")[0]
            providers[namespace]["forms"].add(form_name)
            providers[namespace]["items"].add(item)
    return {
        provider: {
            "forms": sorted(data["forms"]),
            "items": sorted(data["items"]),
        }
        for provider, data in sorted(providers.items())
    }


def apply_overlay_precedence(
    archive_resources: list[dict[str, Any]],
    overlay_resources: list[dict[str, Any]],
    key: str,
    kind: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    effective = list(archive_resources)
    overrides: list[dict[str, Any]] = []
    for overlay in overlay_resources:
        identifier = overlay[key]
        replaced = [resource for resource in effective if resource[key] == identifier]
        effective = [resource for resource in effective if resource[key] != identifier]
        effective.append(overlay)
        if replaced:
            overrides.append(
                {
                    "kind": kind,
                    "id": identifier,
                    "source": overlay["source"],
                    "replaced_sources": sorted({resource["source"] for resource in replaced}),
                }
            )
    return effective, overrides


def build_material_focus(
    material_entry: dict[str, Any],
    mods_directory: Path,
    overlay_data_directory: Path,
    instance: Path,
) -> dict[str, Any]:
    material = material_entry["material"]
    items, tags, providers = material_targets(material_entry)
    jar_recipes, jar_worldgen, jar_issues, jars_scanned = scan_archives(
        mods_directory, material, items, tags, providers
    )
    overlay_recipes, overlay_worldgen, overlay_issues = scan_overlay_recipes(
        overlay_data_directory, material, items, tags, providers
    )
    effective_recipes, recipe_overrides = apply_overlay_precedence(
        jar_recipes, overlay_recipes, "id", "recipe"
    )
    effective_worldgen, worldgen_overrides = apply_overlay_precedence(
        jar_worldgen, overlay_worldgen, "resource", "worldgen"
    )
    recipes = sorted(
        effective_recipes,
        key=lambda recipe: (recipe["id"], recipe["source"], recipe["resource"]),
    )
    worldgen = sorted(
        effective_worldgen,
        key=lambda resource: (resource["namespace"], resource["resource"], resource["source"]),
    )
    overrides = sorted(
        [*recipe_overrides, *worldgen_overrides],
        key=lambda override: (override["kind"], override["id"]),
    )
    role_counts = Counter(recipe["role"] for recipe in recipes)
    namespace_recipe_counts = Counter(recipe["id"].partition(":")[0] for recipe in recipes)
    worldgen_namespaces = sorted({resource["namespace"] for resource in worldgen})
    configs = scan_configs(instance, material, items, providers)

    return {
        "schema_version": 1,
        "method": "static focused material audit",
        "material": material,
        "forms": material_entry["forms"],
        "providers": provider_coverage(material_entry),
        "summary": {
            "jars_scanned": jars_scanned,
            "recipes": len(recipes),
            "recipe_roles": dict(sorted(role_counts.items())),
            "recipe_namespaces": dict(sorted(namespace_recipe_counts.items())),
            "worldgen_resources": len(worldgen),
            "worldgen_namespaces": worldgen_namespaces,
            "config_files": len(configs),
            "datapack_overrides": len(overrides),
            "parse_issues": len(jar_issues) + len(overlay_issues),
        },
        "recipes": recipes,
        "worldgen": worldgen,
        "config_references": configs,
        "datapack_overrides": overrides,
        "parse_issues": sorted([*jar_issues, *overlay_issues]),
        "limitations": [
            "Recipes and worldgen registered only by Java code are not visible to this static audit.",
            "KubeJS recipe-event mutations are not folded into the static recipe list.",
            "A recipe reference proves technical coupling, not that two concrete items are functionally interchangeable.",
            "Runtime registry and recipe dumps are required before disabling world generation or removing outputs.",
        ],
    }


def markdown_focus_report(report: dict[str, Any]) -> str:
    material = report["material"]
    summary = report["summary"]
    lines = [
        f"# Material focus: {material}",
        "",
        f"> Generated by `./nexvvs materials {material}`. Do not edit manually.",
        "",
        "This report records static evidence and effective datapack overrides. Canonical decisions and gameplay policy are recorded separately in `catalog/materials.json`.",
        "",
        "## Summary",
        "",
        f"- Recipes: **{summary['recipes']}**",
        f"- Recipe roles: `{json.dumps(summary['recipe_roles'], sort_keys=True)}`",
        f"- Recipe namespaces: `{json.dumps(summary['recipe_namespaces'], sort_keys=True)}`",
        f"- Worldgen resources: **{summary['worldgen_resources']}**",
        f"- Worldgen namespaces: `{', '.join(summary['worldgen_namespaces']) or 'none'}`",
        f"- Configuration files with relevant references: **{summary['config_files']}**",
        f"- Effective datapack overrides: **{summary['datapack_overrides']}**",
        f"- Parse issues: **{summary['parse_issues']}**",
        "",
        "## Forms and candidates",
        "",
        "| Form | Tags | Candidate items |",
        "| --- | --- | --- |",
    ]
    for form_name, form in report["forms"].items():
        tags = "<br>".join(f"`{tag}`" for tag in form["tags"])
        items = "<br>".join(f"`{item}`" for item in form["items"])
        lines.append(f"| {form_name} | {tags} | {items} |")

    lines.extend(
        [
            "",
            "## Provider coverage",
            "",
            "| Namespace | Forms | Concrete items |",
            "| --- | --- | ---: |",
        ]
    )
    for provider, data in report["providers"].items():
        lines.append(f"| `{provider}` | {', '.join(data['forms'])} | {len(data['items'])} |")

    lines.extend(
        [
            "",
            "## Recipes",
            "",
            "| Recipe | Role | Type | Source | Material references |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for recipe in report["recipes"]:
        references = "<br>".join(f"`{reference}`" for reference in recipe["references"]) or "—"
        lines.append(
            f"| `{recipe['id']}` | {recipe['role']} | `{recipe['type']}` | "
            f"`{recipe['source']}` | {references} |"
        )

    lines.extend(
        [
            "",
            "## World generation",
            "",
            "| Namespace | Resource | Type | References |",
            "| --- | --- | --- | --- |",
        ]
    )
    if report["worldgen"]:
        for resource in report["worldgen"]:
            references = "<br>".join(f"`{reference}`" for reference in resource["references"]) or "—"
            lines.append(
                f"| `{resource['namespace']}` | `{resource['resource']}` | "
                f"`{resource['type']}` | {references} |"
            )
    else:
        lines.append("| — | — | — | No static worldgen resources found |")

    lines.extend(["", "## Configuration references", ""])
    if report["config_references"]:
        for config in report["config_references"]:
            lines.append(f"### `{config['file']}`")
            lines.append("")
            for match in config["matches"]:
                lines.append(f"- Line {match['line']}: `{match['text']}`")
            lines.append("")
    else:
        lines.append("No relevant configuration keys were found.")
        lines.append("")

    lines.extend(["## Effective datapack overrides", ""])
    if report["datapack_overrides"]:
        for override in report["datapack_overrides"]:
            replaced = ", ".join(f"`{source}`" for source in override["replaced_sources"])
            lines.append(
                f"- `{override['kind']}` `{override['id']}` from `{override['source']}` replaces {replaced}."
            )
    else:
        lines.append("No focused datapack override shadows an installed resource.")
    lines.append("")

    provider_names = sorted(report["providers"])
    worldgen_provider_names = sorted(set(provider_names).intersection(summary["worldgen_namespaces"]))
    provider_recipe_counts = summary["recipe_namespaces"]
    lines.extend(
        [
            "## Preliminary assessment",
            "",
            f"- Providers discovered: {', '.join(f'`{name}`' for name in provider_names)}.",
            f"- Namespaces with effective worldgen resources, including removal modifiers: {', '.join(f'`{name}`' for name in worldgen_provider_names) or 'none'}.",
            "- Recipe ownership: "
            + ", ".join(f"`{name}`={provider_recipe_counts.get(name, 0)}" for name in provider_names)
            + ".",
            "- This generated audit does not choose a canonical provider; see `catalog/materials.json` and the material policy document.",
            "",
            "## Required runtime checks",
            "",
            "- Confirm the intended add/remove biome modifiers produce only the selected ore in newly generated chunks.",
            "- Export the live recipe registry and compare it with this static inventory.",
            "- Test mining, smelting, blasting, compacting, decompacting, and Create processing.",
            "- Verify provider-specific tools, ammunition, machines, and advancement triggers.",
            "- Check every proposed conversion for loops or resource multiplication.",
            "",
            "## Limitations",
            "",
        ]
    )
    for limitation in report["limitations"]:
        lines.append(f"- {limitation}")
    return "\n".join(lines) + "\n"

