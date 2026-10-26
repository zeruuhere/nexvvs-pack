from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from tools.material_audit import build_material_catalog, markdown_material_report
from tools.material_focus import build_material_focus, markdown_focus_report


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
IGNORED_SOURCE_NAMES = {".DS_Store", ".gitkeep"}


class NexvvsError(RuntimeError):
    pass


@dataclass(frozen=True)
class SyncEntry:
    status: str
    relative_path: PurePosixPath
    source: Path
    target: Path


@dataclass(frozen=True)
class ProbeMatch:
    relative_path: PurePosixPath
    line_number: int
    text: str


@dataclass(frozen=True)
class ProbeStatus:
    dump_root: Path
    declaration_count: int
    size_bytes: int
    newest_mtime: float | None
    missing_sections: tuple[str, ...]
    api_state: str
    warnings: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.declaration_count > 0 and not self.missing_sections


def load_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError as error:
        raise NexvvsError(f"Required file does not exist: {path}") from error
    except tomllib.TOMLDecodeError as error:
        raise NexvvsError(f"Invalid TOML in {path}: {error}") from error


def load_project(root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    return load_toml(root / "project.toml")


def load_local(root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    local_path = root / "nexvvs.local.toml"
    if not local_path.exists():
        raise NexvvsError(
            "Missing nexvvs.local.toml. Copy nexvvs.local.toml.example and set the local instance paths."
        )
    return load_toml(local_path)


def safe_relative_path(raw_path: str) -> PurePosixPath:
    path = PurePosixPath(raw_path)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise NexvvsError(f"Unsafe repository-relative path: {raw_path!r}")
    return path


def is_ignored_source(path: Path) -> bool:
    return path.name in IGNORED_SOURCE_NAMES or "__pycache__" in path.parts


def is_protected(relative_path: PurePosixPath, protected_roots: Iterable[str]) -> bool:
    protected = {safe_relative_path(item) for item in protected_roots}
    return any(
        relative_path == candidate or candidate in relative_path.parents
        for candidate in protected
    )


def collect_managed_files(
    root: Path, project: dict[str, Any]
) -> dict[PurePosixPath, Path]:
    overlay = root / project["build"]["overrides_directory"]
    sync = project["sync"]
    protected = sync.get("protected_roots", [])
    managed: dict[PurePosixPath, Path] = {}

    def add_file(relative_path: PurePosixPath, source: Path) -> None:
        if is_protected(relative_path, protected):
            raise NexvvsError(f"Protected runtime path cannot be managed: {relative_path}")
        if source.is_symlink():
            raise NexvvsError(f"Symbolic links are not allowed in overrides: {relative_path}")
        managed[relative_path] = source

    for raw_root in sync.get("managed_roots", []):
        relative_root = safe_relative_path(raw_root)
        source_root = overlay.joinpath(*relative_root.parts)
        if not source_root.exists():
            continue
        if not source_root.is_dir():
            raise NexvvsError(f"Managed root is not a directory: {relative_root}")
        for source in sorted(source_root.rglob("*")):
            if not source.is_file() or is_ignored_source(source):
                continue
            relative_path = PurePosixPath(source.relative_to(overlay).as_posix())
            add_file(relative_path, source)

    for raw_file in sync.get("managed_files", []):
        relative_path = safe_relative_path(raw_file)
        source = overlay.joinpath(*relative_path.parts)
        if not source.is_file():
            raise NexvvsError(f"Managed file does not exist: {relative_path}")
        if not is_ignored_source(source):
            add_file(relative_path, source)

    return dict(sorted(managed.items(), key=lambda item: item[0].as_posix()))


def overlay_issues(
    root: Path,
    project: dict[str, Any],
    managed: dict[PurePosixPath, Path],
) -> list[str]:
    overlay = root / project["build"]["overrides_directory"]
    protected = project["sync"].get("protected_roots", [])
    issues: list[str] = []
    for source in sorted(overlay.rglob("*")):
        if not source.is_file() or is_ignored_source(source):
            continue
        relative_path = PurePosixPath(source.relative_to(overlay).as_posix())
        if source.is_symlink():
            issues.append(f"Symbolic link is not allowed: overrides/{relative_path}")
        if is_protected(relative_path, protected):
            issues.append(f"Protected runtime path found: overrides/{relative_path}")
        elif relative_path not in managed:
            issues.append(
                f"Unmanaged override file: overrides/{relative_path}; add it to project.toml intentionally"
            )
    return issues


def check_snbt_balance(path: Path) -> str | None:
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[tuple[str, int]] = []
    quote: str | None = None
    escaped = False
    text = path.read_text(encoding="utf-8")
    for index, character in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
        elif character in "([{":
            stack.append((character, index))
        elif character in ")]}":
            if not stack or stack[-1][0] != pairs[character]:
                return f"unexpected {character!r} at character {index}"
            stack.pop()
    if quote:
        return "unterminated quoted string"
    if stack:
        character, index = stack[-1]
        return f"unclosed {character!r} from character {index}"
    return None


def validation_results(root: Path = REPOSITORY_ROOT) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    warnings: list[str] = []
    try:
        project = load_project(root)
        managed = collect_managed_files(root, project)
        issues.extend(overlay_issues(root, project, managed))
    except NexvvsError as error:
        return [str(error)], warnings

    json_files = list(managed.values())
    json_files.extend((root / "catalog").glob("*.json"))
    for path in sorted(set(json_files)):
        if path.suffix.lower() != ".json":
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            issues.append(f"Invalid JSON in {path.relative_to(root)}: {error}")

    for path in sorted(root.glob("*.toml")):
        if path.name == "nexvvs.local.toml" or path.is_file():
            try:
                load_toml(path)
            except NexvvsError as error:
                issues.append(str(error))

    for path in sorted(managed.values()):
        if path.suffix.lower() == ".snbt":
            problem = check_snbt_balance(path)
            if problem:
                issues.append(f"Invalid SNBT structure in {path.relative_to(root)}: {problem}")

    javascript = [path for path in managed.values() if path.suffix.lower() == ".js"]
    node = shutil.which("node")
    if javascript and not node:
        warnings.append("Node.js is unavailable; JavaScript syntax was not checked")
    elif node:
        for path in sorted(javascript):
            result = subprocess.run(
                [node, "--check", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode:
                message = (result.stderr or result.stdout).strip()
                issues.append(f"Invalid JavaScript in {path.relative_to(root)}: {message}")

    expected_fields = {
        "pack.name",
        "pack.version",
        "platform.minecraft",
        "platform.loader",
        "platform.loader_version",
        "platform.java",
    }
    missing = []
    for dotted in expected_fields:
        section, field = dotted.split(".")
        if not project.get(section, {}).get(field):
            missing.append(dotted)
    if missing:
        issues.append(f"Missing required project fields: {', '.join(sorted(missing))}")

    return issues, warnings


def validate_repository(root: Path = REPOSITORY_ROOT, emit: bool = True) -> bool:
    issues, warnings = validation_results(root)
    if emit:
        for warning in warnings:
            print(f"WARN  {warning}")
        for issue in issues:
            print(f"ERROR {issue}")
        if not issues:
            project = load_project(root)
            count = len(collect_managed_files(root, project))
            print(f"OK    repository valid ({count} managed files)")
    return not issues


def configured_instance(root: Path, target: str) -> Path:
    local = load_local(root)
    raw_path = local.get("instances", {}).get(target)
    if not raw_path:
        raise NexvvsError(f"No path configured for instance {target!r}")
    return Path(raw_path).expanduser().resolve()


def read_instance_metadata(instance: Path) -> dict[str, Any]:
    metadata_path = instance / "minecraftinstance.json"
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise NexvvsError(f"Not a CurseForge Minecraft instance: {instance}") from error
    except json.JSONDecodeError as error:
        raise NexvvsError(f"Invalid CurseForge metadata at {metadata_path}: {error}") from error


def verify_dev_instance(root: Path, project: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    instance = configured_instance(root, "dev")
    stable = configured_instance(root, "stable")
    if instance == stable:
        raise NexvvsError("The Dev instance resolves to the protected Stable instance")
    metadata = read_instance_metadata(instance)
    if "stable" in str(metadata.get("name", "")).lower():
        raise NexvvsError(f"Refusing to use Stable-looking profile as Dev: {metadata.get('name')}")

    expected_minecraft = str(project["platform"]["minecraft"])
    actual_minecraft = str(metadata.get("gameVersion"))
    if actual_minecraft != expected_minecraft:
        raise NexvvsError(
            f"Minecraft mismatch: project requires {expected_minecraft}, instance has {actual_minecraft}"
        )

    loader = metadata.get("baseModLoader") or {}
    expected_loader = f"{project['platform']['loader']}-{project['platform']['loader_version']}"
    if loader.get("name") != expected_loader:
        raise NexvvsError(
            f"Loader mismatch: project requires {expected_loader}, instance has {loader.get('name')}"
        )
    return instance, metadata


def read_text_tail(path: Path, limit: int = 4 * 1024 * 1024) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def probe_api_state(instance: Path) -> tuple[str, str | None]:
    config_path = instance / "kubejs" / "config" / "web_server.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return "unconfigured", None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return "invalid-config", f"ProbeJS web-server configuration is invalid: {error}"

    if not config.get("enabled"):
        return "disabled", None
    port = config.get("port")
    if not isinstance(port, int) or not 1 <= port <= 65535:
        return "invalid-config", "ProbeJS web-server port is invalid"
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return "online", None
    except OSError:
        return "offline", None


def inspect_probe_dump(instance: Path) -> ProbeStatus:
    dump_root = instance / ".probe"
    declarations = sorted(dump_root.rglob("*.d.ts")) if dump_root.is_dir() else []
    size_bytes = 0
    newest_mtime: float | None = None
    for path in declarations:
        try:
            stat = path.stat()
        except OSError:
            continue
        size_bytes += stat.st_size
        newest_mtime = max(newest_mtime or stat.st_mtime, stat.st_mtime)

    populated_sections = {
        path.relative_to(dump_root).parts[0]
        for path in declarations
        if path.relative_to(dump_root).parts
    }
    expected = ("@side-only", "@package", "@special")
    missing_sections = tuple(name for name in expected if name not in populated_sections)
    api_state, api_warning = probe_api_state(instance)
    warnings: list[str] = []
    if api_warning:
        warnings.append(api_warning)

    log_tail = read_text_tail(instance / "logs" / "latest.log")
    if (
        "InjectParchment.transformClass" in log_tail
        and "Illegal group reference" in log_tail
    ):
        warnings.append(
            "ProbeJS 8.0.3 skipped some Parchment Javadoc; generated type declarations remain usable"
        )

    return ProbeStatus(
        dump_root=dump_root,
        declaration_count=len(declarations),
        size_bytes=size_bytes,
        newest_mtime=newest_mtime,
        missing_sections=missing_sections,
        api_state=api_state,
        warnings=tuple(warnings),
    )


def probe_search_roots(dump_root: Path, include_special: bool) -> list[Path]:
    roots = [dump_root / "@side-only", dump_root / "@package"]
    if include_special:
        roots.append(dump_root / "@special")
    return roots


def search_probe_declarations(
    instance: Path,
    query: str,
    *,
    limit: int = 20,
    include_special: bool = False,
) -> list[ProbeMatch]:
    if not query.strip():
        raise NexvvsError("ProbeJS type query cannot be empty")
    if limit < 1:
        raise NexvvsError("ProbeJS result limit must be at least 1")

    dump_root = instance / ".probe"
    if not dump_root.is_dir():
        raise NexvvsError("ProbeJS dump is missing; generate it from the Dev profile first")

    needle = query.casefold()
    matches: list[ProbeMatch] = []
    seen: set[Path] = set()
    for search_root in probe_search_roots(dump_root, include_special):
        if not search_root.is_dir():
            continue
        for path in sorted(search_root.rglob("*.d.ts")):
            if path in seen:
                continue
            seen.add(path)
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line_number, line in enumerate(lines, start=1):
                if needle not in line.casefold():
                    continue
                text = line.strip()
                if len(text) > 320:
                    text = text[:317] + "..."
                matches.append(
                    ProbeMatch(
                        PurePosixPath(path.relative_to(instance).as_posix()),
                        line_number,
                        text,
                    )
                )
                if len(matches) >= limit:
                    return matches
    return matches


def probe_status(root: Path = REPOSITORY_ROOT) -> int:
    project = load_project(root)
    instance, metadata = verify_dev_instance(root, project)
    status = inspect_probe_dump(instance)
    state = "READY" if status.ready else "MISSING"
    print(f"PROBE: {state} ({metadata.get('name')})")
    print(f"DUMP:  {status.dump_root}")
    print(
        f"TYPES: {status.declaration_count} declarations, "
        f"{status.size_bytes / (1024 * 1024):.1f} MiB"
    )
    if status.newest_mtime is not None:
        generated = datetime.fromtimestamp(status.newest_mtime).astimezone()
        print(f"NEWEST: {generated.isoformat(timespec='seconds')}")
    print(f"LIVE API: {status.api_state}")
    for section in status.missing_sections:
        print(f"ERROR missing .probe/{section}")
    for warning in status.warnings:
        print(f"WARN  {warning}")
    return 0 if status.ready else 1


def probe_type(
    query: str,
    *,
    limit: int = 20,
    include_special: bool = False,
    root: Path = REPOSITORY_ROOT,
) -> int:
    project = load_project(root)
    instance, _ = verify_dev_instance(root, project)
    matches = search_probe_declarations(
        instance,
        query,
        limit=limit,
        include_special=include_special,
    )
    for match in matches:
        print(f"{match.relative_path}:{match.line_number}: {match.text}")
    if not matches:
        special_hint = " Use --special for registry literals." if not include_special else ""
        print(f"NO MATCH: {query!r}.{special_hint}")
        return 1
    print(f"MATCHES: {len(matches)} (limit {limit})")
    return 0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def plan_sync(
    managed: dict[PurePosixPath, Path], instance: Path
) -> list[SyncEntry]:
    plan: list[SyncEntry] = []
    for relative_path, source in managed.items():
        target = instance.joinpath(*relative_path.parts)
        if not target.exists():
            status = "CREATE"
        elif not target.is_file():
            raise NexvvsError(f"Sync target exists but is not a file: {target}")
        elif sha256(source) == sha256(target):
            status = "SAME"
        else:
            status = "UPDATE"
        plan.append(SyncEntry(status, relative_path, source, target))
    return plan


def sync_dev(root: Path = REPOSITORY_ROOT, apply: bool = False) -> int:
    project = load_project(root)
    if not validate_repository(root):
        raise NexvvsError("Validation failed; synchronization was not attempted")
    instance, metadata = verify_dev_instance(root, project)
    managed = collect_managed_files(root, project)
    plan = plan_sync(managed, instance)
    changed = [entry for entry in plan if entry.status != "SAME"]

    print(f"Target: {metadata.get('name')} ({instance})")
    for entry in plan:
        print(f"{entry.status:<6} {entry.relative_path}")

    if not apply:
        print(f"DRY-RUN: {len(changed)} change(s); use --apply to write them")
        return 0

    if not changed:
        print("APPLIED: instance already matches the managed source")
        return 0

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_root = root / "backups" / timestamp
    updated = 0
    created = 0
    for entry in changed:
        if entry.status == "UPDATE":
            backup = backup_root.joinpath(*entry.relative_path.parts)
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry.target, backup)
            updated += 1
        else:
            created += 1
        entry.target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(entry.source, entry.target)

    backup_note = f"; backups: {backup_root}" if updated else ""
    print(f"APPLIED: {created} created, {updated} updated{backup_note}")
    return 0


def content_kind(addon: dict[str, Any]) -> str:
    folder = addon.get("modFolderPath")
    if folder:
        return Path(folder).name
    package_type = addon.get("packageType")
    return {3: "resourcepacks", 6: "mods"}.get(package_type, "other")


def addon_author(addon: dict[str, Any]) -> str:
    primary = addon.get("primaryAuthor")
    if isinstance(primary, dict):
        return str(primary.get("name") or "")
    if primary:
        return str(primary)
    authors = addon.get("authors") or []
    names = [str(item.get("name")) for item in authors if isinstance(item, dict) and item.get("name")]
    return ", ".join(names)


def relative_runtime_path(instance: Path, absolute: str) -> str | None:
    try:
        return Path(absolute).resolve().relative_to(instance).as_posix()
    except (OSError, ValueError):
        return None


def audit_instance(root: Path = REPOSITORY_ROOT) -> int:
    project = load_project(root)
    instance, metadata = verify_dev_instance(root, project)
    content: list[dict[str, Any]] = []
    represented: dict[str, set[str]] = {"mods": set(), "resourcepacks": set(), "shaderpacks": set()}

    for addon in metadata.get("installedAddons", []):
        installed = addon.get("installedFile") or {}
        kind = content_kind(addon)
        filename = addon.get("fileNameOnDisk") or installed.get("fileName") or ""
        paths = [
            relative
            for raw in (addon.get("filePaths") or [])
            if (relative := relative_runtime_path(instance, raw))
        ]
        if kind in represented and filename:
            represented[kind].add(filename)
        hashes = {
            str(item.get("type")): str(item.get("value"))
            for item in installed.get("hashes", [])
            if item.get("type") is not None and item.get("value")
        }
        project_id = addon.get("addonID") or installed.get("projectId")
        file_id = installed.get("id")
        export_disabled = int(addon.get("exportDisabledReason") or 0)
        content.append(
            {
                "name": addon.get("name") or filename,
                "author": addon_author(addon),
                "kind": kind,
                "project_id": project_id,
                "file_id": file_id,
                "filename": filename,
                "paths": paths,
                "enabled": bool(addon.get("isEnabled", True)),
                "modified": bool(addon.get("isModified", False)),
                "exportable": bool(project_id and file_id and export_disabled == 0),
                "export_disabled_reason": export_disabled,
                "website": addon.get("webSiteURL") or "",
                "hashes": hashes,
            }
        )

    content.sort(key=lambda item: (item["kind"], str(item["name"]).casefold()))
    unmanaged: list[dict[str, Any]] = []
    for kind in represented:
        directory = instance / kind
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.name not in represented[kind]:
                unmanaged.append(
                    {
                        "kind": kind,
                        "filename": path.name,
                        "size": path.stat().st_size,
                    }
                )

    loader = metadata.get("baseModLoader") or {}
    lock = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_profile": {
            "name": metadata.get("name"),
            "minecraft": metadata.get("gameVersion"),
            "loader": loader.get("name"),
        },
        "content": content,
        "unmanaged_files": unmanaged,
    }
    lock_path = root / project["build"]["lock_file"]
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    mods = [item for item in content if item["kind"] == "mods"]
    resources = [item for item in content if item["kind"] == "resourcepacks"]
    shaders = [item for item in content if item["kind"] == "shaderpacks"]
    lines = [
        "# Installed mods",
        "",
        "> Generated by `./nexvvs audit`. Do not edit manually.",
        "",
        f"- Profile: `{metadata.get('name')}`",
        f"- Minecraft: `{metadata.get('gameVersion')}`",
        f"- Loader: `{loader.get('name')}`",
        f"- Mods: **{len(mods)}**",
        f"- Resource packs: **{len(resources)}**",
        f"- Shader packs: **{len(shaders)}**",
        f"- Unmanaged files: **{len(unmanaged)}**",
        "",
        "| Mod | Author | Installed file | CurseForge IDs | State |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in mods:
        name = str(item["name"]).replace("|", "\\|")
        author = str(item["author"]).replace("|", "\\|") or "—"
        filename = str(item["filename"]).replace("|", "\\|")
        ids = f"{item['project_id']} / {item['file_id']}"
        states = []
        if not item["enabled"]:
            states.append("disabled")
        if item["modified"]:
            states.append("modified")
        if not item["exportable"]:
            states.append("not exportable")
        state = ", ".join(states) or "ok"
        if item["website"]:
            name = f"[{name}]({item['website']})"
        lines.append(f"| {name} | {author} | `{filename}` | `{ids}` | {state} |")

    if unmanaged:
        lines.extend(["", "## Unmanaged runtime files", ""])
        for item in unmanaged:
            lines.append(f"- `{item['kind']}/{item['filename']}` ({item['size']} bytes)")
    (root / "docs" / "MODLIST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        f"AUDIT: {len(mods)} mods, {len(resources)} resource packs, "
        f"{len(shaders)} shader packs, {len(unmanaged)} unmanaged files"
    )
    print(f"WROTE: {lock_path.relative_to(root)}")
    print("WROTE: docs/MODLIST.md")
    return 0


def audit_materials(root: Path = REPOSITORY_ROOT) -> int:
    project = load_project(root)
    instance, metadata = verify_dev_instance(root, project)
    overlay_data = root / project["build"]["overrides_directory"] / "kubejs" / "data"
    catalog = build_material_catalog(instance / "mods", overlay_data)
    catalog["source_profile"] = {
        "name": metadata.get("name"),
        "minecraft": metadata.get("gameVersion"),
        "loader": (metadata.get("baseModLoader") or {}).get("name"),
    }
    catalog_path = root / "catalog" / "materials.discovered.json"
    catalog_path.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    documentation_path = root / "docs" / "MATERIALS.md"
    documentation_path.write_text(markdown_material_report(catalog), encoding="utf-8")
    summary = catalog["summary"]
    print(
        f"MATERIALS: {summary['materials']} materials, {summary['forms']} forms, "
        f"{summary['cross_namespace_conflicts']} cross-mod conflicts, "
        f"{summary['multi_item_forms']} multi-item forms, "
        f"{summary['unresolved_forms']} unresolved forms"
    )
    print(f"WROTE: {catalog_path.relative_to(root)}")
    print(f"WROTE: {documentation_path.relative_to(root)}")
    return 0


def audit_material_focus(material: str, root: Path = REPOSITORY_ROOT) -> int:
    project = load_project(root)
    instance, metadata = verify_dev_instance(root, project)
    overlay_data = root / project["build"]["overrides_directory"] / "kubejs" / "data"
    discovered = build_material_catalog(instance / "mods", overlay_data)
    material_entry = next(
        (entry for entry in discovered["materials"] if entry["material"] == material),
        None,
    )
    if material_entry is None:
        raise NexvvsError(f"Material was not discovered in common tags: {material}")
    report = build_material_focus(
        material_entry,
        instance / "mods",
        overlay_data,
        instance,
    )
    report["source_profile"] = {
        "name": metadata.get("name"),
        "minecraft": metadata.get("gameVersion"),
        "loader": (metadata.get("baseModLoader") or {}).get("name"),
    }
    catalog_path = root / "catalog" / "materials" / f"{material}.audit.json"
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    documentation_path = root / "docs" / "materials" / f"{material}.md"
    documentation_path.parent.mkdir(parents=True, exist_ok=True)
    documentation_path.write_text(markdown_focus_report(report), encoding="utf-8")
    summary = report["summary"]
    print(
        f"MATERIAL {material}: {summary['recipes']} recipes, "
        f"{summary['worldgen_resources']} worldgen resources, "
        f"{summary['config_files']} config files"
    )
    print(f"WROTE: {catalog_path.relative_to(root)}")
    print(f"WROTE: {documentation_path.relative_to(root)}")
    return 0


def zip_bytes(archive: zipfile.ZipFile, name: str, data: bytes, mode: int = 0o644) -> None:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (mode & 0xFFFF) << 16
    archive.writestr(info, data)


def build_archive(root: Path = REPOSITORY_ROOT) -> int:
    if not validate_repository(root):
        raise NexvvsError("Validation failed; build was not created")
    project = load_project(root)
    lock_path = root / project["build"]["lock_file"]
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise NexvvsError("Missing content lock; run ./nexvvs audit first") from error

    modified = [
        item["name"]
        for item in lock.get("content", [])
        if item.get("enabled") and item.get("modified")
    ]
    if modified:
        raise NexvvsError(
            "Refusing to build with modified CurseForge content: " + ", ".join(modified)
        )

    files = [
        {
            "projectID": int(item["project_id"]),
            "fileID": int(item["file_id"]),
            "required": True,
        }
        for item in lock.get("content", [])
        if item.get("enabled") and item.get("exportable")
    ]
    files.sort(key=lambda item: (item["projectID"], item["fileID"]))
    pack = project["pack"]
    platform = project["platform"]
    manifest = {
        "minecraft": {
            "version": str(platform["minecraft"]),
            "modLoaders": [
                {
                    "id": f"{platform['loader']}-{platform['loader_version']}",
                    "primary": True,
                }
            ],
        },
        "manifestType": "minecraftModpack",
        "manifestVersion": 1,
        "name": pack["name"],
        "version": pack["version"],
        "author": pack["author"],
        "files": files,
        "overrides": "overrides",
    }
    managed = collect_managed_files(root, project)
    output_directory = root / project["build"]["output_directory"]
    output_directory.mkdir(parents=True, exist_ok=True)
    filename = f"{pack['name']}-{pack['version']}.zip".replace(" ", "-")
    output = output_directory / filename
    temporary = output.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w") as archive:
        zip_bytes(
            archive,
            "manifest.json",
            (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
        )
        for relative_path, source in managed.items():
            zip_bytes(
                archive,
                f"overrides/{relative_path.as_posix()}",
                source.read_bytes(),
            )
    os.replace(temporary, output)
    print(f"BUILT: {output} ({len(files)} CurseForge files, {len(managed)} overrides)")
    return 0


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nexvvs",
        description="Audit, validate, deploy, and package the NEXVVS modpack.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("audit", help="refresh the CurseForge content inventory")
    materials = subparsers.add_parser("materials", help="audit material forms and common item tags")
    materials.add_argument("material", nargs="?", help="generate a focused audit for one material")
    probe = subparsers.add_parser("probe", help="inspect the generated ProbeJS evidence")
    probe_subparsers = probe.add_subparsers(dest="probe_command", required=True)
    probe_subparsers.add_parser("status", help="report dump and local live-API availability")
    probe_type_parser = probe_subparsers.add_parser(
        "type", help="search generated events, bindings, and Java declarations"
    )
    probe_type_parser.add_argument("query", help="literal symbol, class, method, or recipe type")
    probe_type_parser.add_argument("--limit", type=int, default=20, help="maximum matches (default: 20)")
    probe_type_parser.add_argument(
        "--special",
        action="store_true",
        help="also search the large @special registry-literal tree",
    )
    subparsers.add_parser("validate", help="validate repository-owned content")
    sync = subparsers.add_parser("sync", help="compare or deploy overrides to an instance")
    sync.add_argument("target", choices=["dev"])
    sync.add_argument("--apply", action="store_true", help="write planned changes")
    subparsers.add_parser("build", help="create an importable CurseForge ZIP")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        if args.command == "audit":
            return audit_instance()
        if args.command == "materials":
            return audit_material_focus(args.material) if args.material else audit_materials()
        if args.command == "probe":
            if args.probe_command == "status":
                return probe_status()
            if args.probe_command == "type":
                return probe_type(
                    args.query,
                    limit=args.limit,
                    include_special=args.special,
                )
            raise NexvvsError(f"Unknown probe command: {args.probe_command}")
        if args.command == "validate":
            return 0 if validate_repository() else 1
        if args.command == "sync":
            return sync_dev(apply=args.apply)
        if args.command == "build":
            return build_archive()
        raise NexvvsError(f"Unknown command: {args.command}")
    except NexvvsError as error:
        print(f"ERROR {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

