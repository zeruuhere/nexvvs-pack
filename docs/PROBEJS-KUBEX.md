# ProbeJS and KubeX

Research date: 2026-10-26.

This note evaluates ProbeJS and KubeX for the NEXVVS development workflow. It separates upstream capabilities from local observations and does not authorize a mod update or a KubeJS source-layout migration.

## Executive decision

- **Adopt ProbeJS.** The Dev dump completed and produced 3,573 TypeScript declarations across the side-specific, Java-package, and special registry trees. `./nexvvs probe status` and `./nexvvs probe type` now expose that evidence through a bounded, read-only adapter. [Local lock](../catalog/curseforge.lock.json) [ProbeJS version declaration](https://github.com/Prunoideae/ProbeJS/blob/1.21/gradle.properties)
- **Keep ProbeJS development-only in the eventual release policy.** Its purpose is type generation, editor integration, runtime inspection, and development-agent support rather than player-facing gameplay. It also exposes authenticated local development endpoints, including a command-execution endpoint, which is unnecessary in a normal player pack. [ProbeJS project](https://github.com/Prunoideae/ProbeJS) [ProbeJS web endpoints](https://github.com/Prunoideae/ProbeJS/blob/1.21/src/main/java/moe/wolfgirl/probejs/misc/endpoints/ProbeJSWeb.java)
- **Do not add current KubeX yet.** KubeX 0.0.9 requires Rhino `2101.2.8-build.91`, while NEXVVS currently has `2101.2.7-build.85`. Rhino build 91 is published as a beta and its upstream notes describe a major internal change that may fix or break loop behavior in addons. KubeX therefore needs its own compatibility branch and full boot/world regression before adoption. [Local lock](../catalog/curseforge.lock.json) [KubeX requirements](https://github.com/WD07-Dev/KubeX/blob/1.21.1/gradle.properties) [Rhino 2101.2.8-build.91 notes](https://modrinth.com/mod/rhino/version/2101.2.8-build.91%2BRhino-1.21)
- **Treat KubeX as an optional TypeScript build experiment, not as the pack architecture yet.** It is useful, but its workspace and publication model overlap with the existing `overrides/kubejs` source-of-truth and `./nexvvs` synchronization seam. [NEXVVS architecture](ARCHITECTURE.md) [KubeX README](https://github.com/WD07-Dev/KubeX/blob/1.21.1/README.md)

## Local state verified on 2026-10-26

| Component | NEXVVS state | Upstream minimum relevant here | Result |
| --- | --- | --- | --- |
| Minecraft | 1.21.1 | ProbeJS 8.0.3 and KubeX 0.0.9 target 1.21.1 | Compatible |
| NeoForge | 21.1.264 | ProbeJS and KubeX build against/minimum 21.1.199 | Compatible |
| KubeJS | 2101.7.2-build.377 | ProbeJS: build.365; KubeX: build.374 | Compatible |
| Rhino | 2101.2.7-build.85 | KubeX 0.0.9: 2101.2.8-build.91 | **KubeX blocked** |
| ProbeJS | 8.0.3 installed | Current 1.21.1 release | Present |
| KubeX | Not present in the lock or Dev `mods/` | 0.0.9 is the latest upstream release | Absent |

The NEXVVS values come from [`project.toml`](../project.toml), [`catalog/curseforge.lock.json`](../catalog/curseforge.lock.json), and the audited mod list in [`docs/MODLIST.md`](MODLIST.md). The upstream values come from the [ProbeJS 1.21 build properties](https://github.com/Prunoideae/ProbeJS/blob/1.21/gradle.properties), [ProbeJS NeoForge metadata](https://github.com/Prunoideae/ProbeJS/blob/1.21/src/main/resources/META-INF/neoforge.mods.toml), [KubeX build properties](https://github.com/WD07-Dev/KubeX/blob/1.21.1/gradle.properties), and [KubeX NeoForge metadata](https://github.com/WD07-Dev/KubeX/blob/1.21.1/neoforge/src/main/resources/META-INF/neoforge.mods.toml).

The validated Dev dump contains 3,573 `.d.ts` files and the expected `.probe/@side-only`, `.probe/@package`, and `.probe/@special` trees. ProbeJS also generated side-specific `jsconfig.json` files, editor snippets, and its optional LLM guidance.

The current Dev `latest.log` records ProbeJS 8.0.3 failing inside `InjectParchment.transformClass` with `Illegal group reference`. Source inspection and a minimal Java reproduction confirmed that its Javadoc sanitizer passes replacement text containing `$` through `Matcher.replaceAll`; ProbeJS catches this plugin exception and continues the dump. The practical impact is incomplete Parchment Javadoc for an affected class, not loss of the generated event, binding, Java, or recipe declarations. Keep the warning visible and verify any specifically affected class through its installed JAR or primary upstream source. Full-scan warnings for optional compatibility classes are similarly local to those classes.

## ProbeJS

### What it is

ProbeJS is a KubeJS data dumper and TypeScript declaration generator. Version 8 generates information from the actual running modpack rather than relying on generic examples. Its official 1.21.1 release is NeoForge-only and is built against KubeJS `2101.7.2`. [ProbeJS README](https://github.com/Prunoideae/ProbeJS/blob/1.21/README.md) [ProbeJS 8.0.3 release page](https://www.curseforge.com/minecraft/mc-mods/probejs/files/8304356)

The generated material includes:

- `.probe/@side-only/<side>/...`: events and bindings available to startup, server, or client scripts;
- `.probe/@package/...`: declarations for discovered Java, Minecraft, NeoForge, KubeJS, and addon classes;
- `.probe/@special/...`: large literal types such as registry-related values;
- one `jsconfig.json` for each KubeJS script type;
- VS Code snippets and workspace metadata;
- optional `.github/agents/*.agent.md` files when **LLM support** is enabled. [ProbeJS 1.21 release notes](https://github.com/Prunoideae/ProbeJS/releases/tag/v7.0.0-1.21) [ProbeJS project dump implementation](https://github.com/Prunoideae/ProbeJS/blob/1.21/src/main/java/moe/wolfgirl/probejs/dumps/ProjectDump.java)

ProbeJS 8 also ships dedicated LLM guidance and teaches agents to search the side-specific declarations and targeted Java packages instead of loading the huge `@special` tree wholesale. [ProbeJS generated exploration agent](https://github.com/Prunoideae/ProbeJS/blob/1.21/src/main/resources/assets/probejs/dumps/kubejs-explore.agent.md)

### How to generate the evidence

For ProbeJS 8.0.3 in NEXVVS:

1. Launch the **Dev** CurseForge profile.
2. Enter a local disposable/test world so the integrated server and registries exist.
3. Run `/probejs` to open its GUI.
4. Enable **LLM support**.
5. Keep the automatically detected full-scan mods; add a specific mod ID only if its KubeJS addon types are later missing.
6. Press the dump button and wait for `Dump complete!`.
7. Tell Codex that the dump is ready.

The ProbeJS 8 README documents the `/probejs` GUI flow; older documentation that says `/probejs dump` describes an earlier interface and should not override the installed version's behavior. [ProbeJS 8 README](https://github.com/Prunoideae/ProbeJS/blob/1.21/README.md) [Installed GUI command implementation](https://github.com/Prunoideae/ProbeJS/blob/1.21/src/main/java/moe/wolfgirl/probejs/GameEvents.java)

### How Codex can use it

There are two usable paths.

#### Offline dump path

Codex can search the generated `.d.ts` files directly with targeted queries:

- look under `@side-only/server` for `ServerEvents`, recipe events, and server bindings;
- look under `@side-only/startup` for registry/builders;
- look under `@package` only for a known Java class or method;
- avoid ingesting all of `@special`, because it is deliberately very large;
- use the generated registry snapshot when an item/tag existence question does not require the live game.

This works even after Minecraft closes. Raw `.probe` output should remain generated evidence in the Dev instance, not committed source. A compact, deterministic summary can be written to `catalog/` when it is useful to CI or code review. [ProbeJS paths](https://github.com/Prunoideae/ProbeJS/blob/1.21/src/main/java/moe/wolfgirl/probejs/ProbePaths.java) [NEXVVS repository ownership rules](../AGENTS.md)

#### Live read-only path

The ProbeJS VS Code extension talks to KubeJS's authenticated local web server. It queries registries, registry objects, tags, tag members, recipes, language keys, and commands. The extension also registers these as **VS Code language-model tools**, not as MCP tools. Codex cannot call those VS Code tool registrations directly, but it can use the same local HTTP API through a repository-owned CLI adapter while the game is running. [ProbeJS extension tools](https://github.com/Prunoideae/ProbeJS-Extension/blob/main/package.json) [ProbeJS extension API client](https://github.com/Prunoideae/ProbeJS-Extension/blob/main/src/features/copilot.ts)

Current offline `./nexvvs` interface:

```text
./nexvvs probe status
./nexvvs probe type <symbol-or-class>
./nexvvs probe type <registry-literal> --special
```

Possible future live-query interface:

```text
./nexvvs probe registry <registry-regex> <object-regex>
./nexvvs probe tags <registry> <tag-regex>
./nexvvs probe tag-members <registry> <tag>
./nexvvs probe recipe <recipe-id>
./nexvvs probe snapshot
```

The adapter should:

- locate only the configured Dev instance;
- read the local port and bearer credential internally from `kubejs/config/web_server.json`;
- never print, log, commit, or copy that credential into reports;
- expose only `GET`/read-only queries by default;
- use short timeouts and clearly report when Minecraft or the integrated server is not running;
- keep command execution outside the default surface.

ProbeJS provides an authenticated `POST /api/probejs/run-command` endpoint, and the official VS Code extension registers it as a tool. It executes commands as the first local server player, so exposing it through the normal audit CLI would cross a meaningful safety boundary. If NEXVVS ever adds command execution, it should require an explicit command-specific flag and a task that actually authorizes a world mutation. [ProbeJS command endpoint](https://github.com/Prunoideae/ProbeJS/blob/1.21/src/main/java/moe/wolfgirl/probejs/misc/endpoints/ProbeJSWeb.java) [ProbeJS extension command tool](https://github.com/Prunoideae/ProbeJS-Extension/blob/main/src/features/copilot.ts)

### What the generated agent files do not provide

The optional `.github/agents/*.agent.md` files target VS Code/GitHub Copilot and reference `vscode/*` plus `prunoideae.probejs/*` tools. They are useful documentation, but they are not Codex skills and do not make the VS Code tools appear in Codex. NEXVVS should incorporate the relevant evidence-routing rules into its own project skill instead of treating those files as an integration protocol. [Generated ProbeJS agents](https://github.com/Prunoideae/ProbeJS/tree/1.21/src/main/resources/assets/probejs/dumps) [VS Code tool registration](https://github.com/Prunoideae/ProbeJS-Extension/blob/main/src/features/copilot.ts)

## KubeX

### What it is

KubeX is a KubeJS development workspace and compiler. It creates `kubex/src`, supports JavaScript or TypeScript entry points, bundles with esbuild, lowers output for Rhino, publishes generated scripts and resources into `kubejs/`, preserves source-map information, provides `/kubex doctor` and debug mode, and can export the compiled workspace as a NeoForge mod JAR. It explicitly complements rather than replaces ProbeJS. [KubeX README](https://github.com/WD07-Dev/KubeX/blob/1.21.1/README.md)

The current command surface is:

```text
/kubex init js
/kubex init ts
/kubex build
/kubex sync
/kubex export
/kubex debug [on|off]
/kubex doctor ...
```

KubeX has no documented MCP server or standalone KubeX CLI. Its build command runs npm from the game process; a human or an authorized game-command bridge must invoke the KubeX command for its Rhino post-processing, synchronization, reload, and source-position diagnostics. [KubeX commands](https://github.com/WD07-Dev/KubeX/blob/1.21.1/neoforge/src/main/java/com/ourgram/kubex/neoforge/cmd/CommandRegistry.java) [KubeX builder](https://github.com/WD07-Dev/KubeX/blob/1.21.1/core/src/main/java/com/ourgram/kubex/workspace/Builder.java)

### Compatibility with NEXVVS

KubeX 0.0.9 declares these minimums:

- Minecraft 1.21.1;
- NeoForge 21.1.199;
- KubeJS 2101.7.2-build.374;
- Rhino 2101.2.8-build.91. [KubeX build properties](https://github.com/WD07-Dev/KubeX/blob/1.21.1/gradle.properties) [KubeX metadata](https://github.com/WD07-Dev/KubeX/blob/1.21.1/neoforge/src/main/resources/META-INF/neoforge.mods.toml)

Only Rhino fails against the current NEXVVS matrix. KubeX 0.0.5 was built against Rhino build 85 and could load with the current pack, but later releases added status reporting, export, async/Promise diagnostics, and important loop/scoping fixes. Pinning an older tool would avoid the dependency update while also discarding the fixes that make generated JavaScript safer, so it is not the recommended long-term choice. [KubeX 0.0.5](https://github.com/WD07-Dev/KubeX/releases/tag/0.0.5) [KubeX 0.0.6](https://github.com/WD07-Dev/KubeX/releases/tag/0.0.6) [KubeX 0.0.8](https://github.com/WD07-Dev/KubeX/releases/tag/0.0.8) [KubeX 0.0.9](https://github.com/WD07-Dev/KubeX/releases/tag/0.0.9)

### How Codex could use it after a successful pilot

Once installed in a disposable Dev clone and initialized, Codex could:

1. edit `kubex/src/**/*.{js,ts}` and the workspace build configuration;
2. search the ProbeJS declarations copied into `kubex/.probe`;
3. run `npm install` and `npm run build` for a fast bundler check;
4. ask the user to run `/kubex build`, or use a separately authorized ProbeJS command bridge;
5. read `kubex/.kubex-status.json`, Minecraft logs, emitted source maps, and `/kubex doctor` results;
6. validate the compiled scripts and package the generated `kubejs/` output through the existing NEXVVS release flow.

KubeX writes build/export progress to `.kubex-status.json`, and its `doctor` maps generated line/column positions back to the edited source. [KubeX README: build status and doctor](https://github.com/WD07-Dev/KubeX/blob/1.21.1/README.md#source-maps-and-debugging)

### Architectural and operational risks

- KubeX writes one generated `main.js` into each script group. Existing NEXVVS nested scripts would continue to coexist unless intentionally migrated, which can create duplicate behavior if the same integration exists in both places. [KubeX synchronizer](https://github.com/WD07-Dev/KubeX/blob/1.21.1/core/src/main/java/com/ourgram/kubex/workspace/Synchronizer.java)
- KubeX mirrors `kubex/src/assets`, `config`, and `data` into their KubeJS targets and deletes target files not present in the corresponding KubeX source directory. This conflicts with the current additive/update-only NEXVVS sync policy unless all NEXVVS-owned files are migrated or the seam is redesigned first. [KubeX synchronizer](https://github.com/WD07-Dev/KubeX/blob/1.21.1/core/src/main/java/com/ourgram/kubex/workspace/Synchronizer.java) [NEXVVS safety rules](../AGENTS.md)
- The default workspace runs `npm install` when `node_modules` is missing and uses semver ranges for Babel and esbuild. A pilot should commit `package-lock.json`, review dependency changes, keep automatic rebuild on game start disabled, and never require Node/npm in a player release. [KubeX builder](https://github.com/WD07-Dev/KubeX/blob/1.21.1/core/src/main/java/com/ourgram/kubex/workspace/Builder.java) [KubeX package template](https://github.com/WD07-Dev/KubeX/blob/1.21.1/core/src/main/resources/kubex/templates/common/package.json)
- KubeX is still a `0.0.x` project with a small installed base. Its latest releases specifically fix generated async and loop code, so the compiler must be treated as version-sensitive and tested with representative integrations rather than assumed safe. [KubeX releases](https://github.com/WD07-Dev/KubeX/releases)
- Exporting scripts as a mod JAR is technically supported and removes the runtime KubeX dependency, but it changes NEXVVS distribution, debugging, and source-transparency expectations. The current recommendation is to retain curated `overrides/kubejs` output rather than adopt exported JARs. [KubeX export documentation](https://github.com/WD07-Dev/KubeX/blob/1.21.1/README.md#exporting-a-mod) [NEXVVS architecture](ARCHITECTURE.md)

## Recommended rollout

### Phase A: ProbeJS evidence, no dependency changes

1. Generate the ProbeJS dump in the Dev profile with LLM support enabled.
2. Verify that the dump reaches `Dump complete!`, inspect the log for fatal ProbeJS errors, and record the known KubeJSTweaks bridge warning separately.
3. Verify that `.probe/@side-only`, `.probe/@package`, generated `jsconfig.json`, and the registry snapshot exist.
4. Add a read-only `./nexvvs probe` adapter and tests.
5. Teach the future `nexvvs-kubejs-integration` skill to consult ProbeJS before inventing APIs or IDs.
6. Keep the raw dump out of Git; commit only compact generated reports when they are stable and reviewable.

### Phase B: KubeX proof of concept

1. Create a separate branch and disposable CurseForge clone.
2. Update Rhino to build 91 in that clone and run the established boot, world-entry, Create, magic-addon, and KubeJS smoke tests.
3. Add KubeX 0.0.9 locally to the Dev clone only.
4. Initialize one small TypeScript integration that does not duplicate an existing script.
5. Verify build, sync, reload, source maps, `/kubex doctor`, dedicated-server behavior, and clean release output.
6. Decide whether the TypeScript benefits justify migrating the repository seam. Do not migrate all existing scripts during the experiment.

### Release policy

| Artifact | Dev profile | Public/QA pack |
| --- | --- | --- |
| ProbeJS mod | Yes | No, unless a separately documented player-facing reason appears |
| ProbeJS `.probe`, `.vscode`, generated agents | Local generated tooling | No |
| ProbeJS compact catalog/report | Yes, if deterministic and useful | Optional documentation only |
| KubeX mod | Pilot only | No |
| KubeX `node_modules`, output, status files | Local generated tooling | No |
| Authored KubeX TypeScript/JavaScript source | Yes, if adopted | Repository source, not instance-only |
| Compiled KubeJS scripts/assets/data | Yes | Yes, through `overrides/` after validation |
| KubeX exported mod JAR | Not recommended initially | No under the current architecture |

## Acceptance criteria before saying Codex “uses ProbeJS”

- The current Dev instance has a non-empty ProbeJS dump produced from the exact NEXVVS mod list.
- `./nexvvs probe status` can distinguish missing and ready dumps plus online, offline, disabled, unconfigured, and invalid live-API states.
- Registry/tag queries do not expose the local bearer credential.
- A KubeJS change cites the ProbeJS file or live query used to verify each non-obvious event, class, recipe type, tag, or registry ID.
- The standard `./nexvvs validate`, tests, dry-run sync, and runtime smoke test still pass.

