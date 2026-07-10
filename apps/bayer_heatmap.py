#!/usr/bin/env python3
"""bayer_heatmap - render a raw Bayer-mosaic crop as an intensity heat-map with a
coloured Bayer-channel dot in each cell (+ optional 3D stems).

Reference implementation for a splay feature. Inspect a star PSF / streak at the
individual-photosite level; see undersampling, the checkerboard aliasing, and the
true PSF after an assume-white balance. See design/bayer-heatmap.md for the how &
the per-sensor Bayer parity table.

CLI (standalone test):
    bayer_heatmap.py FRAME.fits --x 531 --y 2216 --size 32 \\
        --pattern SBGGR --out /tmp/hm.png [--no-white] [--no-3d]
FRAME can be FITS (raw mosaic). --pattern is the top-left 2x2 read row-major:
RGGB (IMX708), SBGGR (IMX219), SGBRG (OV5647). If omitted, read from BAYERPAT.

As a library:
    from bayer_heatmap import render
    render(crop, x0, y0, pattern="RGGB", out="hm.png", white=True, threed=True)
"""
import argparse
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DOT = {"R": "#ff3030", "G": "#20c020", "B": "#3060ff"}


def bayer_channel(ys, xs, pattern="RGGB"):
    """Map GLOBAL pixel coords -> 'R'/'G'/'B' arrays for a 2x2 Bayer pattern.

    `pattern` is the top-left 2x2 read ROW-MAJOR: e.g. RGGB = (0,0)=R (0,1)=G
    (1,0)=G (1,1)=B. Use GLOBAL (uncropped) y,x so parity survives cropping.
    'S' prefix (SBGGR/SGBRG) is stripped — it's just "sensor" not a colour.
    """
    p = pattern.upper().lstrip("S")
    if len(p) != 4:
        raise ValueError(f"pattern must be 4 letters (got {pattern!r})")
    cell = {(0, 0): p[0], (0, 1): p[1], (1, 0): p[2], (1, 1): p[3]}
    out = np.empty(ys.shape, dtype="<U1")
    for (dy, dx), c in cell.items():
        out[(ys % 2 == dy) & (xs % 2 == dx)] = c
    return out


def assume_white(sub, chan, thresh=0.15):
    """Scale R,B photosites up to G on the bright (star) patch = assume-white.

    Removes the green-dominated checkerboard so the true PSF shows. Returns
    (z, (wb_R, wb_B)). WB ~1.0 means an already-neutral (white) star.
    """
    br = sub > thresh * sub.max()
    m = {c: (sub[br & (chan == c)].mean() if (br & (chan == c)).any() else 1.0)
         for c in "RGB"}
    z = sub.copy()
    z[chan == "R"] *= m["G"] / max(m["R"], 1.0)
    z[chan == "B"] *= m["G"] / max(m["B"], 1.0)
    return np.clip(z, 0, None), (m["G"] / max(m["R"], 1.0),
                                 m["G"] / max(m["B"], 1.0))


def render(crop, x0, y0, pattern="RGGB", out="bayer_heatmap.png",
           white=True, threed=True, title=""):
    """Render the crop. crop is a 2D raw-mosaic array; (x0,y0) its global origin.

    white: apply assume-white balance. threed: include the 3D-stem panel.
    """
    h, w = crop.shape
    ys, xs = np.mgrid[y0:y0 + h, x0:x0 + w]
    sub = crop.astype(float) - np.median(crop)
    chan = bayer_channel(ys, xs, pattern)
    if white:
        z, (wr, wb) = assume_white(sub, chan)
    else:
        z, (wr, wb) = np.clip(sub, 0, None), (1.0, 1.0)

    ncol = 2 if threed else 1
    fig = plt.figure(figsize=(9 * ncol, 8))
    col = 1
    if threed:
        ax = fig.add_subplot(1, ncol, col, projection="3d")
        for i in range(h):
            for j in range(w):
                ax.plot([xs[i, j], xs[i, j]], [ys[i, j], ys[i, j]],
                        [0, z[i, j]], color=DOT[chan[i, j]], alpha=0.5, lw=0.9)
        ax.scatter(xs.ravel(), ys.ravel(), z.ravel(),
                   c=[DOT[c] for c in chan.ravel()], s=16,
                   depthshade=False, edgecolors="k", linewidths=0.15)
        ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_zlabel("intensity")
        ax.set_title("3D by Bayer channel")
        ax.view_init(elev=25, azim=-70)
        col += 1

    ax2 = fig.add_subplot(1, ncol, col)
    im = ax2.imshow(z, origin="lower", cmap="inferno", aspect="equal",
                    extent=[x0 - .5, x0 + w - .5, y0 - .5, y0 + h - .5])
    for i in range(h):
        for j in range(w):
            ax2.plot(xs[i, j], ys[i, j], "o", ms=3, color=DOT[chan[i, j]],
                     alpha=0.7, mec="k", mew=0.2)
    ax2.set_title("top-down: intensity + Bayer dots")
    plt.colorbar(im, ax=ax2, shrink=0.7)

    sup = title or "Bayer heat-map"
    fig.suptitle(f"{sup} | WB R x{wr:.2f} B x{wb:.2f} | peak {z.max():.0f}",
                 fontsize=13)
    plt.tight_layout()
    plt.savefig(out, dpi=100)
    plt.close(fig)
    return out, (wr, wb)


def _load_crop(path, x, y, size, pattern):
    from astropy.io import fits
    hd = fits.open(path)
    hdu = hd[1] if len(hd) > 1 and hd[1].data is not None else hd[0]
    d = hdu.data.astype(float)
    if pattern is None:
        pattern = (hdu.header.get("BAYERPAT") or "RGGB")
    b = size // 2
    return d[y - b:y + b, x - b:x + b], x - b, y - b, pattern


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("frame")
    ap.add_argument("--x", type=int, required=True)
    ap.add_argument("--y", type=int, required=True)
    ap.add_argument("--size", type=int, default=32)
    ap.add_argument("--pattern", default=None,
                    help="RGGB/SBGGR/SGBRG... (default: FITS BAYERPAT)")
    ap.add_argument("--out", default="/tmp/bayer_heatmap.png")
    ap.add_argument("--no-white", action="store_true")
    ap.add_argument("--no-3d", action="store_true")
    a = ap.parse_args(argv)
    crop, x0, y0, pat = _load_crop(a.frame, a.x, a.y, a.size, a.pattern)
    out, (wr, wb) = render(crop, x0, y0, pattern=pat, out=a.out,
                           white=not a.no_white, threed=not a.no_3d,
                           title=f"{a.frame.split('/')[-1]} @({a.x},{a.y}) {pat}")
    print(f"wrote {out}  pattern={pat}  WB R x{wr:.2f} B x{wb:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
