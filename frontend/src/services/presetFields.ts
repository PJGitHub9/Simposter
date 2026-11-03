// The preset settings Template Manager's type-in form edits, per template.
// Keys, ranges and units mirror the poster editors (EditorPane.vue,
// TextOverlayPanel.vue, KometaCreatorPane.vue) so both places accept the same
// values. `percent` fields are stored 0-1 and shown/typed as 0-100.
// Overlay lists are edited separately (PresetOverlayList.vue). Keys a preset
// has that aren't listed here are kept as they are on save, and fields are
// only ever saved when changed (changedFieldPayload).

export type PresetFieldGroup = 'image' | 'logo' | 'text' | 'extras' | 'fallback'

type ValueOf = (key: string) => unknown

export type PresetField = {
  key: string
  label: string
  group: PresetFieldGroup
  /** Sub-heading the field sits under within its group. */
  section?: string
  type: 'number' | 'percent' | 'select' | 'bool' | 'color' | 'text' | 'font' | 'preset'
  min?: number
  max?: number
  step?: number
  options?: { value: string; label: string }[]
  help?: string
  /** Shown when the preset has no value (also what the renderer assumes). */
  default?: string
  /** Shown only when this returns true (values as the form shows them). Hidden fields keep their value. */
  showIf?: (v: ValueOf) => boolean
  /** Only in the series/movie view (settings that apply to the whole preset). */
  seriesOnly?: boolean
}

export const FIELD_GROUPS: { id: PresetFieldGroup; label: string }[] = [
  { id: 'image', label: 'Image' },
  { id: 'logo', label: 'Logo' },
  { id: 'text', label: 'Text' },
  { id: 'extras', label: 'Extras' },
  { id: 'fallback', label: 'Fallback' },
]

const H_ALIGN = [
  { value: 'left', label: 'Left' },
  { value: 'center', label: 'Center' },
  { value: 'right', label: 'Right' },
]
const V_ALIGN = [
  { value: 'top', label: 'Top' },
  { value: 'center', label: 'Center' },
  { value: 'bottom', label: 'Bottom' },
]
const FONT_WEIGHTS = ['100', '200', '300', '400', '500', '600', '700', '800', '900'].map(v => ({ value: v, label: v }))
const TEXT_TRANSFORMS = [
  { value: 'none', label: 'None' },
  { value: 'uppercase', label: 'UPPERCASE' },
  { value: 'lowercase', label: 'lowercase' },
  { value: 'capitalize', label: 'Capitalize' },
]

const on = (key: string) => (v: ValueOf) => !!v(key)
const textOn = on('text_overlay_enabled')
const hasLogo = (v: ValueOf) => v('logo_mode') !== 'none'
const logoShadowOn = (v: ValueOf) => hasLogo(v) && !!v('uniform_logo_shadow_enabled')
const textShadowOn = (v: ValueOf) => textOn(v) && !!v('shadow_enabled')
const outlineOn = (v: ValueOf) => textOn(v) && !!v('stroke_enabled')

// Text and border settings shared by both templates.
const TEXT_COMMON: PresetField[] = [
  { key: 'text_overlay_enabled', label: 'Custom text on', group: 'text', section: 'Text', type: 'bool' },
  { key: 'custom_text', label: 'Text', group: 'text', section: 'Text', type: 'text', showIf: textOn, help: 'Values like {title}, {year}, {season}, {season number}' },
  { key: 'font_family', label: 'Font', group: 'text', section: 'Text', type: 'font', showIf: textOn },
  { key: 'font_size', label: 'Font size', group: 'text', section: 'Text', type: 'number', min: 20, max: 400, showIf: textOn },
  { key: 'text_color', label: 'Text color', group: 'text', section: 'Text', type: 'color', showIf: textOn },
]
const BORDER: PresetField[] = [
  { key: 'border_enabled', label: 'Border on', group: 'extras', section: 'Border', type: 'bool' },
  { key: 'border_px', label: 'Thickness (px)', group: 'extras', section: 'Border', type: 'number', min: 0, max: 60, showIf: on('border_enabled') },
  { key: 'border_color', label: 'Color', group: 'extras', section: 'Border', type: 'color', showIf: on('border_enabled') },
]
const FADES: PresetField[] = [
  { key: 'top_matte_height_ratio', label: 'Matte %', group: 'image', section: 'Top fade', type: 'percent', min: 0, max: 50 },
  { key: 'top_fade_height_ratio', label: 'Fade %', group: 'image', section: 'Top fade', type: 'percent', min: 0, max: 100 },
  { key: 'matte_height_ratio', label: 'Matte %', group: 'image', section: 'Bottom fade', type: 'percent', min: 0, max: 50 },
  { key: 'fade_height_ratio', label: 'Fade %', group: 'image', section: 'Bottom fade', type: 'percent', min: 0, max: 100 },
]
const fallbackActions = (continueLabel: string) => [
  { value: 'continue', label: continueLabel },
  { value: 'skip', label: 'Skip (no poster is made)' },
  { value: 'template', label: 'Use a different preset' },
]
const isTemplate = (key: string) => (v: ValueOf) => v(key) === 'template'

