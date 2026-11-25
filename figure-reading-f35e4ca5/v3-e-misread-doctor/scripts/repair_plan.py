#!/usr/bin/env python3
"""repair_plan.py — merge detector findings into per-mode repairs + self-checks.

Consumes axis_diagnosis.json (detect_axis_geometry.py) and nondata_elements.json
(detect_nondata_ink.py), maps every live finding to a repair recipe from the
internal table below (expanded with worked numbers in
references/repair_recipes.md), and writes:
  * <out> (default <work>/repair_plan.json) — per-mode repair + one post-read
    self-check question per live mode
  * <work>/misread_report.json — skeleton for the agent to complete while
    reading (per mode: applied yes/no + evidence), later folded into
    result.json's sources/uncertainty.

Exit codes: 0 = nothing to repair; 2 = >=1 repair issued; 1 = error.
Stdlib only.
"""
import argparse
import json
import os
import sys

# ------------------------------------------------------------- recipe table --
RECIPES = {
    "LOG_AXIS_AS_LINEAR": {
        "repair": ("Re-read this axis on a log law: value = 10**((pixel - b)/a) "
                   "with the fitted a, b from axis_diagnosis.json. Report values "
                   "in the original unit but think in decades: equal pixel steps "
                   "are equal RATIOS. Never average raw pixel positions and never "
                   "interpolate linearly in pixel space between decades."),
        "self_check": ("Pick one digitized point: does 10**((pixel-b)/a) reproduce "
                       "a tick-anchored value you can verify by eye on the zoomed "
                       "figure? Quote both numbers as evidence.")},
    "LINEAR_AXIS_AS_LOG": {
        "repair": ("The axis you believed was log is geometrically linear. Re-fit "
                   "pixel = a*value + b and re-read every value taken from this "
                   "axis; state the correction in uncertainty."),
        "self_check": ("Do three evenly spaced tick labels now differ by equal "
                       "ADDITIONS (not ratios)? Quote the three labels.")},
    "SYMLOG_SUSPECT": {
        "repair": ("Axis crosses zero with log-like spacing of |value|. Split "
                   "reading at 0: positive side and negative side each follow "
                   "their own signed-log law; values near zero follow the linear "
                   "threshold region. Do not apply a pure log law."),
        "self_check": ("Where does the axis switch from linear to log behaviour "
                       "(the linthresh)? Give the value and how you found it.")},
    "UNIT_PREFIX": {
        "repair": ("Normalize to the contract's expected unit BEFORE filling "
                   "result.json: multiply every value from this axis by the "
                   "conversion_factor in axis_diagnosis.json (e.g. mV -> V is "
                   "x1e-3). State the conversion explicitly in sources."),
        "self_check": ("What is the final reported unit, and what factor did you "
                       "apply? Show one converted value next to its raw read.")},
    "PERCENT_FRACTION": {
        "repair": ("Decide whether result.json wants percent (0-100) or fraction "
                   "(0-1) and convert ONCE, explicitly. Record which form is "
                   "reported in sources; flag ambiguity in uncertainty if the "
                   "contract is silent."),
        "self_check": ("Is 0.35 in the figure reported as 0.35 or 35? Which one "
                       "does the contract expect, and where did you check?")},
    "DUAL_AXIS": {
        "repair": ("Bind each series to its axis by legend color/marker BEFORE "
                   "reading any value; write the binding (series -> axis side and "
                   "unit) into sources. Read each series only against its own "
                   "axis's tick calibration. Never read a series against the "
                   "other axis, even if the numbers look plausible."),
        "self_check": ("For each series: which axis (side + unit) did you read it "
                       "against, and what visual evidence (color/marker on the "
                       "zoomed legend) proves the binding?")},
    "TRUNCATED_ORIGIN": {
        "repair": ("Report ABSOLUTE values, and additionally state the visual "
                   "distortion: with the axis starting at m instead of 0, bar "
                   "HEIGHT ratios exaggerate VALUE ratios by up to the "
                   "exaggeration_ratio in axis_diagnosis.json. Never quote "
                   "bar-height ratios as value ratios."),
        "self_check": ("Quote one pair of bars: value ratio AND pixel-height "
                       "ratio. Did you report only the value ratio as the "
                       "finding?")},
    "CROPPED_AXIS": {
        "repair": ("Part of the data or axis is cut off. Report values only "
                   "inside the readable range; anything outside is a declared "
                   "gap in uncertainty — never extrapolate past the crop."),
        "self_check": ("Which contract fields are affected by the cropped range, "
                       "and are they marked as gaps with limits stated?")},
    "NONDATA_STAR": {
        "repair": ("Exclude these pixels from every data series. Record the "
                   "stars as a significance annotation: which groups are compared "
                   "and the star count (*/**/***) if legible. Stars are claims "
                   "about the data, not data."),
        "self_check": ("Did any digitized 'point' coincide with a star bbox from "
                       "nondata_elements.json? Confirm none did, or list the "
                       "removed points.")},
    "NONDATA_BRACKET": {
        "repair": ("Exclude bracket ink from data. Record which two groups/bars "
                   "the bracket spans; it defines the comparison the stars above "
                   "it refer to."),
        "self_check": ("Which groups does each bracket connect, and is that "
                       "pairing recorded in sources?")},
    "FIT_LINE": {
        "repair": ("Exclude the fitted line from data points. Report its slope/"
                   "intercept ONLY if the task explicitly asks, and label it as a "
                   "fit (model), never as observed data."),
        "self_check": ("If you reported a slope, is it labelled 'fit' with the "
                       "excluded pixel extent noted? If not asked, did you keep "
                       "it out of result.json values?")},
    "INSET_AXIS": {
        "repair": ("An inset panel has its OWN axes and calibration. Read inset "
                   "content only against inset ticks; never mix inset pixels into "
                   "main-axis calibration. If the inset shows a zoom, prefer the "
                   "inset for fine structure in its range."),
        "self_check": ("Did every value taken from the inset use inset tick "
                       "calibration? Show one example conversion.")},
    "LEGEND_SWAP": {
        "repair": ("Before attributing any value, verify the name -> color/marker "
                   "binding on the zoomed legend itself (legend may overlap the "
                   "plot). If two series are visually similar, anchor the binding "
                   "at a legend swatch, not at a data point."),
        "self_check": ("State the final legend binding you used and the zoom "
                       "evidence for it. Could any two series be swapped? Say why "
                       "not.")},
}

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def load_json(path, what):
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:  # noqa: BLE001
        print("error: cannot read %s (%s): %s" % (what, path, exc),
              file=sys.stderr)
        raise SystemExit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--axis-diag", required=True)
    ap.add_argument("--nondata", required=True)
    ap.add_argument("--card", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    axis_diag = load_json(args.axis_diag, "axis diagnosis")
    nondata = load_json(args.nondata, "nondata elements")
    card = load_json(args.card, "figure card")

    findings = []
    for f in (axis_diag or {}).get("live_modes", []):
        findings.append({"id": f["id"], "source": "detect_axis_geometry",
                         "severity": f.get("severity", "medium"),
                         "where": f.get("axis") or f.get("panel"),
                         "detail": f.get("detail", "")})
    for c in (nondata or {}).get("candidates", []):
        findings.append({"id": c["type"], "source": "detect_nondata_ink",
                         "severity": "medium",
                         "where": c.get("panel"),
                         "detail": c.get("evidence", ""),
                         "bbox": c.get("bbox"),
                         "confidence": c.get("confidence")})

    # one repair per mode id (multiple findings of one mode merge)
    by_mode = {}
    for f in findings:
        by_mode.setdefault(f["id"], []).append(f)

    repairs = []
    report_entries = []
    for mode, items in sorted(by_mode.items(),
                              key=lambda kv: (SEVERITY_ORDER.get(
                                  kv[1][0]["severity"], 3), kv[0])):
        recipe = RECIPES.get(mode, {
            "repair": "No canned recipe — inspect the zoomed figure and apply the "
                      "general rule: verify the suspicious element/unit/axis before "
                      "trusting any value derived from it.",
            "self_check": "What evidence shows this finding was handled?"})
        repairs.append({
            "mode": mode,
            "severity": items[0]["severity"],
            "n_findings": len(items),
            "findings": items,
            "repair": recipe["repair"],
            "self_check": recipe["self_check"],
        })
        report_entries.append({
            "mode": mode,
            "applied": None,          # agent: true/false
            "evidence": None,         # agent: one line of verifiable evidence
            "notes": None,
            "findings_count": len(items),
        })

    plan = {
        "tool": "repair_plan",
        "card": os.path.abspath(args.card),
        "n_modes_live": len(repairs),
        "repairs": repairs,
        "post_read_self_check": [
            {"mode": r["mode"], "question": r["self_check"]} for r in repairs],
        "agent_confirm_from_ink_detector": (nondata or {}).get("agent_confirm", []),
        "usage": ("Read the figure UNDER these repairs. Then complete "
                  "misread_report.json (applied yes/no + evidence per mode) and "
                  "fold conversions, exclusions and bindings into result.json's "
                  "sources; put residual doubt in uncertainty."),
    }
    out = args.out or os.path.join(args.work, "repair_plan.json")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=2, ensure_ascii=False)

    report = {
        "case_note": "skeleton written by repair_plan.py — complete every entry",
        "figure": (card or {}).get("figure_file"),
        "entries": report_entries,
        "all_applied": None,
    }
    report_path = os.path.join(args.work, "misread_report.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    print("wrote %s — %d live mode(s): %s"
          % (out, len(repairs), ", ".join(by_mode) or "none"))
    print("wrote %s (skeleton, %d entries)" % (report_path, len(report_entries)))
    return 2 if repairs else 0


if __name__ == "__main__":
    sys.exit(main())
