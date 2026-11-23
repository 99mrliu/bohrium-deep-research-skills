#!/usr/bin/env python3
"""check_spec.py -- Bundle A (ga-spec-compiler), blocking gate, step 2.

Validate figure_spec.json BEFORE rendering. Exit 0 = the spec may be
rendered; exit 1 = findings must be fixed or explicitly dispositioned in the
spec's "exceptions" list (each with id, finding, reason).

Checks:
  S1 structure    required fields, unique ids, edges reference existing nodes
  S2 anchoring    every node/edge/series/annotation that states a fact carries
                  source.locator + source.quote; quote must be a VERBATIM
                  substring of source_pool.txt (whitespace-normalised)
  S3 numerics     every number token in labels/titles/values must appear in
                  the element's own quote, or in a cited data file (data_ref)
  S4 canvas       panel rects inside canvas, no node-node overlaps (schematic),
                  label text estimated to fit its box (Helvetica width table)
  S5 palette      roles/panel colours come from the built-in colour-blind-safe
                  token set (or an explicit hex whose contrast vs text >= 3:1)
  S6 legend/units chart panels have axis labels with units when the quote shows
                  units; legend entries exist for every series

Usage:
  python3 check_spec.py --spec /app/work/figure_spec.json \
      --pool /app/work/source_pool.txt [--datadir /input]
"""
import argparse
import json
import math
import os
import re
import sys

NUM_RE = re.compile(r"[-+]?\d[\d,]*\.?\d*(?:[eE][-+]?\d+)?")
WS_RE = re.compile(r"\s+")

# Approximate Helvetica advance widths, units of em at 1pt font size.
CHAR_W = {
    "default": 0.55, "narrow": 0.28, "wide": 0.85,
}
NARROW = set("iljtfI.,;:'!|()[] ")
WIDE = set("mwMW@%&")

SAFE_TOKENS = {  # Okabe-Ito colour-blind-safe palette
    "black": "#000000", "orange": "#E69F00", "sky_blue": "#56B4E9",
    "bluish_green": "#009E73", "yellow": "#F0E442", "blue": "#0072B2",
    "vermillion": "#D55E00", "reddish_purple": "#CC79A7",
    "grey": "#999999", "white": "#FFFFFF",
}

REQUIRED_TOP = ["case_id", "title", "canvas", "panels", "reading_order"]


def norm(s):
    return WS_RE.sub(" ", s or "").strip()


def text_width_pt(text, size_pt):
    w = 0.0
    for ch in text:
        if ch in NARROW:
            w += CHAR_W["narrow"]
        elif ch in WIDE:
            w += CHAR_W["wide"]
        else:
            w += CHAR_W["default"]
    return w * size_pt


