# Media Servers: Plex, Jellyfin & Emby

Simposter works with **Plex, Jellyfin and Emby**, in any combination: Plex only, Jellyfin only, or several servers at once (including two of the same kind). This guide covers connecting servers, linking their libraries together, and the features built on top of that.

> Emby uses the same API as Jellyfin and is supported the same way, but it has had far less real-world testing. Please report anything that doesn't work.

---

## Connecting servers

**Settings → Media Servers** has a section for each server type. Click **+ Add a … Server**, enter its URL and credentials, and use **Test Connection** before saving:

- **Plex**: the server URL and an X-Plex-Token.
- **Jellyfin / Emby**: the server URL and an API key (in Jellyfin: Dashboard → API Keys).

Give each server a **name** (e.g. "Jellyfin-main"). The name appears throughout the app, which matters once you have more than one server of the same type.

Plex is optional. If you use only Jellyfin or Emby, skip Plex in the setup wizard (or remove it later) and everything works from your Jellyfin/Emby libraries.

The setup wizard asks which servers you use up front (any combination) and connects them all on one page.

---

## Library groups

A **library group** says "these libraries hold the same content". For example, Plex "Movies" plus Jellyfin "Movies", or Plex "4K Movies" plus Jellyfin "4k-Movies". Manage them in **Settings → Libraries**: each card is one group, with a row for each server type. Pick a library from a row's dropdown to add it, and use ✕ to remove it. Changes are kept when you click **Save Changes**.

A group can contain any mix of servers, including just a single Jellyfin library. Each group appears as its own entry in the sidebar.

Each group also holds its **automatic poster generation** settings (on/off, plus the template and preset to use).

### Merged browsing

When the same title exists on more than one server in a group (matched by TMDb/TVDB ID), it shows as **one card** in Movies, TV Shows, Logos, Backdrops and Batch Edit. Small icons on the card show which servers have it.

- **Show posters from** (top of the grid): picks which server's poster is shown for those merged cards.
- **Merge items** (on the group's card in Settings → Libraries): turn it off to show each server's copy as its own card. "Show posters from" then becomes a filter ("All", or one server).

### Sending to more than one server

When an item exists on several servers, sending opens a picker where you choose which servers get the poster or logo, or all of them. This applies in the manual editor, the grid's resend button and Batch Edit. Simposter finds the item's copy on each server for you.

---

## Scans and automatic posters

- **Scan** on a group (Settings → Libraries), **Scan All Libraries**, and **Scheduled Scans** cover every server in your groups, including collections. To limit the schedule, tick specific groups — each is scanned on every server it includes.
- With **automatic poster generation** turned on for a group, posters are generated for new items a scan finds, on Jellyfin/Emby as well as Plex. A library's very first scan is treated as importing what's already there, not as new arrivals, so linking an existing library doesn't re-render everything.
- If an item exists on both Plex and Jellyfin, it's generated once (from the Plex side) and then sent to the other servers.

Webhooks (Radarr/Sonarr) can target a whole library group. See [WEBHOOKS.md](WEBHOOKS.md#library-groups).

---

## Media Mirror

**Media Mirror** copies artwork from one server to the others in a group, so they stay in sync. Open it from the group's sidebar menu (🪞 Media Mirror). It only appears once the group has more than one server.

- Choose the **source** server, the **target** servers, and which artwork to copy: posters, logos, backdrops and/or square art (square art is Plex-only).
- **Also mirror Collections** copies collection artwork too, with its own artwork choices.
- The mapping tables show which item on each target server matches each source item, with search and pages, and tabs for Movies/TV and Collections. Use the per-row **Send** button to copy a single item.
- **Run Now** for a one-off copy, or turn on the **schedule**. Only images that changed since the last run are copied again. Tick **Re-copy everything** to force a full copy, e.g. after artwork was changed directly on a target server.

---

## Collections across servers

Collections are matched across servers **by name**, ignoring a trailing "Collection" (Plex "Marvel Cinematic Universe" = Jellyfin "Marvel Cinematic Universe Collection"). When names don't line up, open **Collection matching** on the Collections page:

- Pick the matching collection on each server to link collections with different names (e.g. Plex "MCU" and Jellyfin "Marvel Films").
- Choose **— none —** to split a wrong automatic match.
- **Reset** returns a row to automatic, name-based matching.

Changes save immediately and apply everywhere collections are matched: the merged Collections grid, the send picker and Media Mirror.

---

## Server maintenance

**Settings → Cleanup → Media Server Maintenance** has a section for each server:

- **Plex**: Empty Trash, Clean Bundles, Optimize Database.
- **Jellyfin / Emby**: the server's own cleanup tasks, namely Optimize database and Clean Cache/Transcode/Log Directory, plus Clean Activity Log. Each shows when it last ran and the result, and shows progress while running.

---

## Removing a server

Remove a server in **Settings → Media Servers**. When you save:

- its libraries are removed from every library group, and
- Simposter deletes everything it had cached for that server (posters, logos, backdrops, scan data, retry-queue entries).

History and your saved poster files are kept. If you remove Plex, Simposter stops using any `PLEX_URL`/`PLEX_TOKEN` environment variables, so it doesn't reconnect on the next restart. Adding Plex back re-enables them.

---

## Plex-only features

Jellyfin and Emby have no equivalent for these:

- **Square art**: it's a Plex artwork type.
- **Labels**: "Default Labels to Remove", "Label to Add After Sending", Kometa compatibility and webhook ignore labels only apply to Plex items.
