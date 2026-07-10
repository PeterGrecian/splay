# splay state protocol

splay exposes — and, for one of the files, *accepts* — its live state through
three JSON files. This lets anything (a script, a web control page, another
process, an AI assistant) **read what splay has loaded** and **drive the
visualisation** without splay needing a bespoke API. The files are deliberately
plain JSON in a predictable place so they are trivially debuggable with `cat`
and `jq`.

The protocol is transport-agnostic by design: see [Multi-device](#multi-device).

## The three files

By default they live in `$HOME`; override the directory with `$SPLAY_STATE_DIR`.

| File | Direction | Cadence | Purpose |
|---|---|---|---|
| `~/.splay-state.json` | **bidirectional** | write-on-change; read-every-frame (mtime-gated) | The settings. Write it to **drive** the view. |
| `~/.splay-loaded.json` | renderer → reader | write-on-load/reload | The loaded path list — "what's loaded". |
| `~/.splay-frame.json` | renderer → reader | write-often (coalesced ≤ `FRAME_WRITE_HZ`, default 10 Hz) | The cursor (current frame, play state). |

The split is intentional: the cursor changes on every arrow-step and every
autoplay tick, so it lives in its own high-churn file and is rate-limited, while
the settings file only rewrites on a genuine change.

All writes are **atomic** (write to a temp file, then `os.replace`), so a reader
never observes a half-written file.

## `~/.splay-state.json` (settings — read/write)

Every key splay publishes, plus two protocol fields:

```json
{
  "version": 14,
  "writer": "renderer",
  "sort_mode": "name",            // "name" | "mtime" | "added"
  "list_mode": true,              // false = selected-only
  "show_strip": true,
  "show_hud": false,
  "show_regions": true,
  "fullscreen": false,
  "zoom_mode": "fit",             // "fit" | "1x" | "2x"
  "hot_pixel_mask_on": false,
  "hot_pixel_highlight": false,
  "hot_pixel_mask_idx": 0,
  "stretch_lo_pct": 0.5,
  "stretch_hi_pct": 99.5,
  "auto_reload": false,
  "selected": []                  // list of absolute path strings
}
```

When an app/plugin is loaded, the state also carries `"app"`, `"view"`
(`input`/`wipe`/`output`/`mask`) and `"params"` (the plugin's parameter dict).

### `version` and `writer` — the reconciliation rule

splay reads `state` every frame (mtime-gated, so it's near-free when the file is
unchanged). To apply your changes and to keep your write from racing splay's own
writes, two fields coordinate ownership:

- **`writer`** — who last wrote the file. splay writes `"renderer"`. A
  controller MUST write something else, e.g. `"controller"`. splay **ignores any
  file whose `writer` is `"renderer"`** (that's its own write).
- **`version`** — a monotonically increasing integer. splay bumps it on every
  change it makes. **A controller must write `version` strictly greater than the
  current value** — so a controller reads the file first, then writes
  `version + 1` (or higher) with `writer: "controller"`.

What splay does on read:

1. `writer == "renderer"` → ignore (our own write).
2. `version <= current` → **stale / out-of-order → reject**, and splay
   immediately re-publishes its authoritative state with `writer:"renderer"` and
   a bumped version. (This self-heals: a stale file can't linger and contaminate
   a later accepted write with its leftover field values.)
3. otherwise → adopt `version`, apply the settings present, then re-publish the
   reconciled state as `writer:"renderer"`.

So after any accepted controller write, the file converges back to
`writer:"renderer"` with `version` one higher than you wrote — that's your
acknowledgement that splay applied it.

### Driving splay — worked example

```python
import json, pathlib
p = pathlib.Path.home() / ".splay-state.json"
s = json.load(open(p))                       # 1. read current
s["version"] += 1                            # 2. bump version
s["writer"]   = "controller"                 #    claim the write
s["show_hud"] = True                         # 3. set what you want
s["idx"]      = 3                             #    (idx is accepted here too — see below)
json.dump(s, open(p, "w"), indent=1, sort_keys=True)  # 4. atomic-ish write
# Within ~1 frame splay applies it and rewrites the file as writer:"renderer".
```

### Accepted control keys beyond the published settings

- **`idx`** — if present, splay navigates to that frame index (clamped to the
  current scope). It is *accepted* on write but not itself a stored setting; the
  resulting cursor shows up in `~/.splay-frame.json`.

### Which settings apply, and guards

Only keys **present** in your write are applied; everything else is left alone.
Some settings are guarded and will silently no-op if the precondition isn't met:

- `hot_pixel_mask_on` / `hot_pixel_highlight` only take effect when a hot-pixel
  mask is actually configured/loaded. Writing `true` with no mask present is a
  no-op (splay reflects back `false`).
- `sort_mode` must be one of `name`/`mtime`/`added`; `zoom_mode` one of
  `fit`/`1x`/`2x`. Out-of-range values are ignored.
- Stretch and mask changes trigger a FITS re-render.

## `~/.splay-loaded.json` (what's loaded — read-only)

```json
{
  "count": 5,
  "cwd": "/abs/launch/dir",       // working dir splay was launched from
  "paths": ["/abs/path/0001.fits.fz", "..."],
  "source_dirs": ["/abs/dir"],   // dirs splay is watching (for reload)
  "version": 14,
  "writer": "renderer"
}
```

`paths`/`source_dirs` are always absolute (resolved at launch), so the loaded
set is reproducible without knowing the cwd; `cwd` is recorded anyway so a
reader can relaunch splay from the same place the user did.

Written whenever the loaded set changes (initial load, reload, IPC `open`,
`clear`, `Del`). To *add* frames, don't write this file — use the existing IPC
channel (`splay --send` / the socket `open` command); see
`design/splay-and-player-conventions.md` and the IPC notes.

## `~/.splay-frame.json` (cursor — read-only, high-churn)

```json
{
  "idx": 3,
  "current": "/abs/path/0004.fits.fz",
  "count": 5,
  "playing": false,
  "play_dir": 1,
  "play_fps": 60,
  "version": 14,
  "writer": "renderer"
}
```

Coalesced to at most `FRAME_WRITE_HZ` (10 Hz) so a remote backend isn't hammered
on every autoplay tick. The last cursor position after movement settles is
always flushed. To move the cursor, set `idx` in `~/.splay-state.json` (above) or
inject a navigation key over IPC — don't write this file.

## Multi-device / remote control plane

The three files are only *one backing store* for a transport-agnostic state
protocol. In the code this sits behind a `StateStore` seam
(`read_state`/`write_state`/`write_loaded`/`write_frame`); the frame loop never
touches paths directly. That makes the backing store swappable without changing
splay's logic:

- **Local files** (default) — same device, page-cache resident, mtime-gated.
- **Shared directory** (`$SPLAY_STATE_DIR` → an NFS / syncthing path) — a control
  display and a view display on **different devices** share state. The `version`
  field is what makes this safe: across devices mtime ordering is unreliable
  (clock skew, sync lag), so version — not timestamp — decides who wins.
- **Network endpoint** (future) — re-back `StateStore` with HTTP GET/PUT or
  pub/sub for an over-the-internet web control plane. No change to splay's loop.

This is why the cursor is a separate, rate-limited file: on a slow/remote backend
you do not want to push the high-churn cursor on every tick.

## Cost

Reading `state` every frame is near-free: splay stats the file and only parses
the JSON when the mtime has moved. Writes happen only on real change (settings)
or at ≤ 10 Hz (cursor). Files are small (sub-kB to a few kB) and page-cache
resident.

## Implementation pointers

- `StateStore` class and the `SPLAY_STATE_PATH` / `SPLAY_LOADED_PATH` /
  `SPLAY_FRAME_PATH` / `FRAME_WRITE_HZ` constants (top of `splay`).
- `Splay._state_dict` / `_loaded_dict` / `_frame_dict` — what gets published.
- `Splay._sync_state_out` (write-on-change), `_write_frame` (coalesced),
  `_apply_state_in` (mtime-gated read + version reconcile),
  `_apply_external_settings` (apply a controller dict).
- Wired into `Splay.__init__` (initial publish) and `Splay.run` (read at top of
  loop, publish at bottom).
