"""distortion — interactively fit lens distortion + pole position.

A wide-field max-stack of a clear night shows star trails as bent
arcs (barrel distortion). With the right (k1, k2, p1, p2) plus
optical centre (cx, cy), undistorting flattens the trails into true
circles around the celestial pole. In polar view (centred on the
pole) those circles become horizontal straight lines.

Workflow:
  1. Click anywhere on the image to set the pole (pole_x, pole_y).
     The pole is usually OFF the v3w frame — click outside the visible
     area to place it there.
  2. Switch to polar (toggle `view`) and tune k1 until the trails go
     horizontal at the field edge.
  3. Refine with k2 (barrel + pincushion mix), p1/p2 (tangential).
  4. Save: writes <camera-dir>/distortion-<subcam>.json next to the
     image, backing up any previous file.

Defaults are seeded for the eclipticam v3w (IMX708 wide), binned 2x2
to (1296, 2304) and privacy-cropped to (1064, 2304). Adjust the
optical centre with cx/cy if the lens is offset from the image
centre.
"""

import math
import shutil
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import yaml

NAME = "distortion"
DESCRIPTION = __doc__.strip()

# (lo, hi, default, step, kind)
PARAMS = {
    # Pole — where the celestial pole projects. Often OFF-IMAGE. Wide
    # ranges so you can drag well off either side.
    "pole_x":     (-3000.0, 5000.0, 1152.0, 10.0,  "float"),
    "pole_y":     (-3000.0, 3000.0, -800.0, 10.0,  "float"),
    # Optical centre — usually image centre, sometimes slightly off.
    "cx":         (0.0,     2304.0, 1152.0, 1.0,   "float"),
    "cy":         (0.0,     1064.0, 532.0,  1.0,   "float"),
    # Radial distortion. k1 dominates barrel/pincushion; k2 second-order.
    "k1":         (-1.0,    1.0,    0.0,    0.01,  "float"),
    "k2":         (-1.0,    1.0,    0.0,    0.01,  "float"),
    # Tangential distortion — small, off-axis lens shift.
    "p1":         (-0.05,   0.05,   0.0,    0.001, "float"),
    "p2":         (-0.05,   0.05,   0.0,    0.001, "float"),
    # View toggle (image vs polar) — integer 0/1 for slider compatibility.
    "view":       (0,       1,      0,      1,     "int"),
    # Grid spacing for the overlay (in pixels in image view, in
    # radial-pixels in polar view). 0 = no grid.
    "grid":       (0,       400,    80,     20,    "int"),
    # Stretch (asinh strength) — controls how much faint trail signal
    # is pulled out of the dark sky.
    "stretch":    (1.0,     200.0,  30.0,   2.0,   "float"),
}


# Cache the most recent (params, output) so a re-render with the same
# params is a no-op. Splay re-calls process() on every paint.
_LAST = {"key": None, "out": None}


def _params_key(p):
    return tuple(round(float(p[k]), 6) for k in
                 ("pole_x", "pole_y", "cx", "cy",
                  "k1", "k2", "p1", "p2",
                  "view", "grid", "stretch"))


def _to_grey(bgr):
    """Splay loads images as 8-bit BGR even from FITS; collapse to grey
    for stretching. The FITS path through splay already applied an
    auto-stretch, so values are 0..255."""
    if bgr.ndim == 3:
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return bgr


def _asinh_stretch(grey, strength):
    """Re-stretch the (already-displayed) image with a different asinh
    strength. Helps pull faint trails out when defaults are too tame."""
    f = grey.astype(np.float32) / 255.0
    s = np.arcsinh(f * strength) / np.arcsinh(strength)
    return np.clip(s * 255.0, 0, 255).astype(np.uint8)


def _undistort(grey, p):
    """OpenCV undistort with current (k1, k2, p1, p2) about (cx, cy).
    Uses a synthetic camera matrix: focal length = max image dim
    (effective, used only to scale the radial term)."""
    H, W = grey.shape
    f = float(max(H, W))
    K = np.array([[f, 0, float(p["cx"])],
                  [0, f, float(p["cy"])],
                  [0, 0, 1.0]], dtype=np.float64)
    dist = np.array([float(p["k1"]), float(p["k2"]),
                     float(p["p1"]), float(p["p2"]), 0.0],
                    dtype=np.float64)
    return cv2.undistort(grey, K, dist)


