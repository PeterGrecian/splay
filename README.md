# splay / vplay

Desktop frame players for stills and video — keyboard-driven, wipe-comparable,
selection-aware.

## Lineage

Descendants of `play`, a utility I wrote at **The Moving Picture Company in
1996** for SGI IRIX, ported to Linux in 2001. The original handled image
sequences — the natural unit of work in film post-production at the time.

This repo brings the same idea back because modern tooling still doesn't quite
scratch the same itch: a fast viewer for stepping through frames, selecting
them for downstream work, wiping between pairs to compare A/B, treating an
image sequence (or a video) as the first-class object it is.

The name `play` was too generic (and collides with SoX), so the modern split
keeps both halves of the original capability under their natural puns:
**splay** for stills, **vplay** for video.

## Current contents

- **`splay`** — still-image viewer (Python + pygame). Handles a directory or
  explicit list of images. Selection, wipe, thumbnail strip, pixel-pick
  (RGB + HSV), fullscreen, HUD. Used heavily for tuning image-processing
  algorithms where you need to flip between input and output to see the change.

- **`vplay`** — *(planned)* desktop video frame viewer. Sibling to `splay`,
  sharing its interaction model. Not the same as the separate `~/vplay` web
  repo (browser-based player extracted from mywebsite's skycam viewer) — that
  one is a different lineage.

## Status

`splay` is functional. The interaction model (hotkeys, selection semantics,
wipe behaviour, thumbnail strip) is the shared design `vplay` will inherit
when it lands. The two will remain separate executables — no unifying
wrapper.

## Hotkeys (splay)

| Key | Action |
|---|---|
| ← → | previous / next frame |
| s | select current frame |
| d | deselect current frame |
| l | toggle list mode (all) / selected-only mode |
| w | toggle wipe between the two most recently shown frames; mouse X positions the boundary |
| f | toggle fullscreen |
| h | toggle HUD / help |
| click | pixel-pick (prints + displays BGR/RGB + HSV) |
| q / Esc | quit (selection list printed on exit) |

## Install

```
cd ~/play
pip install --user pygame    # or use a venv
ln -s $PWD/splay ~/super/bin/splay    # or however your $PATH is set up
```
