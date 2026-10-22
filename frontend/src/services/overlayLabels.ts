// Display names for overlay layers (elements), shared by the layer list, the
// badge sets panel and the rules editor.
import { describeCondition } from '@/services/overlayFields'
import type { OverlayCondition } from '@/services/overlayEngine'

export interface LabelledElement {
  name?: string
  type?: string
  text?: string
  metadata_field?: string
}

export const ELEMENT_TYPE_LABELS: Record<string, string> = {
  video_badge: 'Video badge',
  audio_badge: 'Audio badge',
  edition_badge: 'Edition badge',
  streaming_platform_badge: 'Streaming badge',
  studio_badge: 'Studio badge',
  custom_image: 'Image',
  full_cover_image: 'Full-poster image',
  text_label: 'Text',
  blur: 'Blur',
  resolution_badge: 'Resolution badge',
  codec_badge: 'Codec badge',
  label_badge: 'Label badge',
}

/** What to call an element: its name, else something descriptive. */
export const elementLabel = (el: LabelledElement, index?: number): string => {
  if (el.name) return el.name
  const type = ELEMENT_TYPE_LABELS[String(el.type)] || String(el.type || 'Element')
  if (el.text) return `${type} "${String(el.text).slice(0, 24)}"`
  if (el.metadata_field) return `${type} (${String(el.metadata_field).replace(/_/g, ' ')})`
  return index !== undefined ? `${type} #${index + 1}` : type
}

/** A name not already used by another element. */
export const uniqueElementName = (elements: LabelledElement[], base: string): string => {
  const taken = new Set(elements.map(e => e.name).filter(Boolean))
  let name = base
  let n = 2
  while (taken.has(name)) name = `${base} ${n++}`
  return name
}

export interface DescribedElement extends LabelledElement {
  conditions?: OverlayCondition[]
  group?: string
  placement?: string
  horizontal_align?: string
  vertical_align?: string
  position_x?: number
  position_y?: number
}

const FIELD_NOUNS: Record<string, string> = {
  video_resolution: 'Resolution badge',
  video_codec: 'Video codec badge',
  audio_codec: 'Audio codec badge',
  audio_channels: 'Audio channels badge',
  audio_language: 'Audio language badge',
}

/** "Resolution badge", 'Text "4K"', "Image": what the layer is, in plain words. */
export const elementNoun = (el: LabelledElement): string => {
  if (el.metadata_field && FIELD_NOUNS[el.metadata_field]) return FIELD_NOUNS[el.metadata_field]!
  const type = ELEMENT_TYPE_LABELS[String(el.type)] || String(el.type || 'Layer')
  if ((el as { box_only?: boolean }).box_only) return 'Background box'
  if (el.type === 'text_label' && el.text) return `Text "${String(el.text).slice(0, 24)}"`
  return type
}

/** "top-left", "bottom", "center", "whole poster". */
export const elementPlace = (el: DescribedElement): string => {
  if (el.type === 'full_cover_image' || el.type === 'blur') return 'whole poster'
  if ((el as { queue?: string }).queue) return `queue "${(el as { queue?: string }).queue}"`
  let v: string
  let h: string
  if (el.placement === 'kometa') {
    v = String(el.vertical_align || 'top').toLowerCase()
    h = String(el.horizontal_align || 'left').toLowerCase()
  } else {
    const x = Number(el.position_x ?? 0.5)
    const y = Number(el.position_y ?? 0.5)
    h = x < 0.34 ? 'left' : x > 0.66 ? 'right' : 'center'
    v = y < 0.34 ? 'top' : y > 0.66 ? 'bottom' : 'center'
  }
  if (v === 'center' && h === 'center') return 'center'
  if (v === 'center') return `${h} side`
  if (h === 'center') return v
  return `${v}-${h}`
}

/** "always", "when Resolution is 4K", "when 3 conditions match". */
export const elementWhen = (el: DescribedElement): string => {
  const c = el.conditions || []
  if (!c.length) return 'always'
  if (c.length === 1) return `when ${describeCondition(c[0]!)}`
  return `when ${c.length} conditions match`
}
