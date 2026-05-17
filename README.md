# play

Desktop frame players for stills and (eventually) video sequences.

## Lineage

Rewrite of `play`, a utility originally written at **The Moving Picture Company in
1996** for SGI IRIX, then ported to Linux in 2001. The original was for image
sequences — the natural unit of work in film post-production at the time.

This repo brings it back because modern tooling still doesn't quite scratch the
same itch: a fast, keyboard-driven viewer for stepping through frames, selecting
them for downstream work, wiping between pairs to compare A/B, and otherwise
treating an image sequence as the first-class object it is.

## Current contents

- **`splay`** — still-image viewer (Python + pygame). Handles a directory or
  explicit list of images. Selection, wipe, thumbnail strip, pixel-pick (RGB
  + HSV), fullscreen, HUD. Used heavily for tuning image-processing algorithms
  where you need to flip between input and output to see the change.

- **`vplay`** — *(planned)* desktop video frame viewer. Not the same as the
  separate `~/vplay` repo (which is a web-based player extracted from
  mywebsite's skycam viewer); this one is a desktop sibling to `splay`,
  sharing its interaction model so they eventually merge.

- **`play`** — *(planned)* nostalgia-driven wrapper that dispatches to `splay`
  or `vplay` based on the args. The eventual unified player.

## Status

`splay` is functional. The interaction model (hotkeys, selection semantics,
wipe behaviour, thumbnail strip) is the prototype shared design that `vplay`
will inherit when it lands. Once both exist and the interactions agree across
them, they collapse into the unified `play`.

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

See `super/bin/play` for the dispatch wrapper.
