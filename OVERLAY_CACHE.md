# Overlay Caching System (v1.4.6)

## Overview

The overlay caching system pre-generates template effects (matte, fade, vignette, grain, wash) as PNG files when saving presets. During batch rendering, these cached overlays are composited over posters instead of rendering effects from scratch, significantly improving performance.

## Architecture

### Components

1. **Backend Schema** (`backend/schemas.py`)
   - Added `useOverlayCache: bool = True` to `PerformanceSettings`
   - Default enabled for immediate performance benefits

2. **Overlay Generation** (`backend/rendering.py`)
   - New `generate_overlay()` function extracts effects pipeline from `build_base_poster()`
   - Creates RGBA image with transparent background + effects only
   - Effects rendered:
     - Matte (bottom darkening)
     - Fade (gradient transition)
     - Vignette (radial edge darkening)
     - Grain (film texture)
     - Wash (cinematic grey tone)

3. **Preset Save Hook** (`backend/api/presets.py`)
   - `/api/presets/save` endpoint generates overlay after saving preset
   - Saves to `config/overlays/{template_id}/{preset_id}.png`
   - Non-fatal: continues if overlay generation fails

4. **Batch Rendering** (`backend/api/batch.py`)
   - New `_render_with_overlay_cache()` function
   - Checks if setting enabled and overlay file exists
   - Fast path: Download poster → resize/zoom → composite cached overlay → add logo
   - Fallback: Standard `render_poster_image()` if cache miss or disabled
   - **uniformlogo template**: Full support for logo positioning, text overlay, and borders in cache path
   - **Other templates**: Falls back to full render for logo positioning

5. **Frontend Toggle** (`frontend/src/views/SettingsView.vue`)
   - Checkbox in Performance section: "Use Overlay Cache"
   - Persisted in UI settings database
   - Change detection and snapshot tracking included

## File Structure

```
config/
  overlays/
    uniformlogo/
      cinematic.png
      modern.png
    universal/
      dramatic.png
```

## Usage Flow

### 1. Save Preset
```
User edits preset → Clicks Save
  ↓
Backend saves options to database
  ↓
generate_overlay(options) creates PNG
  ↓
Save to config/overlays/{template_id}/{preset_id}.png
```

### 2. Batch Render (Cache Hit)
```
Batch operation starts
  ↓
Check useOverlayCache setting (DB)
  ↓
Check overlay file exists
  ↓
Download poster → Resize → Composite overlay → Done
```

### 3. Batch Render (Cache Miss)
```
Batch operation starts
  ↓
No overlay found or setting disabled
  ↓
Standard render_poster_image() path
```

## Performance Benefits

### Before Overlay Caching
- Each poster renders all effects individually
- 50 movies × (matte + fade + vignette + grain) = 200+ effect operations
- Total time: ~5-10 seconds per poster

### After Overlay Caching
- Overlay generated once per preset
- Batch renders composite pre-generated overlay
- Logo positioning added in fast path (uniformlogo)
- Total time: ~1-2 seconds per poster
- **Expected speedup: 3-5x for uniformlogo templates with or without logos**

### uniformlogo Template
- Full cache support: effects cached, logo positioned on top
- Includes text overlay and border rendering
- Most expensive operations (vignette, grain) skipped

### Other Templates
- Falls back to full render when logo present
- Logo positioning logic template-specific
- Future enhancement: Add cache support per template

## Limitations & Future Work

### Current Limitations
1. **Template Support**: Full cache support for uniformlogo template
   - Other templates fall back to full render when logo present
   - universal template and custom templates need logo positioning implementation

2. **Cache Invalidation**: No automatic invalidation when preset modified
   - Overlay regenerated on every save (safe but potentially wasteful)

3. **Logo Source Detection**: Cache path supports all logo modes (stock/match/hex/none)

### Future Enhancements
1. **Universal Template Support**: Add logo positioning for universal template in cache path
2. **Custom Template Support**: Provide template API for cache-aware logo positioning
3. **Cache Versioning**: Add hash/version checking to avoid stale overlays
4. **Progressive Enhancement**: Generate overlays asynchronously in background
5. **Cache Management UI**: View/clear/regenerate cached overlays

