# Changelog

## v1.4.1
- Added visible version badge (top nav and Settings) and centralized version constant.
- Fixed presets: text overlay state and fields now reset/apply correctly; reload pulls fresh values.
- Preview/batch rendering now merges preset options with live slider values so UI tweaks reflect in renders.
- Batch mode improvements: preview caching when cycling movies; status overlay while batch runs; saves honor `saveLocation` and optional batch subfolder.
- Save-to-disk fixes: paths mapped under `/config/output`, template filename respected, frontend shows saved path.
- Settings: new “save batch runs into subfolder” toggle; scan library overlay shows progress/items.
