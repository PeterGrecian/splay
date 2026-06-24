# splay

Keyboard-driven still-image viewer with selection, wipe, thumbnail strip, and
per-pixel RGB/HSV pickoff. Built for fast iteration on image-processing
algorithms where you need to flip rapidly between input and output to judge
the change.

## Lineage

Descendant of `play`, a utility I wrote at **The Moving Picture Company in
1996** for SGI IRIX, ported to Linux in 2001. The original handled image
sequences — the natural unit of work in film post-production at the time.

The name `play` was too generic for a modern PATH (it collides with SoX
among other things), so this rewrite keeps the original capability under its
natural pun: **splay** for stills. A sibling **vplay** for video is planned
as its own repo; the two will share an interaction model but remain separate
executables.

## What it does

- Step through a directory or explicit list of images with the arrow keys.
- Select/deselect frames; toggle between viewing all frames and viewing only
  the selected ones.
- Wipe between the two most recently shown frames — useful A/B comparison
  for before/after.
- Pixel-pick: click a pixel and read its BGR/RGB + HSV in both the on-screen
  HUD and the terminal. Useful for picking thresholds in image-processing
  pipelines.
- Thumbnail strip with names. Selection state shown.
- Fullscreen and a HUD help overlay.

## Hotkeys

| Key | Action |
|---|---|
| ← → | previous / next frame |
| s | select current frame |
| d | deselect current frame |
| l | toggle list mode (all frames) / selected-only mode |
| w | toggle wipe between the two most recently shown frames; mouse X positions the boundary |
| f | toggle fullscreen |
| h | toggle HUD / help |
| click | pixel-pick (prints + displays BGR/RGB + HSV) |
| q / Esc | quit (selection list printed on exit) |

## Install

```
git clone <repo-url> ~/splay
pip install --user pygame      # or use a venv
ln -s ~/splay/splay ~/bin/splay   # or wherever your $PATH points
```

## Usage

```
splay                     # all images in cwd
splay <dir>               # all images in dir (non-recursive)
splay a.png b.png c.png   # explicit list
```

Supported formats: anything pygame can decode (PNG, JPG, BMP, GIF, TIFF,
WebP).

## Scripting & state protocol

splay publishes its live state to three JSON files in `$HOME` (override the
directory with `$SPLAY_STATE_DIR`):

- `~/.splay-state.json` — settings (sort, mask, stretch, modes, …). **Writable**:
  write it to drive the visualisation.
- `~/.splay-loaded.json` — the loaded path list ("what's loaded").
- `~/.splay-frame.json` — the current-frame cursor (high-churn, coalesced).

Read them with `cat`/`jq`. To drive splay, read `~/.splay-state.json`, bump its
`version`, set `writer` to `"controller"`, change the keys you want, and write it
back; splay applies the change within a frame and re-publishes. The `version`
field orders writes so a control plane and the viewer can even run on separate
devices via a shared `$SPLAY_STATE_DIR`. Full spec:
[`design/splay-state-protocol.md`](design/splay-state-protocol.md).

To add/clear frames or inject any hotkey into a running instance, use the IPC
channel: `splay --send key:r`, `splay --send clear` (key names are pygame `K_`
names without the prefix, e.g. `RIGHT`, `HOME`).
