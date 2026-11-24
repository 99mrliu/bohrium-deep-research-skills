#!/usr/bin/env python3
"""font_probe.py -- environment font discovery for ppt-native-edit-proofer.

Discovery chain: fc-list (subprocess) -> common font directories scan ->
honest "unknown" when nothing can be discovered. Never crashes on missing
tools; always writes a report.

Usage:
    python3 font_probe.py --report font_report.json
"""
import argparse
import json
import os
import re
import subprocess
import sys

# Safe font whitelist (theme fonts are added dynamically by edit_lint).
SAFE_FONTS = [
    "Arial", "Helvetica", "Times New Roman", "Times", "Calibri",
    "Calibri Light", "DejaVu Sans", "DejaVu Serif", "Noto Sans",
    "Noto Serif", "Noto Sans CJK SC", "Noto Serif CJK SC",
    "PingFang SC", "Microsoft YaHei", "SimSun", "Songti SC",
    "Liberation Sans", "Liberation Serif",
]

COMMON_FONT_DIRS = [
    "/System/Library/Fonts",
    "/Library/Fonts",
    os.path.expanduser("~/Library/Fonts"),
    "/usr/share/fonts",
    "/usr/local/share/fonts",
]


def run_fc_list():
    """Try fc-list; return list of family names or None if unavailable."""
    try:
        out = subprocess.run(
            ["fc-list", ":", "family"],
            capture_output=True, text=True, timeout=30,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        fams = set()
        for line in out.stdout.splitlines():
            for fam in line.split(","):
                fam = fam.strip()
                if fam:
                    fams.add(fam)
        return sorted(fams)
    except (OSError, subprocess.SubprocessError):
        return None


def scan_font_dirs():
    """Scan common font directories; derive rough family names from file names."""
    found = set()
    for d in COMMON_FONT_DIRS:
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for f in files:
                if f.lower().endswith((".ttf", ".otf", ".ttc")):
                    base = re.sub(r"\.(ttf|otf|ttc)$", "", f, flags=re.I)
                    base = re.sub(r"[-_ ]?(Bold|Italic|Regular|Light|Medium|"
                                  r"Semibold|Black|Thin|Roman).*$", "", base)
                    base = base.replace("-", " ").replace("_", " ").strip()
                    if base:
                        found.add(base)
    return sorted(found) if found else None


def main():
    ap = argparse.ArgumentParser(description="Discover environment fonts and "
                                     "assess safe-font availability.")
    ap.add_argument("--report", required=True, help="Output JSON report path.")
    args = ap.parse_args()

    method = None
    fonts = run_fc_list()
    if fonts:
        method = "fc-list"
    else:
        fonts = scan_font_dirs()
        if fonts:
            method = "directory-scan"
        else:
            fonts = []
            method = "unknown"

    lower_map = {f.lower(): f for f in fonts}
    available_safe, missing_safe = [], []
    for sf in SAFE_FONTS:
        hit = None
        for name in lower_map:
            if sf.lower() in name or name in sf.lower():
                hit = lower_map[name]
                break
        (available_safe if hit else missing_safe).append(hit or sf)

    risks = []
    if method == "unknown":
        risks.append("font discovery failed; availability unknown "
                     "(tool_missing: fc-list and no readable font dirs)")
    for want in ("Arial", "Calibri", "Helvetica"):
        if not any(want.lower() in n for n in lower_map):
            risks.append("metric-standard font '%s' not detected; "
                         "substitution may shift line breaks" % want)
    if not any(("cjk" in n or "pingfang" in n or "yahei" in n or
                "simsun" in n or "songti" in n) for n in lower_map):
        risks.append("no CJK font detected; Chinese text may render as tofu")

    suggested = next((f for f in ("Arial", "Helvetica", "Calibri",
                                  "DejaVu Sans", "Liberation Sans")
                      if any(f.lower() in n for n in lower_map)), None)

    report = {
        "discovery_method": method,
        "font_count": len(fonts),
        "fonts_sample": fonts[:200],
        "safe_fonts_available": sorted(set(available_safe)),
        "safe_fonts_missing": sorted(set(missing_safe)),
        "suggested_body_font": suggested,
        "policy": "inherit theme fonts; do not hardcode private fonts",
        "risks": risks,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print("font_probe: method=%s fonts=%d suggested=%s risks=%d -> %s"
          % (method, len(fonts), suggested, len(risks), args.report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
