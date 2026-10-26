const NEXVVS_LEAD_CANONICAL = {
  ore: 'tfmg:lead_ore',
  deepslateOre: 'tfmg:deepslate_lead_ore',
  raw: 'tfmg:raw_lead',
  rawBlock: 'tfmg:raw_lead_block',
  ingot: 'tfmg:lead_ingot',
  nugget: 'tfmg:lead_nugget',
  plate: 'tfmg:lead_sheet',
  block: 'tfmg:lead_block'
}

const NEXVVS_LEAD_LEGACY = {
  'cgs:lead_ore': NEXVVS_LEAD_CANONICAL.ore,
  'cgs:deepslate_lead_ore': NEXVVS_LEAD_CANONICAL.deepslateOre,
  'cgs:raw_lead': NEXVVS_LEAD_CANONICAL.raw,
  'cgs:raw_lead_block': NEXVVS_LEAD_CANONICAL.rawBlock,
  'cgs:lead_ingot': NEXVVS_LEAD_CANONICAL.ingot,
  'cgs:lead_nugget': NEXVVS_LEAD_CANONICAL.nugget,
  'cgs:lead_block': NEXVVS_LEAD_CANONICAL.block
}

ServerEvents.tags('item', event => {
  const tags = {
    'c:ores/lead': ['cgs:lead_ore', 'cgs:deepslate_lead_ore', NEXVVS_LEAD_CANONICAL.ore, NEXVVS_LEAD_CANONICAL.deepslateOre],
    'c:raw_materials/lead': ['cgs:raw_lead', NEXVVS_LEAD_CANONICAL.raw],
    'c:storage_blocks/raw_lead': ['cgs:raw_lead_block', NEXVVS_LEAD_CANONICAL.rawBlock],
    'c:ingots/lead': ['cgs:lead_ingot', NEXVVS_LEAD_CANONICAL.ingot],
    'c:nuggets/lead': ['cgs:lead_nugget', NEXVVS_LEAD_CANONICAL.nugget],
    'c:plates/lead': [NEXVVS_LEAD_CANONICAL.plate],
    'c:storage_blocks/lead': ['cgs:lead_block', NEXVVS_LEAD_CANONICAL.block]
  }

  Object.entries(tags).forEach(([tag, items]) => {
    items.forEach(item => event.add(tag, item))
  })
})

ServerEvents.tags('block', event => {
  const tags = {
    'c:ores/lead': ['cgs:lead_ore', 'cgs:deepslate_lead_ore', NEXVVS_LEAD_CANONICAL.ore, NEXVVS_LEAD_CANONICAL.deepslateOre],
    'c:storage_blocks/raw_lead': ['cgs:raw_lead_block', NEXVVS_LEAD_CANONICAL.rawBlock],
    'c:storage_blocks/lead': ['cgs:lead_block', NEXVVS_LEAD_CANONICAL.block]
  }

  Object.entries(tags).forEach(([tag, blocks]) => {
    blocks.forEach(block => event.add(tag, block))
  })
})

ServerEvents.recipes(event => {
  const obsoleteCompactingRecipes = [
    'cgs:lead_block_from_lead_ingot',
    'cgs:lead_ingot',
    'cgs:lead_ingot_from_lead_nugget',
    'cgs:lead_nugget',
    'cgs:raw_lead',
    'cgs:raw_lead_block_from_raw_lead'
  ]

  obsoleteCompactingRecipes.forEach(id => event.remove({ id }))

  const outputReplacements = {
    'cgs:raw_lead': NEXVVS_LEAD_CANONICAL.raw,
    'cgs:raw_lead_block': NEXVVS_LEAD_CANONICAL.rawBlock,
    'cgs:lead_ingot': NEXVVS_LEAD_CANONICAL.ingot,
    'cgs:lead_nugget': NEXVVS_LEAD_CANONICAL.nugget,
    'cgs:lead_block': NEXVVS_LEAD_CANONICAL.block
  }

  Object.entries(outputReplacements).forEach(([legacy, canonical]) => {
    event.replaceOutput({ output: legacy }, legacy, canonical)
  })

  Object.entries(NEXVVS_LEAD_LEGACY).forEach(([legacy, canonical]) => {
    const recipeName = legacy.replace(':', '_')
    event
      .stonecutting(canonical, legacy)
      .id(`nexvvs:materials/lead/convert_${recipeName}`)
  })

  console.info('[NEXVVS] Lead material unification recipes loaded')
})