// Fallback rules: what batch, webhook and scheduled renders do when this preset's
// preferred poster or logo isn't found (the manual editor never falls back).
// They apply to the whole preset, so they're edited in the series/movie view.
const FALLBACK: PresetField[] = [
  {
    key: 'logoSource', label: 'Logo source', group: 'fallback', section: 'Logo source', type: 'select', seriesOnly: true, default: '', options: [
      { value: '', label: 'Use default setting' },
      { value: 'tmdb', label: 'TMDb only' },
      { value: 'fanart', label: 'Fanart.tv only' },
      { value: 'tmdb_fanart', label: 'TMDb first, Fanart fallback' },
      { value: 'fanart_tmdb', label: 'Fanart first, TMDb fallback' },
      { value: 'both', label: 'Both merged' },
    ],
  },
  { key: 'fallbackPosterAction', label: 'If the preferred poster isn’t found', group: 'fallback', section: 'Poster', type: 'select', seriesOnly: true, default: 'continue', options: fallbackActions('Use the first available poster') },
  { key: 'fallbackPosterPreset', label: 'Fallback preset', group: 'fallback', section: 'Poster', type: 'preset', seriesOnly: true, showIf: isTemplate('fallbackPosterAction') },
  { key: 'fallbackLogoAction', label: 'If the preferred logo isn’t found', group: 'fallback', section: 'Logo', type: 'select', seriesOnly: true, default: 'continue', options: fallbackActions('Render without a logo') },
  { key: 'fallbackLogoPreset', label: 'Fallback preset', group: 'fallback', section: 'Logo', type: 'preset', seriesOnly: true, showIf: isTemplate('fallbackLogoAction') },
]

