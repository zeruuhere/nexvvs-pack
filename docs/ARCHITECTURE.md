# Architecture

## Source and runtime

The Git repository is the source of truth. A CurseForge instance is a runtime adapter populated from curated files under `overrides/`.

The seam lives at the `./nexvvs` interface. Its implementation handles path validation, platform checks, inventory extraction, comparison, backups, synchronization, and CurseForge packaging. Callers should not recreate that behavior with ad-hoc copy commands.

Two adapters exercise the seam:

1. The Dev instance adapter deploys source files for interactive Minecraft testing.
2. The CurseForge archive adapter produces a clean, importable release candidate for QA.

The Stable profile is a protected reference installation. It is deliberately not a synchronization target.

## Owned content

Only files intentionally authored or curated for NEXVVS belong under `overrides/`:

- `kubejs/startup_scripts`: registries and initialization-time behavior.
- `kubejs/server_scripts`: recipes, tags, loot, server events, and progression logic.
- `kubejs/client_scripts`: tooltips and client presentation.
- `kubejs/data`: datapack resources.
- `kubejs/assets`: resource-pack resources.
- `defaultconfigs`: templates copied into newly created worlds.
- `config`: individual global files explicitly listed in `project.toml`.

Third-party binaries, player state, logs, caches, and personal preferences remain in CurseForge and never become repository source.

## Material catalogs

`catalog/materials.discovered.json` is generated evidence from common item tags found in installed JARs. It records material forms, candidate items, nested tags, and their source files. `catalog/materials.json` is the curated policy and remains the only place where canonical-item and progression decisions are made.

## Configuration lifecycle

Root `config/` files apply at the instance level. `defaultconfigs/` seeds server configuration for new worlds, while an existing world's effective configuration normally lives under `saves/<world>/serverconfig/`. World files are always protected; an existing test world's server configuration may only be changed through a separately reviewed, explicit operation.

## Release lifecycle

1. CurseForge is used to add or update hosted mods in the Dev profile.
2. `./nexvvs audit` records project IDs, file IDs, filenames, and modification state.
3. Source changes are validated and synchronized to Dev.
4. Minecraft provides runtime and gameplay validation.
5. `./nexvvs build` creates `manifest.json` plus curated `overrides/`.
6. The ZIP is imported as a new QA profile and tested with a clean world.
7. A successful candidate is tagged in Git and promoted through CurseForge.

