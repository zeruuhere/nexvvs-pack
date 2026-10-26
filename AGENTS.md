# NEXVVS development rules

This repository is the source of truth for NEXVVS-owned configuration, KubeJS integrations, datapacks, documentation, and validation tooling. CurseForge instances are runtime adapters, not source repositories.

## Platform

- Pack version: 0.5.1
- Minecraft: 1.21.1
- Mod loader: NeoForge 21.1.264
- Java: 21

Never assume an API, registry ID, recipe type, tag, or mod capability exists. Verify it against the installed JARs, generated registry data, or runtime logs.

## Product principles

- Create is the primary technological system.
- Silent Gear is the primary equipment system.
- Magic and technology should have selected, meaningful integrations.
- Progression remains nonlinear.
- Automation provides efficiency and scale; it should not become an artificial gate for every activity.
- Prefer KubeJS, datapacks, tags, and configuration over modifying mod binaries.
- Preserve multiplayer compatibility and dedicated-server behavior.
- Distinguish material equivalence from functional item equivalence.
- Record balance decisions and runtime assumptions in `docs/`.

## Repository ownership

- Put distributable files under `overrides/`.
- Put KubeJS scripts in the matching startup, server, or client directory.
- Use `kubejs/data` for NEXVVS datapack data and `kubejs/assets` for NEXVVS resources.
- Add individual mod configuration files to `sync.managed_files` in `project.toml`; do not version the entire runtime `config/` directory.
- Generated inventories belong in `catalog/` and generated reports in `reports/`.
- Do not commit mod JARs, third-party resource packs, shader packs, worlds, logs, crash reports, caches, player data, or CurseForge's `minecraftinstance.json`.

## Safety

- Never modify or delete player worlds or saves.
- Never sync directly to the Stable instance.
- `./nexvvs sync dev` is a dry run. Writing requires the explicit `--apply` flag.
- Synchronization is additive/update-only: it does not delete runtime files.
- Run `./nexvvs validate` before applying a sync and after every integration change.
- Test world generation changes in a disposable world. Changes to `defaultconfigs/` do not automatically update an existing world's `serverconfig/`.
- Do not edit mod JARs.

## Workflow

1. Change source files in this repository.
2. Refresh discovery data with `./nexvvs audit` or `./nexvvs materials` when relevant.
3. Run `./nexvvs validate` and the test suite.
4. Inspect `./nexvvs sync dev`.
5. Apply with `./nexvvs sync dev --apply` only after reviewing the plan.
6. Launch the Dev profile through CurseForge and test in Minecraft.
7. Inspect logs and document runtime-only findings.
8. Build with `./nexvvs build` and import the ZIP as a clean QA profile before release.

