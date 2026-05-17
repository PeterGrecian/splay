"""skymask — HSV-intersection sky mask for stereo SBS frames.

Splits the SBS in half, HSV-thresholds each eye, intersects the two masks
(parallax-aware: clutter at different positions in each eye fails to agree),
feathers, composites the non-sky regions over a pale-blue sampled from the
brightest agreed-sky pixels.

Click a sky pixel to widen the thresholds to include it; click a non-sky
pixel to tighten them to exclude it. (Heuristic — works best on pixels that
are obvious examples.)
"""

import numpy as np
import cv2

NAME = "skymask"
DESCRIPTION = __doc__.strip()
WANTS = "sbs"

# (lo, hi, default, step, kind)
PARAMS = {
    "h_lo":            (0,    180,  85,   1,    "int"),
    "h_hi":            (0,    180,  130,  1,    "int"),
    "v_min":           (0,    255,  80,   5,    "int"),
    "cloud_s_max":     (0,    255,  110,  5,    "int"),
    "cloud_v_min":     (0,    255,  70,   5,    "int"),
    "feather":         (0.0,  20.0, 2.0,  0.5,  "float"),
    "fill_percentile": (0.0,  100.0, 80.0, 5.0, "float"),
    "bright_bias":     (0.0,  4.0,  2.0,  0.25, "float"),
}

# ---- algorithm ---------------------------------------------------------------

def _split(img):
    w = img.shape[1]
    half = w // 2
    return img[:, :half], img[:, half:]

def _hsv_masks(img_bgr, p):
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    blue  = (H >= p["h_lo"]) & (H <= p["h_hi"]) & (V >= p["v_min"])
    cloud = (S <= p["cloud_s_max"]) & (V >= p["cloud_v_min"])
    combined = (blue | cloud).astype(np.uint8) * 255
    blue_mask = blue.astype(np.uint8) * 255
    return combined, blue_mask

_KER3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

def _intersected_mask(img_bgr, p):
    """Return (intersection_mask, blue_intersection_mask, fill_color_bgr)."""
    L, R = _split(img_bgr)
    mL, bL = _hsv_masks(L, p)
    mR, bR = _hsv_masks(R, p)
    inter = cv2.bitwise_and(mL, mR)
    inter = cv2.morphologyEx(inter, cv2.MORPH_OPEN, _KER3)
    binter = cv2.bitwise_and(bL, bR)
    sel = binter > 127
    if sel.sum() < 100:
        fill = np.array([220, 210, 180], dtype=np.uint8)
    else:
        px = L[sel].astype(np.float32)
        luma = 0.114 * px[:, 0] + 0.587 * px[:, 1] + 0.299 * px[:, 2]
        thr = np.percentile(luma, p["fill_percentile"])
        m = luma >= thr
        px = px[m]; luma = luma[m]
        w = (luma / 255.0) ** p["bright_bias"]
        fill = ((px * w[:, None]).sum(axis=0) / max(w.sum(), 1e-6)).astype(np.uint8)
    return inter, fill

def process(frame_bgr, params):
    """Apply the skymask compositing to an SBS frame."""
    L, R = _split(frame_bgr)
    inter, fill = _intersected_mask(frame_bgr, params)
    feather = params["feather"]
    if feather > 0:
        weight = cv2.GaussianBlur(inter, (0, 0), sigmaX=feather, sigmaY=feather)
    else:
        weight = inter
    weight = (weight / 255.0).astype(np.float32)
    w3 = np.dstack([weight, weight, weight])
    fill_img = np.zeros_like(L); fill_img[:] = fill
    outL = np.clip(L.astype(np.float32) * w3 + fill_img.astype(np.float32) * (1 - w3), 0, 255).astype(np.uint8)
    outR = np.clip(R.astype(np.float32) * w3 + fill_img.astype(np.float32) * (1 - w3), 0, 255).astype(np.uint8)
    return np.hstack([outL, outR])

def mask(frame_bgr, params):
    """Debug view: show the intersection mask (white = sky, black = not)
    duplicated across both eyes so it lines up with the SBS layout."""
    inter, _ = _intersected_mask(frame_bgr, params)
    rgb = cv2.cvtColor(inter, cv2.COLOR_GRAY2BGR)
    return np.hstack([rgb, rgb])

# ---- interaction -------------------------------------------------------------

