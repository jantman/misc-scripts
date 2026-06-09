# zm-find-motion-in-region

Find [ZoneMinder](https://zoneminder.com/) events that contain motion (image
changes) inside an **arbitrary rectangular region of the frame** — a region that
is *not* configured as a ZoneMinder zone.

ZoneMinder only scores motion inside the zones you've set up in advance. If you
need to answer a question after the fact — *"did anything move in **that** corner
of camera 6 between Monday and Wednesday?"* — the stored alarm scores won't help,
because no zone covered that corner. This tool re-analyzes the recorded JPEG
frames of each event, crops them to a Region Of Interest (ROI) you specify, and
reports events where the pixels inside that ROI changed.

It is configuration-driven: no server URLs, usernames, passwords, or other
site-specific values are baked into the code.

---

## How it works

1. Authenticates to the ZoneMinder web API (token auth, ZM 1.34+).
2. Lists events matching a monitor and time window.
3. For each event, downloads its JPEG frames via the `zms` streaming CGI.
4. Crops every frame to your ROI, converts to grayscale, and computes the
   absolute pixel difference between consecutive frames *inside the ROI only*.
5. Flags events where the fraction of changed ROI pixels exceeds a threshold,
   and reports them sorted by peak change.

Because it works off the stored frames, **it can only analyze events whose
recordings still exist on the server.** Events that ZoneMinder has already
purged (or that were lost to a disk failure) have no frames to analyze.

---

## Requirements

- Python 3.9+
- A ZoneMinder server running **1.34 or newer** (token-based API auth).
- API + streaming (`/cgi-bin/zms`) reachable from where you run this.
- Python packages in `requirements.txt` (`requests`, `Pillow`, `numpy`).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Configuration

Copy the example config and fill in your details:

```bash
cp zm_config.example.json zm_config.json
$EDITOR zm_config.json
```

```json
{
  "base_url": "https://zoneminder.example.com",
  "username": "your-zm-user",
  "password": "your-zm-password",
  "verify_ssl": true,
  "timeout": 30
}
```

| Key          | Meaning                                                                                          |
|--------------|--------------------------------------------------------------------------------------------------|
| `base_url`   | Root URL of your ZM web install, **no trailing slash**. If ZM lives under `/zm`, include it (e.g. `https://host/zm`). If it's served at the web root, omit it. |
| `username`   | A ZoneMinder user with API + view permissions.                                                   |
| `password`   | That user's password.                                                                            |
| `verify_ssl` | Set to `false` only for self-signed certs you trust (insecure).                                  |
| `timeout`    | Per-request timeout in seconds.                                                                  |

`zm_config.json` is git-ignored so you won't accidentally commit credentials.
You can also point at a different file with `--config path.json` or the
`ZM_CONFIG` environment variable.

> **Path-prefix note:** This tool talks to `{base_url}/api/...` and
> `{base_url}/cgi-bin/zms`. Many installs (and reverse-proxied ones) serve these
> at the web root rather than under `/zm/`. Put whatever prefix your install
> actually uses into `base_url`.

---

## Quick start

```bash
# 1. Confirm your config + credentials work.
python zm_motion.py test-connection

# 2. Find candidate events for the camera + time window.
#    Times are in the ZoneMinder SERVER's local timezone.
python zm_motion.py list-events --monitor 6 \
    --start "2026-04-29 00:00:00" --end "2026-05-06 10:00:00"

# 3. Grab a reference frame so you can pick ROI coordinates.
python zm_motion.py save-frame --event 123456 -o ref.jpg

# 4. Figure out the ROI (X,Y,W,H in pixels — see below), then verify it
#    visually by drawing it on the reference frame.
python zm_motion.py annotate-region --image ref.jpg --region 800,450,300,200 -o roi.jpg
#    Open roi.jpg and confirm the red box covers the area you care about.

# 5. Scan the time window for motion inside that ROI.
python zm_motion.py scan --monitor 6 \
    --start "2026-04-29 00:00:00" --end "2026-05-06 10:00:00" \
    --region 800,450,300,200 \
    --json-out results.json
```