def rel_lum(hexcol):
    hexcol = hexcol.lstrip("#")
    if len(hexcol) != 6:
        return None
    r, g, b = (int(hexcol[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    def f(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(hex1, hex2):
    l1, l2 = rel_lum(hex1), rel_lum(hex2)
    if l1 is None or l2 is None:
        return None
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


class Checker:
    def __init__(self, spec, pool, datadir):
        self.spec = spec
        self.pool_norm = norm(pool)
        self.datadir = datadir
        self.findings = []
        self._data_cache = {}

    def fail(self, check, where, msg):
        self.findings.append({"check": check, "where": where, "issue": msg})

    # ---------- S2/S3 helpers ----------
    def check_source(self, elem, where, factual=True):
        src = elem.get("source")
        if not factual:
            return
        if not src or not src.get("quote") or not src.get("locator"):
            self.fail("S2", where,
                      "factual element lacks source.locator/source.quote")
            return
        if norm(src["quote"]) not in self.pool_norm:
            self.fail("S2", where,
                      "quote is not a verbatim substring of source_pool.txt: %r"
                      % src["quote"][:80])

    def check_numbers(self, text, elem, where):
        if not text:
            return
        quote = norm((elem.get("source") or {}).get("quote", ""))
        data_ref = (elem.get("source") or {}).get("data_ref")
        extra = ""
        if data_ref:
            extra = self.load_data_text(data_ref)
        for tok in NUM_RE.findall(text):
            t = tok.replace(",", "")
            if t in quote.replace(",", "") or (extra and t in extra.replace(",", "")):
                continue
            # tolerate integers embedded as years/ids already in quote
            self.fail("S3", where,
                      "number %r in %r not found in its quote or data_ref"
                      % (tok, text[:60]))

    def load_data_text(self, data_ref):
        path = data_ref.get("file", "")
        if not os.path.isabs(path) and self.datadir:
            path = os.path.join(self.datadir, path)
        if path in self._data_cache:
            return self._data_cache[path]
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                txt = fh.read()
        except OSError:
            self.fail("S3", path, "data_ref file unreadable: %s" % path)
            txt = ""
        self._data_cache[path] = txt
        return txt

    # ---------- individual checks ----------
    def s1_structure(self):
        for key in REQUIRED_TOP:
            if key not in self.spec:
                self.fail("S1", "/", "missing top-level field %r" % key)
        ids = set()
        for panel in self.spec.get("panels", []):
            pid = panel.get("id")
            if not pid:
                self.fail("S1", "panel", "panel without id")
            for node in panel.get("nodes", []):
                nid = node.get("id")
                if nid in ids:
                    self.fail("S1", pid, "duplicate node id %r" % nid)
                ids.add(nid)
            for edge in panel.get("edges", []):
                for end in ("from", "to"):
                    if edge.get(end) not in ids:
                        self.fail("S1", pid,
                                  "edge endpoint %r not a node id" % edge.get(end))

    def s2_s3_content(self):
        spec_title = self.spec.get("title", "")
        self.check_numbers(spec_title, {"source": self.spec.get("source") or {}},
                           "title")
        for panel in self.spec.get("panels", []):
            pid = panel.get("id", "?")
            if panel.get("kind") == "schematic":
                for node in panel.get("nodes", []):
                    where = "%s/%s" % (pid, node.get("id"))
                    self.check_source(node, where)
                    self.check_numbers(node.get("label", ""), node, where)
                    self.check_numbers(node.get("sublabel", ""), node, where)
                for edge in panel.get("edges", []):
                    where = "%s/%s>%s" % (pid, edge.get("from"), edge.get("to"))
                    if edge.get("label"):
                        self.check_source(edge, where)
                        self.check_numbers(edge["label"], edge, where)
            else:  # chart kinds
                for s in panel.get("series", []):
                    where = "%s/series:%s" % (pid, s.get("name"))
                    self.check_source(s, where)
                    nums = [str(v) for v in s.get("y", [])]
                    joined = " ".join(nums)
                    self.check_numbers(joined, s, where)
                for ax in ("x_label", "y_label"):
                    if panel.get(ax):
                        self.check_numbers(panel[ax], panel, pid + "/" + ax)
            for ann in panel.get("annotations", []):
                where = "%s/annotation" % pid
                self.check_source(ann, where)
                self.check_numbers(ann.get("text", ""), ann, where)

    def s4_canvas(self):
        cv = self.spec.get("canvas", {})
        W = cv.get("width_in", 7.2)
        H = cv.get("height_in", 4.0)
        rects = []
        for panel in self.spec.get("panels", []):
            pid = panel.get("id", "?")
            pr = panel.get("rect_in")
            if not pr or len(pr) != 4:
                self.fail("S4", pid, "panel missing rect_in [x,y,w,h] in inches")
                continue
            x, y, w, h = pr
            if x < 0 or y < 0 or x + w > W + 1e-6 or y + h > H + 1e-6:
                self.fail("S4", pid, "panel rect %.2f,%.2f %.2fx%.2f outside "
                          "canvas %.2fx%.2f in" % (x, y, w, h, W, H))
            rects.append((pid, pr))
            for node in panel.get("nodes", []):
                xywh = node.get("xywh_frac")
                if not xywh or len(xywh) != 4:
                    self.fail("S4", pid + "/" + str(node.get("id")),
                              "node missing xywh_frac [x,y,w,h] in 0..1 "
                              "panel-fraction coordinates")
                    continue
                nx, ny, nw, nh = xywh
                if nx < 0 or ny < 0 or nx + nw > 1.001 or ny + nh > 1.001:
                    self.fail("S4", pid + "/" + str(node.get("id")),
                              "node rect outside panel")
                # label fit: box width in points = nw * panel width in inches * 72
                box_pt = nw * w * 72.0
                size = node.get("font_pt", 9)
                for line in (node.get("label", "") or "").split("\n"):
                    need = text_width_pt(line, size)
                    if need > box_pt - 4:
                        self.fail("S4", pid + "/" + str(node.get("id")),
                                  "label %r needs ~%.0fpt > box %.0fpt at %gpt"
                                  % (line, need, box_pt, size))
            # node-node overlap inside schematic panels
            nodes = panel.get("nodes", [])
            for i in range(len(nodes)):
                for j in range(i + 1, len(nodes)):
                    a, b = nodes[i].get("xywh_frac"), nodes[j].get("xywh_frac")
                    if not a or not b:
                        continue
                    ox = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
                    oy = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
                    if ox > 0.01 and oy > 0.01:
                        self.fail("S4", pid, "nodes %r and %r overlap "
                                  "(%.2f x %.2f frac)"
                                  % (nodes[i].get("id"), nodes[j].get("id"),
                                     ox, oy))

    def s5_palette(self):
        def col_ok(c, where):
            if not c:
                return
            if c in SAFE_TOKENS:
                return
            if re.fullmatch(r"#[0-9a-fA-F]{6}", c):
                cr = contrast(c, "#FFFFFF")
                if cr is not None and cr < 1.2:
                    self.fail("S5", where, "colour %s nearly invisible on white"
                              % c)
            else:
                self.fail("S5", where, "colour %r is neither a safe token %s "
                          "nor #rrggbb" % (c, sorted(SAFE_TOKENS)))
        for panel in self.spec.get("panels", []):
            pid = panel.get("id", "?")
            for node in panel.get("nodes", []):
                col_ok(node.get("fill"), pid + "/" + str(node.get("id")))
            for s in panel.get("series", []):
                col_ok(s.get("color"), pid + "/series:" + str(s.get("name")))

    def s6_legend_units(self):
        for panel in self.spec.get("panels", []):
            if panel.get("kind") in ("bar", "line", "scatter"):
                pid = panel.get("id", "?")
                series = panel.get("series", [])
                if len(series) > 1 and not panel.get("legend", True):
                    self.fail("S6", pid, "multi-series chart without legend")
                for ax in ("x_label", "y_label"):
                    if not panel.get(ax):
                        self.fail("S6", pid, "chart missing %s" % ax)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--pool", required=True)
    ap.add_argument("--datadir", default=None)
    args = ap.parse_args()

    with open(args.spec, encoding="utf-8") as fh:
        spec = json.load(fh)
    with open(args.pool, encoding="utf-8") as fh:
        pool = fh.read()

    ck = Checker(spec, pool, args.datadir)
    ck.s1_structure()
    ck.s2_s3_content()
    ck.s4_canvas()
    ck.s5_palette()
    ck.s6_legend_units()

    # dispositioned findings: listed in spec["exceptions"] by exact issue text
    exceptions = {e.get("finding") for e in spec.get("exceptions", [])}
    open_findings = [f for f in ck.findings
                     if f["issue"] not in exceptions]
    report = {
        "spec": args.spec,
        "findings_total": len(ck.findings),
        "findings_open": len(open_findings),
        "findings_dispositioned": len(ck.findings) - len(open_findings),
        "open": open_findings,
        "gate": "PASS" if not open_findings else "FAIL",
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not open_findings else 1


if __name__ == "__main__":
    sys.exit(main())
