import assert from 'assert'
import { readFileSync } from 'fs'
import test from 'node:test'

// the UI's helpers are ES modules without a package "type", so load the file
// as a data URL instead of setting up a bundler for tests
const source = readFileSync(
  new URL('../src/helpers/selection.js', import.meta.url)
)
const { nextSelection } = await import(
  'data:text/javascript;base64,' + source.toString('base64')
)

const order = ['a/', 'b/', 'c.pdb', 'd.sdf', 'e.nanome']
const none = { items: [], anchor: null }

test('a plain click selects only that item', () => {
  const start = { items: ['a/', 'c.pdb'], anchor: 'a/' }
  assert.deepStrictEqual(nextSelection(start, order, 'd.sdf'), {
    items: ['d.sdf'],
    anchor: 'd.sdf'
  })
})

test('ctrl/cmd toggles an item in and out', () => {
  const one = nextSelection(none, order, 'c.pdb', { toggle: true })
  const two = nextSelection(one, order, 'a/', { toggle: true })
  assert.deepStrictEqual(two, { items: ['a/', 'c.pdb'], anchor: 'a/' })
  const back = nextSelection(two, order, 'c.pdb', { toggle: true })
  assert.deepStrictEqual(back, { items: ['a/'], anchor: 'c.pdb' })
})

test('shift selects the range from the anchor, either direction', () => {
  const start = { items: ['b/'], anchor: 'b/' }
  assert.deepStrictEqual(
    nextSelection(start, order, 'd.sdf', { range: true }),
    {
      items: ['b/', 'c.pdb', 'd.sdf'],
      anchor: 'b/'
    }
  )
  const down = { items: ['d.sdf'], anchor: 'd.sdf' }
  assert.deepStrictEqual(
    nextSelection(down, order, 'a/', { range: true }).items,
    ['a/', 'b/', 'c.pdb', 'd.sdf']
  )
})

test('shift keeps the anchor, so a second shift-click resizes the range', () => {
  const start = { items: ['b/'], anchor: 'b/' }
  const wide = nextSelection(start, order, 'e.nanome', { range: true })
  const narrow = nextSelection(wide, order, 'c.pdb', { range: true })
  assert.deepStrictEqual(narrow.items, ['b/', 'c.pdb'])
})

test('shift with ctrl/cmd adds the range to the selection', () => {
  const start = { items: ['a/', 'd.sdf'], anchor: 'd.sdf' }
  const next = nextSelection(start, order, 'e.nanome', {
    range: true,
    toggle: true
  })
  assert.deepStrictEqual(next.items, ['a/', 'd.sdf', 'e.nanome'])
})

test('shift without an anchor in this folder acts like a plain click', () => {
  assert.deepStrictEqual(nextSelection(none, order, 'c.pdb', { range: true }), {
    items: ['c.pdb'],
    anchor: 'c.pdb'
  })
})

test('items no longer in the folder are dropped', () => {
  const stale = { items: ['gone.pdb', 'a/'], anchor: 'a/' }
  const next = nextSelection(stale, order, 'b/', { toggle: true })
  assert.deepStrictEqual(next.items, ['a/', 'b/'])
})
