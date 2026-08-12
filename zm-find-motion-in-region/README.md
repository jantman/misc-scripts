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
3. For each event, reads its JPEG frames — from a local copy of the events
   directory if you have one (`--events-dir`), otherwise downloading them via
   the `zms` streaming CGI — iterating the event's full frame range (see
   "ZoneMinder frame quirks" below).
4. Crops every frame to your ROI, converts to grayscale, and computes the
   absolute pixel difference between consecutive frames *inside the ROI only*.
5. Flags events where the fraction of changed ROI pixels exceeds a threshold,
   and reports them sorted by peak change.

Because it works off the stored frames, **it can only analyze events whose
recordings still exist on the server.** Events that ZoneMinder has already
purged (or that were lost to a disk failure) have no frames to analyze.

### ZoneMinder frame quirks (and how this tool handles them)

Getting complete, accurate frame coverage out of ZoneMinder is surprisingly
fiddly; this tool deals with three real behaviors observed on live installs:

- **Sparse frame metadata.** The API's per-event `Frame[]` list only contains a
  record for each *interesting* frame (alarm frames plus a little context) and
  collapses the rest into sparse "Bulk" records — it is **not** a complete frame
  list. Driving analysis off it would skip most of the recording. Instead, for a
  full (`all`) scan this tool iterates the real `1..N` frame range (`N` = the
  event's declared frame count), fetching each frame by number.
- **Black "Failed getting frame" placeholders.** When `zms` cannot extract a
  frame it still returns HTTP 200 with a valid JPEG — a near-black image reading
  *"Failed getting frame"*. Treated naively, the jump from a real frame to this
  black image looks like ~100% motion. The tool detects and skips these (see
  `--blank-mean` / `--blank-std`).
- **Out-of-range frame clamping / static duplicates.** Asking `zms` for a frame
  number past the end of an event returns a copy of an existing frame, and a
  genuinely static scene yields consecutive identical frames. Either way,
  byte-identical consecutive frames carry no motion, so the tool skips them.

The `scan` output reports how many frames were skipped as blank / duplicate so
you can see what happened.

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
| `username`   | A ZoneMinder user with API + view permissions. **Omit** if your install has authentication disabled (`ZM_OPT_USE_AUTH` off) — see below. |
| `password`   | That user's password. Omit alongside `username`.                                                 |
| `verify_ssl` | Set to `false` only for self-signed certs you trust (insecure).                                  |
| `timeout`    | Per-request timeout in seconds.                                                                  |
| `cache_dir`  | Optional. Directory for the on-disk frame cache (see [Frame cache & resuming](#frame-cache--resuming)). Leave `""` to disable, or override per-run with `--cache-dir`. |
| `events_dir` | Optional. Local copy of ZoneMinder's events tree (see [Reading frames from a local events tree](#reading-frames-from-a-local-events-tree)). Leave `""` to disable, or override per-run with `--events-dir`. |

### Installs without authentication

If ZoneMinder is running with `ZM_OPT_USE_AUTH` off, leave `username` and
`password` out of the config entirely; the tool then talks to the API and `zms`
without a token instead of failing on a login the server doesn't want:

```json
{
  "base_url": "http://zoneminder.example.com",
  "events_dir": "/mnt/zm-events"
}
```

`test-connection` tells you which mode it's in.

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

# 6. Turn the numbers back into pictures you can flip through.
python zm_motion.py --cache-dir /big/disk/zm-cache matches \
    --results results.json --min-fraction 0.02 --top 200
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
| `--frame-type`   | `all`   | `all` examines the event's full frame range; `alarm` only examines ZM-flagged alarm frames (faster, but biased toward whatever zones *were* configured — usually you want `all` for non-zone regions). |
| `--sample-every` | `1`     | Examine only every Nth frame. `--sample-every 3` is ~3× faster but may miss brief motion. Each frame is a full-resolution JPEG fetched over HTTP (~0.5–1s each), so this is the main speed lever for long events. |

Two advanced flags control the black-placeholder detector (see "ZoneMinder
frame quirks"). You rarely need to touch these:

| Flag           | Default | Effect                                                                          |
|----------------|---------|---------------------------------------------------------------------------------|
| `--blank-mean` | `6.0`   | A frame is treated as the "Failed getting frame" placeholder and skipped if its mean brightness is below this **and** its std is below `--blank-std`. Set `0` to disable placeholder skipping entirely. |
| `--blank-std`  | `10.0`  | The standard-deviation half of the blank test. Requiring low std as well as low brightness prevents a genuinely dark-but-textured night frame from being discarded. |

**Recommended workflow for tuning:** pick one event you *know* has the motion
you care about and one you know doesn't, run `scan --event <id> --verbose` on
each, and look at the per-frame percentages. Set `--min-fraction` between the two.

```bash
python zm_motion.py scan --event 123456 --region 800,450,300,200 --verbose
```

Use `--json-out results.json` to capture the peak metric for **every** event
(not just the flagged ones) for offline analysis.

---

## Frame cache & resuming

Downloading frames is by far the slowest part of a scan (each frame is a
full-resolution JPEG fetched over HTTP, ~0.5–1s each), and a large time window
can be **hundreds of thousands** of frames. To make big jobs practical and
interruptible, the tool can cache frames on disk.

Point it at a cache directory — either `--cache-dir PATH` (global flag, goes
*before* the subcommand) or `"cache_dir"` in the config:

```bash
# Pre-download every frame in the window into the cache (resumable, 8 at a time):
python zm_motion.py --cache-dir /big/disk/zm-cache download \
    --monitor 1 --start "2026-06-07 14:00:00" --end "2026-06-07 22:00:00" \
    --workers 8

# Then scan — frames are read from disk, so this is fast and re-runnable:
python zm_motion.py --cache-dir /big/disk/zm-cache scan \
    --monitor 1 --start "2026-06-07 14:00:00" --end "2026-06-07 22:00:00" \
    --region 1488,604,136,223 --json-out results.json
```

How it works:

- Frames are stored as `<cache-dir>/<event_id>/<frame_id>.jpg`. Writes are
  atomic (`.tmp` then rename), so an interrupted download never leaves a partial
  file that a later run would trust.
- `fetch_frame` reads the cache first; any command (`scan`, `save-frame`,
  `download`) that needs a cached frame loads it from disk instead of the network.
- **Resuming:** re-running `download` (or `scan`) skips frames already on disk,
  so an interrupted run picks up where it left off — only the missing frames are
  fetched.
- `download` and `scan` should use the **same** `--frame-type` / `--sample-every`,
  or just download at the default (full coverage) so any later scan sampling is
  already cached. If a scan needs a frame that isn't cached, it simply downloads
  (and caches) it on the fly.
- Disk use: full-res JPEGs run ~600 KB each, so budget accordingly (e.g. ~600 MB
  per 1000 frames). The cache is plain files — delete the directory (or a single
  `<event_id>/` subdir) to reclaim space.

Without a cache dir the tool behaves as before: frames are fetched into memory,
used once, and discarded (nothing persists between runs).

### Downloading in parallel

`download` fetches `--workers` frames at a time (default `4`). Frame fetches are
almost entirely latency — request, wait for `zms` to decode one JPEG, receive —
so parallelism is close to a linear speedup on the wall clock.

Each concurrent request spawns a **`zms` process on the ZoneMinder server**, so
this trades server load for your time. `8` is reasonable on a healthy box; back
off if the ZM UI gets sluggish or you start seeing errors. `--workers 1` restores
fully serial downloading.

Progress is still reported per event, in order, however many workers are running
— results are consumed in submission order, so a fast later event never jumps the
line in the log. A frame that fails (HTTP 500, connection reset, non-JPEG body)
is counted as an error and skipped, never cached, so a later run retries it.

`scan` itself is deliberately single-threaded: it diffs *consecutive* frames, so
it has to see them in order. The intended pattern for a big job is a parallel
`download` to fill the cache, then a `scan` that reads from disk.

### Fetching at reduced scale

The global `--scale PCT` flag (default `100`) asks `zms` to render frames at a
percentage of source resolution. `--scale 50` is roughly a 4× reduction in bytes
and decode time, which matters a lot across hundreds of thousands of frames.

```bash
python zm_motion.py --cache-dir /big/disk/zm-cache --scale 50 download \
    --monitor 1 --start "2026-06-07 14:00:00" --end "2026-06-07 22:00:00" --workers 8
```

Two things to keep straight:

- **ROI coordinates are in scaled pixels.** At `--scale 50` every coordinate
  halves, so a full-size ROI of `1488,604,136,223` becomes `744,302,68,111`. The
  simplest way to avoid arithmetic errors is to pass the same `--scale` to
  `save-frame`, pick the ROI off *that* image, and use the same `--scale` for
  `scan`.
- **Scaled frames are cached separately.** They're stored as
  `<frame_id>@<scale>.jpg`, so a 50%-scale download can never be silently served
  to a full-scale scan. Full-size frames keep the plain `<frame_id>.jpg` name, so
  caches created before this flag existed stay valid.

Downscaling also lowers sensitivity slightly — fine detail is averaged away
before the diff — so re-tune `--min-fraction` if you switch scales mid-campaign.

---

## Reading frames from a local events tree

If you have ZoneMinder's events directory available locally — an NFS/SMB mount,
a snapshot, a restored backup, or because you're running this *on* the ZM box —
point `--events-dir` at it and frames are read straight off disk. No HTTP, no
`zms` processes, no frame cache needed:

```bash
python zm_motion.py --events-dir /mnt/zm-events scan --monitor 6 \
    --start "2026-08-04 00:00:00" --end "2026-08-04 05:00:00" \
    --region 700,300,500,400 --json-out results.json
```

This is *much* faster than fetching, and it's the same pixels: a local scan and
an HTTP scan of the same event produce byte-identical diff metrics. Measured
against a 1920×1080 monitor over NFS, a 100-frame event took ~2.5 s locally
versus ~1 minute of frame fetches.

Point `--events-dir` at the directory that holds the **per-monitor
subdirectories** — the local equivalent of `/var/cache/zoneminder/events`:

```
/mnt/zm-events/
    6/                                  <- monitor id
        2026-08-04/                     <- event date
            1647875/                    <- event id
                00001-capture.jpg
                00001-analyse.jpg
                ...
```

Details:

- **All three ZM storage schemes work** (`Deep`, `Medium`, `Shallow`). The tool
  re-roots the server-side path ZoneMinder reports for each event
  (`FileSystemPath`) onto your local directory, so it doesn't matter that the
  server calls it `/var/cache/zoneminder/events` and you mounted it somewhere
  else. Older ZM APIs that don't report that path fall back to rebuilding it
  from the monitor, date, and event id.
- **`-capture.jpg` is used** — the raw recorded frame. If a monitor was
  configured to save only analysis JPEGs, the tool falls back to `-analyse.jpg`
  and says so once: those images have ZoneMinder's motion boxes and zone
  outlines drawn onto them, which is genuine pixel change inside an ROI.
- **Anything missing locally still falls back to HTTP.** A partially mounted or
  partially pruned archive just works; `scan` prints how many events it located
  locally up front. `download` skips frames that are already on the mount.
- **No frame cache is needed.** Frames read locally are not copied into
  `--cache-dir` — they're already files on disk. `matches` links straight at the
  events tree.
- **Not combinable with `--scale`.** Frames on disk are always full resolution,
  so mixing them with downscaled fetched frames would make ROI coordinates mean
  two different things. The tool rejects the combination rather than guessing.
- **Read-only is fine** — nothing is ever written to the events tree.

`test-connection` verifies the mount as well as the API, resolving a real event
and one of its frames so you find out immediately if the path is wrong:

```
$ python zm_motion.py --events-dir /mnt/zm-events test-connection
OK — reaching http://zoneminder.example.com without authentication
ZoneMinder version: 1.38.3, API: 2.0

Local events tree: /mnt/zm-events
  event 1677802 -> /mnt/zm-events/16/2026-08-12/1677802
  frame 1 -> /mnt/zm-events/16/2026-08-12/1677802/00001-capture.jpg
```

The API is still used to *list* events and their metadata — only the frame
images come from disk — so `base_url` is required either way.

---

## Reviewing hits: the `matches` command

`scan --json-out` gives you numbers. `matches` turns them back into pictures:
it symlinks the single peak frame of every flagged event into one directory,
named so that **a filename sort is a score sort**.

```bash
python zm_motion.py --cache-dir /big/disk/zm-cache matches \
    --results results.json --min-fraction 0.05 --top 200 --clear
```

```
matches/
    040.12pct_eid00001234_f000002.jpg -> /big/disk/zm-cache/1234/2.jpg
    015.00pct_eid00001240_f000007.jpg -> /big/disk/zm-cache/1240/7.jpg
    007.31pct_eid00001301_f000003.jpg -> /big/disk/zm-cache/1301/3.jpg
```

Open the directory in any image browser (geeqie, gthumb, nautilus, even GIMP)
and page through candidates strongest-first. This is usually much faster than
opening events one at a time in the ZoneMinder UI.

- `--min-fraction` / `--top` re-filter the *existing* results file — no rescan
  needed, so you can tighten or loosen the cut in seconds.
- Links point at the local events tree when `--events-dir` is set, otherwise at
  the cache. With `--events-dir` no cache or downloads are involved at all.
- A peak frame that's in neither place is downloaded into the cache (just one
  frame per event, so this is cheap even after a cacheless scan). `--no-fetch`
  skips them instead.
- `--clear` removes existing symlinks from the output directory first. It only
  ever unlinks symlinks — a real file in there is never touched.
- Requires a cache directory, since that's what the links point into.

---

## Commands reference

| Command            | Purpose                                                          |
|--------------------|-----------------------------------------------------------------|
| `test-connection`  | Verify config + authentication; print ZM version.               |
| `list-events`      | List events by monitor / time window / minimum duration.        |
| `save-frame`       | Download a single frame (defaults to the event's middle frame). |
| `annotate-region`  | Draw an ROI box on an image to verify coordinates.              |
| `scan`             | The main command: scan events for motion inside the ROI.        |
| `download`         | Pre-fetch event frames into the cache dir (parallel, resumable). |
| `matches`          | Symlink flagged events' peak frames into one directory to browse. |

Run any command with `-h` for its full options, e.g. `python zm_motion.py scan -h`.
The `--config`, `--cache-dir`, `--events-dir`, and `--scale` flags are global and
go *before* the subcommand.

---

## Notes, caveats & troubleshooting

- **Timezone:** ZoneMinder stores `StartTime` in the *server's* local time. Pass
  `--start`/`--end` in that same timezone, or you'll select the wrong events.
- **Camera must be static:** pixel-diffing assumes a fixed camera. A PTZ camera
  that moves, or auto-exposure/IR-cut transitions (day↔night), will register as
  ROI "motion." Pick an ROI and threshold that tolerate this, or restrict the
  time window.
- **Purged recordings can't be analyzed:** if `scan` reports `no usable frames`
  (all frames blank/duplicate/unreadable) or events show 0 frames, the underlying
  JPEGs/MP4s are gone (retention, disk full, or hardware failure). The DB event
  record can survive even when the pixel data does not.
- **Lots of "blank" or "duplicate" skips is normal:** the per-event summary
  counts frames skipped as ZM placeholders (blank) or static/clamped repeats
  (duplicate). A static scene legitimately produces many duplicates — those carry
  no motion, so skipping them costs nothing. If a *real* dark scene is being
  wrongly skipped as blank, lower `--blank-mean` (or set it to `0` to disable).
- **"no access_token returned":** your ZM is older than 1.34 or has API auth
  disabled. This tool only supports token auth.
- **Login returns non-JSON / 404 on `/api/...`:** your `base_url` prefix is
  wrong — try adding or removing a `/zm` segment.
- **Slow scans:** large time windows × many frames = many HTTP fetches. If you
  can mount the events directory, `--events-dir` removes the fetching entirely
  and is by far the biggest win — see
  [Reading frames from a local events tree](#reading-frames-from-a-local-events-tree).
  Otherwise: narrow the window, raise `--sample-every`, pre-filter with
  `list-events`, and use a `--cache-dir` (plus the `download` command) so frames
  are fetched once and reused — see
  [Frame cache & resuming](#frame-cache--resuming). For big fetching jobs,
  `download --workers 8 --scale 50` is the largest lever available.

---

## Provenance

This is a genericized, credential-free rewrite of a one-off investigation script.
Verify behavior against your own ZoneMinder install before relying on results.
