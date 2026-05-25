DONE: file-change reload. 'r' rescans source dirs for new files and reloads
any known file whose mtime changed; 'R' toggles a 1Hz auto-rescan
(default off, --auto-reload to start it on).

DONE: bundled venv at /home/peter/splay/.venv (pygame astropy numpy opencv-python),
shebang points at .venv python so splay works from any shell without activating
anything. Recreate after a Python upgrade:
  python3 -m venv /home/peter/splay/.venv
  /home/peter/splay/.venv/bin/pip install --upgrade pip
  /home/peter/splay/.venv/bin/pip install pygame astropy numpy opencv-python