def _to_polar(grey, pole_x, pole_y):
    """Warp to polar around (pole_x, pole_y). Star trails (constant
    radius from pole) become horizontal lines."""
    H, W = grey.shape
    # Choose an output canvas: max radius reaches the farthest image
    # corner from the pole. Output width = max_r, height = full angle
    # range (we map [-pi, pi] -> [0, H_out)).
    corners = np.array([[0, 0], [W, 0], [0, H], [W, H]], dtype=np.float64)
    dists = np.hypot(corners[:, 0] - pole_x, corners[:, 1] - pole_y)
    max_r = int(np.ceil(dists.max()))
    if max_r <= 0:
        return grey
    out_w = min(max_r, 2400)  # cap so it stays viewable
    out_h = grey.shape[0]
    return cv2.warpPolar(
        grey, (out_w, out_h), (float(pole_x), float(pole_y)), max_r,
        cv2.INTER_LINEAR + cv2.WARP_FILL_OUTLIERS)


def _draw_grid_image(bgr, p):
    """Concentric circles + radial spokes around the pole, drawn as a
    faint overlay. Radial step = grid pixels."""
    step = int(p["grid"])
    if step <= 0:
        return bgr
    H, W = bgr.shape[:2]
    px, py = int(round(p["pole_x"])), int(round(p["pole_y"]))
    overlay = bgr.copy()
    # Concentric circles
    max_r = int(np.hypot(max(px, W - px), max(py, H - py)))
    for r in range(step, max_r + step, step):
        cv2.circle(overlay, (px, py), r, (0, 165, 255), 1, cv2.LINE_AA)
    # Spokes every 30°
    for deg in range(0, 360, 30):
        a = math.radians(deg)
        x2 = int(round(px + max_r * math.cos(a)))
        y2 = int(round(py + max_r * math.sin(a)))
        cv2.line(overlay, (px, py), (x2, y2), (0, 165, 255), 1, cv2.LINE_AA)
    return cv2.addWeighted(overlay, 0.35, bgr, 0.65, 0)


def _draw_grid_polar(bgr, p, max_r):
    """Horizontal lines at constant radius, vertical lines at constant
    angle. Star trails should sit ON the horizontals."""
    step = int(p["grid"])
    if step <= 0:
        return bgr
    H, W = bgr.shape[:2]
    overlay = bgr.copy()
    px_per_r = W / float(max_r) if max_r > 0 else 1.0
    # Verticals at constant radius
    r = step
    while r < max_r:
        x = int(round(r * px_per_r))
        cv2.line(overlay, (x, 0), (x, H - 1), (0, 165, 255), 1, cv2.LINE_AA)
        r += step
    # Horizontals at every 30° (the polar axis spans 360°)
    for k in range(1, 12):
        y = int(round(H * k / 12))
        cv2.line(overlay, (0, y), (W - 1, y), (0, 165, 255), 1, cv2.LINE_AA)
    return cv2.addWeighted(overlay, 0.35, bgr, 0.65, 0)


def _annotate(bgr, p):
    """Burn the current params + view name into the top-left corner."""
    lines = [
        f"view: {'polar' if int(p['view']) else 'image'}",
        f"pole: ({p['pole_x']:.0f}, {p['pole_y']:.0f})",
        f"centre: ({p['cx']:.0f}, {p['cy']:.0f})",
        f"k1={p['k1']:+.3f}  k2={p['k2']:+.3f}",
        f"p1={p['p1']:+.4f}  p2={p['p2']:+.4f}",
    ]
    y = 20
    for line in lines:
        cv2.putText(bgr, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (255, 255, 255), 1, cv2.LINE_AA)
        y += 18
    return bgr