---

## Finding your ROI coordinates

The ROI is given as `X,Y,W,H` in **pixels**, where `X,Y` is the top-left corner
(origin is the top-left of the frame) and `W,H` are width and height.

The easy workflow:

1. `save-frame` a representative frame to a JPEG.
2. Open it in any image editor (GIMP, Preview, even a browser with dev tools)
   and read off the pixel coordinates of the rectangle you want.
3. Use `annotate-region` to draw your guess back onto the frame and eyeball it.
4. Adjust and repeat until the red box sits where you want.

Make sure the ROI fits within the frame; `annotate-region` warns you if it
extends past the image bounds (it will be clipped during analysis).

---

## Tuning detection

`scan` has two knobs that control sensitivity:

| Flag                | Default | Effect                                                                                   |
|---------------------|---------|------------------------------------------------------------------------------------------|
| `--pixel-threshold` | `25`    | How different (0–255 grayscale) a pixel must be between two frames to count as "changed". Lower = more sensitive to subtle changes/noise; higher = only strong changes. |
| `--min-fraction`    | `0.02`  | What fraction (0–1) of the ROI's pixels must change in a single frame-pair to flag the event. `0.02` = 2% of the ROI. |

Two more flags control performance vs. thoroughness:

| Flag             | Default | Effect                                                                                  |
|------------------|---------|-----------------------------------------------------------------------------------------|
| `--frame-type`   | `all`   | `all` examines every frame; `alarm` only examines ZM-flagged alarm frames (faster, but biased toward whatever zones *were* configured — usually you want `all` for non-zone regions). |
| `--sample-every` | `1`     | Examine only every Nth frame. `--sample-every 3` is ~3× faster but may miss brief motion. |

**Recommended workflow for tuning:** pick one event you *know* has the motion
you care about and one you know doesn't, run `scan --event <id> --verbose` on
each, and look at the per-frame percentages. Set `--min-fraction` between the two.

```bash
python zm_motion.py scan --event 123456 --region 800,450,300,200 --verbose
```

Use `--json-out results.json` to capture the peak metric for **every** event
(not just the flagged ones) for offline analysis.

---

## Commands reference

| Command            | Purpose                                                          |
|--------------------|-----------------------------------------------------------------|
| `test-connection`  | Verify config + authentication; print ZM version.               |
| `list-events`      | List events by monitor / time window / minimum duration.        |
| `save-frame`       | Download a single frame (defaults to the event's middle frame). |
| `annotate-region`  | Draw an ROI box on an image to verify coordinates.              |
| `scan`             | The main command: scan events for motion inside the ROI.        |

Run any command with `-h` for its full options, e.g. `python zm_motion.py scan -h`.

---

## Notes, caveats & troubleshooting

- **Timezone:** ZoneMinder stores `StartTime` in the *server's* local time. Pass
  `--start`/`--end` in that same timezone, or you'll select the wrong events.
- **Camera must be static:** pixel-diffing assumes a fixed camera. A PTZ camera
  that moves, or auto-exposure/IR-cut transitions (day↔night), will register as
  ROI "motion." Pick an ROI and threshold that tolerate this, or restrict the
  time window.
- **Purged recordings can't be analyzed:** if `scan` reports `ERROR: Failed to
  fetch frame ...` or events show 0 frames, the underlying JPEGs/MP4s are gone
  (retention, disk full, or hardware failure). The DB event record can survive
  even when the pixel data does not.
- **"no access_token returned":** your ZM is older than 1.34 or has API auth
  disabled. This tool only supports token auth.
- **Login returns non-JSON / 404 on `/api/...`:** your `base_url` prefix is
  wrong — try adding or removing a `/zm` segment.
- **Slow scans:** large time windows × many frames = many HTTP fetches. Narrow
  the window, raise `--sample-every`, or pre-filter with `list-events`.

---

## Provenance

This is a genericized, credential-free rewrite of a one-off investigation script.
Verify behavior against your own ZoneMinder install before relying on results.
