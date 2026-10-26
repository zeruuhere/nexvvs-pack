# NEXVVS

Versioned development workspace for the NEXVVS Minecraft modpack.

The Git repository contains only NEXVVS-owned integrations and curated configuration. CurseForge remains responsible for installing mods and launching Minecraft; the Dev instance is a deployment target, not the source of truth.

## Current platform

| Item | Version |
| --- | --- |
| NEXVVS | 0.5.1 |
| Minecraft | 1.21.1 |
| NeoForge | 21.1.264 |
| Java | 21 |

## Local setup

`nexvvs.local.toml` contains machine-specific instance paths and is intentionally ignored by Git. An initial local file is already configured on this Mac; use `nexvvs.local.toml.example` on another machine.

## Commands

```bash
./nexvvs audit
./nexvvs materials
./nexvvs materials lead
./nexvvs validate
./nexvvs sync dev
./nexvvs sync dev --apply
./nexvvs build
python3 -m unittest discover -s tests -v
```

- `audit` reads CurseForge metadata and refreshes the content lock and mod list. It does not modify the instance.
- `materials` statically audits material tags inside the installed JARs and refreshes the discovered-material catalog.
- `materials <name>` creates a focused recipe, worldgen, provider, and configuration report for one discovered material.
- `validate` checks repository structure plus JSON, TOML, SNBT balance, and JavaScript syntax.
- `sync dev` compares the curated overrides with the Dev instance. It is a dry run unless `--apply` is supplied.
- `build` creates a deterministic CurseForge ZIP containing `manifest.json` and `overrides/`.

See [architecture](docs/ARCHITECTURE.md) and [testing](docs/TESTING.md) before adding gameplay integrations.

