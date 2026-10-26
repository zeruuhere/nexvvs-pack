# Lead unification policy

## Decision

TFMG is the canonical lead provider. Create: Gunsmithing remains installed and its ammunition mechanics remain intact.

## Canonical forms

| Form | Canonical item |
| --- | --- |
| Ore | `tfmg:lead_ore`, `tfmg:deepslate_lead_ore` |
| Raw material | `tfmg:raw_lead` |
| Raw storage block | `tfmg:raw_lead_block` |
| Ingot | `tfmg:lead_ingot` |
| Nugget | `tfmg:lead_nugget` |
| Plate | `tfmg:lead_sheet` |
| Storage block | `tfmg:lead_block` |

`cgs:lead_balls` is a functional ammunition component and is not replaced.

## World generation

The CGS biome modifier is overridden with a NeoForge `remove_features` modifier. TFMG remains the only lead ore provider in newly generated chunks. Existing chunks and existing CGS ore blocks are not deleted or rewritten.

CGS ore in existing chunks keeps its Silk Touch behavior. Normal drops are redirected to `tfmg:raw_lead` while preserving the original CGS quantity and Fortune behavior.

## Recipes and migration

- Concrete CGS compacting/decompacting recipes are removed in favor of TFMG's tag-aware recipes.
- Supported recipe outputs that produce generic CGS lead forms are redirected to TFMG.
- Create Ore Excavation keeps the CGS vein definition but produces `tfmg:raw_lead`.
- One-way 1:1 stonecutting recipes convert legacy CGS forms to TFMG without colliding with existing shapeless compacting recipes.
- Common item and block tags retain both providers so existing items remain usable.

## Runtime acceptance criteria

- No KubeJS startup, tag, recipe, or datapack errors.
- Only TFMG lead ore appears in newly generated chunks.
- Existing CGS ores mine and process into canonical material.
- CGS lead balls and ammunition recipes continue to work.
- Create pressing produces `tfmg:lead_sheet`.
- Create Ore Excavation produces `tfmg:raw_lead`.
- Compacting, decompacting, and migration recipes do not multiply resources.
