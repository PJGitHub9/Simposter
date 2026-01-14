# Webhook Integration Guide

Simposter supports automatic poster generation via webhooks from Radarr, Sonarr, and Tautulli. This allows you to automatically create and apply custom posters when new media is added to your Plex library.

## Configuration

### 1. Enable Automatic Poster Generation

In the Simposter web UI:
1. Navigate to **Settings** → **Performance** tab
2. Scroll to **Automatic Poster Generation** section
3. Configure your preferences:
   - **Automatically Send to Plex**: When enabled, generated posters are automatically uploaded to Plex
   - **Default Labels for Webhook Posters**: Comma-separated labels to apply (e.g., `Overlay, Auto-Generated`)

### 2. Get Your Webhook URLs

The webhook URL format varies by integration:

#### Radarr (Movies)
```
http://YOUR_SERVER:5000/webhook/radarr/{template_id}/{preset_id}
```

#### Sonarr (TV Shows)
```
http://YOUR_SERVER:5000/webhook/sonarr/{template_id}/{preset_id}?include_seasons=true
```

#### Tautulli (Plex Events)
```
http://YOUR_SERVER:5000/webhook/tautulli?template_id={template_id}&preset_id={preset_id}&event_types=added,watched
```

**URL Parameters:**
- `{template_id}`: The template to use for poster generation (e.g., `universal`, `aura`)
- `{preset_id}`: The preset configuration to apply (e.g., `default`, `minimalist`)
- `include_seasons` (Sonarr only): Set to `true` to generate posters for all seasons, `false` for series poster only
- `event_types` (Tautulli only): Comma-separated events to process: `added`, `watched`, `updated`

---

## Radarr Setup

1. Open Radarr web interface
2. Go to **Settings** → **Connect**
3. Click the **+** button to add a new connection
4. Select **Webhook**
5. Configure:
   - **Name**: Simposter Poster Generator
   - **On Download**: ✅ Enabled
   - **On Import**: ✅ Enabled
   - **On Upgrade**: ✅ Enabled (optional)
   - **URL**: `http://YOUR_SERVER:5000/webhook/radarr/universal/default`
   - **Method**: POST
6. Click **Test** to verify connection
7. Click **Save**

---

## Sonarr Setup

1. Open Sonarr web interface
2. Go to **Settings** → **Connect**
3. Click the **+** button to add a new connection
4. Select **Webhook**
5. Configure:
   - **Name**: Simposter Poster Generator
   - **On Download**: ✅ Enabled
   - **On Import**: ✅ Enabled
   - **On Upgrade**: ✅ Enabled (optional)
   - **On Series Add**: ✅ Enabled (optional)
   - **URL**: `http://YOUR_SERVER:5000/webhook/sonarr/universal/default?include_seasons=true`
   - **Method**: POST
6. Click **Test** to verify connection
7. Click **Save**

**Note:** Set `include_seasons=true` to automatically generate posters for all seasons when a new episode is imported.

---

## Tautulli Setup

1. Open Tautulli web interface
2. Go to **Settings** → **Notification Agents**
3. Click **Add a new notification agent**
4. Select **Webhook**
5. Configure the **Configuration** tab:
   - **Webhook URL**: `http://YOUR_SERVER:5000/webhook/tautulli?template_id=universal&preset_id=default&event_types=added`
   - **Webhook Method**: POST
6. Configure the **Triggers** tab:
   - ✅ **Recently Added** (for new media)
   - ✅ **Watched** (optional, for regenerating after first watch)
7. Configure the **Data** tab - use the following JSON body:
```json
{
  "event": "{action}",
  "media_type": "{media_type}",
  "title": "{title}",
  "year": "{year}",
  "tmdb_id": "{tmdb_id}",
  "tvdb_id": "{tvdb_id}",
  "season": "{season_num}",
  "episode": "{episode_num}"
}
```
8. Click **Save**

---

## Advanced Configuration

### Custom Templates and Presets

You can specify different templates and presets per integration:

**Example 1: Use different templates for movies vs TV shows**
- Radarr: `http://YOUR_SERVER:5000/webhook/radarr/aura/cinematic`
- Sonarr: `http://YOUR_SERVER:5000/webhook/sonarr/universal/default`

**Example 2: Different presets for 4K vs 1080p libraries**
- Library 1 (1080p): `http://YOUR_SERVER:5000/webhook/radarr/universal/default`
- Library 2 (4K): `http://YOUR_SERVER:5000/webhook/radarr/universal/4k-enhanced`

### Event Filtering

**Sonarr Season Control:**
- `include_seasons=true`: Generates posters for ALL seasons when an episode imports
- `include_seasons=false`: Only generates the series poster

**Tautulli Event Types:**
- `event_types=added`: Only process newly added media
- `event_types=watched`: Only process media after first watch
- `event_types=added,watched`: Process both events

---

## Troubleshooting

### Webhook Not Triggering

1. **Check webhook URL**: Ensure `YOUR_SERVER` is replaced with your actual server IP/hostname
2. **Test endpoint**: Visit `http://YOUR_SERVER:5000/webhook/test` to verify webhooks are active
3. **Check logs**: View Simposter backend logs for webhook errors
4. **Verify network access**: Ensure Radarr/Sonarr/Tautulli can reach Simposter's port 5000

### Posters Not Auto-Sending to Plex

1. Navigate to **Settings** → **Performance** → **Automatic Poster Generation**
2. Ensure **Automatically Send to Plex** is enabled
3. Verify Plex credentials are configured in **Settings** → **General** → **Plex Connection**

### Wrong Template/Preset Applied

1. Verify the `template_id` and `preset_id` in your webhook URL match existing templates
2. Check **Settings** → **Templates** to see available templates
3. Test poster generation manually first to ensure template works

---

## Example Webhook URLs

```
# Basic movie poster generation
http://localhost:5000/webhook/radarr/universal/default

# TV show with all seasons
http://localhost:5000/webhook/sonarr/aura/default?include_seasons=true

# Tautulli for added media only
http://localhost:5000/webhook/tautulli?template_id=universal&preset_id=default&event_types=added

# Multiple event types in Tautulli
http://localhost:5000/webhook/tautulli?template_id=aura&preset_id=enhanced&event_types=added,watched,updated
```

---

## Notes

- Webhooks run asynchronously - posters may take a few seconds to generate
- Large TV shows with many seasons may take longer to process
- Labels configured in "Default Labels for Webhook Posters" are applied to all webhook-generated posters
- Manual poster generation via the web UI is not affected by webhook settings