export const UNIFORMLOGO_FIELDS: PresetField[] = [
  // Image
  {
    key: 'poster_filter', label: 'Poster filter', group: 'image', section: 'Poster', type: 'select', options: [
      { value: 'all', label: 'All posters' },
      { value: 'textless', label: 'Textless only' },
      { value: 'text', label: 'With text' },
    ],
  },
  { key: 'poster_shift_y', label: 'Poster shift Y %', group: 'image', section: 'Poster', type: 'percent', min: -50, max: 50 },
  ...FADES,
  { key: 'vignette_strength', label: 'Vignette %', group: 'image', section: 'Effects', type: 'percent', min: 0, max: 100 },
  { key: 'grain_amount', label: 'Grain %', group: 'image', section: 'Effects', type: 'percent', min: 0, max: 60 },
  // Logo
  {
    key: 'logo_mode', label: 'Logo mode', group: 'logo', section: 'Logo', type: 'select', options: [
      { value: 'original', label: 'Keep original' },
      { value: 'match', label: 'Color match poster' },
      { value: 'hex', label: 'Custom hex' },
      { value: 'none', label: 'No logo' },
    ],
  },
  { key: 'logo_hex', label: 'Logo hex color', group: 'logo', section: 'Logo', type: 'color', showIf: v => v('logo_mode') === 'hex' },
  {
    key: 'logo_preference', label: 'Logo style', group: 'logo', section: 'Logo', type: 'select', showIf: hasLogo, options: [
      { value: 'first', label: 'First available' },
      { value: 'white', label: 'White logos' },
      { value: 'color', label: 'Colored logos' },
    ],
  },
  { key: 'uniform_logo_max_w', label: 'Width (px)', group: 'logo', section: 'Logo box', type: 'number', min: 50, max: 1800, showIf: hasLogo },
  { key: 'uniform_logo_max_h', label: 'Height (px)', group: 'logo', section: 'Logo box', type: 'number', min: 50, max: 2800, showIf: hasLogo },
  { key: 'uniform_logo_offset_x', label: 'X %', group: 'logo', section: 'Logo box', type: 'percent', min: 0, max: 100, showIf: hasLogo },
  { key: 'uniform_logo_offset_y', label: 'Y %', group: 'logo', section: 'Logo box', type: 'percent', min: 0, max: 100, showIf: hasLogo },
  { key: 'uniform_logo_h_align', label: 'Horizontal align', group: 'logo', section: 'Logo box', type: 'select', options: H_ALIGN, showIf: hasLogo },
  { key: 'uniform_logo_v_align', label: 'Vertical align', group: 'logo', section: 'Logo box', type: 'select', options: V_ALIGN, showIf: hasLogo },
  { key: 'uniform_logo_shadow_enabled', label: 'Drop shadow on', group: 'logo', section: 'Drop shadow', type: 'bool', showIf: hasLogo },
  { key: 'uniform_logo_shadow_opacity', label: 'Opacity', group: 'logo', section: 'Drop shadow', type: 'number', min: 0, max: 100, showIf: logoShadowOn },
  { key: 'uniform_logo_shadow_angle', label: 'Angle', group: 'logo', section: 'Drop shadow', type: 'number', min: -180, max: 180, showIf: logoShadowOn },
  { key: 'uniform_logo_shadow_distance', label: 'Distance', group: 'logo', section: 'Drop shadow', type: 'number', min: 0, max: 100, showIf: logoShadowOn },
  { key: 'uniform_logo_shadow_size', label: 'Size', group: 'logo', section: 'Drop shadow', type: 'number', min: 0, max: 250, showIf: logoShadowOn },
  { key: 'uniform_logo_shadow_color', label: 'Color', group: 'logo', section: 'Drop shadow', type: 'color', showIf: logoShadowOn },
  // Text
  ...TEXT_COMMON,
  { key: 'font_weight', label: 'Font weight', group: 'text', section: 'Text', type: 'select', options: FONT_WEIGHTS, showIf: textOn },
  { key: 'text_align', label: 'Text align', group: 'text', section: 'Text', type: 'select', options: H_ALIGN, showIf: textOn },
  { key: 'text_transform', label: 'Text case', group: 'text', section: 'Text', type: 'select', options: TEXT_TRANSFORMS, showIf: textOn },
  { key: 'letter_spacing', label: 'Letter spacing', group: 'text', section: 'Text', type: 'number', min: -5, max: 20, showIf: textOn },
  { key: 'line_height', label: 'Line height %', group: 'text', section: 'Text', type: 'percent', min: 80, max: 200, showIf: textOn },
  { key: 'text_box_max_w', label: 'Width (px)', group: 'text', section: 'Text box', type: 'number', min: 50, max: 1800, showIf: textOn },
  { key: 'text_box_max_h', label: 'Height (px)', group: 'text', section: 'Text box', type: 'number', min: 50, max: 2800, showIf: textOn },
  { key: 'text_box_offset_x', label: 'X %', group: 'text', section: 'Text box', type: 'percent', min: 0, max: 100, showIf: textOn },
  { key: 'text_box_offset_y', label: 'Y %', group: 'text', section: 'Text box', type: 'percent', min: 0, max: 100, showIf: textOn },
  { key: 'text_box_h_align', label: 'Horizontal align', group: 'text', section: 'Text box', type: 'select', options: H_ALIGN, showIf: textOn },
  { key: 'text_box_v_align', label: 'Vertical align', group: 'text', section: 'Text box', type: 'select', options: V_ALIGN, showIf: textOn },
  { key: 'shadow_enabled', label: 'Shadow on', group: 'text', section: 'Shadow', type: 'bool', showIf: textOn },
  { key: 'shadow_blur', label: 'Blur', group: 'text', section: 'Shadow', type: 'number', min: 0, max: 50, showIf: textShadowOn },
  { key: 'shadow_offset_x', label: 'Offset X', group: 'text', section: 'Shadow', type: 'number', min: -30, max: 30, showIf: textShadowOn },
  { key: 'shadow_offset_y', label: 'Offset Y', group: 'text', section: 'Shadow', type: 'number', min: -30, max: 30, showIf: textShadowOn },
  { key: 'shadow_opacity', label: 'Opacity %', group: 'text', section: 'Shadow', type: 'percent', min: 0, max: 100, showIf: textShadowOn },
  { key: 'shadow_color', label: 'Color', group: 'text', section: 'Shadow', type: 'color', showIf: textShadowOn },
  { key: 'stroke_enabled', label: 'Outline on', group: 'text', section: 'Outline', type: 'bool', showIf: textOn },
  { key: 'stroke_width', label: 'Width', group: 'text', section: 'Outline', type: 'number', min: 1, max: 20, showIf: outlineOn },
  { key: 'stroke_color', label: 'Color', group: 'text', section: 'Outline', type: 'color', showIf: outlineOn },
  // Extras
  ...BORDER,
  ...FALLBACK,
]

