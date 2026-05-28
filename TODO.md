DONE: Delete hotkey removes current file from the list (disk untouched).

DONE: stepping frames no longer wraps; clamps at first/last instead.

DONE: 'g' opens current frame in GIMP. FITS files are exported to
~/tmp/splay-gimp/<stem>.png at the current stretch (and hot-pixel
mask state) since GIMP's FITS support is unreliable.

DONE: file-change reload. 'r' rescans source dirs for new files and reloads
any known file whose mtime changed; 'R' toggles a 1Hz auto-rescan
(default off, --auto-reload to start it on).

DONE: bundled venv at /home/peter/splay/.venv (pygame astropy numpy opencv-python),
shebang points at .venv python so splay works from any shell without activating
anything. Recreate after a Python upgrade:
  python3 -m venv /home/peter/splay/.venv
  /home/peter/splay/.venv/bin/pip install --upgrade pip
  /home/peter/splay/.venv/bin/pip install pygame astropy numpy opencv-python