def process(frame_bgr, params):
    key = _params_key(params)
    if _LAST["key"] == key and _LAST["out"] is not None:
        return _LAST["out"]

    grey = _to_grey(frame_bgr)
    grey = _asinh_stretch(grey, float(params["stretch"]))
    grey = _undistort(grey, params)

    if int(params["view"]):
        # Polar view — find max radius for grid scaling.
        H, W = grey.shape
        corners = np.array([[0, 0], [W, 0], [0, H], [W, H]], dtype=np.float64)
        dists = np.hypot(corners[:, 0] - float(params["pole_x"]),
                         corners[:, 1] - float(params["pole_y"]))
        max_r = int(np.ceil(dists.max()))
        polar = _to_polar(grey, float(params["pole_x"]),
                          float(params["pole_y"]))
        bgr = cv2.cvtColor(polar, cv2.COLOR_GRAY2BGR)
        bgr = _draw_grid_polar(bgr, params, max_r)
    else:
        bgr = cv2.cvtColor(grey, cv2.COLOR_GRAY2BGR)
        bgr = _draw_grid_image(bgr, params)

    bgr = _annotate(bgr, params)
    _LAST["key"] = key
    _LAST["out"] = bgr
    return bgr


def on_click(x, y, frame_bgr, params):
    """Click sets the pole position. In polar view we don't change it
    (click is meaningless there — the pole is by definition at r=0)."""
    if int(params["view"]):
        return {}
    return {"pole_x": float(x), "pole_y": float(y)}


# ---- save current params via splay's render submission hook ---------------


def _params_to_save(params):
    out = {
        "model": "opencv_brown",
        "k1": float(params["k1"]),
        "k2": float(params["k2"]),
        "p1": float(params["p1"]),
        "p2": float(params["p2"]),
        "cx": float(params["cx"]),
        "cy": float(params["cy"]),
        "pole_x": float(params["pole_x"]),
        "pole_y": float(params["pole_y"]),
        "saved_utc": datetime.now(timezone.utc).isoformat(),
    }
    return out


def _sidecar_path(source: Path) -> Path:
    """Sidecar lives next to the source FITS / image. Named after the
    subcam if the filename starts with v1_/v3w_; else generic. YAML for
    hand-editing + comments."""
    name = source.stem.split("_")[0]
    if name in ("v1", "v3w"):
        return source.parent / f"distortion-{name}.yaml"
    return source.parent / "distortion.yaml"


# ---- splay plugin hooks: on_open (load) + on_save (Ctrl-S) ---------------


def on_open(source_path):
    """Called by splay whenever the displayed image changes. Return a
    partial dict of params to merge into the live state, or None."""
    sidecar = _sidecar_path(Path(source_path))
    if not sidecar.exists():
        return None
    try:
        data = yaml.safe_load(sidecar.read_text()) or {}
    except Exception as e:
        print(f"distortion: failed to read {sidecar}: {e}")
        return None
    # Keep only known PARAMS keys; ignore comments / extra fields.
    out = {k: data[k] for k in PARAMS if k in data}
    print(f"distortion: loaded {sidecar.name}")
    return out


def on_save(source_path, params):
    """Called by splay on Ctrl-S. Write YAML next to the image, back up
    any previous version so a bad slider position can't clobber a good
    calibration. Returns a message string for splay to print."""
    source = Path(source_path)
    sidecar = _sidecar_path(source)
    if sidecar.exists():
        bak = sidecar.with_suffix(
            sidecar.suffix + "."
            + datetime.now().strftime("%Y%m%dT%H%M%S") + ".bak")
        shutil.copy2(sidecar, bak)
        backup_note = f"  (previous → {bak.name})"
    else:
        backup_note = ""
    payload = _params_to_save(params)
    # Human-friendly header + stable key order.
    header = (
        "# distortion calibration — opencv Brown model\n"
        f"# saved: {payload['saved_utc']}\n"
        f"# source: {source.name}\n"
        "# pole_x/pole_y: celestial pole projection on the sensor (off-image OK)\n"
        "# cx/cy: optical centre of the lens on the sensor\n"
        "# k1/k2: radial distortion coefficients\n"
        "# p1/p2: tangential distortion coefficients\n"
        "---\n"
    )
    body = yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)
    sidecar.write_text(header + body)
    return f"distortion: saved {sidecar.name}{backup_note}"


# Splay's existing render_command hook also saves, for compat with the
# old Ctrl-R muscle memory.
def render_command(params, source_path):
    msg = on_save(source_path, params)
    return msg, ":"
