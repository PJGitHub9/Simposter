# Settings Refactor Plan - v2.0.0

## Overview
Refactor SettingsView.vue (3000 lines) into tabbed interface with separate component files.

## Tab Structure

### 1. General Tab (`GeneralTab.vue`) ✅ CREATED
**Content:**
- Theme selector (neon/dark/light)
- Poster grid density slider

**Props:** theme, posterDensity, unsavedChanges
**Emits:** update:theme, update:posterDensity, save

---

### 2. Libraries Tab (`LibrariesTab.vue`) ✅ UPDATED (v1.5.0)
**Content:**
- Plex Connection section
  - Plex URL
  - Plex Token
  - Test Connection button
- Movie Libraries section
  - Library mappings (displayName, remove labels)
  - **Per-library auto-generation settings (v1.5.0)**:
    - Enable/disable checkbox
    - Template/preset dropdown (combined format)
  - Add/remove movie libraries
- TV Show Libraries section
  - Library mappings (displayName, remove labels)
  - **Per-library auto-generation settings (v1.5.0)**:
    - Enable/disable checkbox
    - Template/preset dropdown (combined format)
  - Add/remove TV libraries
- Library Scanning section
  - Scan All Libraries button
  - Scheduled Scan settings (cron, library selection)
  - Next run time display

**Props:** plex config, library mappings, scheduler config, available presets, loading states
**Emits:** test-connection, save-plex, add-library, remove-library, scan-library, update-scheduler, update-auto-gen

---

### 3. Integrations Tab
Removed (Radarr/Sonarr/Tautulli integrations deprecated).

---

### 4. Save Locations Tab (`SaveLocationsTab.vue`)
**Content:**
- Movie Save Location
  - Input field with variables: {library}, {title}, {year}, {key}
- TV Show Save Location
  - Input field with variables: {library}, {title}, {year}, {key}, {season}
- Save Batch in Subfolder toggle

**Props:** movieSaveLocation, tvShowSaveLocation, saveBatchInSubfolder, unsavedChanges
**Emits:** update:movieSaveLocation, update:tvShowSaveLocation, update:saveBatchInSubfolder, save

---

### 5. Performance Tab (`PerformanceTab.vue`)
**Content:**
- Rendering Performance section
  - Use Overlay Cache toggle
  - Concurrent Rendering input (number)
  - JPEG Quality slider (if used)
- Cache Management section
  - Clear Frontend Cache button
  - Clear Backend Cache button
  - Cache statistics display

**Props:** performance settings, cache stats, loading states
**Emits:** update performance settings, clear-cache, save

---

### 6. Advanced Tab (`AdvancedTab.vue`)
**Content:**
- Preset Management section
  - Export Presets button
  - Import Presets modal/textarea
- API Configuration section
  - Rate limiting settings (if exposed)
  - Debug mode toggle
- Logs Configuration section
  - Log level dropdown
  - Max log size
  - Max backups

**Props:** logs config, preset export/import states
**Emits:** export-presets, import-presets, update-logs, save

---

## Implementation Steps

### Phase 1: Create Tab Components ✅ COMPLETE
- [x] GeneralTab.vue ✅
- [x] LibrariesTab.vue ✅
- [x] SaveLocationsTab.vue ✅
- [x] PerformanceTab.vue ✅
- [x] AdvancedTab.vue ✅

### Phase 2: Create Tabbed SettingsView Shell ✅ COMPLETE
- [x] Create tab navigation UI (horizontal tabs) ✅
- [x] Set up tab switching logic (active tab state) ✅
- [x] Import all tab components ✅
- [x] Pass props and handle emits ✅
- [x] Preserve unsaved changes warning across tabs ✅
- [x] Add URL routing for tabs (e.g., /settings?tab=advanced) ✅

### Phase 3: Enhancements & Improvements ✅ COMPLETE
- [x] All content extracted to appropriate tabs ✅
- [x] Added theme selector with all 6 themes ✅
- [x] Multi-select library scheduler (checkbox based) ✅
- [x] Individual scan buttons per library ✅
- [x] Replaced preset import/export with DB backup/restore ✅
- [x] URL routing for tab state persistence ✅

### Phase 4: Testing
- [ ] Test tab switching
- [ ] Test unsaved changes detection
- [ ] Test all save operations
- [ ] Test connection tests
- [ ] Test library scanning
- [ ] Test preset import/export
- [ ] Test cache clearing

### Phase 5: Cleanup
- [ ] Remove old SettingsView.vue sections
- [ ] Update routing (if needed)
- [ ] Update documentation
- [ ] Test in Docker

---

## Data Flow

```
SettingsView (Parent)
  ├─ Loads all settings from API
  ├─ Tracks unsaved changes
  ├─ Handles all save operations
  └─ Passes data to tabs via props
      ├─ GeneralTab (theme, posterDensity)
      ├─ LibrariesTab (plex, mappings, scheduler)
      ├─ SaveLocationsTab (save locations)
      ├─ PerformanceTab (performance settings, cache)
      └─ AdvancedTab (presets, logs)

Tabs emit events:
  - update:* events for two-way binding
  - save event for persisting changes
  - action events (test-connection, scan-library, clear-cache, etc.)
```

---

## Notes

- Keep all API calls in parent SettingsView
- Tabs are presentational components
- Use v-model for simple fields
- Use events for actions (buttons)
- Preserve existing functionality exactly
- Tab state persisted in URL query param (optional enhancement)
