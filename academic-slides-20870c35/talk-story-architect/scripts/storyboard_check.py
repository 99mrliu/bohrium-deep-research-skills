#!/usr/bin/env python3
"""Validate a talk storyboard against the gates in references/storyboard-spec.md.

Usage:
  python3 storyboard_check.py storyboard.json [--contract contract.json]
          [--material material.json] [--audience audience.json] [--edit]

Exit 0 when every gate passes, 1 with a numbered violation list otherwise.
Stdlib only; safe to run in the harness environment.
"""
import json
import re
import sys

TOPIC_LABELS = {
    "method", "methods", "results", "conclusion", "conclusions", "background",
    "introduction", "overview", "summary", "approach", "experiments",
    "discussion", "related work", "outline", "agenda",
    "方法", "结果", "结论", "背景", "引言", "概述", "总结", "实验", "讨论",
    "相关工作", "实验结果", "研究背景", "目录", "大纲",
}
CONTENT_ROLES = {"hook", "context", "gap", "idea", "method", "validation",
                 "result", "limitation", "takeaway"}
RESULT_ROLES = {"result", "validation"}
QUALIFIERS = re.compile(
    r"(show|demonstrat|confirm|establish|suggest|indicat|consistent with|"
    r"preliminar|hypothes|appear|roughly|about|approx|~|±|%|倍|"
    r"表明|证实|证明|显示|初步|提示|可能|约|左右|下降|提升|降低|提高|优于|相当)",
    re.IGNORECASE)


def fail(violations, gate, msg):
    violations.append(f"[gate {gate}] {msg}")


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    sb = load(argv[0])
    opts = {}
    i = 1
    edit_mode = False
    while i < len(argv):
        if argv[i] == "--edit":
            edit_mode = True
            i += 1
        else:
            opts[argv[i].lstrip("-")] = argv[i + 1]
            i += 2

    violations = []
    slides = sb.get("slides", [])
    content = [s for s in slides if s.get("role") != "backup"]

    contract = load(opts["contract"]) if "contract" in opts else {}
    want_count = contract.get("slide_count")
    want_range = contract.get("slide_count_range")
    # Gate 1: count
    if isinstance(want_count, int) and len(content) != want_count:
        fail(violations, 1, f"slide count {len(content)} != mandated {want_count}")
    if isinstance(want_range, list) and len(want_range) == 2 and not (
            want_range[0] <= len(content) <= want_range[1]):
        fail(violations, 1, f"slide count {len(content)} outside {want_range}")

    # Gate 2: time
    duration = sb.get("duration_sec") or contract.get("speaking_sec")
    total = sum(s.get("time_sec", 0) for s in content)
    if duration:
        if abs(total - duration) > 0.10 * duration:
            fail(violations, 2,
                 f"sum(time_sec)={total} not within ±10% of {duration}")
        for s in content:
            t = s.get("time_sec", 0)
            if not 20 <= t <= 240:
                fail(violations, 2, f"slide {s.get('index')} time {t}s outside 20-240s")
            if t > 0.2 * duration and not s.get("key_result"):
                fail(violations, 2,
                     f"slide {s.get('index')} takes {t}s (>20% of total) without key_result flag")

    # Gate 3: single message
    for s in content:
        h = (s.get("headline") or "").strip()
        bare = h.rstrip(".。!！")
        if not h:
            fail(violations, 3, f"slide {s.get('index')} missing headline")
            continue
        if bare.lower() in TOPIC_LABELS or bare in TOPIC_LABELS:
            fail(violations, 3, f"slide {s.get('index')} headline is a topic label: {h!r}")
        if len(h.split()) < 6 and len(re.findall(r"[一-鿿]", h)) < 8:
            fail(violations, 3, f"slide {s.get('index')} headline too short: {h!r}")
        if ";" in h or "；" in h:
            fail(violations, 3, f"slide {s.get('index')} headline chains multiple claims: {h!r}")

    # Gate 4: headline test
    roles = [s.get("role") for s in content]
    if roles and roles[0] not in ("title", "hook", "framing"):
        fail(violations, 4, f"first slide role {roles[0]!r} is not an opening beat")
    if "takeaway" not in roles[-2:]:
        fail(violations, 4, "no takeaway among the last two content slides")
    first_result = next((k for k, r in enumerate(roles) if r in RESULT_ROLES), None)
    if first_result is not None and not any(
            r in ("context", "gap", "idea", "method", "hook") for r in roles[:first_result]):
        fail(violations, 4, "a result/validation slide appears before any setup beat")
    for s in content:
        if s.get("role") in RESULT_ROLES:
            h = s.get("headline", "")
            if not QUALIFIERS.search(h) and not re.search(r"\d", h):
                fail(violations, 4,
                     f"slide {s.get('index')} result headline lacks a qualifier or value: {h!r}")

    # Gate 5: support closure
    material_locs = set()
    if "material" in opts:
        mat = load(opts["material"])
        for r in mat.get("results", []):
            loc = r.get("locator", {})
            material_locs.add(str(loc.get("figure_or_table", "")))
            material_locs.add(str(loc.get("section", "")))
    for s in content:
        sup = s.get("support", [])
        if s.get("role") not in ("framing", "title") and not sup:
            fail(violations, 5, f"slide {s.get('index')} ({s.get('role')}) has no support locator")
        if material_locs:
            for sp in sup:
                loc = str(sp.get("locator", ""))
                if sp.get("kind") in ("figure", "table") and not any(
                        m and m in loc for m in material_locs):
                    fail(violations, 5,
                         f"slide {s.get('index')} support {loc!r} matches no material locator")

    # Gate 6: objection closure
    if "audience" in opts:
        aud = load(opts["audience"])
        mapped = {o.get("question") for o in sb.get("objection_map", [])}
        valid_idx = {s.get("index") for s in slides} | {b.get("index") for b in sb.get("backups", [])}
        for ob in aud.get("objections", []):
            q = ob.get("question")
            if q not in mapped and ob.get("answered_by", "").startswith("none") is False:
                fail(violations, 6, f"objection not covered in objection_map: {q!r}")
        for om in sb.get("objection_map", []):
            if om.get("slide") not in valid_idx:
                fail(violations, 6, f"objection_map points at missing slide {om.get('slide')}")

    # Gate 7: edit-mode closure
    if edit_mode:
        for s in slides:
            ss = s.get("source_slide")
            if s.get("role") == "preserved":
                continue
            if ss is not None and not isinstance(ss, int):
                fail(violations, 7, f"slide {s.get('index')} source_slide not an integer")

    if violations:
        print(f"STORYBOARD INVALID — {len(violations)} violation(s):")
        for k, v in enumerate(violations, 1):
            print(f"  {k}. {v}")
        return 1
    print(f"storyboard OK: {len(content)} slides, total {total}s"
          + (f" of {duration}s" if duration else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
