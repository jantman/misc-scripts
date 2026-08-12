#!/usr/bin/env python3
"""
zm_motion.py — Find ZoneMinder events with motion in an arbitrary region of the frame.

ZoneMinder's built-in motion detection only scores motion inside *configured zones*.
This tool lets you scan recorded events for image changes inside an arbitrary
rectangular Region Of Interest (ROI) that is NOT set up as a zone — useful for
after-the-fact investigations ("did anything move in *that* corner of the frame
between these two dates?").

It works by pulling the JPEG frames of each event from the ZM web API, cropping
each frame to your ROI, and computing a frame-to-frame pixel difference inside the
crop. Events whose ROI difference exceeds a threshold are reported.

No URLs, credentials, or other site-specific values are baked in — everything
comes from a JSON config file (see zm_config.example.json) or CLI flags.

See README.md for full usage, including how to find your ROI coordinates.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import quote

try:
    import requests
except ImportError:
    sys.exit("Missing dependency 'requests'. Run: pip install -r requirements.txt")

try:
    import numpy as np
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit("Missing dependency 'Pillow'/'numpy'. Run: pip install -r requirements.txt")


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

DEFAULT_CONFIG_PATH = os.environ.get("ZM_CONFIG", "zm_config.json")


@dataclass
class Config:
    base_url: str
    username: str
    password: str
    verify_ssl: bool = True
    timeout: int = 30
    cache_dir: str | None = None

    @classmethod
    def load(cls, path: str) -> "Config":
        if not os.path.exists(path):
            sys.exit(
                f"Config file not found: {path}\n"
                "Copy zm_config.example.json to zm_config.json and fill it in, "
                "or pass --config / set $ZM_CONFIG."
            )
        with open(path) as fh:
            data = json.load(fh)
        missing = [k for k in ("base_url", "username", "password") if not data.get(k)]
        if missing:
            sys.exit(f"Config {path} is missing required keys: {', '.join(missing)}")
        return cls(
            base_url=data["base_url"].rstrip("/"),
            username=data["username"],
            password=data["password"],
            verify_ssl=data.get("verify_ssl", True),
            timeout=int(data.get("timeout", 30)),
            cache_dir=data.get("cache_dir") or None,
        )


# --------------------------------------------------------------------------- #
# ZoneMinder API client
# --------------------------------------------------------------------------- #


class ZMClient:
    """Minimal ZoneMinder API client.

    Deliberately uses the bare base_url with no '/zm/' path prefix — many ZM
    installs (and reverse-proxied ones) serve the API at the web root. If your
    install lives under '/zm', just include that in base_url in the config.
    """

    def __init__(self, cfg: Config, cache_dir: str | None = None, scale: int = 100):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.verify = cfg.verify_ssl
        self._local = threading.local()
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = threading.Lock()
        # Directory for the on-disk frame cache (None disables caching). Frames
        # are stored as <cache_dir>/<event_id>/<frame_id>.jpg.
        self.cache_dir = cache_dir or cfg.cache_dir
        # Percent scale applied by zms when rendering frames (100 = source size).
        self.scale = scale

    def _session(self) -> requests.Session:
        """Return a Session owned by the calling thread.

        requests.Session is not documented as thread-safe — its cookie jar and
        redirect/auth state are mutated per request — so the threaded downloader
        gives each worker its own. The main thread keeps self.session, which is
        what every single-threaded code path uses.
        """
        if threading.current_thread() is threading.main_thread():
            return self.session
        sess = getattr(self._local, "session", None)
        if sess is None:
            sess = requests.Session()
            sess.verify = self.cfg.verify_ssl
            self._local.session = sess
        return sess

    # -- auth ------------------------------------------------------------- #

    def login(self) -> str:
        """Authenticate and return an access token (cached until near expiry).

        The token is shared by every thread, so refreshes are serialized: without
        the lock, N workers hitting expiry at once would each POST a login.
        """
        now = time.time()
        if self._access_token and now < self._token_expires_at - 60:
            return self._access_token

        with self._token_lock:
            # Re-check under the lock — another thread may have just refreshed.
            now = time.time()
            if self._access_token and now < self._token_expires_at - 60:
                return self._access_token

            url = f"{self.cfg.base_url}/api/host/login.json"
            resp = self._session().post(
                url,
                data={"user": self.cfg.username, "pass": self.cfg.password},
                timeout=self.cfg.timeout,
            )
            if resp.status_code != 200:
                sys.exit(
                    f"Login failed ({resp.status_code}) at {url}\n"
                    f"Response: {resp.text[:500]}"
                )
            try:
                payload = resp.json()
            except ValueError:
                sys.exit(f"Login response was not JSON. Check base_url. Body:\n{resp.text[:500]}")

            token = payload.get("access_token")
            if not token:
                # Older ZM (<1.34) used cookie auth; not supported here.
                sys.exit(
                    "Login succeeded but no 'access_token' was returned. "
                    "This tool requires ZoneMinder 1.34+ token auth.\n"
                    f"Payload keys: {list(payload.keys())}"
                )
            self._access_token = token
            # access_token_expires is seconds-from-now (commonly 7200).
            expires_in = float(payload.get("access_token_expires", 3600))
            self._token_expires_at = now + expires_in
            return token

    # -- low-level GET ---------------------------------------------------- #

    def _api_get(self, path: str) -> dict[str, Any]:
        token = self.login()
        sep = "&" if "?" in path else "?"
        url = f"{self.cfg.base_url}{path}{sep}token={token}"
        resp = self._session().get(url, timeout=self.cfg.timeout)
        if resp.status_code != 200:
            sys.exit(f"API GET failed ({resp.status_code}): {url}\n{resp.text[:500]}")
        return resp.json()

    # -- events ----------------------------------------------------------- #

    def list_events(
        self,
        monitor_id: int | None,
        start: str | None,
        end: str | None,
        min_duration: float | None = None,
    ) -> list[dict[str, Any]]:
        """Return event records matching the filters.

        Note the URL-encoded space (%20) between field and operator — without it,
        some ZM installs silently ignore the condition.
        """
        conditions: list[str] = []
        if monitor_id is not None:
            conditions.append(f"MonitorId:{monitor_id}")
        if start:
            conditions.append("StartTime %3E=:" + start)  # >=
        if end:
            conditions.append("StartTime %3C=:" + end)  # <=

        # Build path; encode each condition segment but keep '/' separators.
        cond_path = "/".join(quote(c, safe=":%") for c in conditions)
        base = "/api/events/index"
        if cond_path:
            base = f"{base}/{cond_path}"

        events: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self._api_get(f"{base}.json?page={page}&sort=StartTime&direction=asc")
            chunk = [e["Event"] for e in payload.get("events", [])]
            events.extend(chunk)
            pagination = payload.get("pagination", {})
            page_count = pagination.get("pageCount") or 1
            if page >= page_count:
                break
            page += 1

        if min_duration is not None:
            events = [
                e for e in events
                if e.get("Length") is not None and float(e["Length"]) >= min_duration
            ]
        return events

    def get_event(self, event_id: int) -> dict[str, Any]:
        """Return {'Event': {...}, 'Frame': [...], ...} for one event.

        The API wraps the record in a top-level 'event' key; unwrap it so
        callers can read ['Event'] / ['Frame'] directly.
        """
        payload = self._api_get(f"/api/events/{event_id}.json")
        return payload.get("event", payload)

    # -- frames (images) -------------------------------------------------- #

    def frame_cache_path(self, event_id: int, frame_id: int) -> str | None:
        """Path this frame would occupy in the on-disk cache (None if disabled).

        Scaled frames get a '@<scale>' suffix so that images fetched at
        different --scale values never collide in one cache (a 50%-scale JPEG
        served up to a full-scale scan would silently break ROI coordinates).
        Full-scale frames keep the plain name, so caches predating --scale
        remain valid.
        """
        if not self.cache_dir:
            return None
        name = f"{frame_id}.jpg" if self.scale == 100 else f"{frame_id}@{self.scale}.jpg"
        return os.path.join(self.cache_dir, str(event_id), name)

    def fetch_frame(self, event_id: int, frame_id: int) -> Image.Image:
        """Return a single JPEG frame, reading the on-disk cache first.

        Frames are fetched via /cgi-bin/zms (the portable way to pull one frame
        out of a stored event; the web /index.php?view=image path 404s on some
        installs). When a cache_dir is configured, a previously downloaded frame
        is loaded from disk instead of re-fetched, and freshly downloaded frames
        are written to disk — so an interrupted scan/download resumes without
        re-downloading what it already has.
        """
        cache_path = self.frame_cache_path(event_id, frame_id)
        if cache_path and os.path.exists(cache_path):
            try:
                return Image.open(cache_path).convert("RGB")
            except Exception:
                # Corrupt/partial cache file — fall through and re-download.
                pass

        token = self.login()
        url = (
            f"{self.cfg.base_url}/cgi-bin/zms"
            f"?mode=single&source=event&event={event_id}&frame={frame_id}&token={token}"
        )
        if self.scale != 100:
            url += f"&scale={self.scale}"
        resp = self._session().get(url, timeout=self.cfg.timeout)
        if resp.status_code != 200 or not resp.content:
            raise RuntimeError(
                f"Failed to fetch frame {frame_id} of event {event_id} "
                f"(HTTP {resp.status_code}, {len(resp.content)} bytes)"
            )
        if not resp.content.startswith(b"\xff\xd8"):
            # zms occasionally answers 200 with an HTML error page rather than a
            # JPEG; caching that would poison every later run for this frame.
            raise RuntimeError(
                f"Frame {frame_id} of event {event_id} was not a JPEG "
                f"({len(resp.content)} bytes)"
            )

        if cache_path:
            # Write atomically so an interrupted write never leaves a partial
            # JPEG that a later run would treat as a valid cached frame.
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            # Thread id in the temp name so two workers racing on the same frame
            # cannot write each other's partial file before the rename.
            tmp = f"{cache_path}.{threading.get_ident()}.tmp"
            with open(tmp, "wb") as fh:
                fh.write(resp.content)
            os.replace(tmp, cache_path)

        from io import BytesIO
        return Image.open(BytesIO(resp.content)).convert("RGB")


# --------------------------------------------------------------------------- #
# Region / image analysis
# --------------------------------------------------------------------------- #


@dataclass
class Region:
    x: int
    y: int
    w: int
    h: int

    @classmethod
    def parse(cls, spec: str) -> "Region":
        try:
            x, y, w, h = (int(v.strip()) for v in spec.split(","))
        except ValueError:
            sys.exit(f"Invalid --region '{spec}'. Expected 'X,Y,W,H' (pixels), e.g. 100,200,300,150")
        if w <= 0 or h <= 0:
            sys.exit("--region width and height must be positive")
        return cls(x, y, w, h)

    @property
    def box(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.w, self.y + self.h)

    @property
    def area(self) -> int:
        return self.w * self.h


def roi_diff(a: np.ndarray, b: np.ndarray, pixel_threshold: int) -> dict[str, float]:
    """Compare two equally-sized grayscale ROI arrays.

    Returns metrics describing how much changed:
      changed_pixels   — number of pixels whose abs difference exceeds the threshold
      changed_fraction — changed_pixels / total pixels (0..1)
      mean_diff        — mean absolute difference across the ROI
    """
    if a.shape != b.shape:
        # Resolution changed mid-event (rare); resize b onto a.
        b = np.asarray(
            Image.fromarray(b.astype(np.uint8)).resize((a.shape[1], a.shape[0])),
            dtype=np.float32,
        )
    diff = np.abs(a - b)
    changed = int(np.count_nonzero(diff > pixel_threshold))
    total = a.size or 1
    return {
        "changed_pixels": float(changed),
        "changed_fraction": changed / total,
        "mean_diff": float(diff.mean()),
    }


def is_blank_frame(gray: np.ndarray, blank_mean: float, blank_std: float) -> bool:
    """Detect ZoneMinder's "Failed getting frame" placeholder image.

    When zms cannot extract a frame it returns, with HTTP 200 and a valid JPEG
    body, a near-black image bearing the text "Failed getting frame". If treated
    as real data, the transition real-frame -> black-placeholder registers as
    massive (false) motion. The placeholder is near-uniform and near-black
    (mean ~1, std ~4), which is easily separated from real frames (even dark
    night scenes carry sensor noise / scene texture, giving much higher std).

    A frame is flagged blank only if BOTH its mean brightness and its standard
    deviation fall below the thresholds, so a merely-dark-but-textured real
    frame is not discarded. Set blank_mean <= 0 to disable the check.
    """
    if blank_mean <= 0:
        return False
    return float(gray.mean()) < blank_mean and float(gray.std()) < blank_std


def select_frame_ids(
    total_frames: int,
    frame_records: list[dict[str, Any]],
    frame_type: str,
    sample_every: int,
) -> list[int]:
    """Return the list of FrameIds to examine.

    ZoneMinder only keeps an individual DB record per "interesting" frame
    (alarm frames plus a little context) and collapses the rest into sparse
    "Bulk" records — so the Frame[] metadata is NOT a complete frame list.
    The actual JPEGs, however, are all retrievable by number via zms, so for
    a full ('all') scan we iterate the real 1..total_frames range to get
    complete coverage and proper consecutive-frame diffs.

    For an 'alarm' scan we use the DB records (only alarm frames have them),
    falling back to the full range if none are present.
    """
    if frame_type == "alarm":
        ids = sorted(
            int(f["FrameId"])
            for f in frame_records
            if str(f.get("Type", "")).lower() == "alarm"
        )
        if not ids:  # no alarm records — fall back to a full scan
            ids = list(range(1, total_frames + 1))
    else:
        if total_frames > 0:
            ids = list(range(1, total_frames + 1))
        else:  # no count available — fall back to whatever records exist
            ids = sorted(int(f["FrameId"]) for f in frame_records)

    if sample_every > 1:
        ids = ids[::sample_every]
    return ids


@dataclass
class EventResult:
    event_id: int
    name: str
    start_time: str
    length: float
    max_changed_fraction: float
    max_changed_pixels: float
    peak_frame_id: int | None
    frames_examined: int
    blank_frames: int = 0
    duplicate_frames: int = 0
    fetch_errors: int = 0
    error: str | None = None


def analyze_event(
    client: ZMClient,
    event: dict[str, Any],
    region: Region,
    pixel_threshold: int,
    frame_type: str,
    sample_every: int,
    blank_mean: float = 6.0,
    blank_std: float = 10.0,
    verbose: bool = False,
) -> EventResult:
    eid = int(event["Id"])
    detail = client.get_event(eid)
    frame_records = detail.get("Frame") or []
    total_frames = int(event.get("Frames") or detail.get("Event", {}).get("Frames") or 0)
    chosen = select_frame_ids(total_frames, frame_records, frame_type, sample_every)

    res = EventResult(
        event_id=eid,
        name=event.get("Name", ""),
        start_time=event.get("StartTime", ""),
        length=float(event.get("Length") or 0.0),
        max_changed_fraction=0.0,
        max_changed_pixels=0.0,
        peak_frame_id=None,
        frames_examined=0,
    )

    if not chosen:
        res.error = "no frames"
        return res

    prev: np.ndarray | None = None
    prev_hash: int | None = None
    for fid in chosen:
        try:
            img = client.fetch_frame(eid, fid)
        except RuntimeError:
            # A single unreadable frame shouldn't abort the whole event; skip
            # it. The diff resumes from the next successfully fetched frame.
            res.fetch_errors += 1
            prev = None
            continue

        gray_full = np.asarray(img.convert("L"), dtype=np.float32)

        # Skip ZoneMinder's "Failed getting frame" black placeholder, which zms
        # serves (HTTP 200, valid JPEG) when it cannot extract a real frame.
        if is_blank_frame(gray_full, blank_mean, blank_std):
            res.blank_frames += 1
            prev = None
            continue

        # Skip clamp/duplicate frames. zms clamps an out-of-range frame number
        # to an existing frame, so consecutive byte-identical frames are not
        # real motion data — drop them (they only ever yield zero diff anyway).
        cur_hash = hash(gray_full.tobytes())
        if prev_hash is not None and cur_hash == prev_hash:
            res.duplicate_frames += 1
            continue
        prev_hash = cur_hash

        cur = gray_full[region.y:region.y + region.h, region.x:region.x + region.w]
        if prev is not None:
            m = roi_diff(prev, cur, pixel_threshold)
            res.frames_examined += 1
            if m["changed_fraction"] > res.max_changed_fraction:
                res.max_changed_fraction = m["changed_fraction"]
                res.max_changed_pixels = m["changed_pixels"]
                res.peak_frame_id = fid
            if verbose:
                print(
                    f"    event {eid} frame {fid}: "
                    f"changed={m['changed_fraction']*100:.2f}% "
                    f"({int(m['changed_pixels'])}px) mean={m['mean_diff']:.1f}"
                )
        prev = cur

    if res.frames_examined == 0:
        res.error = (
            f"no usable frames (blank={res.blank_frames}, "
            f"dup={res.duplicate_frames}, fetch_errors={res.fetch_errors})"
        )
    elif verbose and (res.blank_frames or res.duplicate_frames or res.fetch_errors):
        print(
            f"    event {eid}: skipped {res.blank_frames} blank, "
            f"{res.duplicate_frames} duplicate, {res.fetch_errors} unreadable; "
            f"analyzed {res.frames_examined} pair(s)"
        )
    return res


# --------------------------------------------------------------------------- #
# Subcommands
# --------------------------------------------------------------------------- #


def make_client(args: argparse.Namespace) -> ZMClient:
    """Build a ZMClient, letting a --cache-dir flag override the config value."""
    cfg = Config.load(args.config)
    scale = int(getattr(args, "scale", 100) or 100)
    if not 1 <= scale <= 400:
        sys.exit("--scale must be between 1 and 400 (percent); anything over 100 upscales.")
    return ZMClient(cfg, cache_dir=getattr(args, "cache_dir", None), scale=scale)


def cmd_test_connection(args: argparse.Namespace) -> int:
    client = make_client(args)
    token = client.login()
    print(f"OK — authenticated to {client.cfg.base_url}")
    print(f"Access token (truncated): {token[:24]}...")
    # Sanity check an API read.
    version = client._api_get("/api/host/getVersion.json")
    print(f"ZoneMinder version: {version.get('version', '?')}, API: {version.get('apiversion', '?')}")
    return 0


def cmd_list_events(args: argparse.Namespace) -> int:
    client = make_client(args)
    events = client.list_events(args.monitor, args.start, args.end, args.min_duration)
    if not events:
        print("No events matched.")
        return 0
    print(f"{'EventId':>8}  {'StartTime':<20} {'Len(s)':>7}  {'Frames':>6}  Name")
    print("-" * 70)
    for e in events:
        print(
            f"{e['Id']:>8}  {e.get('StartTime',''):<20} "
            f"{float(e.get('Length') or 0):>7.1f}  "
            f"{e.get('Frames') or '?':>6}  {e.get('Name','')}"
        )
    print(f"\n{len(events)} event(s).")
    return 0


def cmd_save_frame(args: argparse.Namespace) -> int:
    client = make_client(args)
    frame_id = args.frame
    if frame_id is None:
        # Default to a middle frame so the user gets a representative image.
        detail = client.get_event(args.event)
        frames = detail.get("Frame") or []
        if not frames:
            sys.exit(f"Event {args.event} has no frame metadata.")
        frame_id = int(frames[len(frames) // 2]["FrameId"])
        print(f"No --frame given; using middle frame {frame_id}.")
    img = client.fetch_frame(args.event, frame_id)
    img.save(args.output)
    print(f"Saved frame {frame_id} of event {args.event} -> {args.output} ({img.width}x{img.height})")
    return 0


def cmd_annotate_region(args: argparse.Namespace) -> int:
    region = Region.parse(args.region)
    img = Image.open(args.image).convert("RGB")
    draw = ImageDraw.Draw(img)
    draw.rectangle(region.box, outline=(255, 0, 0), width=3)
    label = f"{region.x},{region.y} {region.w}x{region.h}"
    draw.text((region.x + 4, max(0, region.y - 14)), label, fill=(255, 0, 0))
    img.save(args.output)
    print(f"Wrote {args.output} with ROI {label} drawn on {os.path.basename(args.image)}")
    if region.x + region.w > img.width or region.y + region.h > img.height:
        print(
            f"  WARNING: ROI extends beyond image bounds ({img.width}x{img.height}). "
            "It will be clipped during analysis."
        )
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    client = make_client(args)
    region = Region.parse(args.region)

    if args.event:
        events = [client.get_event(args.event)["Event"]]
    else:
        events = client.list_events(args.monitor, args.start, args.end, args.min_duration)

    if not events:
        print("No events matched.")
        return 0

    cache_note = f", cache={client.cache_dir}" if client.cache_dir else ""
    print(
        f"Scanning {len(events)} event(s) for motion in ROI "
        f"{region.x},{region.y} {region.w}x{region.h} "
        f"(pixel_threshold={args.pixel_threshold}, frames={args.frame_type}, "
        f"sample_every={args.sample_every}{cache_note})\n"
    )

    results: list[EventResult] = []
    for i, ev in enumerate(events, 1):
        print(f"[{i}/{len(events)}] event {ev['Id']} ({ev.get('StartTime','')}) ...", flush=True)
        r = analyze_event(
            client, ev, region,
            pixel_threshold=args.pixel_threshold,
            frame_type=args.frame_type,
            sample_every=args.sample_every,
            blank_mean=args.blank_mean,
            blank_std=args.blank_std,
            verbose=args.verbose,
        )
        results.append(r)
        if r.error:
            print(f"      -> ERROR: {r.error}")
        else:
            flag = "  <<< MOTION" if r.max_changed_fraction >= args.min_fraction else ""
            print(
                f"      -> peak {r.max_changed_fraction*100:.2f}% "
                f"({int(r.max_changed_pixels)}px) at frame {r.peak_frame_id} "
                f"over {r.frames_examined} frame-pairs{flag}"
            )

    hits = [r for r in results if not r.error and r.max_changed_fraction >= args.min_fraction]
    hits.sort(key=lambda r: r.max_changed_fraction, reverse=True)

    print("\n" + "=" * 72)
    print(f"RESULTS: {len(hits)} event(s) with ROI motion >= {args.min_fraction*100:.2f}%")
    print("=" * 72)
    print(f"{'EventId':>8}  {'StartTime':<20} {'Peak%':>7} {'PeakFrame':>9}  Name")
    for r in hits:
        print(
            f"{r.event_id:>8}  {r.start_time:<20} "
            f"{r.max_changed_fraction*100:>6.2f}% {str(r.peak_frame_id):>9}  {r.name}"
        )

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(
                [r.__dict__ for r in results],
                fh,
                indent=2,
            )
        print(f"\nFull results (all events) written to {args.json_out}")
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    """Pre-fetch frames into the on-disk cache so a later scan reads from disk.

    Downloading frames is by far the slowest part of a scan, so this lets you
    fill the cache up front (and resume if interrupted — already-cached frames
    are skipped). Use the SAME --frame-type/--sample-every here as you will for
    the scan, or the default full coverage, so the scan actually hits the cache.
    """
    client = make_client(args)
    if not client.cache_dir:
        sys.exit("download requires a cache directory: pass --cache-dir or set cache_dir in the config.")

    if args.event:
        events = [client.get_event(args.event)["Event"]]
    else:
        events = client.list_events(args.monitor, args.start, args.end, args.min_duration)
    if not events:
        print("No events matched.")
        return 0

    workers = max(1, args.workers)

    # Plan the work so we can show meaningful progress.
    plan: list[tuple[int, list[int]]] = []
    if args.frame_type == "alarm":
        # 'alarm' needs one extra API round trip per event to read the frame
        # records; fetch those concurrently too, since it is pure latency.
        def _alarm_ids(ev: dict[str, Any]) -> tuple[int, list[int]]:
            eid = int(ev["Id"])
            total = int(ev.get("Frames") or 0)
            recs = client.get_event(eid).get("Frame") or []
            return eid, select_frame_ids(total, recs, "alarm", args.sample_every)

        with ThreadPoolExecutor(max_workers=workers) as ex:
            plan = list(ex.map(_alarm_ids, events))
    else:
        for ev in events:
            eid = int(ev["Id"])
            total = int(ev.get("Frames") or 0)
            plan.append((eid, select_frame_ids(total, [], "all", args.sample_every)))

    # Drop events with no frames to fetch; the per-event progress below walks
    # `plan` in step with the task stream and an empty entry would desync it.
    empty = [eid for eid, ids in plan if not ids]
    plan = [(eid, ids) for eid, ids in plan if ids]
    if empty:
        print(f"Skipping {len(empty)} event(s) with no frames: {empty[:10]}"
              f"{' ...' if len(empty) > 10 else ''}")

    tasks: list[tuple[int, int]] = [(eid, fid) for eid, ids in plan for fid in ids]
    total_planned = len(tasks)
    scale_note = f", scale={client.scale}%" if client.scale != 100 else ""
    print(
        f"Downloading frames for {len(events)} event(s) into {client.cache_dir}\n"
        f"  frame_type={args.frame_type}, sample_every={args.sample_every}, "
        f"workers={workers}{scale_note}, ~{total_planned} frames planned\n"
    )
    if not tasks:
        print("Nothing to download.")
        return 0

    def download_one(task: tuple[int, int]) -> str:
        eid, fid = task
        path = client.frame_cache_path(eid, fid)
        if path and os.path.exists(path):
            return "cached"
        try:
            client.fetch_frame(eid, fid)  # downloads and writes to cache
            return "downloaded"
        except RuntimeError:
            return "error"
        except requests.RequestException:
            # Connection reset / timeout against a busy zms — one frame's
            # failure shouldn't tear down the whole run.
            return "error"

    downloaded = cached = errors = 0
    done = 0
    ev_index = 0
    ev_dl = ev_cached = ev_err = 0
    ev_seen = 0

    # ThreadPoolExecutor.map yields results in submission order, so tasks stay
    # grouped by event and the per-event summaries below remain accurate and
    # in order regardless of how many workers ran them.
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for (eid, _fid), status in zip(tasks, ex.map(download_one, tasks)):
            done += 1
            ev_seen += 1
            if status == "downloaded":
                downloaded += 1
                ev_dl += 1
            elif status == "cached":
                cached += 1
                ev_cached += 1
            else:
                errors += 1
                ev_err += 1

            if ev_seen == len(plan[ev_index][1]):
                print(
                    f"[{ev_index + 1}/{len(plan)}] event {eid}: "
                    f"downloaded {ev_dl}, already-cached {ev_cached}, errors {ev_err} "
                    f"({ev_seen} frames)",
                    flush=True,
                )
                ev_index += 1
                ev_dl = ev_cached = ev_err = ev_seen = 0

            if done % 200 == 0:
                print(
                    f"  ... {done}/{total_planned} frames "
                    f"(downloaded={downloaded}, cached={cached}, errors={errors})",
                    flush=True,
                )

    print(
        f"\nDone. downloaded={downloaded}, already-cached={cached}, errors={errors} "
        f"of {total_planned} planned frames.\nCache: {client.cache_dir}"
    )
    return 0


def cmd_matches(args: argparse.Namespace) -> int:
    """Symlink each flagged event's peak frame into one directory for review.

    `scan --json-out` gives you numbers; this turns them back into pictures. The
    link names lead with the zero-padded peak percentage, so any image browser
    (geeqie, gthumb, nautilus) sorting by filename shows you the strongest
    candidates first — far faster than opening events one at a time in the ZM UI.
    """
    client = make_client(args)
    if not client.cache_dir:
        sys.exit(
            "matches needs a cache directory to link into: pass --cache-dir or set "
            "cache_dir in the config. Peak frames missing from the cache are fetched "
            "into it (one frame per event) unless --no-fetch is given."
        )

    if not os.path.exists(args.results):
        sys.exit(f"Results file not found: {args.results} (create it with 'scan --json-out')")
    with open(args.results) as fh:
        results = json.load(fh)
    if not isinstance(results, list):
        sys.exit(f"{args.results} is not a scan results list (expected a JSON array).")

    rows = [
        r for r in results
        if not r.get("error")
        and r.get("peak_frame_id") is not None
        and float(r.get("max_changed_fraction") or 0.0) >= args.min_fraction
    ]
    rows.sort(key=lambda r: float(r["max_changed_fraction"]), reverse=True)
    if args.top is not None:
        rows = rows[: args.top]

    if not rows:
        print(
            f"No events in {args.results} reached {args.min_fraction * 100:.2f}%. "
            "Lower --min-fraction to widen the net."
        )
        return 0

    os.makedirs(args.out, exist_ok=True)
    if args.clear:
        # Only ever unlink symlinks — never a real file that happens to live here.
        removed = 0
        for name in os.listdir(args.out):
            path = os.path.join(args.out, name)
            if os.path.islink(path):
                os.unlink(path)
                removed += 1
        if removed:
            print(f"Cleared {removed} existing symlink(s) from {args.out}/")

    linked = fetched = missing = 0
    for r in rows:
        eid = int(r["event_id"])
        fid = int(r["peak_frame_id"])
        pct = float(r["max_changed_fraction"]) * 100.0

        path = client.frame_cache_path(eid, fid)
        if not os.path.exists(path):
            if args.no_fetch:
                missing += 1
                continue
            try:
                client.fetch_frame(eid, fid)  # writes into the cache
                fetched += 1
            except (RuntimeError, requests.RequestException) as exc:
                print(f"  event {eid} frame {fid}: {exc}")
                missing += 1
                continue

        # Pad the percentage so a lexical filename sort matches score order.
        link = os.path.join(args.out, f"{pct:06.2f}pct_eid{eid:08d}_f{fid:06d}.jpg")
        if os.path.islink(link) or os.path.exists(link):
            os.unlink(link)
        os.symlink(os.path.abspath(path), link)
        linked += 1

    print(
        f"\nLinked {linked} frame(s) into {args.out}/ "
        f"(fetched {fetched} not already cached, {missing} unavailable)."
    )
    print(f"Browse them sorted by name — highest ROI change first: {os.path.abspath(args.out)}")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="zm_motion.py",
        description="Find ZoneMinder events with motion in an arbitrary (non-zone) region of the frame.",
    )
    p.add_argument(
        "--config", default=DEFAULT_CONFIG_PATH,
        help=f"Path to JSON config (default: {DEFAULT_CONFIG_PATH} or $ZM_CONFIG)",
    )
    p.add_argument(
        "--cache-dir", default=None,
        help="Directory for the on-disk frame cache (overrides 'cache_dir' in the "
             "config). Frames are stored as <cache-dir>/<event_id>/<frame_id>.jpg and "
             "reused on later runs, so scans/downloads resume without re-downloading.",
    )
    p.add_argument(
        "--scale", type=int, default=100, metavar="PCT",
        help="Percent scale zms renders frames at (default 100 = source resolution). "
             "50 quarters the bytes and speeds downloads up substantially, but ROI "
             "coordinates are in SCALED pixels — use the same --scale for save-frame, "
             "download, and scan. Scaled frames are cached separately from full-size ones.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # test-connection
    sp = sub.add_parser("test-connection", help="Verify config + authentication.")
    sp.set_defaults(func=cmd_test_connection)

    # list-events
    sp = sub.add_parser("list-events", help="List events matching monitor / time filters.")
    sp.add_argument("--monitor", type=int, help="Monitor ID (e.g. 6)")
    sp.add_argument("--start", help="StartTime >= (ZM server local time, 'YYYY-MM-DD HH:MM:SS')")
    sp.add_argument("--end", help="StartTime <= (ZM server local time, 'YYYY-MM-DD HH:MM:SS')")
    sp.add_argument("--min-duration", type=float, help="Only events at least N seconds long")
    sp.set_defaults(func=cmd_list_events)

    # save-frame
    sp = sub.add_parser("save-frame", help="Download one frame (to pick ROI coordinates from).")
    sp.add_argument("--event", type=int, required=True, help="Event ID")
    sp.add_argument("--frame", type=int, help="FrameId (default: middle frame of the event)")
    sp.add_argument("-o", "--output", default="frame.jpg", help="Output image path (default frame.jpg)")
    sp.set_defaults(func=cmd_save_frame)

    # annotate-region
    sp = sub.add_parser("annotate-region", help="Draw an ROI box on an image to verify coordinates.")
    sp.add_argument("--image", required=True, help="Input image (e.g. one saved by save-frame)")
    sp.add_argument("--region", required=True, help="ROI as 'X,Y,W,H' in pixels")
    sp.add_argument("-o", "--output", default="region.jpg", help="Annotated output (default region.jpg)")
    sp.set_defaults(func=cmd_annotate_region)

    # scan
    sp = sub.add_parser("scan", help="Scan events for motion inside the ROI (the main command).")
    sp.add_argument("--region", required=True, help="ROI as 'X,Y,W,H' in pixels")
    grp = sp.add_argument_group("event selection")
    grp.add_argument("--event", type=int, help="Scan a single event ID (overrides the filters below)")
    grp.add_argument("--monitor", type=int, help="Monitor ID")
    grp.add_argument("--start", help="StartTime >= (ZM server local time)")
    grp.add_argument("--end", help="StartTime <= (ZM server local time)")
    grp.add_argument("--min-duration", type=float, help="Only events at least N seconds long")
    tune = sp.add_argument_group("detection tuning")
    tune.add_argument(
        "--pixel-threshold", type=int, default=25,
        help="Per-pixel grayscale delta (0-255) that counts as 'changed' (default 25)",
    )
    tune.add_argument(
        "--min-fraction", type=float, default=0.02,
        help="Fraction of ROI pixels (0-1) that must change to flag an event (default 0.02 = 2%%)",
    )
    tune.add_argument(
        "--frame-type", choices=["all", "alarm"], default="all",
        help="Examine all frames or only ZM 'alarm' frames (default all)",
    )
    tune.add_argument(
        "--sample-every", type=int, default=1,
        help="Only examine every Nth selected frame (speeds up long events; default 1)",
    )
    tune.add_argument(
        "--blank-mean", type=float, default=6.0,
        help="Treat a frame as ZM's black 'Failed getting frame' placeholder if its "
             "mean brightness is below this AND std is below --blank-std (default 6.0; "
             "set 0 to disable placeholder skipping)",
    )
    tune.add_argument(
        "--blank-std", type=float, default=10.0,
        help="Std-dev half of the blank-frame test (default 10.0)",
    )
    sp.add_argument("--json-out", help="Write full per-event results to this JSON file")
    sp.add_argument("-v", "--verbose", action="store_true", help="Print per-frame diff metrics")
    sp.set_defaults(func=cmd_scan)

    # download
    sp = sub.add_parser(
        "download",
        help="Pre-fetch event frames into the cache dir (so a later scan reads from disk).",
    )
    sp.add_argument("--event", type=int, help="Download a single event ID (overrides the filters below)")
    sp.add_argument("--monitor", type=int, help="Monitor ID")
    sp.add_argument("--start", help="StartTime >= (ZM server local time)")
    sp.add_argument("--end", help="StartTime <= (ZM server local time)")
    sp.add_argument("--min-duration", type=float, help="Only events at least N seconds long")
    sp.add_argument(
        "--frame-type", choices=["all", "alarm"], default="all",
        help="Download the full frame range or only ZM 'alarm' frames (default all). "
             "Use the same value you will pass to 'scan'.",
    )
    sp.add_argument(
        "--sample-every", type=int, default=1,
        help="Download only every Nth frame (default 1 = all). Use the same value you "
             "will pass to 'scan', or the default so any scan sampling hits the cache.",
    )
    sp.add_argument(
        "--workers", type=int, default=4,
        help="Parallel frame downloads (default 4). Each concurrent request spawns a "
             "zms process on the ZoneMinder server, so raising this trades server load "
             "for wall-clock time; 8 is reasonable on a healthy box, 1 disables threading.",
    )
    sp.set_defaults(func=cmd_download)

    # matches
    sp = sub.add_parser(
        "matches",
        help="Symlink the peak frame of each flagged event into one directory for review.",
    )
    sp.add_argument(
        "--results", default="results.json",
        help="Scan results JSON written by 'scan --json-out' (default results.json)",
    )
    sp.add_argument(
        "--min-fraction", type=float, default=0.02,
        help="Only link events whose peak ROI change was at least this fraction "
             "(default 0.02 = 2%%). Re-filter without re-scanning.",
    )
    sp.add_argument("--top", type=int, help="Link at most N events (highest peak first)")
    sp.add_argument(
        "-o", "--out", default="matches",
        help="Directory to create the symlinks in (default matches/)",
    )
    sp.add_argument(
        "--clear", action="store_true",
        help="Remove existing symlinks from the output directory first (never real files)",
    )
    sp.add_argument(
        "--no-fetch", action="store_true",
        help="Don't download peak frames missing from the cache; skip them instead",
    )
    sp.set_defaults(func=cmd_matches)

    return p


def main(argv: Iterable[str] | None = None) -> int:
    # Stream output line-by-line even when stdout is piped (e.g. into `tee` or a
    # log file). Without this, Python block-buffers a non-TTY stdout and the
    # per-frame/per-event progress would not appear until the buffer fills.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass

    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
