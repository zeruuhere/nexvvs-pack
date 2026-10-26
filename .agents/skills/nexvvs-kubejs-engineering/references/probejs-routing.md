# ProbeJS evidence routing

Use the Dev instance configured in `nexvvs.local.toml`. The raw dump is generated evidence and stays outside Git.

## Search order

| Question | First evidence |
| --- | --- |
| Server event or recipe callback | `.probe/@side-only/server/events` |
| Server binding | `.probe/@side-only/server/bindings` |
| Startup registry or builder | `.probe/@side-only/startup` |
| Client event or binding | `.probe/@side-only/client` |
| Known Java class or method | `.probe/@package` |
| Exact registry literal | `.probe/@special`, only through a targeted `--special` query |
| Item tag contents or datapack recipe | Installed mod JAR data, NEXVVS catalog, or future live read-only API |

Start with:

```bash
./nexvvs probe status
./nexvvs probe type 'ServerEvents'
./nexvvs probe type 'create:pressing' --special
```

The type search is literal and case-insensitive. It searches side-specific declarations and Java packages by default and caps output. Refine the symbol instead of raising the limit without a reason.

## Current dump caveats

The validated NEXVVS dump was produced by ProbeJS 8.0.3 with KubeJS `2101.7.2-build.377` on NeoForge `21.1.264`.

ProbeJS 8.0.3 can log `Illegal group reference` from `InjectParchment.transformClass` when a Parchment Javadoc link contains `$`. ProbeJS catches this transform failure, and the NEXVVS dump still contains its events, bindings, Java declarations, and recipe schemas. Treat the warning as missing Javadoc enrichment for an affected class; if that class matters, verify it from the installed JAR or primary upstream source.

Full-scan messages about absent optional compatibility classes can also leave individual declarations incomplete. Confirm a missing class against the installed mod list before treating it as a pack defect.

ProbeJS's local web server is authenticated. Status checks may test whether its port is reachable, but tooling must keep the `auth` value private. Mutation and command-execution endpoints are outside this workflow.