## Testing

### Validation Steps
1. **Save Preset**
   ```
   - Navigate to editor
   - Modify matte/fade/vignette/grain settings
   - Save preset
   - Verify: config/overlays/{template_id}/{preset_id}.png exists
   - Check: File size > 0, valid PNG format
   ```

2. **Batch Render (Cache Enabled)**
   ```
   - Enable "Use Overlay Cache" in Settings
   - Select movies without logos (or logo mode = none)
   - Start batch render
   - Check logs: "[BATCH] Using cached overlay: ..."
   - Verify: Posters match manual preview (visual accuracy)
   - Measure: Render time improvement
   ```

3. **Batch Render (Cache Disabled)**
   ```
   - Disable "Use Overlay Cache" in Settings
   - Batch render same movies
   - Verify: Falls back to standard rendering
   - Confirm: Visual output identical
   ```

4. **Logo Support (uniformlogo)**
   ```
   - Select movies with logos
   - Use uniformlogo template
   - Batch render with cache enabled
   - Check logs: "Applied uniformlogo positioning with cached overlay"
   - Verify: Logos positioned correctly
   - Confirm: Text overlays and borders render properly
   ```

## Configuration

### Enable/Disable
```json
{
  "performance": {
    "useOverlayCache": true
  }
}
```

### Verify Setting
```bash
# Check database
sqlite3 config/settings/simposter.db "SELECT value FROM ui_settings WHERE key='performance'"

# Should contain: "useOverlayCache": true
```

### Clear Cache
```bash
# Remove all overlays
rm -rf config/overlays/

# Remove specific template
rm -rf config/overlays/uniformlogo/

# Remove specific preset
rm config/overlays/uniformlogo/cinematic.png
```

## Troubleshooting

### Overlay Not Generated
- **Check logs**: Look for `[PRESETS] Generated overlay cache` or errors
- **Permissions**: Ensure write access to `config/overlays/`
- **Options**: Verify preset has effect options (matte/fade/vignette/grain)

### Visual Differences
- **Non-uniformlogo templates**: Falls back to full render with logos
- **Template mismatch**: Overlay generated for different template
- **Stale cache**: Delete overlay file and resave preset

### Performance No Better
- **Non-uniformlogo templates**: May fall back to full render with logos
- **Cache disabled**: Check Settings → Performance → Use Overlay Cache
- **File I/O**: SSD vs HDD affects composite speed
- **Small batches**: Overhead only amortized over large batches (10+ movies)

## Technical Details

### Overlay Generation Algorithm
```python
1. Create transparent RGBA canvas (2000×3000)
2. Apply matte gradient (bottom → top fade to black)
3. Apply fade transition (smooth gradient above matte)
4. Render vignette (radial darkening from edges)
5. Generate film grain texture (randomized noise)
6. Apply wash effect (neutral grey overlay)
7. Save as PNG with alpha channel
```

### Fast Composite Algorithm (uniformlogo)
```python
1. Download poster from TMDb/Fanart
2. Resize poster to canvas size (2000×3000)
3. Apply zoom/shift transformations
4. Load cached overlay PNG
5. Alpha composite overlay over poster
6. Download and process logo (apply color mode)
7. Calculate logo bounding box (max width/height)
8. Scale logo to fit, center in bounding box
9. Composite logo onto canvas
10. Add text overlay if enabled
11. Add border if enabled
12. Return final image
```

### Why PNG Format?
- **Alpha channel**: Required for transparent effects
- **Lossless**: No quality degradation from caching
- **Fast decode**: PIL efficiently loads PNG
- **File size**: ~500KB - 2MB per overlay (acceptable)

## Dependencies

- **PIL/Pillow**: Image compositing and alpha blending
- **NumPy**: Grain texture generation
- **SQLite**: Settings persistence
- **FastAPI**: Endpoint handling

## References

- Template rendering: `backend/templates/universal.py`
- Effect functions: `_add_vignette()`, `_add_grain()`, `build_base_poster()`
- Settings schema: `backend/schemas.py`
- Frontend UI: `frontend/src/views/SettingsView.vue`
