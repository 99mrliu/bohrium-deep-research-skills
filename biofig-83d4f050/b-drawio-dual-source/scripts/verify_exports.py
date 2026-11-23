#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_exports.py -- post-export verification for the dual-source pipeline.

Checks (each reported as {"name", "status": pass|fail|skip, "detail"}):
  drawio_parses          mxfile XML parses, has mxGraphModel/root
  drawio_cells_complete  every entity:/edge:/compartment: id from geometry exists
  drawio_labels          entity labels present as mxCell values
  svg_parses             SVG parses with xml.etree
  svg_ids_and_labels     expected ids + entity label texts present in SVG
  legend_consistency     every used edge kind + encoding legend appears in the
                         SVG legend layer
  png_exists_nonempty    PNG exists and is non-trivial
  png_size_expected      PNG pixel size == canvas size (needs PIL; skip if absent)
  color_checks           PNG pixel probes vs expected colors (needs PIL;
                         --color-checks JSON: [{"entity":"akt","expect":"#ff8800",
                         "tolerance":40}, ...] or explicit {"pixel":[x,y]})
  pdf_exists_nontrivial  PDF exists and is > 500 bytes

Exit code 0 when nothing failed, 1 otherwise.
CLI: python3 verify_exports.py --geometry FILE [--drawio F] [--svg F]
     [--png F] [--pdf F] [--color-checks FILE] [--out FILE]
