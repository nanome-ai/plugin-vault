// The selection after clicking `item` in a folder whose items are `order`.
// A plain click selects only the item, ctrl/cmd toggles it, and shift selects
// the range from the anchor (the last item clicked without shift), added to
// the selection when ctrl/cmd is also held.
export function nextSelection({ items, anchor }, order, item, modifiers = {}) {
  const { toggle = false, range = false } = modifiers
  let chosen

  if (range && order.includes(anchor)) {
    const ends = [order.indexOf(anchor), order.indexOf(item)]
    const from = Math.min(...ends)
    const to = Math.max(...ends)
    const span = order.slice(from, to + 1)
    chosen = toggle ? items.concat(span) : span
  } else if (toggle) {
    chosen = items.includes(item)
      ? items.filter(i => i !== item)
      : items.concat(item)
    anchor = item
  } else {
    chosen = [item]
    anchor = item
  }

  // keep the folder's order and drop anything no longer in it
  return { items: order.filter(i => chosen.includes(i)), anchor }
}
