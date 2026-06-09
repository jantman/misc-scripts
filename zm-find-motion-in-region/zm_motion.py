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
import time
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

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.verify = cfg.verify_ssl
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    # -- auth ------------------------------------------------------------- #

    def login(self) -> str:
        """Authenticate and return an access token (cached until near expiry)."""
        now = time.time()
        if self._access_token and now < self._token_expires_at - 60:
            return self._access_token

        url = f"{self.cfg.base_url}/api/host/login.json"
        resp = self.session.post(
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
        resp = self.session.get(url, timeout=self.cfg.timeout)
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
        """Return {'Event': {...}, 'Frame': [...]} for one event."""
        payload = self._api_get(f"/api/events/{event_id}.json")
        return payload

    # -- frames (images) -------------------------------------------------- #

    def fetch_frame(self, event_id: int, frame_id: int) -> Image.Image:
        """Fetch a single JPEG frame via the streaming CGI (zms 'single' mode).

        Uses /cgi-bin/zms which is the portable way to pull one frame out of a
        stored event. The web /index.php?view=image path is NOT used because it
        404s on some installs.
        """
        token = self.login()
        url = (
            f"{self.cfg.base_url}/cgi-bin/zms"
            f"?mode=single&source=event&event={event_id}&frame={frame_id}&token={token}"
        )
        resp = self.session.get(url, timeout=self.cfg.timeout)
        if resp.status_code != 200 or not resp.content:
            raise RuntimeError(
                f"Failed to fetch frame {frame_id} of event {event_id} "
                f"(HTTP {resp.status_code}, {len(resp.content)} bytes)"
            )
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


def crop_gray(img: Image.Image, region: Region) -> np.ndarray:
    """Crop to the ROI and return a float32 grayscale array."""
    crop = img.convert("L").crop(region.box)
    return np.asarray(crop, dtype=np.float32)


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


def select_frames(frames: list[dict[str, Any]], frame_type: str, sample_every: int) -> list[dict[str, Any]]:
    """Pick which frames of an event to examine."""
    if frame_type == "alarm":
        chosen = [f for f in frames if str(f.get("Type", "")).lower() == "alarm"]
        # Always keep some context if there were no alarm frames.
        if not chosen:
            chosen = frames
    else:
        chosen = frames
    if sample_every > 1:
        chosen = chosen[::sample_every]
    return chosen


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
    error: str | None = None


def analyze_event(
    client: ZMClient,
    event: dict[str, Any],
    region: Region,
    pixel_threshold: int,
    frame_type: str,
    sample_every: int,
    verbose: bool = False,
) -> EventResult:
    eid = int(event["Id"])
    detail = client.get_event(eid)
    frames = detail.get("Frame") or []
    chosen = select_frames(frames, frame_type, sample_every)

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
    try:
        for f in chosen:
            fid = int(f["FrameId"])
            img = client.fetch_frame(eid, fid)
            cur = crop_gray(img, region)
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
    except RuntimeError as exc:
        res.error = str(exc)
    return res


# --------------------------------------------------------------------------- #
# Subcommands
# --------------------------------------------------------------------------- #


def cmd_test_connection(args: argparse.Namespace) -> int:
    cfg = Config.load(args.config)
    client = ZMClient(cfg)
    token = client.login()
    print(f"OK — authenticated to {cfg.base_url}")
    print(f"Access token (truncated): {token[:24]}...")
    # Sanity check an API read.
    version = client._api_get("/api/host/getVersion.json")
    print(f"ZoneMinder version: {version.get('version', '?')}, API: {version.get('apiversion', '?')}")
    return 0


def cmd_list_events(args: argparse.Namespace) -> int:
    cfg = Config.load(args.config)
    client = ZMClient(cfg)
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
    cfg = Config.load(args.config)
    client = ZMClient(cfg)
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
    cfg = Config.load(args.config)
    client = ZMClient(cfg)
    region = Region.parse(args.region)

    if args.event:
        events = [client.get_event(args.event)["Event"]]
    else:
        events = client.list_events(args.monitor, args.start, args.end, args.min_duration)

    if not events:
        print("No events matched.")
        return 0

    print(
        f"Scanning {len(events)} event(s) for motion in ROI "
        f"{region.x},{region.y} {region.w}x{region.h} "
        f"(pixel_threshold={args.pixel_threshold}, frames={args.frame_type}, "
        f"sample_every={args.sample_every})\n"
    )

    results: list[EventResult] = []
    for i, ev in enumerate(events, 1):
        print(f"[{i}/{len(events)}] event {ev['Id']} ({ev.get('StartTime','')}) ...", flush=True)
        r = analyze_event(
            client, ev, region,
            pixel_threshold=args.pixel_threshold,
            frame_type=args.frame_type,
            sample_every=args.sample_every,
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
    sp.add_argument("--json-out", help="Write full per-event results to this JSON file")
    sp.add_argument("-v", "--verbose", action="store_true", help="Print per-frame diff metrics")
    sp.set_defaults(func=cmd_scan)

    return p


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