"""
import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET


def _hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _check(name, status, detail=""):
    return {"name": name, "status": status, "detail": detail}


def run_checks(geometry_path, drawio=None, svg=None, png=None, pdf=None,
               color_checks_path=None):
    with open(geometry_path, "r", encoding="utf-8") as fh:
        model = json.load(fh)
    checks = []
    ent_ids = ["entity:%s" % e["id"] for e in model.get("entities", [])]
    edge_ids = ["edge:%s" % e["id"] for e in model.get("edges", [])]
    comp_ids = ["compartment:%s" % c["id"] for c in model.get("compartments", [])]
    labels = {e["id"]: e["label"] for e in model.get("entities", [])}

    # --- drawio ---------------------------------------------------------------
    if drawio:
        try:
            tree = ET.parse(drawio)
            root = tree.getroot()
            if root.tag != "mxfile" or root.find(".//mxGraphModel/root") is None:
                raise ValueError("missing mxfile/mxGraphModel/root structure")
            checks.append(_check("drawio_parses", "pass", os.path.basename(drawio)))
        except Exception as exc:
            checks.append(_check("drawio_parses", "fail", str(exc)))
            checks.append(_check("drawio_cells_complete", "skip", "parse failed"))
            checks.append(_check("drawio_labels", "skip", "parse failed"))
        else:
            ids = {el.get("id") for el in root.iter("mxCell")}
            values = {el.get("id"): el.get("value", "") for el in root.iter("mxCell")}
            missing = [c for c in ent_ids + edge_ids + comp_ids if c not in ids]
            checks.append(_check(
                "drawio_cells_complete", "pass" if not missing else "fail",
                "all %d cells present" % len(ent_ids + edge_ids + comp_ids)
                if not missing else "missing: %s" % ", ".join(missing[:8])))
            bad = ["entity:%s" % eid for eid, lab in labels.items()
                   if values.get("entity:%s" % eid) != lab]
            checks.append(_check(
                "drawio_labels", "pass" if not bad else "fail",
                "labels intact" if not bad else "mismatch: %s" % ", ".join(bad[:8])))

    # --- svg -------------------------------------------------------------------
    svg_texts, legend_text = [], ""
    if svg:
        try:
            tree = ET.parse(svg)
            root = tree.getroot()
            checks.append(_check("svg_parses", "pass", os.path.basename(svg)))
        except Exception as exc:
            checks.append(_check("svg_parses", "fail", str(exc)))
            checks.append(_check("svg_ids_and_labels", "skip", "parse failed"))
            checks.append(_check("legend_consistency", "skip", "parse failed"))
        else:
            ids = {el.get("id") for el in root.iter()}
            texts = [(el.text or "") for el in root.iter()
                     if el.tag.endswith("text")]
            svg_texts = texts
            missing_ids = [c for c in ent_ids + edge_ids if c not in ids]
            missing_labels = [lab for lab in labels.values()
                              if not any(lab in t for t in texts)]
            ok = not missing_ids and not missing_labels
            detail = []
            if missing_ids:
                detail.append("missing ids: %s" % ", ".join(missing_ids[:8]))
            if missing_labels:
                detail.append("missing labels: %s" % ", ".join(missing_labels[:8]))
            checks.append(_check("svg_ids_and_labels", "pass" if ok else "fail",
                                 "; ".join(detail) if detail else "ids+labels ok"))
            legend_layer = None
            for el in root.iter():
                if el.get("id") == "layer-legend":
                    legend_layer = el
                    break
            legend_text = " ".join(
                (el.text or "") for el in (legend_layer.iter() if legend_layer
                                           is not None else []))
            used_kinds = {e.get("kind", "uncertain") for e in model.get("edges", [])}
            problems = []
            if used_kinds or model.get("encodings"):
                if legend_layer is None:
                    problems.append("no layer-legend")
                for k in sorted(used_kinds):
                    if k not in legend_text:
                        problems.append("edge kind %r not in legend" % k)
                for enc in model.get("encodings", []):
                    want = enc.get("legend") or enc.get("field", "")
                    if want and want not in legend_text:
                        problems.append("encoding legend %r missing" % want)
            checks.append(_check(
                "legend_consistency", "pass" if not problems else "fail",
                "legend matches used encodings" if not problems
                else "; ".join(problems)))

    # --- png/pdf ----------------------------------------------------------------
    if png:
        if not os.path.exists(png) or os.path.getsize(png) < 1000:
            checks.append(_check("png_exists_nonempty", "fail",
                                 "missing or <1000 bytes"))
        else:
            checks.append(_check("png_exists_nonempty", "pass",
                                 "%d bytes" % os.path.getsize(png)))
        try:
            from PIL import Image
        except ImportError:
            checks.append(_check("png_size_expected", "skip", "PIL not installed"))
            img = None
        else:
            img = Image.open(png).convert("RGB")
            w = model.get("canvas", {}).get("width", 1200)
            h = model.get("canvas", {}).get("height", 850)
            ok = abs(img.size[0] - w) <= 2 and abs(img.size[1] - h) <= 2
            checks.append(_check(
                "png_size_expected", "pass" if ok else "fail",
                "size %sx%s (expected %sx%s)" % (img.size[0], img.size[1], w, h)))
        # color probes
        if color_checks_path:
            if img is None:
                checks.append(_check("color_checks", "skip", "PIL not installed"))
            else:
                try:
                    with open(color_checks_path, "r", encoding="utf-8") as fh:
                        probes = json.load(fh)
                    ents = {e["id"]: e for e in model.get("entities", [])}
                    bad = []
                    for probe in probes:
                        tol = int(probe.get("tolerance", 40))
                        expect = _hex_to_rgb(probe["expect"])
                        if "entity" in probe:
                            e = ents[probe["entity"]]
                            # modal color over the inner 50% box: fill dominates
                            # area, text glyphs and strokes are rare variants
                            counts = {}
                            x0 = int(e["x"] + e["w"] * 0.25)
                            x1 = int(e["x"] + e["w"] * 0.75)
                            y0 = int(e["y"] + e["h"] * 0.25)
                            y1 = int(e["y"] + e["h"] * 0.75)
                            for sx in range(x0, max(x1, x0 + 1), 2):
                                for sy in range(y0, max(y1, y0 + 1), 2):
                                    c = img.getpixel((min(sx, img.size[0] - 1),
                                                      min(sy, img.size[1] - 1)))
                                    counts[c] = counts.get(c, 0) + 1
                            got = max(counts.items(), key=lambda kv: kv[1])[0]
                            px, py = (x0 + x1) // 2, (y0 + y1) // 2
                        else:
                            px, py = [int(v) for v in probe["pixel"]]
                            px = min(max(px, 0), img.size[0] - 1)
                            py = min(max(py, 0), img.size[1] - 1)
                            got = img.getpixel((px, py))
                        if any(abs(g - ex) > tol for g, ex in zip(got, expect)):
                            bad.append("%s@%d,%d got #%02x%02x%02x expect %s"
                                       % (probe.get("entity", "pixel"), px, py,
                                          got[0], got[1], got[2], probe["expect"]))
                    checks.append(_check(
                        "color_checks", "pass" if not bad else "fail",
                        "%d probes ok" % len(probes) if not bad
                        else "; ".join(bad[:5])))
                except Exception as exc:
                    checks.append(_check("color_checks", "fail", str(exc)))
    if pdf:
        if not os.path.exists(pdf) or os.path.getsize(pdf) < 500:
            checks.append(_check("pdf_exists_nontrivial", "fail",
                                 "missing or <500 bytes"))
        else:
            checks.append(_check("pdf_exists_nontrivial", "pass",
                                 "%d bytes" % os.path.getsize(pdf)))
    return checks


def main(argv=None):
    ap = argparse.ArgumentParser(description="verify drawio/SVG/PNG/PDF exports")
    ap.add_argument("--geometry", required=True)
    ap.add_argument("--drawio")
    ap.add_argument("--svg")
    ap.add_argument("--png")
    ap.add_argument("--pdf")
    ap.add_argument("--color-checks")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    checks = run_checks(args.geometry, args.drawio, args.svg, args.png, args.pdf,
                        args.color_checks)
    failed = [c for c in checks if c["status"] == "fail"]
    summary = {"status": "pass" if not failed else "fail", "checks": checks}
    out = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(out + "\n")
    print(out)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
