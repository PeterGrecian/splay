# Astrocam Hardware Upgrades

Retiring the 13+ year old Pis. New kit: **Pi5**, **Pi4**, **wide-angle v3 camera**.

## Assignments

| Role | Host | Camera | Location |
|---|---|---|---|
| **elipticam** | Pi5 | v3 wide (IMX708, ~120° diag) | Indoors, behind glass, well ventilated |
| **starcam** | Pi4 | v2 (IMX219) initially | Pole-thrust enclosure outside a window |

Pi5 indoors is the easy thermal case. Pi4 in a sealed pole enclosure is the harder one — night-only operation gives big thermal headroom (idle in the sun by day, working in 10-15°C cooler air at night).

## Enclosure (Pi4 / starcam)

- Passive aluminium case (Argon/Flirc-style) inside the pole enclosure
- **Gore-Tex breather vent at the bottom** — drains condensation, equalises pressure, won't ingress driven rain like a top vent would
- Silica gel sachet
- USB3 SSD for local buffer (no spinning disk on a pole)

## Appliance Posture (starcam specifically)

Starcam needs to be an appliance — boots headless, recovers from power cuts, no SSH required for normal life.

- cloud-init image (reuse `cloud-init-init`) so reflashing is trivial
- systemd services with `Restart=always` + hardware watchdog
- Capture and processing as **separate services** — a wedged processor must not stop capture
- Status via pi-fleet (already done) + local LED
- Consider read-only root / overlayfs so power cuts don't corrupt SD
- Daytime is the maintenance window: OTA updates, log rotation, self-test, reboot if uptime > N days

Camera cover (already on skycam, presumably similar here) closes when bright. If the Pi can read its state, that's useful metadata for the nightly artefacts ("clouded out at 3am") and stops the pipeline plate-solving frames of the inside of a lens cap.

## Data Flow — "Light In, Stars Out"

Move processing onto the Pi; retire the NFS round-trip.

```
sensor → local USB SSD (raw frames)
       → on-Pi processing (per-frame, overnight + morning)
       → S3 (nightly artefacts: timelapse MP4, derotated stack, detections JSON, stats)
       → puppy (composite video assembly)
       → YouTube
```

Raw frames stay local. Only distilled output goes to AWS. A 256GB SSD holds months of v2 raws — long reprocessing window if the pipeline changes.

## Compute Budget (Pi4)

Pi4 has ~4 cores, ~6× a Pi1. Two windows:

- **Overnight** (~10h dark × 4 cores ≈ 40 core-hours): runs alongside capture. Best for per-frame work that streams as frames arrive — plate solve, detection extraction.
- **Morning** (~6h post-dawn × 4 cores ≈ 24 core-hours, no capture competing): heavy stuff. Derotation, stacking, lens distortion solve, pole finder refinement, timelapse encode.

64 core-hours/day is a serious budget. Pole-finder and lens-distortion solvers are one-shot (per session, or per week if the rig doesn't move) — amortised, cheap. Per-frame plate solve dominates and parallelises trivially across 4 cores.

**Thermal risk:** morning grind competes with ambient warming up. Start heavy work *before* dawn so most finishes while it's cold. Accept some throttling (Pi4 throttles to ~1.5GHz, ~30% throughput loss) as the fallback.

## Deliverables — Daily 2-Minute Video

Modelled on skycam. Deliverables by noon (target) or evening (fallback).

**Per-camera nightly artefacts** (Pi → S3 by ~6am):
- Timelapse MP4 (raw rotation, clouds drifting)
- Derotated stack: stars as points, horizon fixed
- Detections JSON: count, dimmest magnitude, brightest, anomalies (aircraft/satellite/meteor/transient candidates)

**Daily composite video** (assembled off-Pi):
- Intro card (date, conditions, moon phase)
- North + South timelapses (side-by-side or sequential)
- Derotated reveal
- Animated tour: pan/zoom across the derotated image hitting named stars/constellations, programmatically selected from a catalogue using the WCS solve
- Stats card: N stars detected, dimmest mag, clear/cloudy fraction
- Music

**Assembly host:** prefer not to recruit puppy (8-core i5), but it's the right tool if needed — ffmpeg with music library and fonts, all assets in one place. Pi pushes artefacts overnight; puppy pulls and assembles in minutes, stays mostly idle.

## Rain Detector (starcam)

Veroboard rain sensor: two interleaved tracks on stripboard exposed to the weather. A drop bridges the tracks and pulls the input low.

- 10k pull-up resistor from the GPIO input to 3V3
- Other track to GND
- Dry = high (pulled up), wet = low (drops short across the tracks)
- Mount under the pole enclosure lip so direct rain hits it but it's not sitting in standing water
- Read in capture daemon; if wet, close cover and emit a "rained out" stats record (same path as cloudy-out)

## Cloudy-Night Policy

Skycam's camera cover handles this at capture time. For starcam: emit a "clouded out" stats record so the daily video pipeline can either skip, post a short filler, or batch into a weekly digest.

## Open Questions

- Confirm v2 sensor on hand isn't itself 13 years old and due for replacement
- Read camera cover state from the Pi? (existing skycam mechanism)
- Composite video: daily-regardless, only-when-clear, or weekly-digest cadence?
- Decommission NFS box entirely, or keep as belt-and-braces rsync target?
