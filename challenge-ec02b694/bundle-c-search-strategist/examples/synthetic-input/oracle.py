#!/usr/bin/env python3
"""oracle.py -- SYNTHETIC hidden response surface for the demo only.

This script stands in for real laboratory experiments.  It is NOT part of the
skill; the evaluator's cases replace it with real measurements.

Surface (deliberately hidden from the search scripts):
    response = 1 - 8e-5*(temperature-410)^2
                 - 2e-1*(time-3.5)^2
                 - 2e-4*(flow-180)^2
                 + deterministic_noise(coordinates, replicate)   # in [-0.005, 0.005]

The noise is a pure function of the coordinates plus the replicate index
(sha256 based), so re-running the demo reproduces every number byte-for-byte
while confirmation repeats still see non-zero apparent noise.

Usage:
    python3 oracle.py --points batch.json --round N --csv results.csv

--points accepts either a next_batch.py decision JSON (uses its "points"
list) or a bare JSON list of point dicts.  Rows are appended to the CSV with
header: round,temperature,time,flow,response.
"""

import argparse
import csv
import hashlib
import json
import os
import sys

PARAMS = ["temperature", "time", "flow"]


def fail(msg, code=2):
    sys.stdout.write(json.dumps({"status": "error", "error": msg},
                                ensure_ascii=False, indent=2) + "\n")
    sys.exit(code)


def noise(coords, replicate):
    payload = json.dumps([coords, replicate], sort_keys=True).encode("utf-8")
    h = int(hashlib.sha256(payload).hexdigest()[:8], 16) / 0xFFFFFFFF
    return (h - 0.5) * 2 * 0.005


def surface(t, tm, f):
    return (1.0
            - 8e-5 * (t - 410.0) ** 2
            - 2e-1 * (tm - 3.5) ** 2
            - 2e-4 * (f - 180.0) ** 2)


def main(argv=None):
    ap = argparse.ArgumentParser(description="synthetic oracle (demo only)")
    ap.add_argument("--points", required=True)
    ap.add_argument("--round", required=True)
    ap.add_argument("--csv", required=True)
    args = ap.parse_args(argv)
    try:
        round_no = int(str(args.round))
    except ValueError:
        fail("--round must be an integer")
    try:
        with open(args.points, encoding="utf-8") as fh:
            payload = json.load(fh)
    except FileNotFoundError:
        fail("file not found: %s" % args.points)
    except json.JSONDecodeError as exc:
        fail("invalid JSON in %s: %s" % (args.points, exc))
    points = payload.get("points") if isinstance(payload, dict) else payload
    if not isinstance(points, list):
        fail("points payload must be a list (or a decision JSON with 'points')")
    rows = []
    for i, pt in enumerate(points):
        if not isinstance(pt, dict):
            fail("point #%d is not an object" % i)
        try:
            coords = {n: float(pt[n]) for n in PARAMS}
        except (KeyError, TypeError, ValueError):
            fail("point #%d missing/non-numeric coordinate (need %s)"
                 % (i, ", ".join(PARAMS)))
        replicate = int(pt.get("replicate", 0))
        value = surface(coords["temperature"], coords["time"], coords["flow"])
        value += noise(coords, replicate)
        rows.append({"round": round_no,
                     "temperature": coords["temperature"],
                     "time": coords["time"],
                     "flow": coords["flow"],
                     "response": round(value, 6)})
    write_header = not os.path.exists(args.csv)
    try:
        with open(args.csv, "a", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh, fieldnames=["round", "temperature", "time", "flow",
                                "response"])
            if write_header:
                writer.writeheader()
            writer.writerows(rows)
    except OSError as exc:
        fail("cannot write %s: %s" % (args.csv, exc))
    sys.stdout.write(json.dumps({"status": "ok", "rows_appended": len(rows)},
                                ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        fail("unexpected error: %s: %s" % (type(exc).__name__, exc), code=2)
