// A preset's overlay lists, as stored: `ids` bottom-to-top (last = drawn on
// top), `below` the subset drawn under the logo and text. Seasons inherit the
// series lists unless the season config overrides them (season_options is a
// diff over options, merged the way backend resolve_season_options() does).

export type OverlayLists = { ids: string[]; below: string[] }
export type PresetOverlayLists = { series: OverlayLists; season: OverlayLists }

function listsOf(options: Record<string, any>): OverlayLists {
  return {
    ids: Array.isArray(options.overlay_config_ids) ? [...options.overlay_config_ids] : [],
    below: Array.isArray(options.overlay_config_ids_below) ? [...options.overlay_config_ids_below] : [],
  }
}

export function presetOverlayLists(
  options: Record<string, any>,
  seasonOptions?: Record<string, any> | null,
): PresetOverlayLists {
  const base = options || {}
  return { series: listsOf(base), season: listsOf({ ...base, ...(seasonOptions || {}) }) }
}

function sameList(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((v, i) => v === b[i])
}

/** True if any list differs in content or order (an Above/Below flip counts). */
export function overlayListsChanged(a: PresetOverlayLists, b: PresetOverlayLists): boolean {
  return !(
    sameList(a.series.ids, b.series.ids) &&
    sameList(a.series.below, b.series.below) &&
    sameList(a.season.ids, b.season.ids) &&
    sameList(a.season.below, b.season.below)
  )
}
