#!/usr/bin/env python3
"""detect_axis_geometry.py — cheap mechanical screen for axis-related misread modes.

Reads a figure_card.json (agent-written, schema in references/failure_taxonomy.md)
and fires on:
  * LOG_AXIS_AS_LINEAR / LINEAR_AXIS_AS_LOG / SYMLOG_SUSPECT  (tick-geometry fits)
  * DUAL_AXIS            (two tick columns / two y-unit strings)
  * TRUNCATED_ORIGIN     (bar-like chart whose value axis starts > 0)
  * UNIT_PREFIX          (m/u/k/M prefix mismatch vs table_units)
  * PERCENT_FRACTION     (% axis vs 0-1 fraction table, or reverse)
  * CROPPED_AXIS         (element inventory bleeding past the plot-area bbox)

Writes <work>/axis_diagnosis.json.
Exit codes: 0 = clean run, no live modes; 2 = clean run, >=1 live mode; 1 = error.

Stdlib + numpy only. Pixel coordinates follow the image convention
(origin top-left, y down); a tick's `pixel` is the coordinate ALONG its axis.
"""
import argparse
import json
import math
import os
import re
import sys

import numpy as np

RESID_GOOD = 0.02        # relative RMS residual below which a fit "explains" the axis
RESID_DOMINANCE = 0.30   # winning fit must have < 30% of the loser's residual

# ---------------------------------------------------------------- unit parsing
SI_PREFIX = {
    "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6,
    "m": 1e-3, "c": 1e-2, "k": 1e3, "M": 1e6, "G": 1e9,
}
BASE_UNITS = {"V", "A", "s", "g", "m", "Hz", "W", "J", "Pa", "L", "mol", "N", "F",
              "ohm", "Ohm", "Ω", "K", "C", "T", "eV", "bar", "rpm"}
SCI_RE = re.compile(r"[×xX]\s*10\^?\{?(-?\d+)\}?")
EXP_RE = re.compile(r"^[+-]?\d+(\.\d+)?[eE]([+-]?\d+)$")


def parse_unit(raw):
    """Parse a verbatim unit string -> dict(base, multiplier, kind, notation)."""
    if raw is None:
        return {"raw": None, "base": None, "multiplier": 1.0, "kind": "unknown",
                "notation": None}
    s = str(raw).strip()
    out = {"raw": raw, "base": None, "multiplier": 1.0, "kind": "unknown",
           "notation": None}
    if not s or s in {"-", "1", "unitless", "a.u.", "arb."}:
        out.update(base="unitless", kind="unitless")
        return out
    m = SCI_RE.search(s)
    if m:
        out["notation"] = "x10^%s" % m.group(1)
        out["multiplier"] *= 10.0 ** int(m.group(1))
        s = SCI_RE.sub("", s).strip()
    if s in {"%", "percent", "pct"}:
        out.update(base="fraction", multiplier=out["multiplier"] * 1e-2,
                   kind="percent")
        return out
    if s in {"‰", "permille"}:
        out.update(base="fraction", multiplier=out["multiplier"] * 1e-3,
                   kind="permille")
        return out
    if s in {"fraction", "ratio"}:
        out.update(base="fraction", kind="fraction")
        return out
    if s in BASE_UNITS:                       # e.g. bare "m" is metre, not milli
        out.update(base=s, kind="si")
        return out
    if len(s) > 1 and s[0] in SI_PREFIX and s[1:] in BASE_UNITS:
        out.update(base=s[1:], multiplier=out["multiplier"] * SI_PREFIX[s[0]],
                   kind="si")
        return out
    out.update(base=s, kind="unparsed")
    return out


# ---------------------------------------------------------------- axis fitting
def _fit(xs, ys):
    """Least squares ys = a*xs + b -> (a, b, relative_rms_residual)."""
    a, b = np.polyfit(np.asarray(xs, float), np.asarray(ys, float), 1)
    pred = a * np.asarray(xs, float) + b
    rms = float(np.sqrt(np.mean((np.asarray(ys, float) - pred) ** 2)))
    span = float(max(ys) - min(ys)) or 1.0
    return float(a), float(b), rms / span


