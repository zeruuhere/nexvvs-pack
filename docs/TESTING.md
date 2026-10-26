# Testing strategy

## Static checks

Run:

```bash
./nexvvs validate
python3 -m unittest discover -s tests -v
```

Validation covers the managed-file allowlist, protected runtime paths, JSON and TOML parsing, basic SNBT delimiter integrity, and JavaScript syntax through Node.js when available.

Static validation cannot prove registry IDs or KubeJS event behavior. Those require a Minecraft data reload or restart and inspection of `logs/kubejs/` plus `logs/latest.log`.

## Runtime levels

1. **Reload:** server recipe/tag changes with `/reload`; client resources with `F3+T`.
2. **Restart:** startup scripts, registrations, loader configuration, and uncertain mod behavior.
3. **Disposable world:** world generation, structures, dimensions, and `defaultconfigs` changes.
4. **Clean QA import:** release ZIP, first startup, new world creation, save/reload, and multiplayer connection.

## Initial smoke test

- Reach the title screen without KubeJS errors.
- Create a disposable world and spawn successfully.
- Run `/reload` and inspect KubeJS logs.
- Search representative recipes in JEI.
- Place and operate a basic Create kinetic network.
- Save, quit, reopen the world, and confirm no registry remapping errors.

