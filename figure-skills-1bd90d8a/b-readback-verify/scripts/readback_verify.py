#!/usr/bin/env python3
"""readback_verify.py -- independent SVG read-back verification.

PURE STDLIB (no matplotlib, no numpy). Parses the SVG that draw_figure.py
wrote, recovers numeric values from glyph GEOMETRY by fitting the
pixel->data affine transform from detected axis tick labels, and compares
the recovered values against figure_plan.json within tolerance. A figure
must not ship until this passes (or the failure is disclosed).

Usage:
  python3 readback_verify.py --svg /app/output/figure.svg \
      --plan figure_plan.json --report /app/output/verify_report.json

Always exits 0. Unlocatable glyphs degrade a check to "unverifiable"
(with a reason) instead of crashing.
"""
import sys
import os
import re
import csv
import json
import math
import argparse
import subprocess
import xml.etree.ElementTree as ET
import shutil

NUM_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


def local(tag):
    return tag.split("}")[-1]


def parse_style(s):
    out = {}
    for part in (s or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def parse_num(s):
    s = (s or "").strip().replace("−", "-").replace(",", "")
    if NUM_RE.match(s):
        try:
            return float(s)
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------- SVG model
class SVGDoc:
    def __init__(self, path):
        self.path = path
        self.texts = []   # {content,x,y,style,ancestors}
        self.paths = []   # {d,style,ancestors}
        self.uses = []    # {x,y,style,ancestors}
        self.gids = set()
        tree = ET.parse(path)
        self.root = tree.getroot()
        self._walk(self.root, [])

    def _walk(self, el, ancestors):
        tag = local(el.tag)
        new_anc = ancestors
        if tag == "g":
            gid = el.get("id")
            if gid:
                self.gids.add(gid)
                new_anc = ancestors + [gid]
        elif tag == "text":
            content = "".join(el.itertext())
            self.texts.append({
                "content": content,
                "x": float(el.get("x", "0") or 0),
                "y": float(el.get("y", "0") or 0),
                "style": parse_style(el.get("style", "")),
                "transform": el.get("transform", ""),
                "ancestors": ancestors,
            })
        elif tag == "path":
            self.paths.append({
                "d": el.get("d", ""),
                "style": parse_style(el.get("style", "")),
                "ancestors": ancestors,
            })
        elif tag == "use":
            href = el.get("{http://www.w3.org/1999/xlink}href") or \
                el.get("href", "")
            self.uses.append({
                "x": float(el.get("x", "0") or 0),
                "y": float(el.get("y", "0") or 0),
                "href": href,
                "style": parse_style(el.get("style", "")),
                "ancestors": ancestors,
            })
        for child in el:
            self._walk(child, new_anc)

    def under(self, gid_prefix):
        """entries grouped under a <g id=gid_prefix...> (exact or prefix)."""
        out = []
        for coll in (self.texts, self.paths, self.uses):
            for e in coll:
                if any(a == gid_prefix or a.startswith(gid_prefix)
                       for a in e["ancestors"]):
                        out.append(e)
        return out


PATH_TOKEN_RE = re.compile(r"([MLZCQmlzcq])|(-?\d+\.?\d*(?:[eE][+-]?\d+)?)")


def path_vertices(d):
    """Extract (x,y) of M/L commands only (curves contribute endpoints too)."""
    verts = []
    cmd = None
    nums = []
    tokens = PATH_TOKEN_RE.findall(d or "")
    pending = []
    cur = None
    for letter, num in tokens:
        if letter:
            cmd = letter
            pending = []
            continue
        if num is None or cmd is None:
            continue
        pending.append(float(num))
        if cmd in ("M", "L", "m", "l") and len(pending) == 2:
            x, y = pending
            if cmd in ("m", "l") and cur is not None:
                x, y = cur[0] + x, cur[1] + y
            cur = (x, y)
            verts.append(cur)
            pending = []
            if cmd in ("M", "m"):
                cmd = "L" if cmd == "M" else "l"
        elif cmd in ("C", "c") and len(pending) == 6:
            x, y = pending[4], pending[5]
            if cmd == "c" and cur is not None:
                x, y = cur[0] + x, cur[1] + y
            cur = (x, y)
            verts.append(cur)
            pending = []
        elif cmd in ("Q", "q") and len(pending) == 4:
            x, y = pending[2], pending[3]
            if cmd == "q" and cur is not None:
                x, y = cur[0] + x, cur[1] + y
            cur = (x, y)
            verts.append(cur)
            pending = []
    return verts


def lsq_fit(xs, ys):
    """Least squares y = a*x + b. Returns (a, b) or None."""
    n = len(xs)
    if n < 2:
        return None
    sx = sum(xs); sy = sum(ys)
    sxx = sum(x * x for x in xs); sxy = sum(x * y for x, y in zip(xs, ys))
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-12:
        return None
    a = (n * sxy - sx * sy) / denom
    b = (sy - a * sx) / n
    return a, b


def first_color(style):
    for key in ("fill", "stroke"):
        v = style.get(key)
        if v and v != "none":
            v = v.strip().lower()
            if re.match(r"^#[0-9a-f]{6}$", v):
                return v
            return v
    return None


def has_ancestor(entry, prefix):
    return any(a.startswith(prefix) for a in entry["ancestors"])


# ---------------------------------------------------------------- checks
class Report:
    def __init__(self):
        self.checks = []

    def add(self, cid, status, detail, repair=None):
        self.checks.append({"id": cid, "status": status, "detail": detail,
                            "repair": repair or {}})

    def summary(self):
        s = {"pass": 0, "fail": 0, "warn": 0, "unverifiable": 0}
        for c in self.checks:
            s[c["status"]] = s.get(c["status"], 0) + 1
        s["overall"] = "fail" if s["fail"] else (
            "pass_with_warnings" if (s["warn"] or s["unverifiable"]) else "pass")
        return s


def fit_transforms(doc, rep):
    """Fit pixel->data transforms per axes group, from tick label text."""
    axes_ids = sorted({a for t in doc.texts for a in t["ancestors"]
                       if re.match(r"^axes_\d+$", a)})
    if not axes_ids:
        axes_ids = ["axes_1"]  # single-axes fallback bucket
    transforms = {}
    for aid in axes_ids:
        in_axes = lambda e: (aid in e["ancestors"]) or (
            aid == "axes_1" and not any(
                re.match(r"^axes_\d+$", a) for a in e["ancestors"]))
        yt, xt = [], []
        for t in doc.texts:
            if not in_axes(t):
                continue
            if has_ancestor(t, "ytick_"):
                yt.append(t)
            elif has_ancestor(t, "xtick_"):
                xt.append(t)
        # Pair each tick label with the exact tick-MARK position (the <use>
        # glyph inside the same tick group). Text y is the glyph BASELINE,
        # which carries a constant offset that would bias the affine fit's
        # intercept against true glyph geometry; tick marks are exact.
        def mark_pos(tick_gid, axis):
            pts = [u for u in doc.uses if tick_gid in u["ancestors"]]
            if not pts:
                return None
            vals = sorted(u[axis] for u in pts)
            return vals[len(vals) // 2]
        def tick_anchor(t, axis):
            for a in t["ancestors"]:
                if a.startswith("ytick_") or a.startswith("xtick_"):
                    m = mark_pos(a, axis)
                    if m is not None:
                        return m
            return t[axis]  # fallback: text anchor (baseline-biased for y)
        y_pairs = [(parse_num(t["content"]), tick_anchor(t, "y"))
                   for t in yt]
        y_pairs = [(v, p) for v, p in y_pairs if v is not None]
        fit_y = lsq_fit([v for v, _ in y_pairs], [p for _, p in y_pairs]) \
            if len(y_pairs) >= 2 else None
        x_numeric = [(parse_num(t["content"]), tick_anchor(t, "x"))
                     for t in xt]
        x_numeric = [(v, p) for v, p in x_numeric if v is not None]
        fit_x = None
        x_cats = None
        if xt and len(x_numeric) == len(xt):
            fit_x = lsq_fit([v for v, _ in x_numeric],
                            [p for _, p in x_numeric])
        elif xt:
            ordered = sorted(xt, key=lambda t: tick_anchor(t, "x"))
            x_cats = [{"label": t["content"].strip(),
                       "px": tick_anchor(t, "x")} for t in ordered]
        transforms[aid] = {
            "y": fit_y, "x": fit_x, "x_cats": x_cats,
            "y_ticks": [(v, round(p, 3)) for v, p in
                        sorted(y_pairs)],
            "x_tick_labels": [t["content"] for t in sorted(
                xt, key=lambda t: t["x"])],
        }
    return transforms


def inv(fit, pix):
    a, b = fit
    return (pix - b) / a


def read_table(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
        if isinstance(obj, dict):
            return {str(k): [coerce(v) for v in vals]
                    for k, vals in obj.items()}
        cols = {}
        for row in obj:
            for k, v in row.items():
                cols.setdefault(str(k), []).append(coerce(v))
        return cols
    with open(path, encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096); f.seek(0)
        try:
            delim = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
        except csv.Error:
            delim = "\t" if ext == ".tsv" else ","
        rows = list(csv.reader(f, delimiter=delim))
    header = [h.strip() for h in rows[0]]
    cols = {h: [] for h in header}
    for r in rows[1:]:
        for i, h in enumerate(header):
            cols[h].append(coerce(r[i]) if i < len(r) else None)
    return cols


def coerce(v):
    if isinstance(v, (int, float)):
        return None if (isinstance(v, float) and math.isnan(v)) else float(v)
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in ("nan", "na", "n/a", "null"):
        return None
    try:
        return float(s)
    except ValueError:
        return s


def plan_values(spec, base_dir):
    if isinstance(spec, dict):
        p = spec.get("file")
        if not os.path.isabs(p):
            p = os.path.join(base_dir, p)
        table = read_table(p)
        col = spec.get("column")
        if col not in table:
            raise KeyError("column %r not in %s" % (col, p))
        return table[col], "%s#%s" % (os.path.basename(p), col)
    return [coerce(v) for v in (spec or [])], "literal"


def find_group_paths(doc, gid):
    return [p for p in doc.paths if gid in p["ancestors"]]


def find_group_uses(doc, gid):
    return [u for u in doc.uses if gid in u["ancestors"]]


def rect_from_path(p):
    verts = path_vertices(p["d"])
    if len(verts) < 4:
        return None
    xs = [v[0] for v in verts]; ys = [v[1] for v in verts]
    if max(xs) - min(xs) < 1e-6 or max(ys) - min(ys) < 1e-6:
        return None
    return min(xs), max(xs), min(ys), max(ys)


def compare_series(recovered, expected, tol, cid_prefix, rep, what,
                   source_locator, cat_names=None):
    """recovered/expected: list aligned by index (None = gap)."""
    fails = []
    compared = 0
    per = []
    for i, (rv, ev) in enumerate(zip(recovered, expected)):
        if ev is None and rv is None:
            per.append({"index": i, "status": "expected_gap"})
            continue
        if ev is None:
            continue
        if rv is None:
            fails.append({"index": i, "expected": ev, "recovered": None})
            continue
        compared += 1
        dev = abs(rv - ev)
        per.append({"index": i,
                    "category": (cat_names[i] if cat_names else i),
                    "expected": round(ev, 6), "recovered": round(rv, 6),
                    "abs_dev": round(dev, 6)})
        if dev > tol:
            fails.append(per[-1])
    detail = ("%s: %d/%d values match within tol=%.4g" %
              (what, compared - len([f for f in fails
                                     if f["recovered"] is not None]),
               compared, tol))
    if fails:
        exp = [e for e in expected if e is not None]
        rec = [r for r in recovered if r is not None]
        hint = ("re-bind 'values' to the correct source column; recovered "
                "values %s came from the SVG, expected %s came from %s. "
                "If recovered equals another series' expected values, that "
                "series' column was swapped in." %
                ([round(r, 4) for r in rec[:8]],
                 [round(e, 4) for e in exp[:8]], source_locator))
        rep.add(cid_prefix, "fail", detail + "; mismatches: " +
                json.dumps(fails[:5]),
                repair={"action": "fix_plan",
                        "target": what,
                        "suggestion": hint})
        return False
    rep.add(cid_prefix, "pass", detail)
    return True


def panel_axes_id(pi):
    return "axes_%d" % (pi + 1)


def verify_chart(doc, plan, rep, base_dir, out):
    transforms = fit_transforms(doc, rep)
    out["transform"] = {}
    for aid, t in transforms.items():
        out["transform"][aid] = {
            "y": {"a": t["y"][0], "b": t["y"][1]} if t["y"] else None,
            "x": {"a": t["x"][0], "b": t["x"][1]} if t["x"] else None,
            "x_cats": t["x_cats"],
        }
    out["recovered_values"] = {}
    vcfg = plan.get("verify", {})
    tol_rel = float(vcfg.get("tol_rel", 0.02))

    panels = plan.get("panels") or [{}]
    for pi, panel in enumerate(panels):
        pid = str(panel.get("id", "p%d" % pi))
        aid = panel_axes_id(pi)
        t = transforms.get(aid) or (list(transforms.values())[0]
                                    if len(transforms) == 1 else None)
        if t is None or t["y"] is None:
            rep.add("transform_y", "unverifiable",
                    "panel %s: could not fit y transform (<2 numeric "
                    "y tick labels found)" % pid,
                    repair={"action": "redraw", "target": pid,
                            "suggestion": "ensure y axis has >=2 numeric "
                            "ticks; check the SVG contains tick text"})
            continue
        rep.add("transform_y@%s" % pid, "pass",
                "py = %.6g*val + %.6g (from %d ticks)" %
                (t["y"][0], t["y"][1], len(t["y_ticks"])))
        # y span for tolerance
        all_vals = []
        for s in panel.get("series", []):
            spec = s.get("values")
            locator = s.get("source_locator", "?")
            try:
                vals, locator = plan_values(spec, base_dir)
            except Exception as e:
                rep.add("plan_data@%s" % pid, "fail",
                        "cannot resolve values of series %r: %s" %
                        (s.get("name"), e),
                        repair={"action": "fix_plan", "target": s.get("name"),
                                "suggestion": str(e)})
                vals = []
            all_vals += [v for v in vals if isinstance(v, (int, float))]
            s["_resolved"] = vals
            s["_locator"] = locator
        if not all_vals:
            rep.add("data_values@%s" % pid, "unverifiable",
                    "no numeric plan values resolved")
            continue
        yspan = max(all_vals) - min(all_vals) or abs(max(all_vals)) or 1.0
        tol = max(tol_rel * yspan, float(vcfg.get("tol_abs", 1e-9)))

        ptype = panel.get("type", "bar")
        cats = [str(c) for c in panel.get("categories", [])]
        for s in panel.get("series", []):
            name = str(s.get("name", ""))
            vals = s.get("_resolved", [])
            locator = s.get("_locator", s.get("source_locator", "?"))
            gid = ("bar__%s__%s__" % (pid, name)) if ptype == "bar" \
                else ("series__%s__%s" % (pid, name))
            if ptype == "bar":
                bars = {}
                for g in sorted(doc.gids):
                    if g.startswith(gid):
                        try:
                            idx = int(g.rsplit("__", 1)[1])
                        except (ValueError, IndexError):
                            continue
                        ps = find_group_paths(doc, g)
                        if ps:
                            r = rect_from_path(ps[0])
                            if r:
                                bars[idx] = r
                recovered = []
                for i in range(len(vals)):
                    if i not in bars:
                        recovered.append(None)
                        continue
                    x0, x1, y0, y1 = bars[i]
                    v_top = inv(t["y"], y0)
                    v_bot = inv(t["y"], y1)
                    ev = vals[i]
                    if isinstance(ev, (int, float)) and ev < 0:
                        recovered.append(min(v_top, v_bot))
                    else:
                        recovered.append(max(v_top, v_bot))
                out["recovered_values"][name] = [
                    None if r is None else round(r, 6) for r in recovered]
                if not bars:
                    rep.add("bar_values@%s/%s" % (pid, name), "unverifiable",
                            "no gid-tagged bar glyphs found (bar__%s__%s__*)"
                            % (pid, name))
                else:
                    compare_series(recovered, vals, tol,
                                   "bar_values@%s/%s" % (pid, name), rep,
                                   "series %r bars" % name, locator, cats)
                # error bars
                if s.get("yerr") is not None:
                    err_gid = "err__%s__%s" % (pid, name)
                    found = any(g == err_gid for g in doc.gids) or \
                        any(has_ancestor(p, err_gid) for p in doc.paths)
                    rep.add("errorbar_caps@%s/%s" % (pid, name),
                            "pass" if found else "fail",
                            "yerr declared; error-bar glyphs %s" %
                            ("present" if found else "MISSING"),
                            repair=None if found else {
                                "action": "redraw", "target": name,
                                "suggestion": "pass yerr with capsize>0 to "
                                "the bar call"})
            else:  # line / scatter
                group_paths = find_group_paths(doc, gid)
                group_uses = find_group_uses(doc, gid)
                pts = None
                if ptype == "scatter" and group_uses:
                    pts = [(u["x"], u["y"]) for u in group_uses]
                elif group_paths:
                    line_paths = [p for p in group_paths
                                  if p["style"].get("fill") == "none"]
                    src = line_paths[0] if line_paths else group_paths[0]
                    pts = path_vertices(src["d"])
                elif group_uses:
                    pts = [(u["x"], u["y"]) for u in group_uses]
                if pts is None:
                    rep.add("%s_values@%s/%s" % (ptype, pid, name),
                            "unverifiable",
                            "no glyph found for gid %s" % gid)
                    continue
                xspec = s.get("x", panel.get("x"))
                if xspec is None:
                    xs_exp = [float(i) for i in range(len(vals))]
                else:
                    try:
                        xs_exp, _ = plan_values(xspec, base_dir)
                    except Exception as e:
                        rep.add("plan_data@%s/%s" % (pid, name), "fail",
                                "cannot resolve x: %s" % e)
                        continue
                pairs = [(x, y) for x, y in zip(xs_exp, vals)
                         if isinstance(x, (int, float))
                         and isinstance(y, (int, float))]
                if t["x"] is None:
                    rep.add("transform_x@%s" % pid, "unverifiable",
                            "x axis not numeric-fitted (categorical?)")
                    continue
                if len(pts) != len(pairs):
                    rep.add("%s_values@%s/%s" % (ptype, pid, name), "fail",
                            "glyph count %d != data count %d (NaN dropped "
                            "by drawer?)" % (len(pts), len(pairs)),
                            repair={"action": "fix_plan", "target": name,
                                    "suggestion": "reconcile NaN handling; "
                                    "drawer drops NaN points by design"})
                    continue
                rec_y = [inv(t["y"], py) for _, py in pts]
                rec_x = [inv(t["x"], px) for px, _ in pts]
                exp_y = [p[1] for p in pairs]
                exp_x = [p[0] for p in pairs]
                out["recovered_values"][name] = [
                    round(r, 6) for r in rec_y]
                xs = [v for v in exp_x if isinstance(v, (int, float))]
                xspan = (max(xs) - min(xs)) or 1.0
                xtol = max(tol_rel * xspan, 1e-9)
                ok_y = compare_series(rec_y, exp_y, tol,
                                      "%s_values@%s/%s" % (ptype, pid, name),
                                      rep, "series %r y" % name, locator)
                ok_x = compare_series(rec_x, exp_x, xtol,
                                      "%s_x@%s/%s" % (ptype, pid, name),
                                      rep, "series %r x" % name, locator)
        # tick range coverage
        tick_vals = [v for v, _ in t["y_ticks"]]
        if tick_vals:
            dmin, dmax = min(all_vals), max(all_vals)
            if dmin < min(tick_vals) - tol or dmax > max(tick_vals) + 2 * tol:
                rep.add("tick_range@%s" % pid, "warn",
                        "data span [%.4g, %.4g] exceeds tick span "
                        "[%.4g, %.4g]; possible clipping" %
                        (dmin, dmax, min(tick_vals), max(tick_vals)),
                        repair={"action": "fix_plan", "target": pid,
                                "suggestion": "extend y limits or verify "
                                "no glyph is clipped by the axes bbox"})
            else:
                rep.add("tick_range@%s" % pid, "pass",
                        "data span within tick span")
        # axis labels (scoped to this panel's axes group)
        all_text = " || ".join(x["content"] for x in doc.texts
                               if aid in x["ancestors"])
        for axis in ("x", "y"):
            lab = str(panel.get("%s_label" % axis, "") or "")
            unit = str(panel.get("%s_unit" % axis, "") or "")
            full = ("%s (%s)" % (lab, unit)) if (lab and unit
                                                 and unit not in lab) else lab
            if not full:
                rep.add("axis_label@%s/%s" % (pid, axis), "fail",
                        "plan declares no %s label; axis will be unlabeled" %
                        axis,
                        repair={"action": "fix_plan", "target": pid,
                                "suggestion": "set %s_label and %s_unit" %
                                (axis, axis)})
            elif full in all_text or lab in all_text:
                missing_unit = unit and unit not in all_text
                rep.add("axis_label@%s/%s" % (pid, axis),
                        "warn" if missing_unit else "pass",
                        "label %r found%s" % (lab, " but unit %r absent" %
                                              unit if missing_unit else ""),
                        repair={"action": "fix_plan", "target": pid,
                                "suggestion": "include unit in axis label"}
                        if missing_unit else None)
            else:
                rep.add("axis_label@%s/%s" % (pid, axis), "fail",
                        "declared label %r not found among SVG texts" % full,
                        repair={"action": "fix_plan", "target": pid,
                                "suggestion": "set %s_label to the intended "
                                "text (with unit)" % axis})
        # legend
        names = [str(s.get("name", "")) for s in panel.get("series", [])]
        if panel.get("legend", True) and names:
            legend_texts = [x for x in doc.texts
                            if has_ancestor(x, "legend_")
                            and aid in x["ancestors"]]
            legend_texts.sort(key=lambda e: (e["y"], e["x"]))
            found = [x["content"].strip() for x in legend_texts]
            if found == names:
                rep.add("legend_order@%s" % pid, "pass",
                        "legend entries match plan series order: %s" % found)
            else:
                rep.add("legend_order@%s" % pid, "fail",
                        "legend entries %s != plan series order %s" %
                        (found, names),
                        repair={"action": "fix_plan", "target": pid,
                                "suggestion": "align series order/names with "
                                "the intended legend (swapped series cause "
                                "legend<->data mismatch)"})
            # legend color vs series color: for each legend text entry find
            # the handle glyph nearest to it in y (and left of the text).
            handles = []  # (mid_y, mid_x, color)
            for pth in doc.paths:
                if not has_ancestor(pth, "legend_") or \
                        aid not in pth["ancestors"]:
                    continue
                verts = path_vertices(pth["d"])
                if not verts:
                    continue
                col = first_color(pth["style"])
                if not col or col in ("#ffffff", "#cccccc"):
                    continue  # legend frame
                my = sum(v[1] for v in verts) / len(verts)
                mx = sum(v[0] for v in verts) / len(verts)
                handles.append((my, mx, col))
            for u in doc.uses:
                if has_ancestor(u, "legend_") and aid in u["ancestors"]:
                    col = first_color(u["style"])
                    if col:
                        handles.append((u["y"], u["x"], col))
            handle_colors = []
            for lt in legend_texts:
                cands = [h for h in handles
                         if abs(h[0] - lt["y"]) < 12 and h[1] < lt["x"]]
                cands.sort(key=lambda h: abs(h[0] - lt["y"]))
                handle_colors.append(cands[0][2] if cands else None)
            series_colors = []
            for s in panel.get("series", []):
                name = str(s.get("name", ""))
                gid = ("bar__%s__%s__" % (pid, name)) if ptype == "bar" \
                    else ("series__%s__%s" % (pid, name))
                col = None
                for g in doc.gids:
                    if g.startswith(gid):
                        entries = find_group_paths(doc, g) or \
                            find_group_uses(doc, g)
                        if entries:
                            if ptype == "bar":
                                col = entries[0]["style"].get("fill")
                            else:
                                col = (entries[0]["style"].get("stroke")
                                       or entries[0]["style"].get("fill"))
                        break
                series_colors.append((col or "").lower() or None)
            mism = [(names[i], series_colors[i],
                     handle_colors[i] if i < len(handle_colors) else None)
                    for i in range(min(len(names), len(handle_colors)))
                    if series_colors[i] and handle_colors[i]
                    and series_colors[i] != handle_colors[i]]
            if mism:
                rep.add("legend_color@%s" % pid, "fail",
                        "legend handle color != series color: %s" % mism,
                        repair={"action": "redraw", "target": pid,
                                "suggestion": "series color drifted from "
                                "legend; re-render from the plan, do not "
                                "hand-edit the SVG"})
            elif handle_colors:
                rep.add("legend_color@%s" % pid, "pass",
                        "legend handle colors match series colors")


def verify_global(doc, plan, rep):
    # editability
    n_text = len(doc.texts)
    n_path = len(doc.paths)
    if n_text == 0 and n_path > 20:
        rep.add("editable_text", "fail",
                "SVG has 0 <text> elements and %d paths: text was converted "
                "to outlines (not editable). Set svg.fonttype='none'." %
                n_path,
                repair={"action": "redraw", "target": "rcParams",
                        "suggestion": "svg.fonttype='none'; re-export"})
    else:
        rep.add("editable_text", "pass",
                "%d <text> elements present (editable vector text)" % n_text)
    # CJK / tofu
    blob = "".join(t["content"] for t in doc.texts)
    tofu = blob.count("�") + blob.count("□")
    # U+2212 (minus) and common typographic chars are safe in base fonts
    safe = {"−", "–", "—", "×", "±", "°", "·", "µ"}
    nonascii = any(ord(c) > 127 and c not in safe for c in blob)
    if tofu:
        rep.add("cjk_tofu", "fail",
                "found %d replacement/box glyphs (U+FFFD/□) -> CJK font "
                "missing at render time" % tofu,
                repair={"action": "redraw", "target": "fonts",
                        "suggestion": "install a CJK font (Noto Sans CJK SC "
                        "etc.) or transliterate labels"})
    elif nonascii:
        fams = set()
        for t in doc.texts:
            ff = t["style"].get("font-family", "")
            for f in ff.split(","):
                f = f.strip().strip("'\"")
                if f:
                    fams.add(f)
        if shutil.which("fc-list"):
            try:
                out = subprocess.run(["fc-list", ":", "family"],
                                     capture_output=True, text=True,
                                     timeout=20).stdout
                ok = any(f in out for f in fams)
            except Exception:
                ok = None
            if ok is False:
                rep.add("cjk_tofu", "warn",
                        "non-ASCII text present; fonts %s not confirmed by "
                        "fc-list" % sorted(fams))
            else:
                rep.add("cjk_tofu", "pass",
                        "non-ASCII text present; font families: %s" %
                        sorted(fams))
        else:
            rep.add("cjk_tofu", "warn",
                    "non-ASCII text present; fc-list unavailable, cannot "
                    "confirm embedded font families %s render correctly. "
                    "Inspect the PNG preview manually." % sorted(fams))
    else:
        rep.add("cjk_tofu", "pass", "ASCII-only text")
    # occlusion heuristic
    def est_box(t):
        fs = float(str(t["style"].get("font-size", "10px")
                       ).replace("px", "") or 10)
        w = sum(1.0 if ord(c) > 0x2E7F else 0.6 for c in t["content"]) * fs
        h = 1.1 * fs
        anchor = t["style"].get("text-anchor", "start")
        x = t["x"]
        if anchor == "end":
            x -= w
        elif anchor == "middle":
            x -= w / 2
        y = t["y"] - 0.8 * fs
        m = re.search(r"rotate\(\s*(-?[\d.]+)", t.get("transform", ""))
        if m and abs(abs(float(m.group(1))) - 90) < 1:
            # rotated label (e.g. ylabel): swap extents around the anchor
            cx, cy = t["x"], t["y"]
            return cx - h / 2, cy - w / 2, h, w
        return x, y, w, h
    boxes = [(est_box(t), t["content"][:20]) for t in doc.texts
             if t["content"].strip()]
    overlaps = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            (x1, y1, w1, h1), _ = boxes[i]
            (x2, y2, w2, h2), _ = boxes[j]
            ox = min(x1 + w1, x2 + w2) - max(x1, x2)
            oy = min(y1 + h1, y2 + h2) - max(y1, y2)
            if ox > 0 and oy > 0:
                area = ox * oy
                if area > 0.3 * min(w1 * h1, w2 * h2):
                    overlaps.append((boxes[i][1], boxes[j][1]))
    if overlaps:
        rep.add("occlusion", "warn",
                "%d possible text-overlap pairs (heuristic), e.g. %s" %
                (len(overlaps), overlaps[:3]),
                repair={"action": "fix_plan", "target": "layout",
                        "suggestion": "shorten labels, rotate ticks, or "
                        "enlarge width_mm/height_mm"})
    else:
        rep.add("occlusion", "pass", "no significant text overlaps estimated")


def verify_diagram(doc, plan, rep, out):
    d = plan.get("diagram") or {}
    svg_blob = "".join(t["content"] for t in doc.texts)
    squashed = re.sub(r"\s+", "", svg_blob)
    bad = []
    for n in d.get("nodes", []):
        label = str(n.get("label", ""))
        if re.sub(r"\s+", "", label) not in squashed:
            bad.append(label)
    if bad:
        rep.add("diagram_labels", "fail",
                "node labels missing or misspelled in SVG: %s" % bad,
                repair={"action": "fix_plan", "target": "diagram.nodes",
                        "suggestion": "copy entity names character-for-"
                        "character from the source paper; fix: %s" % bad})
    else:
        rep.add("diagram_labels", "pass",
                "all %d node labels found with exact spelling" %
                len(d.get("nodes", [])))
    missing_edges = []
    for ei, e in enumerate(d.get("edges", [])):
        gid = "edge__%d" % ei
        if gid not in doc.gids or not find_group_paths(doc, gid):
            missing_edges.append(ei)
    if missing_edges:
        rep.add("diagram_edges", "fail",
                "edges not rendered: %s" % missing_edges,
                repair={"action": "fix_plan", "target": "diagram.edges",
                        "suggestion": "check from/to node ids exist"})
    else:
        rep.add("diagram_edges", "pass",
                "all %d edges rendered" % len(d.get("edges", [])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--svg", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    rep = Report()
    out = {"svg": args.svg, "plan": args.plan, "checks": rep.checks,
           "transform": {}, "recovered_values": {}}
    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)
    base_dir = os.path.dirname(os.path.abspath(args.plan))
    try:
        doc = SVGDoc(args.svg)
    except Exception as e:
        rep.add("svg_parse", "fail", "cannot parse SVG: %s" % e,
                repair={"action": "redraw", "target": "svg",
                        "suggestion": "re-run draw_figure.py; the file is "
                        "not well-formed XML"})
    else:
        mode = plan.get("mode", "chart")
        if mode == "diagram":
            verify_diagram(doc, plan, rep, out)
        else:
            verify_chart(doc, plan, rep, base_dir, out)
        verify_global(doc, plan, rep)
    out["summary"] = rep.summary()
    os.makedirs(os.path.dirname(os.path.abspath(args.report)) or ".",
                exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    s = out["summary"]
    print("verify: overall=%s  pass=%d fail=%d warn=%d unverifiable=%d" %
          (s["overall"], s["pass"], s["fail"], s["warn"], s["unverifiable"]))
    for c in rep.checks:
        if c["status"] in ("fail", "warn", "unverifiable"):
            print("  [%s] %s: %s" % (c["status"].upper(), c["id"],
                                     c["detail"][:160]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
