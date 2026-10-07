// One Discord/Apprise notification for a whole editor send (poster and/or logo,
// to one or more servers). The editors send each upload with notify:false, then
// call this once with every server that succeeded, so a "Send to Plex +
// Jellyfin with logo" click produces one notification, not four.
import { getApiBase } from './apiBase'

const apiBase = getApiBase()

export interface SendSummary {
  ratingKey: string
  serverIds: string[]
  assets: string[]
  templateId?: string
  presetId?: string
  libraryId?: string | number | null
  title?: string
  year?: number | string | null
  imageData?: string | null
}

export async function notifySendSummary(summary: SendSummary): Promise<void> {
  if (!summary.serverIds.length || !summary.assets.length) return
  try {
    await fetch(`${apiBase}/api/media-server/notify-send`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        rating_key: summary.ratingKey,
        server_ids: summary.serverIds,
        assets: summary.assets,
        template_id: summary.templateId || '',
        preset_id: summary.presetId || '',
        library_id: summary.libraryId != null ? String(summary.libraryId) : null,
        title: summary.title || null,
        year: Number(summary.year) || null,
        image_data: summary.imageData || null,
      }),
    })
  } catch {
    /* notifications are best-effort */
  }
}