export const KOMETA_FIELDS: PresetField[] = [
  { key: 'kometa_base_color', label: 'Base color', group: 'image', section: 'Background', type: 'color' },
  { key: 'kometa_white_wash', label: 'White wash', group: 'image', section: 'Background', type: 'bool' },
  { key: 'kometa_texture_url', label: 'Texture URL', group: 'image', section: 'Background', type: 'text', help: 'Leave empty for a flat color' },
  ...FADES,
  { key: 'kometa_center_fade_strength', label: 'Center fade %', group: 'image', section: 'Effects', type: 'percent', min: 0, max: 100 },
  { key: 'grain_amount', label: 'Grain %', group: 'image', section: 'Effects', type: 'percent', min: 0, max: 60 },
  { key: 'kometa_logo_url', label: 'Logo URL', group: 'logo', section: 'Logo', type: 'text' },
  { key: 'kometa_logo_width', label: 'Logo width (px)', group: 'logo', section: 'Logo', type: 'number', min: 100, max: 2000 },
  { key: 'kometa_logo_offset_y', label: 'Logo offset Y (px)', group: 'logo', section: 'Logo', type: 'number', min: -1500, max: 1500 },
  ...TEXT_COMMON.map(f => (f.key === 'font_size' ? { ...f, min: 10, max: 500 } : f)),
  { key: 'position_y', label: 'Text position Y %', group: 'text', section: 'Text', type: 'percent', min: 0, max: 100, showIf: textOn },
  ...BORDER,
]

export function fieldsFor(templateId: string): PresetField[] {
  return templateId === 'kometa' ? KOMETA_FIELDS : UNIFORMLOGO_FIELDS
}

/** Whether a field is shown, given the values the form currently shows. */
export function isFieldVisible(field: PresetField, valueOf: ValueOf): boolean {
  return field.showIf ? field.showIf(valueOf) : true
}

/** Stored option value → what the form shows. */
export function toDisplay(field: PresetField, stored: unknown): unknown {
  if (field.type === 'percent') {
    const n = Number(stored)
    return stored == null || stored === '' || Number.isNaN(n) ? '' : Math.round(n * 1000) / 10
  }
  if (field.type === 'bool') return !!stored
  if (field.type === 'number') return stored == null ? '' : stored
  if ((stored == null || stored === '') && field.default !== undefined) return field.default
  return stored == null ? '' : String(stored)
}

/** What the form holds → stored option value. Empty numbers become null (not saved). */
export function fromDisplay(field: PresetField, shown: unknown): unknown {
  if (field.type === 'percent' || field.type === 'number') {
    if (shown === '' || shown == null) return null
    const n = Number(shown)
    if (Number.isNaN(n)) return null
    return field.type === 'percent' ? Math.round(n * 10) / 1000 : n
  }
  if (field.type === 'bool') return !!shown
  return shown == null ? '' : String(shown)
}

/**
 * Only the fields whose shown value changed since the form loaded, converted
 * for storage. Untouched fields are never sent, so a save can't write ''/false
 * over keys the preset doesn't have (the renderer would read those instead of
 * its defaults) or re-round an untouched percentage.
 */
export function changedFieldPayload(
  fields: PresetField[],
  loaded: Record<string, unknown>,
  current: Record<string, unknown>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const f of fields) {
    if (String(current[f.key] ?? '') === String(loaded[f.key] ?? '')) continue
    const v = fromDisplay(f, current[f.key])
    if (v !== null) out[f.key] = v
  }
  return out
}