def fit_axis_type(ticks):
    """Compare linear vs log fits of tick (value, pixel) pairs."""
    vals = [float(t["value"]) for t in ticks]
    pix = [float(t["pixel"]) for t in ticks]
    res = {"n_ticks": len(ticks)}
    la, lb, lres = _fit(vals, pix)
    res["linear"] = {"a": la, "b": lb, "relative_residual": lres}
    if all(v > 0 for v in vals):
        ga, gb, gres = _fit([math.log10(v) for v in vals], pix)
        res["log"] = {"a": ga, "b": gb, "relative_residual": gres}
    if min(vals) < 0 < max(vals):  # possible symlog: |v| spacing log-like
        sa, sb, sres = _fit([math.copysign(math.log10(1 + abs(v)), v) for v in vals],
                            pix)
        res["symlog_probe"] = {"a": sa, "b": sb, "relative_residual": sres}

    verdict, conf = "ambiguous", 0.0
    gres = res.get("log", {}).get("relative_residual")
    if gres is not None and gres < RESID_GOOD and gres < RESID_DOMINANCE * lres:
        verdict = "log"
        conf = min(0.99, 1.0 - gres / max(lres, 1e-9))
    elif lres < RESID_GOOD and (gres is None or lres < RESID_DOMINANCE * gres):
        verdict = "linear"
        conf = min(0.99, 1.0 - lres / max(gres or 1.0, 1e-9))
    elif "symlog_probe" in res and res["symlog_probe"]["relative_residual"] < RESID_GOOD \
            and res["symlog_probe"]["relative_residual"] < RESID_DOMINANCE * lres:
        verdict = "symlog-suspect"
        conf = 0.6
    elif lres < RESID_GOOD:
        verdict, conf = "linear", 0.5
    res["verdict"], res["confidence"] = verdict, round(conf, 3)
    return res


# ------------------------------------------------------------------- detectors
def detect_axis_types(card, live):
    axes_out = []
    for ax in card.get("axes", []):
        aid = ax.get("id", "axis_%d" % len(axes_out))
        entry = {"id": aid, "orientation": ax.get("orientation"),
                 "panel": ax.get("panel"), "side": ax.get("side"),
                 "label_verbatim": ax.get("label_verbatim"),
                 "unit_verbatim": ax.get("unit_verbatim"),
                 "declared_type": ax.get("declared_type"),
                 "unit_parse": parse_unit(ax.get("unit_verbatim")), "flags": []}
        ticks = ax.get("ticks") or []
        numeric = [t for t in ticks
                   if isinstance(t.get("value"), (int, float))
                   and isinstance(t.get("pixel"), (int, float))]
        if len(numeric) >= 3 and ax.get("declared_type") not in (None, "categorical"):
            fit = fit_axis_type(numeric)
            entry["fit"] = fit
            decl = (ax.get("declared_type") or "").lower()
            verdict = fit["verdict"]
            if decl == "linear" and verdict == "log":
                fl = {"id": "LOG_AXIS_AS_LINEAR", "severity": "high",
                      "detail": ("declared 'linear' but tick geometry fits log10 "
                                 "(rel. residual %.4f vs linear %.4f); read values as "
                                 "10**((pixel-b)/a) with a=%.4f b=%.2f"
                                 % (fit["log"]["relative_residual"],
                                    fit["linear"]["relative_residual"],
                                    fit["log"]["a"], fit["log"]["b"]))}
                entry["flags"].append(fl)
                live.append({**fl, "axis": aid})
            elif decl == "log" and verdict == "linear":
                fl = {"id": "LINEAR_AXIS_AS_LOG", "severity": "high",
                      "detail": "declared 'log' but tick geometry fits linear better"}
                entry["flags"].append(fl)
                live.append({**fl, "axis": aid})
            elif verdict == "symlog-suspect" and decl != "symlog":
                fl = {"id": "SYMLOG_SUSPECT", "severity": "medium",
                      "detail": "ticks cross zero with log-like |value| spacing"}
                entry["flags"].append(fl)
                live.append({**fl, "axis": aid})
        elif ax.get("declared_type") not in (None, "categorical"):
            entry["fit"] = {"verdict": "insufficient_ticks",
                            "n_ticks": len(numeric),
                            "note": "need >=3 numeric ticks; axis type unverified"}

        # truncated origin on bar-like value axes
        rng = ax.get("range")
        chart = (ax.get("chart_type") or card.get("chart_type") or "").lower()
        if (rng and len(rng) == 2 and "bar" in chart
                and ax.get("orientation") in ("y", None)
                and isinstance(rng[0], (int, float)) and rng[0] > 0):
            lo, hi = float(rng[0]), float(rng[1])
            axis_range = hi - lo
            full_range = hi - 0.0
            visible_fraction = axis_range / full_range if full_range else None
            exaggeration = full_range / axis_range if axis_range else None
            smallest_bar_factor = hi / (hi - lo) if hi > lo else None
            fl = {"id": "TRUNCATED_ORIGIN", "severity": "high",
                  "detail": ("bar chart value axis starts at %g (>0); visible "
                             "fraction of full range %.3f, zero-baseline "
                             "exaggeration ratio %.2f"
                             % (lo, visible_fraction, exaggeration)),
                  "visible_fraction": round(visible_fraction, 4),
                  "exaggeration_ratio": round(exaggeration, 3),
                  "smallest_bar_distortion": (round(smallest_bar_factor, 3)
                                              if smallest_bar_factor else None)}
            entry["flags"].append(fl)
            live.append({**fl, "axis": aid})
        axes_out.append(entry)
    return axes_out