def on_click(x, y, frame_bgr, params):
    """Widen/tighten the HSV thresholds so the clicked pixel's classification
    changes. Heuristic: if the pixel is currently NOT sky, widen the cloud
    branch to include it; if it IS sky, tighten the blue branch to exclude it.

    The user picks the pixel they care about; the algorithm picks which knob
    moves and by how much.
    """
    h, w = frame_bgr.shape[:2]
    half = w // 2
    # If the click is on the right half, map back to left coords for fairness.
    x_in_half = x if x < half else x - half
    L = frame_bgr[:, :half]
    pixel = L[y, x_in_half]  # BGR
    hsv = cv2.cvtColor(pixel.reshape(1, 1, 3), cv2.COLOR_BGR2HSV)[0, 0]
    Hh, S, V = int(hsv[0]), int(hsv[1]), int(hsv[2])

    # Is this pixel currently classified as sky in the LEFT eye?
    in_blue  = (params["h_lo"] <= Hh <= params["h_hi"]) and V >= params["v_min"]
    in_cloud = (S <= params["cloud_s_max"]) and (V >= params["cloud_v_min"])
    is_sky = in_blue or in_cloud

    print(f"  click: HSV=({Hh},{S},{V})  blue={in_blue}  cloud={in_cloud}  is_sky={is_sky}")

    if not is_sky:
        # Widen whichever branch is closest to passing.
        # Distance to blue: how far outside [h_lo..h_hi] is Hh, or how far below v_min?
        # Distance to cloud: how much above cloud_s_max is S, or below cloud_v_min is V?
        upd = {}
        # Try the cloud branch first — it's the catch-all for greys.
        if S > params["cloud_s_max"]:
            upd["cloud_s_max"] = min(255, S + 5)
        if V < params["cloud_v_min"]:
            upd["cloud_v_min"] = max(0, V - 5)
        # If the pixel is bluish-but-too-dim, lower v_min.
        if params["h_lo"] <= Hh <= params["h_hi"] and V < params["v_min"]:
            upd["v_min"] = max(0, V - 5)
        # If the pixel is in the wrong hue range entirely, nudge h_lo/h_hi.
        if Hh < params["h_lo"]:
            upd["h_lo"] = max(0, Hh - 2)
        elif Hh > params["h_hi"]:
            upd["h_hi"] = min(180, Hh + 2)
        return upd
    else:
        # Tighten — exclude the clicked pixel. Pick the branch it's in.
        upd = {}
        if in_cloud:
            # Make cloud branch stricter. Move the boundary just past this pixel.
            if S >= params["cloud_s_max"] - 5:  # close to the edge in S
                upd["cloud_s_max"] = max(0, S - 5)
            else:
                upd["cloud_v_min"] = min(255, V + 5)
        elif in_blue:
            if Hh - params["h_lo"] < params["h_hi"] - Hh:
                upd["h_lo"] = min(180, Hh + 2)
            else:
                upd["h_hi"] = max(0, Hh - 2)
        return upd

# ---- render dispatch ---------------------------------------------------------

def render_command(params, source_path):
    """Build the bin/submit-skymask invocation. source_path comes from a
    sidecar .source.txt in the frame directory."""
    if not source_path:
        raise RuntimeError("no .source.txt sidecar — cannot dispatch render")
    import shlex, datetime, pathlib
    # The submitter lives in the stereo repo.
    submitter = pathlib.Path.home() / "photography" / "stereo" / "bin" / "submit-skymask"
    if not submitter.is_file():
        raise RuntimeError(f"missing submitter: {submitter}")
    # Derive a slug from the source URL/path.
    stem = pathlib.Path(source_path).stem.replace(".", "-")
    slug = f"{stem}-skymask"
    cmd = [
        str(submitter),
        "--slug", slug,
        "--source", source_path,
        "--h-lo", str(params["h_lo"]),
        "--h-hi", str(params["h_hi"]),
        "--v-min", str(params["v_min"]),
        "--cloud-s-max", str(params["cloud_s_max"]),
        "--cloud-v-min", str(params["cloud_v_min"]),
        "--feather", str(params["feather"]),
        "--fill-percentile", str(params["fill_percentile"]),
        "--bright-bias", str(params["bright_bias"]),
        "--submit",
    ]
    desc = (f"Submit skymask render of\n  {source_path}\n"
            f"slug: {slug}\n"
            f"params: h={params['h_lo']}-{params['h_hi']} "
            f"v_min={params['v_min']} "
            f"cloud_s_max={params['cloud_s_max']} "
            f"cloud_v_min={params['cloud_v_min']} "
            f"feather={params['feather']} "
            f"fill_pct={params['fill_percentile']} "
            f"bright_bias={params['bright_bias']}\n"
            f"~5 min wall on Cloud Run, ~$0.01")
    return desc, cmd
