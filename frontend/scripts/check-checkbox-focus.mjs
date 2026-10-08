import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { compile } from 'tailwindcss'

// Compile the actual default skin, not a second copy of its class names.
const source = await readFile(new URL('../src/components/ui/Checkbox.tsx', import.meta.url), 'utf8')
const skin = source.match(/className=\{cn\(([\s\S]*?),\s*className,\s*\)\}/)?.[1]
assert.ok(skin, 'Checkbox default className must be discoverable')
const classes = [...skin.matchAll(/'([^']+)'/g)].flatMap((match) => match[1].split(/\s+/))
assert.ok(classes.includes('outline-none'), 'Regression must exercise the default outline reset')
const compiler = await compile('@theme { --color-black: #000; }\n@tailwind utilities;')
const css = compiler.build(classes)

// Only applicable class rules participate: @property initial-value and the
// lower-priority global base layer cannot restore an explicitly reset style.
const declarations = new Map()
const focusRules = []
for (const [, selector, body] of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
  const trimmed = selector.trim()
  if (trimmed !== '.outline-none' && !/^\.focus-visible\\:[^\s]+:focus-visible$/.test(trimmed)) continue
  if (trimmed.includes(':focus-visible')) focusRules.push(trimmed)
  for (const [, property, value] of body.matchAll(/([\w-]+)\s*:\s*([^;]+);/g)) {
    declarations.set(property, value.trim())
  }
}
assert.ok(focusRules.length > 0, 'Expected compiled focus-visible rules')
const style = declarations.get('outline-style')?.replace(
  /var\((--[\w-]+)\)/g,
  (_, property) => declarations.get(property) ?? 'unset',
)
assert.equal(style, 'solid', `Checkbox focus outline is ${style}; focus must override outline-none`)
assert.equal(declarations.get('outline-width'), '2px')
assert.equal(declarations.get('outline-offset'), '2px')
assert.equal(declarations.get('outline-color'), 'var(--color-black)')
console.log('PASS Checkbox actual Tailwind focus rules: solid, 2px, offset 2px, black')