def detect_dual_axis(card, live):
    panels = {}
    for ax in card.get("axes", []):
        if ax.get("orientation") == "y":
            panels.setdefault(ax.get("panel", "main"), []).append(ax)
    out = {"panels": {}, "flagged": False}
    for panel, axes in panels.items():
        sides = {a.get("side") for a in axes}
        units = {a.get("unit_verbatim") for a in axes}
        info = {"n_y_axes": len(axes), "sides": sorted(s for s in sides if s),
                "units": sorted(u for u in units if u)}
        if len(axes) >= 2 and (len([s for s in sides if s]) >= 2
                               or len([u for u in units if u]) >= 2):
            info["dual_axis"] = True
            out["flagged"] = True
            fl = {"id": "DUAL_AXIS", "severity": "high", "panel": panel,
                  "detail": ("panel '%s' has %d y axes (sides=%s, units=%s); bind "
                             "each series to its axis by legend color/marker BEFORE "
                             "reading" % (panel, len(axes), info["sides"],
                                          info["units"]))}
            live.append(fl)
        out["panels"][panel] = info
    if out["flagged"] and len(card.get("legend") or []) >= 2:
        for f in live:
            if f["id"] == "DUAL_AXIS":
                f["detail"] += ("; legend has %d entries — swapped binding is the "
                                "classic failure" % len(card["legend"]))
    return out


