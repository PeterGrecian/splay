# Bayer-mosaic heat-map rendering (feature spec + how-to)

A view for inspecting a small crop of a **raw Bayer mosaic** at the individual-
photosite level: intensity as a heat-map, with each cell tagged by its Bayer
colour (R/G/B) as a coloured dot, optionally in 3D (stems) and/or top-down.
Developed in the astro project for PSF / streak / undersampling inspection; worth
making a first-class splay feature.

## What it shows and why it's useful

A raw Bayer frame is a checkerboard of R/G/G/B photosites. At the few-pixel scale
of a star PSF, you cannot see the true structure in a normal render because the
Bayer pattern dominates. This view separates the two:

- **Heat-map (intensity)** — the actual photosite values, asinh/linear stretched.
- **Coloured dot per cell** — R (red), G (green), B (blue) at each pixel centre,
  so you can see *which colour* each value belongs to and judge the star's colour
  balance, the checkerboard aliasing, and the true (gain-corrected) PSF shape.
- **Optional 3D stems** — z = intensity, coloured by channel: reads the PSF as a
  surface, great for seeing sub-pixel undersampling (a sharp star is a spike;
  neighbours near zero = undersampled; spread = well-sampled).

Used to: measure PSF FWHM, spot undersampling (v3w ~1px vs astrocam soft), see
focus-breathing width change, and do the **assume-white** balance (scale R,B up to
G on the star patch) which removes the green-checkerboard so the *true* PSF shows.

## The Bayer parity (CRITICAL — per sensor)

Each pixel's colour is `(y%2, x%2)` mapped by the sensor's Bayer pattern, using
the pixel's **GLOBAL** coordinates (not crop-local), so the parity is correct
after cropping. The four Pi sensors in the astro fleet:

| Sensor      | Camera        | BAYERPAT | (0,0) (1,0)/(0,1) (1,1) parity |
|-------------|---------------|----------|--------------------------------|
| IMX219      | astrocam (v2) | SBGGR    | (0,0)=B  G  (1,1)=R            |
| OV5647      | v1 / starcam  | SGBRG    | (0,0)=G  ... (see note)        |
| IMX708      | v3w (Mod3 W)  | RGGB     | (0,0)=R  G  (1,1)=B            |

NOTE: BAYERPAT strings and the actual (y%2,x%2) parity can differ by convention
(rotation_180, DNG vs raw). ALWAYS verify against a bright white star: the R and
B channel means should be scalable to G (assume-white). If R/B come out on the
wrong photosites the parity map is off — swap it. For a generic feature, read the
`BAYERPAT` FITS header and map it, but expose an override.

## Assume-white balance (the key correction)

On the star patch (pixels above ~15% of peak), compute per-channel means Rm,Gm,Bm,
then scale the R and B photosites up to G: `R *= Gm/Rm; B *= Gm/Bm`. This removes
the green-dominated checkerboard so the heat-map/3D shows the *true* PSF, not the
Bayer pattern. For a white star Rm≈Gm≈Bm (factors ~1.0) — meaning it's already
balanced (a real result: a neutral star). For a coloured star the factors differ.
Do the balance on the STAR patch, not the sky (sky WB is ~neutral and misleading).

## Reference implementation

See `apps/bayer_heatmap.py` (extracted from the astro scratch). Core:

```python
import numpy as np, matplotlib.pyplot as plt

def bayer_channel(ys, xs, pattern="RGGB"):
    """Map GLOBAL pixel coords -> 'R'/'G'/'B' for a 2x2 Bayer pattern.
    pattern is the top-left 2x2 read row-major: RGGB, BGGR, GBRG, GRBG."""
    p = {(0,0):pattern[0],(0,1):pattern[1],(1,0):pattern[2],(1,1):pattern[3]}
    out = np.empty(ys.shape, dtype='<U1')
    for (dy,dx),c in p.items():
        out[(ys%2==dy)&(xs%2==dx)] = c
    return out

def assume_white(sub, chan, thresh=0.15):
    """Scale R,B photosites up to G on the bright (star) patch. Returns z, wb."""
    br = sub > thresh*sub.max()
    m = {c: sub[br&(chan==c)].mean() if (br&(chan==c)).any() else 1.0
         for c in 'RGB'}
    z = sub.copy()
    z[chan=='R'] *= m['G']/max(m['R'],1); z[chan=='B'] *= m['G']/max(m['B'],1)
    return np.clip(z,0,None), (m['G']/max(m['R'],1), m['G']/max(m['B'],1))

def render(crop, x0, y0, pattern="RGGB", out="heatmap.png", white=True):
    h,w = crop.shape
    ys,xs = np.mgrid[y0:y0+h, x0:x0+w]
    sub = crop - np.median(crop)
    chan = bayer_channel(ys, xs, pattern)
    z,(wr,wb) = assume_white(sub, chan) if white else (np.clip(sub,0,None),(1,1))
    dot = {'R':'#ff3030','G':'#20c020','B':'#3060ff'}
    fig = plt.figure(figsize=(18,8))
    # 3D stems (z = intensity, coloured by channel)
    ax = fig.add_subplot(121, projection='3d')
    for i in range(h):
        for j in range(w):
            ax.plot([xs[i,j]]*2,[ys[i,j]]*2,[0,z[i,j]],
                    color=dot[chan[i,j]], alpha=0.5, lw=0.9)
    ax.scatter(xs,ys,z,c=[dot[c] for c in chan.ravel()],s=16,
               depthshade=False,edgecolors='k',linewidths=0.15)
    ax.view_init(elev=25,azim=-70); ax.set_title('3D by Bayer channel')
    # top-down heat-map + coloured Bayer dot per cell
    ax2 = fig.add_subplot(122)
    im = ax2.imshow(z, origin='lower', cmap='inferno', aspect='equal',
                    extent=[x0-.5,x0+w-.5,y0-.5,y0+h-.5])
    for i in range(h):
        for j in range(w):
            ax2.plot(xs[i,j],ys[i,j],'o',ms=3,color=dot[chan[i,j]],
                     alpha=0.7,mec='k',mew=0.2)
    plt.colorbar(im,ax=ax2,shrink=0.7)
    fig.suptitle(f'Bayer heat-map | WB R x{wr:.2f} B x{wb:.2f} | peak {z.max():.0f}')
    plt.tight_layout(); plt.savefig(out,dpi=100)
```

## Feature integration ideas (for splay)
- **Trigger**: a key in splay on a hovered pixel → crop N×N around it → render.
- **Crop size**: ~24–40 px is right for a star PSF; make it a param.
- **Bayer pattern**: read from the FITS `BAYERPAT` header; fall back to a per-camera
  map; allow an override key (parity conventions vary — see note above).
- **White toggle**: assume-white on/off (off shows the raw green-dominated mosaic;
  on shows the true PSF). Report the WB factors (they double as a colour readout).
- **Dot size / 3D-vs-2D**: options. The coloured dot is the signature — keep it.
- **Stretch**: asinh with the crop's own scale (small crop, dark background).

## Gotchas learned (astro)
- Parity MUST use global coords or cropping shifts the colours.
- Do assume-white on the STAR, not the sky.
- A "white" star gives WB ~1.0 — that's correct, not a bug.
- Beware summing/rendering artifacts: measure on the raw crop, not a rendered PNG.
