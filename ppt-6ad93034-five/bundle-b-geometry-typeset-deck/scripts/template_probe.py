#!/usr/bin/env python3
"""template_probe.py -- extract slide geometry and theme data from a .pptx template.

Opens the pptx as a plain zip (pure stdlib) and parses:
  ppt/presentation.xml      -> sldSz (EMU width/height)
  ppt/theme/theme1.xml      -> major/minor latin + ea fonts, accent1..6 + dk1/lt1 colors
  ppt/slideMasters/*.xml    -> footer / slide-number placeholder presence

Writes <work>/theme.json:
  {slide_w_emu, slide_h_emu, fonts:{title,body,ea}, colors:{accent1..6,text,bg},
   footer:bool, source:"template"|"defaults", assumptions:[...]}

No template (or unparsable) -> Office defaults (12192000x6858000 EMU, Calibri,
Office accents) and the fallback is recorded in `assumptions`.
"""
import argparse
import json
import os
import sys
import zipfile
import xml.etree.ElementTree as ET

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}

DEFAULT_THEME = {
    "slide_w_emu": 12192000,
    "slide_h_emu": 6858000,
    "fonts": {"title": "Calibri Light", "body": "Calibri", "ea": ""},
    "colors": {
        "accent1": "4472C4", "accent2": "ED7D31", "accent3": "A5A5A5",
        "accent4": "FFC000", "accent5": "5B9BD5", "accent6": "70AD47",
        "text": "000000", "bg": "FFFFFF",
    },
    "footer": False,
    "source": "defaults",
    "assumptions": [],
}


def _color_of(elem):
    """Extract hex color from an a:clrScheme child (srgbClr or sysClr)."""
    if elem is None:
        return None
    srgb = elem.find("a:srgbClr", NS)
    if srgb is not None and srgb.get("val"):
        return srgb.get("val").upper()
    sysc = elem.find("a:sysClr", NS)
    if sysc is not None and sysc.get("lastClr"):
        return sysc.get("lastClr").upper()
    return None


def probe(template_path):
    """Return the theme dict; never raises on a missing/broken template."""
    theme = json.loads(json.dumps(DEFAULT_THEME))  # deep copy
    if not template_path or not os.path.isfile(template_path):
        theme["assumptions"].append(
            "template not found at %r; using Office defaults "
            "(12192000x6858000 EMU, Calibri, Office accents)" % template_path)
        return theme
    try:
        zf = zipfile.ZipFile(template_path)
    except (zipfile.BadZipFile, OSError) as exc:
        theme["assumptions"].append(
            "template %r is not a readable pptx zip (%s); using Office defaults"
            % (template_path, exc))
        return theme

    with zf:
        names = set(zf.namelist())
        # --- slide size -----------------------------------------------------
        try:
            pres = ET.fromstring(zf.read("ppt/presentation.xml"))
            sldsz = pres.find("p:sldSz", NS)
            if sldsz is not None:
                theme["slide_w_emu"] = int(sldsz.get("cx"))
                theme["slide_h_emu"] = int(sldsz.get("cy"))
        except Exception as exc:  # noqa: BLE001 - probe must never crash
            theme["assumptions"].append("could not parse sldSz: %s" % exc)
        # --- theme fonts & colors -------------------------------------------
        theme_name = next((n for n in sorted(names)
                           if n.startswith("ppt/theme/theme")), None)
        if theme_name:
            try:
                root = ET.fromstring(zf.read(theme_name))
                scheme = root.find(".//a:fontScheme", NS)
                if scheme is not None:
                    maj = scheme.find("a:majorFont", NS)
                    mnr = scheme.find("a:minorFont", NS)
                    if maj is not None:
                        lat = maj.find("a:latin", NS)
                        ea = maj.find("a:ea", NS)
                        if lat is not None and lat.get("typeface"):
                            theme["fonts"]["title"] = lat.get("typeface")
                        if ea is not None and ea.get("typeface"):
                            theme["fonts"]["ea"] = ea.get("typeface")
                    if mnr is not None:
                        lat = mnr.find("a:latin", NS)
                        if lat is not None and lat.get("typeface"):
                            theme["fonts"]["body"] = lat.get("typeface")
                clr = root.find(".//a:clrScheme", NS)
                if clr is not None:
                    for i in range(1, 7):
                        v = _color_of(clr.find("a:accent%d" % i, NS))
                        if v:
                            theme["colors"]["accent%d" % i] = v
                    dk1 = _color_of(clr.find("a:dk1", NS))
                    lt1 = _color_of(clr.find("a:lt1", NS))
                    if dk1:
                        theme["colors"]["text"] = dk1
                    if lt1:
                        theme["colors"]["bg"] = lt1
            except Exception as exc:  # noqa: BLE001
                theme["assumptions"].append("could not parse theme xml: %s" % exc)
        else:
            theme["assumptions"].append("no ppt/theme/theme*.xml in template; "
                                        "default fonts/colors kept")
        # --- footer / slide-number placeholders in masters -------------------
        theme["footer"] = False
        for name in sorted(names):
            if name.startswith("ppt/slideMasters/") and name.endswith(".xml"):
                try:
                    mroot = ET.fromstring(zf.read(name))
                    for ph in mroot.iter("{%s}ph" % NS["p"]):
                        if ph.get("type") in ("ftr", "sldNum"):
                            theme["footer"] = True
                            break
                except Exception:  # noqa: BLE001
                    continue
    theme["source"] = "template"
    return theme


def main(argv=None):
    ap = argparse.ArgumentParser(description="Probe a pptx template for geometry/theme.")
    ap.add_argument("--template",
                    default=os.path.join(os.environ.get("CASE_INPUT_DIR", "/input"),
                                         "target-template.pptx"))
    ap.add_argument("--work", default=os.environ.get("CASE_WORK_DIR", "/app/work"))
    ap.add_argument("--out", default=None, help="output path (default <work>/theme.json)")
    args = ap.parse_args(argv)

    theme = probe(args.template)
    out = args.out or os.path.join(args.work, "theme.json")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(theme, fh, indent=2, ensure_ascii=False, sort_keys=False)
        fh.write("\n")
    print("template_probe: source=%s slide=%dx%d EMU title=%r body=%r -> %s"
          % (theme["source"], theme["slide_w_emu"], theme["slide_h_emu"],
             theme["fonts"]["title"], theme["fonts"]["body"], out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