def detect_units(card, axes_out, live):
    table_parsed = [parse_unit(u) for u in (card.get("table_units") or [])]
    table_parsed = [p for p in table_parsed if p["base"]]
    comparisons = []
    for ax in axes_out:
        ap = ax["unit_parse"]
        if not ap["base"]:
            continue
        for tp in table_parsed:
            if ap["base"] == tp["base"] == "fraction" and ap["kind"] != tp["kind"]:
                fl = {"id": "PERCENT_FRACTION", "severity": "medium",
                      "axis": ax["id"],
                      "detail": ("axis unit %r (x%g) vs table unit %r (x%g) — "
                                 "percent/fraction mix-up risk; factor %g"
                                 % (ap["raw"], ap["multiplier"], tp["raw"],
                                    tp["multiplier"],
                                    ap["multiplier"] / tp["multiplier"]))}
                ax["flags"].append(fl)
                live.append(fl)
                comparisons.append({"axis": ax["id"], "axis_unit": ap["raw"],
                                    "table_unit": tp["raw"], "flag": True})
            elif (ap["base"] == tp["base"] and ap["kind"] == "si"
                  and abs(ap["multiplier"] - tp["multiplier"]) > 0
                  and ap["multiplier"] != tp["multiplier"]):
                factor = ap["multiplier"] / tp["multiplier"]
                fl = {"id": "UNIT_PREFIX", "severity": "high", "axis": ax["id"],
                      "detail": ("axis unit %r vs table unit %r share base %r but "
                                 "differ by factor %g — prefix mix-up risk (mV read "
                                 "as V etc.)" % (ap["raw"], tp["raw"], ap["base"],
                                                 factor)),
                      "conversion_factor_axis_to_table": factor}
                ax["flags"].append(fl)
                live.append(fl)
                comparisons.append({"axis": ax["id"], "axis_unit": ap["raw"],
                                    "table_unit": tp["raw"], "flag": True})
    return {"table_units_parsed": table_parsed, "comparisons": comparisons}


def detect_cropped(card, live):
    """Element inventory bleeding outside the plot-area bbox -> cropped/cut ink."""
    bbox = card.get("plot_area_bbox")
    if isinstance(bbox, dict):
        out = {}
        for panel, bb in bbox.items():
            out[panel] = _cropped_for_bbox(card, live, bb, panel)
        return out
    if isinstance(bbox, list) and len(bbox) == 4:
        return _cropped_for_bbox(card, live, bbox, None)
    return {}


def _cropped_for_bbox(card, live, bb, panel):
    x0, y0, x1, y1 = [float(v) for v in bb]
    bleed = []
    for el in card.get("element_inventory") or []:
        eb = el.get("bbox")
        if not eb or len(eb) != 4:
            continue
        if panel and el.get("panel") not in (None, panel):
            continue
        if eb[0] < x0 - 2 or eb[1] < y0 - 2 or eb[2] > x1 + 2 or eb[3] > y1 + 2:
            bleed.append(el)
    if bleed:
        fl = {"id": "CROPPED_AXIS", "severity": "medium",
              "panel": panel,
              "detail": ("%d inventoried element(s) extend past the plot-area bbox — "
                         "axis or data may be cropped; values outside the readable "
                         "range are gaps, not extrapolations" % len(bleed))}
        live.append(fl)
        return {"panel": panel, "bleeding_elements": len(bleed), "flag": True}
    return {"panel": panel, "bleeding_elements": 0, "flag": False}


# ----------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--card", required=True, help="figure_card.json path")
    ap.add_argument("--work", required=True, help="work dir for axis_diagnosis.json")
    ap.add_argument("--out", default=None, help="output path (default <work>/axis_diagnosis.json)")
    args = ap.parse_args()
    try:
        with open(args.card, encoding="utf-8") as fh:
            card = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        print("error: cannot read card: %s" % exc, file=sys.stderr)
        return 1

    live = []
    axes_out = detect_axis_types(card, live)
    dual = detect_dual_axis(card, live)
    units = detect_units(card, axes_out, live)
    cropped = detect_cropped(card, live)

    diag = {
        "tool": "detect_axis_geometry",
        "card": os.path.abspath(args.card),
        "live_modes": live,
        "n_live_modes": len(live),
        "axes": axes_out,
        "dual_axis": dual,
        "units": units,
        "cropped": cropped,
        "caveat": ("Heuristics only: a clean result does not prove absence; every "
                   "flag still needs visual confirmation on the zoomed figure."),
    }
    out = args.out or os.path.join(args.work, "axis_diagnosis.json")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(diag, fh, indent=2, ensure_ascii=False)
    print("wrote %s — %d live mode(s): %s"
          % (out, len(live), ", ".join(sorted({f["id"] for f in live})) or "none"))
    return 2 if live else 0


if __name__ == "__main__":
    sys.exit(main())
