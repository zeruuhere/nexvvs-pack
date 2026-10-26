---
name: nexvvs-kubejs-engineering
description: Ground KubeJS recipes, tags, events, and cross-mod integrations in the NEXVVS ProbeJS dump and installed mod evidence. Use when implementing or reviewing KubeJS gameplay scripts, Create processing, material integration, registry builders, or addon APIs in this repository.
---

# NEXVVS KubeJS engineering

Treat the current Dev instance as evidence and this repository as source. Never infer an event, method, recipe schema, tag, or registry ID from examples for another Minecraft version.

## Evidence loop

1. Read `AGENTS.md` and identify whether the change belongs in startup, server, client, data, assets, or configuration.
2. Run `./nexvvs probe status`. Continue with generated declarations when it reports `READY`; call out warnings that affect the requested API.
3. Read [ProbeJS routing](references/probejs-routing.md), then query each non-obvious symbol with `./nexvvs probe type '<symbol>'`. Use `--special` only for a targeted registry literal.
4. Verify item, block, tag, and recipe IDs against installed-JAR data, an existing NEXVVS catalog, or a targeted ProbeJS result. Record which evidence established each unusual identifier.
5. Inspect neighboring scripts and preserve their script type and conventions.
6. Edit only repository-owned source under `overrides/`; keep runtime-generated ProbeJS files in the Dev instance.
7. Run `./nexvvs validate`, `python3 -m unittest discover -s tests -v`, and `./nexvvs sync dev`. A gameplay change is ready for runtime testing only when all three succeed and the dry-run contains only intended files.
8. State the exact in-game smoke test still required. A clean static check is evidence, not proof of gameplay balance or multiplayer behavior.

## Implementation rules

- Prefer schema-backed KubeJS builders when the generated declarations expose them; use raw JSON recipes when that is the verified interface or preserves data more faithfully.
- Keep material equivalence separate from functional-item equivalence. Run `./nexvvs materials <name>` before changing canonical material behavior.
- Preserve nonlinear progression: industrial automation improves throughput without silently removing viable magic, crafting, or exploration routes.
- Keep dedicated-server safety explicit. Client-only APIs belong in client scripts; registry creation belongs in startup scripts; recipes and tags normally belong in server scripts or datapack data.
- Keep changes narrow and reversible. Add focused regression tests for deterministic policy or generated JSON when the repository has a testable seam.
- Treat missing or ambiguous ProbeJS declarations as an investigation branch: inspect the installed JAR or primary upstream documentation and label any remaining runtime assumption.
- KubeX is not part of the active toolchain. Continue authoring curated files under `overrides/kubejs` until its compatibility pilot is explicitly approved.

## Completion criteria

Finish only when every introduced API and identifier has cited local evidence, repository validation and tests pass, the sync plan is reviewed, and the remaining Minecraft test is concrete enough for another person to reproduce.
